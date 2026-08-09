from __future__ import annotations
import csv, io, os, shutil, tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import Application
from .schemas_api import ApplicationCreate, ApplicationOut, LoginRequest
from .services import analyze, parse_upload

app = FastAPI(title="LoanLens AI", version="1.0.0", description="Explainable bank loan decision intelligence")
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
Base.metadata.create_all(bind=engine)

def create_record(data, db, source="manual"):
    result = analyze(data)
    name = str(data.get("applicant_name") or data.get("name") or data.get("Name") or f"Applicant {datetime.utcnow():%H%M%S}")
    obj = Application(applicant_name=name, email=str(data.get("email", "")), loan_type=str(data.get("loan_type", "Personal Loan")), source_file=source, raw_data=data, **result)
    db.add(obj); db.flush(); return obj

@app.get("/health")
def health(): return {"status":"healthy", "service":"loanlens-api"}

@app.post("/auth/login")
def login(body: LoginRequest):
    users = {"admin":("admin123","Admin"), "officer":("officer123","Loan Officer")}
    if body.username not in users or users[body.username][0] != body.password: raise HTTPException(401, "Invalid credentials")
    return {"access_token": f"demo-{body.username}-token", "token_type":"bearer", "user":{"name":body.username.title(),"role":users[body.username][1]}}

@app.post("/applications", response_model=ApplicationOut, status_code=201)
def create_application(body: ApplicationCreate, db: Session=Depends(get_db)):
    obj=create_record(body.model_dump(),db); db.commit(); db.refresh(obj); return obj

@app.get("/applications", response_model=list[ApplicationOut])
def applications(status: Optional[str]=None, db: Session=Depends(get_db)):
    q=db.query(Application); return q.filter(Application.status==status).order_by(Application.created_at.desc()).all() if status else q.order_by(Application.created_at.desc()).all()

@app.get("/applications/{application_id}", response_model=ApplicationOut)
def application(application_id: str, db: Session=Depends(get_db)):
    obj=db.get(Application, application_id)
    if not obj: raise HTTPException(404,"Application not found")
    return obj

@app.post("/upload")
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
        suffix=Path(filename).suffix.lower()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            shutil.copyfileobj(uploaded.file,tmp); path=Path(tmp.name)
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
                    documents.append({"filename":filename,"data":row})
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
                if applicant_name: row["documents"]=[{"filename":filename,"data":dict(row)}]
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

@app.post("/analyze/{application_id}", response_model=ApplicationOut)
def reanalyze(application_id:str, db:Session=Depends(get_db)):
    obj=db.get(Application,application_id)
    if not obj: raise HTTPException(404,"Application not found")
    for k,v in analyze(obj.raw_data or {}).items(): setattr(obj,k,v)
    db.commit(); db.refresh(obj); return obj

@app.get("/dashboard")
def dashboard(db:Session=Depends(get_db)):
    a=db.query(Application).all(); total=len(a); statuses=Counter(x.status for x in a); sentiments=Counter(x.sentiment for x in a)
    return {"total_applications":total,"approved":statuses["APPROVE"],"rejected":statuses["REJECT"],"pending":statuses["REVIEW"],
      "average_risk":round(sum(x.risk_score for x in a)/total,1) if total else 0,"fraud_alerts":sum(x.fraud_score>=50 for x in a),
      "status_distribution":dict(statuses),"sentiment_distribution":dict(sentiments),"recent":[ApplicationOut.model_validate(x) for x in a[-8:][::-1]],
      "monthly":[{"month":m,"applications":sum(x.created_at.month==i for x in a)} for i,m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],1)]}

@app.get("/analytics")
def analytics(db:Session=Depends(get_db)):
    a=db.query(Application).all(); bands=lambda value: "Low" if value<35 else "Medium" if value<70 else "High"
    return {"risk":dict(Counter(bands(x.risk_score) for x in a)),"fraud":dict(Counter(bands(x.fraud_score) for x in a)),"sentiment":dict(Counter(x.sentiment for x in a))}

@app.get("/fraud-report")
def fraud_report(db:Session=Depends(get_db)): return [{"id":x.id,"applicant":x.applicant_name,"score":x.fraud_score,"reason":x.explanation} for x in db.query(Application).filter(Application.fraud_score>=40).all()]
@app.get("/sentiment-report")
def sentiment_report(db:Session=Depends(get_db)): return [{"id":x.id,"sentiment":x.sentiment,"confidence":x.sentiment_confidence} for x in db.query(Application).all()]
@app.get("/reports/applications.csv")
def export_csv(db:Session=Depends(get_db)):
    out=io.StringIO(); w=csv.writer(out); w.writerow(["ID","Applicant","Status","Risk","Fraud","Sentiment"])
    for x in db.query(Application).all(): w.writerow([x.id,x.applicant_name,x.status,x.risk_score,x.fraud_score,x.sentiment])
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=loan-report.csv"})
