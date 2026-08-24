"""
Context-Aware MPLADS Anomaly Detection Model Training (v2)
==========================================================

Improvements over v1:
1. Peer-group comparison: projects compared against state-level peers
2. Ratio-based features: expenditure-to-sanctioned ratio, financial-vs-physical progress gap
3. Statistical z-scores relative to state peers, not global population
4. Peer statistics stored with model for inference-time lookup
"""

import os
import sys
import warnings
warnings.filterwarnings("ignore")

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from database import SessionLocal
from models import Project


MODEL_PATH = os.path.join(os.path.dirname(__file__), "anomaly_model.pkl")


def load_projects():
    db = SessionLocal()
    try:
        projects = db.query(Project).all()
        data = [
            {
                column.name: getattr(project, column.name)
                for column in Project.__table__.columns
            }
            for project in projects
        ]
        return pd.DataFrame(data)
    finally:
        db.close()


def compute_peer_statistics(df):
    peer_stats = {"national": {}, "by_state": {}, "by_type": {}}

    for col in ["sanctioned_amount", "expenditure", "completion_percentage"]:
        valid = df[col].dropna()
        peer_stats["national"][col] = {
            "median": float(valid.median()),
            "mean": float(valid.mean()),
            "std": float(valid.std()),
            "q25": float(valid.quantile(0.25)),
            "q75": float(valid.quantile(0.75)),
        }

    sanctioned = df["sanctioned_amount"].replace(0, np.nan)
    utilization = (df["expenditure"] / sanctioned).dropna().clip(0, 5)
    peer_stats["national"]["utilization_ratio"] = {
        "median": float(utilization.median()),
        "mean": float(utilization.mean()),
        "std": float(utilization.std()),
        "q25": float(utilization.quantile(0.25)),
        "q75": float(utilization.quantile(0.75)),
    }

    fin_phys_gap = df["expenditure"] - (df["sanctioned_amount"] * df["completion_percentage"] / 100.0)
    peer_stats["national"]["fin_phys_gap"] = {
        "median": float(fin_phys_gap.median()),
        "mean": float(fin_phys_gap.mean()),
        "std": float(fin_phys_gap.std()),
        "q25": float(fin_phys_gap.quantile(0.25)),
        "q75": float(fin_phys_gap.quantile(0.75)),
    }

    for state, grp in df.groupby("state"):
        if pd.isna(state) or state == "":
            continue
        state_stats = {}
        for col in ["sanctioned_amount", "expenditure", "completion_percentage"]:
            valid = grp[col].dropna()
            if len(valid) < 3:
                state_stats[col] = peer_stats["national"][col].copy()
            else:
                state_stats[col] = {
                    "median": float(valid.median()),
                    "mean": float(valid.mean()),
                    "std": float(max(float(valid.std()), 1e-10)),
                    "q25": float(valid.quantile(0.25)),
                    "q75": float(valid.quantile(0.75)),
                    "count": len(valid),
                }
        s_sanctioned = grp["sanctioned_amount"].replace(0, np.nan)
        s_util = (grp["expenditure"] / s_sanctioned).dropna().clip(0, 5)
        if len(s_util) >= 3:
            state_stats["utilization_ratio"] = {
                "median": float(s_util.median()),
                "mean": float(s_util.mean()),
                "std": float(max(float(s_util.std()), 1e-10)),
                "q25": float(s_util.quantile(0.25)),
                "q75": float(s_util.quantile(0.75)),
            }
        else:
            state_stats["utilization_ratio"] = peer_stats["national"]["utilization_ratio"].copy()
        s_gap = grp["expenditure"] - (grp["sanctioned_amount"] * grp["completion_percentage"] / 100.0)
        if len(s_gap.dropna()) >= 3:
            state_stats["fin_phys_gap"] = {
                "median": float(s_gap.median()),
                "mean": float(s_gap.mean()),
                "std": float(max(float(s_gap.std()), 1e-10)),
                "q25": float(s_gap.quantile(0.25)),
                "q75": float(s_gap.quantile(0.75)),
            }
        else:
            state_stats["fin_phys_gap"] = peer_stats["national"]["fin_phys_gap"].copy()
        peer_stats["by_state"][state] = state_stats

    for ptype, grp in df.groupby("project_type"):
        if pd.isna(ptype) or ptype == "":
            continue
        type_stats = {}
        for col in ["sanctioned_amount", "expenditure", "completion_percentage"]:
            valid = grp[col].dropna()
            if len(valid) < 10:
                type_stats[col] = peer_stats["national"][col].copy()
            else:
                type_stats[col] = {
                    "median": float(valid.median()),
                    "mean": float(valid.mean()),
                    "std": float(max(float(valid.std()), 1e-10)),
                    "q25": float(valid.quantile(0.25)),
                    "q75": float(valid.quantile(0.75)),
                }
        peer_stats["by_type"][ptype] = type_stats

    return peer_stats


