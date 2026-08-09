"""Train and persist an anomaly model from the bundled personal-loan workbook."""
from pathlib import Path
import joblib, pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/"Bank_Personal_Loan_Modelling.xlsx"
data=pd.read_excel(source, sheet_name="Data")
numeric=data.select_dtypes("number").dropna(axis=1, how="all").drop(columns=[c for c in data.columns if c.lower() in {"id","personal loan"}],errors="ignore")
model=Pipeline([("impute",SimpleImputer(strategy="median")),("scale",StandardScaler()),("model",IsolationForest(n_estimators=250,contamination=.05,random_state=42))])
model.fit(numeric)
joblib.dump({"pipeline":model,"features":list(numeric.columns)},ROOT/"models"/"fraud_isolation_forest.joblib")
print(f"Saved model trained on {len(data)} rows and {len(numeric.columns)} features")
