from __future__ import annotations
import csv, io, logging, os, tempfile
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import or_
from sqlalchemy.orm import Session
from .agentic_rag import build_evidence, plan_query, run_agentic_assessment
from .database import get_db
from .logging_config import configure_logging, request_metrics
from .governance import fairness_report, drift_report, model_registry
from .explainability import explain_supervised_prediction
from .integrations import CreditBureauAdapter, NarrativeLLMAdapter
from .background_jobs import process_intake_job
from .models import AgentRun, Application, AuditEvent, DecisionOverride, EvaluationRun, ProcessingJob, User
from .rag_evaluation import run_backtest
from .schemas_api import AgentQuery, ApplicationCreate, ApplicationOut, BacktestRequest, BootstrapAdminRequest, LoginRequest, OverrideRequest
from .security import AuthContext, create_access_token, current_user, hash_password, require_roles, verify_password
from .services import analyze, parse_upload, score_record
from .vector_store import semantic_search, sync_evidence_index, vector_backend

ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024

configure_logging()
logger = logging.getLogger("loanlens")
app = FastAPI(title="LoanLens AI", version="2.0.0", description="Local-first agentic RAG for explainable loan decision support")
app.middleware("http")(request_metrics)
default_cors_origins = ",".join(
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
)
cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", default_cors_origins).split(",") if origin.strip()]
local_network_origin_regex = (
    r"^http://(?:localhost|127\.0\.0\.1|10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})"
    r":(?:3000|5173)$"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=local_network_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)
def create_record(data, db, source="manual"):
    result = analyze(data)
    name = str(data.get("applicant_name") or data.get("name") or data.get("Name") or f"Applicant {datetime.utcnow():%H%M%S}")
    obj = Application(applicant_name=name, email=str(data.get("email", "")), loan_type=str(data.get("loan_type", "Personal Loan")), source_file=source, raw_data=data, **result)
    db.add(obj); db.flush(); return obj