def get_peer_stats_for_project(row, peer_stats, level="state"):
    if level == "state":
        state = row.get("state", "")
        if state and state in peer_stats.get("by_state", {}):
            return peer_stats["by_state"][state]
    elif level == "type":
        ptype = row.get("project_type", "")
        if ptype and ptype in peer_stats.get("by_type", {}):
            return peer_stats["by_type"][ptype]
    return peer_stats["national"]


def create_peer_relative_features(row, peer_stats):
    sanctioned = float(row.get("sanctioned_amount", 0) or 0)
    expenditure = float(row.get("expenditure", 0) or 0)
    completion = float(row.get("completion_percentage", 0) or 0)

    state_peer = get_peer_stats_for_project(row, peer_stats, level="state")
    national_peer = peer_stats["national"]
    features = {}

    features["log_sanctioned"] = np.log1p(sanctioned)
    features["log_expenditure"] = np.log1p(expenditure)
    features["completion_pct"] = completion

    sanctioned_safe = max(sanctioned, 1)
    features["utilization_ratio"] = min(expenditure / sanctioned_safe, 5.0)
    features["unspent_ratio"] = max(0, sanctioned - expenditure) / sanctioned_safe
    features["expenditure_per_completion"] = expenditure / max(completion, 1)
    features["remaining_completion"] = max(0, 100 - completion)

    features["zero_expenditure"] = 1 if expenditure == 0 else 0
    features["zero_completion"] = 1 if completion == 0 else 0
    features["high_value_project"] = 1 if sanctioned >= 1_000_000 else 0
    features["overspent"] = 1 if sanctioned > 0 and expenditure > sanctioned else 0

    sm = state_peer.get("sanctioned_amount", {}).get("median", 1)
    ss = state_peer.get("sanctioned_amount", {}).get("std", 1)
    em = state_peer.get("expenditure", {}).get("median", 1)
    es = state_peer.get("expenditure", {}).get("std", 1)
    cm = state_peer.get("completion_percentage", {}).get("median", 1)
    cs = state_peer.get("completion_percentage", {}).get("std", 1)
    um = state_peer.get("utilization_ratio", {}).get("median", 0.5)
    us = state_peer.get("utilization_ratio", {}).get("std", 0.3)
    gm = state_peer.get("fin_phys_gap", {}).get("median", 0)
    gs = state_peer.get("fin_phys_gap", {}).get("std", 1)

    features["sanctioned_zscore"] = (sanctioned - sm) / max(ss, 1)
    features["expenditure_zscore"] = (expenditure - em) / max(es, 1)
    features["completion_zscore"] = (completion - cm) / max(cs, 1)
    features["sanctioned_vs_state_median"] = sanctioned / max(sm, 1)
    features["expenditure_vs_state_median"] = expenditure / max(em, 1)
    features["completion_vs_state_median"] = completion / max(cm, 1)

    my_util = min(expenditure / sanctioned_safe, 5.0)
    features["utilization_vs_state"] = (my_util - um) / max(us, 0.01)
    fin_phys_gap = expenditure - (sanctioned * completion / 100.0)
    features["fin_phys_gap_vs_state"] = (fin_phys_gap - gm) / max(gs, 1)

    nm = national_peer.get("sanctioned_amount", {}).get("median", 1)
    ns = national_peer.get("sanctioned_amount", {}).get("std", 1)
    nem = national_peer.get("expenditure", {}).get("median", 1)
    nes = national_peer.get("expenditure", {}).get("std", 1)
    features["sanctioned_national_zscore"] = (sanctioned - nm) / max(ns, 1)
    features["expenditure_national_zscore"] = (expenditure - nem) / max(nes, 1)
    features["sanctioned_order_of_magnitude"] = np.log10(max(sanctioned, 1)) - np.log10(max(nm, 1))

    state_count = state_peer.get("sanctioned_amount", {}).get("count", 0)
    features["peer_group_size"] = min(state_count / 1000.0, 15.0)

    return features


