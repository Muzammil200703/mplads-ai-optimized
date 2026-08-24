"""
Context-Aware Risk Predictor with SHAP Explanations (v2)
========================================================

Uses peer-group statistics to compare each project against its state-level
peers. SHAP TreeExplainer provides feature-level attribution for every
prediction, making risk scores fully explainable.

Backward-compatible: all v1 fields are still returned. New fields
add explanations and contributing factors.
"""

import os
import numpy as np
import joblib
import shap as _shap

MODEL_PATH = os.path.join(os.path.dirname(__file__), "anomaly_model.pkl")

model = None
features = []
peer_stats = None
model_version = "1.0"
_shap_explainer = None

try:
    if os.path.exists(MODEL_PATH):
        model_data = joblib.load(MODEL_PATH)
        model = model_data.get("model")
        features = model_data.get("features", [])
        peer_stats = model_data.get("peer_stats")
        model_version = model_data.get("version", "1.0")
        if model is not None:
            _shap_explainer = _shap.TreeExplainer(model)
except Exception as e:
    print(f"Warning: Could not load anomaly ML model: {e}")


# ============================================================
# Human-readable feature labels
# ============================================================

FEATURE_LABELS = {
    "log_sanctioned": "Sanctioned amount",
    "log_expenditure": "Expenditure amount",
    "completion_pct": "Physical completion",
    "utilization_ratio": "Fund utilization rate",
    "unspent_ratio": "Unspent fund proportion",
    "expenditure_per_completion": "Cost per unit completion",
    "remaining_completion": "Remaining work",
    "zero_expenditure": "Zero expenditure recorded",
    "zero_completion": "Zero progress recorded",
    "high_value_project": "High-value project flag",
    "overspent": "Overspending flag",
    "sanctioned_zscore": "Sanctioned amount vs state peers",
    "expenditure_zscore": "Expenditure vs state peers",
    "completion_zscore": "Completion vs state peers",
    "sanctioned_vs_state_median": "Sanctioned vs state median",
    "expenditure_vs_state_median": "Expenditure vs state median",
    "completion_vs_state_median": "Completion vs state median",
    "utilization_vs_state": "Utilization vs state peers",
    "fin_phys_gap_vs_state": "Financial-physical progress gap vs state",
    "sanctioned_national_zscore": "Sanctioned amount vs national",
    "expenditure_national_zscore": "Expenditure vs national",
    "sanctioned_order_of_magnitude": "Sanctioned magnitude rank",
    "peer_group_size": "State peer group size",
}