def save_upload(uploaded: UploadFile) -> Path:
    suffix = Path(uploaded.filename or "upload").suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {suffix or 'none'}")
    size = 0
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        path = Path(tmp.name)
        while True:
            chunk = uploaded.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                path.unlink(missing_ok=True)
                raise HTTPException(413, f"{uploaded.filename or 'Upload'} exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
            tmp.write(chunk)
    return path


def persist_agent_run(application_id: str, report: dict, db: Session) -> AgentRun:
    run = AgentRun(
        application_id=application_id,
        query=report["query"],
        intent=report["plan"]["intent"],
        status="VERIFIED" if report["verification"]["verified"] else "REVIEW_REQUIRED",
        answer=report["answer"],
        evidence=report["retrieved_evidence"],
        policy_evidence=report["policy_evidence"],
        document_assessment=report["document_assessment"],
        fraud_assessment=report["fraud_assessment"],
        decision=report["decision"],
        verification=report["verification"],
        trace=report["trace"],
    )
    db.add(run)
    db.add(AuditEvent(
        actor="agent-orchestrator", action="agent.run", resource_type="application", resource_id=application_id,
        details={"intent": run.intent, "status": run.status, "recommendation": report["decision"]["recommendation"]},
    ))
    db.flush()
    return run


def agent_run_payload(run: AgentRun) -> dict:
    return {
        "run_id": run.id,
        "application_id": run.application_id,
        "query": run.query,
        "intent": run.intent,
        "status": run.status,
        "answer": run.answer,
        "retrieved_evidence": run.evidence,
        "policy_evidence": run.policy_evidence,
        "document_assessment": run.document_assessment,
        "fraud_assessment": run.fraud_assessment,
        "decision": run.decision,
        "verification": run.verification,
        "trace": run.trace,
        "created_at": run.created_at,
    }


def execute_agent_query(obj: Application, db: Session, question: str | None = None, top_k: int = 5) -> dict:
    record = obj.raw_data or {}
    evidence = build_evidence(record)
    sync_evidence_index(db, obj.id, evidence)
    query = question or "Assess fraud, credit risk, eligibility, income consistency, and document evidence."
    intent = plan_query(query, top_k)["intent"]
    metadata_filters = {
        "income": ["salary_slip", "income_tax_return", "form_16", "ITR"],
        "eligibility": ["salary_slip", "income_tax_return", "form_16", "ITR", "bank_statement"],
    }.get(intent)
    semantic = semantic_search(db, obj.id, query, max(top_k * 2, 8), metadata_filters)
    return run_agentic_assessment(record, score_record(record), question, top_k, semantic)

@app.get("/health")
def health(): return {"status":"healthy", "service":"loanlens-api", "version":"2.0.0"}

@app.get("/metrics", include_in_schema=False)
def metrics(): return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/auth/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    username = body.username.strip().lower()
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    token = create_access_token(user.username, user.role)
    db.add(AuditEvent(actor=user.username, action="auth.login", resource_type="user", resource_id=str(user.id)))
    db.commit()
    return {"access_token": token, "token_type":"bearer", "expires_in": 1800, "user":{"name":user.username,"role":user.role}}


@app.post("/auth/bootstrap", status_code=201)
def bootstrap_admin(body: BootstrapAdminRequest, db: Session = Depends(get_db)):
    expected = os.getenv("AUTH_BOOTSTRAP_SECRET", "")
    if not expected or body.bootstrap_secret != expected:
        raise HTTPException(403, "Bootstrap is disabled or the secret is invalid")
    if db.query(User).count():
        raise HTTPException(409, "A user already exists; use the identity administration workflow")
    user = User(username=body.username.strip().lower(), password_hash=hash_password(body.password), role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "role": user.role}


@app.get("/auth/config")
def auth_config():
    return {
        "auth_required": os.getenv("AUTH_REQUIRED", "false").lower() in {"1", "true", "yes"},
        "local_jwt": True,
        "oidc_configured": bool(os.getenv("OIDC_ISSUER") and os.getenv("OIDC_CLIENT_ID")),
        "roles": ["admin", "loan_officer", "auditor"],
    }

@app.post("/applications", response_model=ApplicationOut, status_code=201, dependencies=[Depends(current_user)])
def create_application(body: ApplicationCreate, db: Session=Depends(get_db)):
    obj=create_record(body.model_dump(),db); db.commit(); db.refresh(obj); return obj

@app.get("/applications", dependencies=[Depends(current_user)])
def applications(status: Optional[str]=None, q: Optional[str]=None, page: int=1, page_size: int=20, db: Session=Depends(get_db)):
    if page < 1 or page_size < 1 or page_size > 100: raise HTTPException(400, "page must be positive and page_size must be 1-100")
    query=db.query(Application)
    if status: query=query.filter(Application.status==status)
    if q:
        term=f"%{q.strip()}%"
        query=query.filter(or_(Application.applicant_name.ilike(term),Application.id.ilike(term),Application.email.ilike(term)))
    total=query.count(); items=query.order_by(Application.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"items":[ApplicationOut.model_validate(x) for x in items],"total":total,"page":page,"page_size":page_size,"pages":max(1,(total+page_size-1)//page_size)}

@app.get("/applications/{application_id}", response_model=ApplicationOut, dependencies=[Depends(current_user)])
def application(application_id: str, db: Session=Depends(get_db)):
    obj=db.get(Application, application_id)
    if not obj: raise HTTPException(404,"Application not found")
    return obj


@app.get("/agent/capabilities")
def agent_capabilities(db: Session = Depends(get_db)):
    return {
        "mode": "local-first deterministic agentic RAG",
        "agents": ["planner", "retriever", "document_specialist", "fraud_investigator", "credit_risk", "compliance", "answer_writer", "verifier"],
        "fraud_checks": [
            "cross-document identity consistency", "income consistency", "duplicate document fingerprinting",
            "suspicious-language screening", "loan-to-income anomaly", "employer evidence", "PAN format",
        ],
        "guardrails": ["evidence citations", "grounding verification", "human review on uncertainty", "encrypted audit trail"],
        "vector_store": vector_backend(db),
    }


@app.post("/applications/{application_id}/agent/analyze", status_code=201, dependencies=[Depends(current_user)])
def agent_analyze(application_id: str, db: Session = Depends(get_db)):
    obj = db.get(Application, application_id)
    if not obj:
        raise HTTPException(404, "Application not found")
    report = execute_agent_query(obj, db)
    run = persist_agent_run(application_id, report, db)
    decision, fraud = report["decision"], report["fraud_assessment"]
    obj.status = decision["recommendation"]
    obj.fraud_score = decision["fraud_score"]
    obj.ai_summary = report["answer"]
    if fraud["signals"]:
        obj.explanation = "; ".join(signal["description"] for signal in fraud["signals"])
    obj.processing_log = [f"{step['agent']}: {step['status']}" for step in report["trace"]]
    db.commit()
    logger.info("agent_analysis_complete application_id=%s run_id=%s", application_id, run.id)
    return {"run_id": run.id, "application_id": application_id, **report}


@app.post("/applications/{application_id}/agent/query", status_code=201, dependencies=[Depends(current_user)])
def agent_query(application_id: str, body: AgentQuery, db: Session = Depends(get_db)):
    obj = db.get(Application, application_id)
    if not obj:
        raise HTTPException(404, "Application not found")
    report = execute_agent_query(obj, db, body.question, body.top_k)
    run = persist_agent_run(application_id, report, db)
    db.commit()
    logger.info("agent_query_complete application_id=%s run_id=%s intent=%s", application_id, run.id, run.intent)
    return {"run_id": run.id, "application_id": application_id, **report}


@app.get("/applications/{application_id}/agent/runs", dependencies=[Depends(current_user)])
def agent_runs(application_id: str, limit: int = 20, db: Session = Depends(get_db)):
    if not db.get(Application, application_id):
        raise HTTPException(404, "Application not found")
    limit = max(1, min(limit, 100))
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.application_id == application_id)
        .order_by(AgentRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return [agent_run_payload(run) for run in runs]


@app.post("/applications/{application_id}/override", status_code=201)
def override_decision(application_id: str, body: OverrideRequest, db: Session = Depends(get_db), user: AuthContext = Depends(require_roles("admin", "loan_officer"))):
    obj = db.get(Application, application_id)
    if not obj:
        raise HTTPException(404, "Application not found")
    previous = obj.status
    override = DecisionOverride(
        application_id=application_id, previous_status=previous, new_status=body.new_status,
        reason=body.reason, actor=user.username,
    )
    obj.status = body.new_status
    db.add(override)
    db.add(AuditEvent(
        actor=user.username, action="decision.override", resource_type="application", resource_id=application_id,
        details={"previous_status": previous, "new_status": body.new_status, "override_id": override.id},
    ))
    db.commit()
    db.refresh(override)
    return {"override_id": override.id, "application_id": application_id, "previous_status": previous, "new_status": body.new_status, "reason": body.reason, "actor": user.username, "created_at": override.created_at}


@app.get("/applications/{application_id}/overrides", dependencies=[Depends(current_user)])
def decision_overrides(application_id: str, db: Session = Depends(get_db)):
    if not db.get(Application, application_id):
        raise HTTPException(404, "Application not found")
    rows = db.query(DecisionOverride).filter(DecisionOverride.application_id == application_id).order_by(DecisionOverride.created_at.desc()).all()
    return [{"id": row.id, "previous_status": row.previous_status, "new_status": row.new_status, "reason": row.reason, "actor": row.actor, "created_at": row.created_at} for row in rows]


@app.get("/governance/models")
def governance_models(user: AuthContext = Depends(require_roles("admin", "auditor"))):
    return {"models": model_registry()}


@app.get("/applications/{application_id}/explainability", dependencies=[Depends(current_user)])
def application_explainability(application_id: str, db: Session = Depends(get_db)):
    obj = db.get(Application, application_id)
    if not obj:
        raise HTTPException(404, "Application not found")
    return {
        "scorecard_reasons": obj.explanation.split("; ") if obj.explanation else [],
        "supervised_model": explain_supervised_prediction(obj.raw_data or {}),
        "comparison_mode": "side-by-side",
    }


@app.get("/governance/drift")
def governance_drift(db: Session = Depends(get_db), user: AuthContext = Depends(require_roles("admin", "auditor"))):
    return drift_report(db.query(Application).all())


@app.get("/governance/fairness")
def governance_fairness(attribute: str, db: Session = Depends(get_db), user: AuthContext = Depends(require_roles("admin", "auditor"))):
    try:
        return fairness_report(db.query(Application).all(), attribute)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/governance/retention")
def retention_policy():
    return {
        "audit_event_days": int(os.getenv("AUDIT_RETENTION_DAYS", "2555")),
        "processing_job_days": int(os.getenv("JOB_RETENTION_DAYS", "30")),
        "application_records": "No automatic deletion; follow the lender's approved records schedule.",
    }


@app.delete("/governance/retention")
def enforce_retention(dry_run: bool = True, db: Session = Depends(get_db), user: AuthContext = Depends(require_roles("admin"))):
    now = datetime.utcnow()
    audit_cutoff = now - timedelta(days=int(os.getenv("AUDIT_RETENTION_DAYS", "2555")))
    job_cutoff = now - timedelta(days=int(os.getenv("JOB_RETENTION_DAYS", "30")))
    audit_query = db.query(AuditEvent).filter(AuditEvent.created_at < audit_cutoff)
    job_query = db.query(ProcessingJob).filter(ProcessingJob.created_at < job_cutoff)
    counts = {"audit_events": audit_query.count(), "processing_jobs": job_query.count()}
    if not dry_run:
        audit_query.delete(synchronize_session=False)
        job_query.delete(synchronize_session=False)
        db.add(AuditEvent(actor=user.username, action="retention.enforce", resource_type="governance", details=counts))
        db.commit()
    return {"dry_run": dry_run, "eligible_for_deletion": counts, "cutoffs": {"audit_events": audit_cutoff, "processing_jobs": job_cutoff}}


@app.get("/applications/{application_id}/adverse-action", dependencies=[Depends(current_user)])
def adverse_action_notice(application_id: str, db: Session = Depends(get_db)):
    obj = db.get(Application, application_id)
    if not obj:
        raise HTTPException(404, "Application not found")
    run = db.query(AgentRun).filter(AgentRun.application_id == application_id).order_by(AgentRun.created_at.desc()).first()
    reasons = (run.decision or {}).get("adverse_action_reasons", []) if run else []
    return {
        "application_id": application_id,
        "recommendation": obj.status,
        "reason_codes": reasons,
        "notice": "This recommendation used the listed application factors. Contact a loan officer to correct evidence or request human review.",
        "model_versions": {item["name"]: item["version"] for item in model_registry() if item["stage"] == "production"},
    }
@app.get("/integrations/status")
def integration_status():
    return {"credit_bureau": CreditBureauAdapter.status(), "narrative_llm": NarrativeLLMAdapter.status(), "sso": {"configured": bool(os.getenv("OIDC_ISSUER") and os.getenv("OIDC_CLIENT_ID"))}}


@app.post("/applications/{application_id}/bureau/verify", dependencies=[Depends(current_user)])
def verify_bureau(application_id: str, db: Session = Depends(get_db)):
    obj = db.get(Application, application_id)
    if not obj:
        raise HTTPException(404, "Application not found")
    result = CreditBureauAdapter.verify(obj.raw_data or {})
    db.add(AuditEvent(actor="integration-adapter", action="bureau.verify", resource_type="application", resource_id=application_id, details={"status": result["status"]}))
    db.commit()
    return result


@app.post("/applications/{application_id}/narrative", dependencies=[Depends(current_user)])
def external_narrative(application_id: str, db: Session = Depends(get_db)):
    obj = db.get(Application, application_id)
    if not obj:
        raise HTTPException(404, "Application not found")
    report = execute_agent_query(obj, db)
    if not report["verification"]["verified"]:
        raise HTTPException(409, "Narrative generation requires a verified grounded report")
    result = NarrativeLLMAdapter.summarize(report)
    db.add(AuditEvent(actor="integration-adapter", action="narrative.generate", resource_type="application", resource_id=application_id, details={"status": result["status"], "used_for_scoring": False}))
    db.commit()
    return result

@app.post("/upload", dependencies=[Depends(current_user)])
def upload(
    files: List[UploadFile]=File(...),
    applicant_name: Optional[str]=Form(None),
    loan_type: str=Form("Personal Loan"),
    db: Session=Depends(get_db),
):
    if len(files) > 25: raise HTTPException(400, "A batch can contain at most 25 files")
    allowed_loan_types={"Personal Loan","Home Loan","Car Loan","Education Loan","Business Loan","Gold Loan"}
    if loan_type not in allowed_loan_types: raise HTTPException(400, "Unsupported loan type")
    if applicant_name is not None:
        applicant_name=applicant_name.strip()
        if len(applicant_name) < 2 or len(applicant_name) > 160: raise HTTPException(400, "Applicant name must contain 2 to 160 characters")
    seen=set(); created=[]; skipped=0; results=[]
    for uploaded in files:
        filename=uploaded.filename or "upload"
        path=save_upload(uploaded)
        try:
            rows=parse_upload(path)
            file_created=[]
            for row in rows[:1000]:
                if applicant_name: row["applicant_name"]=applicant_name
                row["loan_type"]=loan_type
                # Named uploads represent one applicant document pack. Merge
                # subsequent documents into the first application for a single decision.
                if applicant_name and created:
                    primary=created[0]
                    existing=dict(primary.raw_data or {})
                    documents=list(existing.get("documents", []))
                    incoming_documents = row.get("documents") or [{"filename":filename,"data":row}]
                    documents.extend(incoming_documents)
                    existing["documents"]=documents
                    existing["comments"]="\n".join(filter(None,[str(existing.get("comments", "")),str(row.get("comments", ""))]))
                    existing.update({k:v for k,v in row.items() if k not in existing or existing[k] in (None,"")})
                    existing["applicant_name"]=applicant_name; existing["loan_type"]=loan_type
                    primary.raw_data=existing
                    primary.source_file=", ".join(dict.fromkeys(filter(None,[primary.source_file,filename])))
                    for key,value in analyze(existing).items(): setattr(primary,key,value)
                    file_created.append(primary)
                    continue
                fingerprint=str(row.get("email") or row.get("ID") or row.get("id") or "")
                if fingerprint and fingerprint in seen: skipped+=1; continue
                seen.add(fingerprint)
                if applicant_name and not row.get("documents"): row["documents"]=[{"filename":filename,"data":dict(row)}]
                obj=create_record(row,db,filename); created.append(obj); file_created.append(obj)
            results.append({"filename":filename,"status":"analyzed","records":len(file_created),"application_ids":[x.id for x in file_created]})
        except Exception as exc:
            results.append({"filename":filename,"status":"failed","records":0,"error":str(exc)})
        finally: path.unlink(missing_ok=True)
    if not created:
        db.rollback()
        raise HTTPException(400, {"message":"No applications could be extracted","files":results})
    db.commit()
    return {"message":"Batch analysis complete","applicant_name":applicant_name,"loan_type":loan_type,"files_received":len(files),"files_analyzed":sum(x["status"]=="analyzed" for x in results),
      "created":len(created),"duplicates_skipped":skipped,"application_ids":[x.id for x in created],"results":results}


@app.post("/upload/async", status_code=202, dependencies=[Depends(current_user)])
def upload_async(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    applicant_name: Optional[str] = Form(None),
    loan_type: str = Form("Personal Loan"),
    db: Session = Depends(get_db),
):
    if not files or len(files) > 25:
        raise HTTPException(400, "Provide between 1 and 25 files")
    allowed_loan_types={"Personal Loan","Home Loan","Car Loan","Education Loan","Business Loan","Gold Loan"}
    if loan_type not in allowed_loan_types:
        raise HTTPException(400, "Unsupported loan type")
    if applicant_name is not None:
        applicant_name = applicant_name.strip()
        if len(applicant_name) < 2 or len(applicant_name) > 160:
            raise HTTPException(400, "Applicant name must contain 2 to 160 characters")
    paths = []
    try:
        paths = [str(save_upload(uploaded)) for uploaded in files]
    except HTTPException:
        for path in paths:
            Path(path).unlink(missing_ok=True)
        raise
    job = ProcessingJob(
        input_manifest={"files": [uploaded.filename for uploaded in files], "applicant_name": applicant_name, "loan_type": loan_type}
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(process_intake_job, job.id, paths, applicant_name, loan_type)
    return {"job_id": job.id, "status": job.status, "poll_url": f"/jobs/{job.id}"}


@app.get("/jobs/{job_id}", dependencies=[Depends(current_user)])
def processing_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {"job_id": job.id, "status": job.status, "job_type": job.job_type, "result": job.result, "error": job.error, "created_at": job.created_at, "updated_at": job.updated_at}

@app.post("/analyze/{application_id}", response_model=ApplicationOut, dependencies=[Depends(current_user)])
def reanalyze(application_id:str, db:Session=Depends(get_db)):
    obj=db.get(Application,application_id)
    if not obj: raise HTTPException(404,"Application not found")
    for k,v in analyze(obj.raw_data or {}).items(): setattr(obj,k,v)
    db.commit(); db.refresh(obj); return obj

@app.get("/dashboard", dependencies=[Depends(current_user)])
def dashboard(db:Session=Depends(get_db)):
    a=db.query(Application).all(); total=len(a); statuses=Counter(x.status for x in a); sentiments=Counter(x.sentiment for x in a)
    years=sorted({x.created_at.year for x in a}); selected_year=max(years) if years else datetime.utcnow().year
    return {"total_applications":total,"approved":statuses["APPROVE"],"rejected":statuses["REJECT"],"pending":statuses["REVIEW"],
      "average_risk":round(sum(x.risk_score for x in a)/total,1) if total else 0,"fraud_alerts":sum(x.fraud_score>=50 for x in a),
      "status_distribution":dict(statuses),"sentiment_distribution":dict(sentiments),"recent":[ApplicationOut.model_validate(x) for x in a[-8:][::-1]],
      "monthly_year":selected_year,"monthly":[{"month":m,"applications":sum(x.created_at.year==selected_year and x.created_at.month==i for x in a)} for i,m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],1)]}

@app.get("/analytics", dependencies=[Depends(current_user)])
def analytics(db:Session=Depends(get_db)):
    a=db.query(Application).all(); bands=lambda value: "Low" if value<35 else "Medium" if value<70 else "High"
    return {"risk":dict(Counter(bands(x.risk_score) for x in a)),"fraud":dict(Counter(bands(x.fraud_score) for x in a)),"sentiment":dict(Counter(x.sentiment for x in a))}

@app.get("/fraud-report", dependencies=[Depends(current_user)])
def fraud_report(db:Session=Depends(get_db)): return [{"id":x.id,"applicant":x.applicant_name,"score":x.fraud_score,"reason":x.explanation} for x in db.query(Application).filter(Application.fraud_score>=40).all()]
@app.get("/sentiment-report", dependencies=[Depends(current_user)])
def sentiment_report(db:Session=Depends(get_db)): return [{"id":x.id,"sentiment":x.sentiment,"confidence":x.sentiment_confidence} for x in db.query(Application).all()]
@app.get("/reports/applications.csv", dependencies=[Depends(current_user)])
def export_csv(db:Session=Depends(get_db)):
    out=io.StringIO(); w=csv.writer(out); w.writerow(["ID","Applicant","Status","Risk","Fraud","Sentiment"])
    for x in db.query(Application).all(): w.writerow([x.id,x.applicant_name,x.status,x.risk_score,x.fraud_score,x.sentiment])
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=loan-report.csv"})

@app.post("/evaluation/backtest", status_code=201, dependencies=[Depends(require_roles("admin", "auditor"))])
def evaluation_backtest(body: BacktestRequest, db: Session=Depends(get_db)):
    report=run_backtest([case.model_dump() for case in body.cases],body.top_k)
    failures=[item for item in report["results"] if not item["retrieval_hit"] or not item["verification"]["verified"]]
    run=EvaluationRun(name=body.name,dataset_size=report["dataset_size"],metrics=report["metrics"],failures=failures)
    db.add(run); db.commit(); db.refresh(run)
    logger.info("evaluation_complete run_id=%s cases=%s",run.id,run.dataset_size)
    return {"run_id":run.id,**report}

@app.get("/evaluation/runs", dependencies=[Depends(require_roles("admin", "auditor"))])
def evaluation_runs(limit: int=20, db: Session=Depends(get_db)):
    limit=max(1,min(limit,100))
    runs=db.query(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(limit).all()
    return [{"id":x.id,"name":x.name,"dataset_size":x.dataset_size,"metrics":x.metrics,"failures":x.failures,"created_at":x.created_at} for x in runs]