def create_features(df, peer_stats):
    feature_rows = []
    for _, row in df.iterrows():
        feat = create_peer_relative_features(row.to_dict(), peer_stats)
        feature_rows.append(feat)
    features = pd.DataFrame(feature_rows, index=df.index)
    features = features.replace([np.inf, -np.inf], 0).fillna(0)
    return features


def train_model():
    print("\n" + "=" * 60)
    print("CONTEXT-AWARE ANOMALY DETECTION MODEL TRAINING (v2)")
    print("=" * 60)

    print("\n1. Loading MPLADS projects...")
    df = load_projects()
    print(f"   Projects loaded: {len(df)}")
    print(f"   States: {df['state'].nunique()}")
    print(f"   Project types: {df['project_type'].nunique()}")

    print("\n2. Computing peer-group statistics...")
    peer_stats = compute_peer_statistics(df)
    print(f"   State groups: {len(peer_stats['by_state'])}")
    print(f"   Type groups: {len(peer_stats['by_type'])}")

    print("\n3. Creating context-aware features...")
    X = create_features(df, peer_stats)
    print(f"   Features: {X.shape[1]}")
    for col in X.columns:
        print(f"     - {col}")

    print("\n4. Training Isolation Forest (300 estimators)...")
    model = IsolationForest(
        n_estimators=300,
        contamination=0.01,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X)

    predictions = model.predict(X)
    anomaly_scores = model.decision_function(X)
    df["ml_anomaly"] = predictions == -1
    df["ml_anomaly_score"] = anomaly_scores
    anomaly_count = int(df["ml_anomaly"].sum())

    print("\n" + "=" * 60)
    print("ML ANOMALY DETECTION RESULTS (v2 - Context-Aware)")
    print("=" * 60)
    print(f"Total projects : {len(df)}")
    print(f"Anomalies      : {anomaly_count}")
    print(f"Normal projects: {len(df) - anomaly_count}")
    print(f"Anomaly rate   : {(anomaly_count / len(df)) * 100:.2f}%")

    display_columns = [
        "id", "project_name", "state", "project_type",
        "sanctioned_amount", "expenditure", "completion_percentage",
        "status", "ml_anomaly_score"
    ]
    available_columns = [c for c in display_columns if c in df.columns]
    print("\nMost anomalous projects (v2):")
    print(
        df[df["ml_anomaly"]]
        .sort_values("ml_anomaly_score", ascending=True)[available_columns]
        .head(15)
        .to_string(index=False)
    )

    model_data = {
        "model": model,
        "features": list(X.columns),
        "peer_stats": peer_stats,
        "version": "2.0",
        "description": "Context-aware peer-relative anomaly detection",
    }
    joblib.dump(model_data, MODEL_PATH)
    file_size_mb = os.path.getsize(MODEL_PATH) / (1024 * 1024)
    print(f"\nModel saved to: {MODEL_PATH}")
    print(f"Model file size: {file_size_mb:.2f} MB")
    print(f"\n{'=' * 60}")
    print("TRAINING COMPLETE")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    train_model()