def _explain_shap_value(feature_name, shap_val, feature_val):
    """
    Generate a human-readable explanation for a single SHAP contribution.

    For IsolationForest via SHAP:
    - Negative SHAP values push toward anomaly (more negative = more anomalous)
    - Positive SHAP values push toward normal
    """
    label = FEATURE_LABELS.get(feature_name, feature_name)

    # Binary flags
    if feature_name == "overspent" and feature_val > 0:
        return f"Expenditure exceeds sanctioned amount (flagged)"
    if feature_name == "zero_expenditure" and feature_val > 0:
        return f"No expenditure recorded despite project being active"
    if feature_name == "zero_completion" and feature_val > 0:
        return f"Zero physical completion percentage"
    if feature_name == "high_value_project" and feature_val > 0:
        return f"High-value project (sanctioned >= 10 lakh)"
    if feature_name == "peer_group_size" and shap_val < -0.3:
        return f"Anomaly is unusual relative to the large state peer group"

    # Peer-relative features: explain the z-score direction
    if feature_name == "sanctioned_zscore":
        if shap_val < -0.15:
            direction = "significantly higher" if feature_val > 0 else "much lower"
            return f"Sanctioned amount is {direction} than typical projects in this state"
        elif shap_val > 0.15:
            return f"Sanctioned amount is consistent with state peers"

    if feature_name == "expenditure_zscore":
        if shap_val < -0.15:
            direction = "much higher" if feature_val > 0 else "much lower"
            return f"Expenditure is {direction} than state peer average"

    if feature_name == "completion_zscore":
        if shap_val < -0.15:
            direction = "much lower" if feature_val < 0 else "much higher"
            return f"Physical completion is {direction} than state peer average"

    if feature_name == "utilization_vs_state":
        if shap_val < -0.15:
            if feature_val > 0:
                return f"Fund utilization is significantly higher than state peers"
            else:
                return f"Fund utilization is much lower than state peers"

    if feature_name == "fin_phys_gap_vs_state":
        if shap_val < -0.15:
            if feature_val > 0:
                return f"Expenditure is much higher than expected for the reported progress"
            else:
                return f"Financial and physical progress are both atypically low"

    if feature_name == "sanctioned_national_zscore":
        if shap_val < -0.15:
            direction = "much higher" if feature_val > 0 else "much lower"
            return f"Sanctioned amount is {direction} than the national median"

    if feature_name == "expenditure_national_zscore":
        if shap_val < -0.15:
            direction = "much higher" if feature_val > 0 else "much lower"
            return f"Expenditure is {direction} compared to national average"

    if feature_name == "sanctioned_vs_state_median":
        if shap_val < -0.1 and feature_val > 3:
            return f"Sanctioned amount is {feature_val:.1f}x the state median (very large)"
        elif shap_val < -0.1 and feature_val < 0.1:
            return f"Sanctioned amount is only {feature_val*100:.0f}% of state median (very small)"

    if feature_name == "expenditure_vs_state_median":
        if shap_val < -0.1 and feature_val > 3:
            return f"Expenditure is {feature_val:.1f}x the state median (very large)"
        elif shap_val < -0.1 and feature_val < 0.1:
            return f"Expenditure is negligible compared to state median"

    if feature_name == "completion_vs_state_median":
        if shap_val < -0.1 and feature_val < 0.3:
            return f"Completion is {feature_val*100:.0f}% of state median (very low progress)"

    # --- Peer-relative feature explanations ---
    if feature_name == "sanctioned_vs_state_median":
        if shap_val < -0.1 and feature_val > 3:
            return f"Sanctioned amount is {feature_val:.1f}x the state median (very large)"
        elif shap_val < -0.1 and feature_val < 0.1:
            return f"Sanctioned amount is only {feature_val*100:.0f}% of state median (very small)"

    if feature_name == "expenditure_vs_state_median":
        if shap_val < -0.1 and feature_val > 3:
            return f"Expenditure is {feature_val:.1f}x the state median (very large)"
        elif shap_val < -0.1 and feature_val < 0.1:
            return f"Expenditure is negligible compared to state median"

    if feature_name == "completion_vs_state_median":
        if shap_val < -0.1 and feature_val < 0.3:
            return f"Completion is {feature_val*100:.0f}% of state median (very low progress)"
        elif shap_val < -0.1 and feature_val > 3:
            return f"Completion is much higher than state peers (may indicate unusual status)"

    if feature_name == "sanctioned_order_of_magnitude":
        if shap_val < -0.15:
            if feature_val > 1:
                return f"Sanctioned amount is orders of magnitude above national median"
            elif feature_val < -1:
                return f"Sanctioned amount is orders of magnitude below national median"

    if feature_name == "log_sanctioned":
        if shap_val < -0.15:
            return f"Log-scale sanctioned amount contributes to unusual profile"

    if feature_name == "log_expenditure":
        if shap_val < -0.15:
            return f"Log-scale expenditure contributes to unusual profile"

    if feature_name == "expenditure_per_completion":
        if shap_val < -0.15 and feature_val > 100000:
            return f"Cost per unit completion is very high (Rs {feature_val:,.0f} per %)"

    # Generic fallback for significant contributions
    if shap_val < -0.3:
        return f"{label} is strongly anomalous (value: {feature_val:.2f})"
    elif shap_val < -0.15:
        return f"{label} is somewhat unusual (value: {feature_val:.2f})"

    return None


def _compute_feature_contributions(project):
    """
    Compute per-feature contributions using SHAP values.
    Returns list of (feature_name, shap_value, feature_value, explanation)
    sorted by absolute SHAP contribution (most anomalous first).
    """
    sanctioned = float(getattr(project, "sanctioned_amount", 0) or 0)
    expenditure = float(getattr(project, "expenditure", 0) or 0)
    completion = float(getattr(project, "completion_percentage", 0) or 0)
    state = getattr(project, "state", "")
    project_type = getattr(project, "project_type", "")

    if not peer_stats or not _shap_explainer or not features:
        return []

    # Compute features
    from ml.train_anomaly_model import create_peer_relative_features
    row = {"state": state, "project_type": project_type,
           "sanctioned_amount": sanctioned, "expenditure": expenditure,
           "completion_percentage": completion}
    feat = create_peer_relative_features(row, peer_stats)

    X = np.array([[feat.get(f, 0) for f in features]])

    try:
        shap_values = _shap_explainer.shap_values(X)[0]
    except Exception:
        return []

    contributions = []
    for i, fname in enumerate(features):
        sv = float(shap_values[i])
        fv = float(X[0][i])
        explanation = _explain_shap_value(fname, sv, fv)
        contributions.append({
            "feature": fname,
            "label": FEATURE_LABELS.get(fname, fname),
            "shap_value": round(sv, 4),
            "feature_value": round(fv, 4),
            "explanation": explanation,
            "contributes_to_anomaly": sv < -0.05,
        })

    # Sort: most anomalous contributions first (most negative SHAP)
    contributions.sort(key=lambda x: x["shap_value"])

    return contributions


