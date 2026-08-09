from .database import Base, SessionLocal, engine
from .models import Application
from .app import create_record

SAMPLES=[
 {"applicant_name":"Ananya Rao","income":1450000,"loan_amount":2400000,"credit_score":782,"dti":24,"employment_years":8,"comments":"Stable income and excellent repayment history","employer":"Infosys"},
 {"applicant_name":"Rohan Mehta","income":720000,"loan_amount":1800000,"credit_score":688,"dti":44,"employment_years":3,"comments":"Regular salary but one late payment","employer":"RetailCo"},
 {"applicant_name":"Meera Iyer","income":2100000,"loan_amount":3200000,"credit_score":810,"dti":19,"employment_years":11,"comments":"Excellent customer with reliable financial history","employer":"TCS"},
 {"applicant_name":"Vikram Singh","income":0,"loan_amount":5000000,"credit_score":545,"dti":72,"employment_years":1,"comments":"Urgent application following business loss"},
 {"applicant_name":"Sara Khan","income":980000,"loan_amount":1500000,"credit_score":735,"dti":31,"employment_years":5,"comments":"Good repayment record and stable role","employer":"Wipro"},
]
Base.metadata.create_all(engine)
db=SessionLocal()
if not db.query(Application).count():
 for row in SAMPLES: create_record(row,db,"sample-seed")
 db.commit()
print(f"Applications: {db.query(Application).count()}")
db.close()
