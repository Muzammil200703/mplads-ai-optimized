import os
import joblib
import pandas as pd

MODEL_PATH = os.path.join(os.path.dirname(__file__), "anomaly_model.pkl")

model = None
features = []

try:
    if os.path.exists(MODEL_PATH):
        model_data = joblib.load(MODEL_PATH)
        model = model_data.get("model")
        features = model_data.get("features", [])
except Exception as e:
    print(f"Warning: Could not load anomaly ML model: {e}")

def create_project_features(project):
    data = {
        "sanctioned_amount": getattr(project, "sanctioned_amount", 0) or 0,
        "expenditure": getattr(project, "expenditure", 0) or 0,
        "completion_percentage": getattr(project, "completion_percentage", 0) or 0,
    }
    df = pd.DataFrame([data])
    df["utilization_ratio"] = df["expenditure"] / df["sanctioned_amount"].replace(0, 1)
    df["unspent_amount"] = df["sanctioned_amount"] - df["expenditure"]
    df["expenditure_per_completion"] = df["expenditure"] / df["completion_percentage"].replace(0, 1)
    df["remaining_completion"] = 100 - df["completion_percentage"]
    df["high_value_project"] = (df["sanctioned_amount"] >= 1000000).astype(int)
    df["zero_expenditure"] = (df["expenditure"] == 0).astype(int)
    df["zero_completion"] = (df["completion_percentage"] == 0).astype(int)

    if features:
        for f in features:
            if f not in df.columns:
                df[f] = 0
        df = df[features]

    df = df.replace([float("inf"), float("-inf")], 0).fillna(0)
    return df

def predict_risk(project):
    sanctioned = float(getattr(project, "sanctioned_amount", 0) or 0)
    expenditure = float(getattr(project, "expenditure", 0) or 0)
    completion = float(getattr(project, "completion_percentage", 0) or 0)
    status_str = str(getattr(project, "status", "") or "").lower()

    ml_anomaly = False
    anomaly_score = 0.0

    if model is not None and features:
        try:
            X = create_project_features(project)
            pred = model.predict(X)[0]
            anomaly_score = float(model.decision_function(X)[0])
            ml_anomaly = bool(pred == -1)
        except Exception:
            pass

    risk_score = 0
    reasons = []

    # Rule 1: Overspending
    if sanctioned > 0 and expenditure > sanctioned:
        reasons.append("Expenditure exceeds sanctioned amount")
        risk_score += 40

    # Rule 2: High expenditure with low completion
    if sanctioned > 0 and (expenditure / sanctioned) >= 0.80 and completion < 50:
        reasons.append("High expenditure with low physical completion")
        risk_score += 35

    # Rule 3: Zero progress with disbursements
    if expenditure > 0 and completion == 0:
        reasons.append("Disbursements made with 0% physical completion")
        risk_score += 30

    # Rule 4: High-value project with very low completion
    if sanctioned >= 1000000 and completion < 25:
        reasons.append("High-value project with severe progress delay")
        risk_score += 20

    # Rule 5: Marked completed with low completion percentage
    if status_str == "completed" and completion < 90:
        reasons.append("Project marked completed but physical progress is below 90%")
        risk_score += 25

    # Rule 6: High completion with zero expenditure reported
    if completion >= 80 and expenditure == 0:
        reasons.append("High completion recorded with zero expenditure")
        risk_score += 20

    # Rule 7: Very low fund utilization on major project
    if sanctioned >= 500000 and (expenditure / sanctioned) < 0.10 and completion < 30:
        reasons.append("Very low fund utilization and low completion")
        risk_score += 15

    # ML Anomaly contribution
    if ml_anomaly:
        risk_score += 25
        reasons.append("Statistical anomaly detected by ML Isolation Forest model")

    risk_score = min(100, max(0, risk_score))

    if risk_score >= 60:
        risk_level = "High"
    elif risk_score >= 30:
        risk_level = "Medium"
    elif risk_score > 0:
        risk_level = "Low"
    else:
        risk_level = "None"

    return {
        "ml_anomaly": ml_anomaly,
        "ml_score": round(anomaly_score, 4),
        "risk_score": risk_score,
        "risk_level": risk_level,
        "is_anomaly": len(reasons) > 0,
        "reasons": reasons,
    }