def _summarize_reasons(contributions, rule_reasons, risk_level):
    """
    Generate a concise summary of the main risk factors.
    Combines SHAP-based ML contributions with rule-based reasons.
    """
    factors = []

    # Add rule-based reasons first (these are deterministic and clear)
    for reason in rule_reasons:
        factors.append({
            "source": "rule",
            "explanation": reason,
        })

    # Add top ML contributions that have explanations
    ml_factors = [
        c for c in contributions
        if c["contributes_to_anomaly"] and c["explanation"]
    ]
    for c in ml_factors[:5]:  # Top 5 ML factors
        factors.append({
            "source": "ml",
            "explanation": c["explanation"],
            "feature": c["feature"],
            "impact": round(abs(c["shap_value"]), 4),
        })

    # Generate overall summary
    if risk_level == "High":
        summary = "This project exhibits multiple significant anomalies requiring audit attention."
    elif risk_level == "Medium":
        summary = "This project shows several patterns that deviate from expected norms."
    elif risk_level == "Low":
        summary = "This project has minor deviations from typical patterns."
    else:
        summary = "This project appears consistent with normal project patterns."

    return {
        "summary": summary,
        "risk_factors": factors,
        "ml_contribution_count": sum(1 for f in factors if f["source"] == "ml"),
        "rule_contribution_count": sum(1 for f in factors if f["source"] == "rule"),
    }


def create_project_features(project):
    """Create features for a single project, using peer stats if available."""
    sanctioned = float(getattr(project, "sanctioned_amount", 0) or 0)
    expenditure = float(getattr(project, "expenditure", 0) or 0)
    completion = float(getattr(project, "completion_percentage", 0) or 0)

    if peer_stats:
        from ml.train_anomaly_model import create_peer_relative_features as _crf
        row = {"state": getattr(project, "state", ""),
               "project_type": getattr(project, "project_type", ""),
               "sanctioned_amount": sanctioned, "expenditure": expenditure,
               "completion_percentage": completion}
        feat = _crf(row, peer_stats)

        import pandas as pd
        df = pd.DataFrame([feat])
        if features:
            for f in features:
                if f not in df.columns:
                    df[f] = 0
            df = df[features]
        df = df.replace([float("inf"), float("-inf")], 0).fillna(0)
        return df

    # Fallback: v1 absolute features
    import pandas as pd
    data = {
        "sanctioned_amount": sanctioned,
        "expenditure": expenditure,
        "completion_percentage": completion,
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
    """
    Predict risk for a project with full explainability.

    Returns:
        ml_anomaly: bool
        ml_score: float (decision function value; lower = more anomalous)
        risk_score: int (0-100, rule-based + ML combined)
        risk_level: str (High/Medium/Low/None)
        is_anomaly: bool
        reasons: list[str] (backward-compatible rule-based reasons)
        explanation: dict (NEW: full explanation with contributing factors)
    """
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
    ml_reason = None
    if ml_anomaly:
        risk_score += 25
        if peer_stats:
            ml_reason = "Contextual anomaly detected by peer-relative ML model"
        else:
            ml_reason = "Statistical anomaly detected by ML Isolation Forest model"
        reasons.append(ml_reason)

    risk_score = min(100, max(0, risk_score))

    if risk_score >= 60:
        risk_level = "High"
    elif risk_score >= 30:
        risk_level = "Medium"
    elif risk_score > 0:
        risk_level = "Low"
    else:
        risk_level = "None"

    # --- EXPLAINABILITY (new) ---
    contributions = _compute_feature_contributions(project)
    explanation = _summarize_reasons(contributions, reasons, risk_level)

    # Format contributing factors for API response
    top_factors = []
    for c in contributions:
        if c["contributes_to_anomaly"] and c["explanation"]:
            top_factors.append({
                "source": "ml",
                "feature": c["feature"],
                "label": c["label"],
                "explanation": c["explanation"],
                "shap_value": c["shap_value"],
                "feature_value": c["feature_value"],
            })
    # Add rule-based factors
    for reason in reasons:
        top_factors.append({
            "source": "rule",
            "explanation": reason,
        })

    return {
        "ml_anomaly": ml_anomaly,
        "ml_score": round(anomaly_score, 4),
        "risk_score": risk_score,
        "risk_level": risk_level,
        "is_anomaly": len(reasons) > 0,
        "reasons": reasons,
        # New explainability fields
        "explanation": explanation,
        "contributing_factors": top_factors[:10],
    }
