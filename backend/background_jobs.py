"""Local background worker entrypoints; replaceable with a durable queue adapter."""
from __future__ import annotations

from pathlib import Path

from .database import SessionLocal
from .models import Application, AuditEvent, ProcessingJob
from .services import analyze, parse_upload


def _new_application(data: dict, source: str) -> Application:
    result = analyze(data)
    return Application(
        applicant_name=str(data.get("applicant_name") or data.get("name") or Path(source).stem)[:160],
        email=str(data.get("email", "")), loan_type=str(data.get("loan_type", "Personal Loan")),
        source_file=source, raw_data=data, **result,
    )


def process_intake_job(job_id: str, paths: list[str], applicant_name: str | None, loan_type: str) -> None:
    db = SessionLocal()
    job = db.get(ProcessingJob, job_id)
    if not job:
        db.close()
        return
    try:
        job.status = "RUNNING"
        db.commit()
        records: list[tuple[dict, str]] = []
        for raw_path in paths:
            path = Path(raw_path)
            for row in parse_upload(path)[:1000]:
                row["loan_type"] = loan_type
                if applicant_name:
                    row["applicant_name"] = applicant_name
                records.append((row, path.name))
        created = []
        if applicant_name and records:
            combined = dict(records[0][0])
            combined["documents"] = []
            comments, sources = [], []
            for row, source in records:
                sources.append(source)
                comments.append(str(row.get("comments") or ""))
                combined["documents"].extend(row.get("documents") or [{"filename": source, "data": row}])
                combined.update({key: value for key, value in row.items() if key not in combined or combined[key] in (None, "")})
            combined["comments"] = "\n".join(filter(None, comments))
            application = _new_application(combined, ", ".join(dict.fromkeys(sources)))
            db.add(application)
            created.append(application)
        else:
            for row, source in records:
                application = _new_application(row, source)
                db.add(application)
                created.append(application)
        db.flush()
        job.status = "COMPLETED"
        job.result = {"application_ids": [item.id for item in created], "records": len(created)}
        db.add(AuditEvent(actor="background-worker", action="intake.complete", resource_type="job", resource_id=job.id, details=job.result))
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(ProcessingJob, job_id)
        if job:
            job.status = "FAILED"
            job.error = str(exc)[:2000]
            db.commit()
    finally:
        db.close()
        for raw_path in paths:
            Path(raw_path).unlink(missing_ok=True)
