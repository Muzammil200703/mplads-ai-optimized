import os
import sys
import joblib
import pandas as pd

from sklearn.ensemble import IsolationForest

# Allow importing backend files
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)

from database import SessionLocal
from models import Project


MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "anomaly_model.pkl"
)


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


def create_features(df):

    features = pd.DataFrame(index=df.index)

    features["sanctioned_amount"] = (
        df["sanctioned_amount"].fillna(0)
    )

    features["expenditure"] = (
        df["expenditure"].fillna(0)
    )

    features["completion_percentage"] = (
        df["completion_percentage"].fillna(0)
    )

    features["utilization_ratio"] = (
        features["expenditure"]
        /
        features["sanctioned_amount"].replace(0, 1)
    )

    features["unspent_amount"] = (
        features["sanctioned_amount"]
        -
        features["expenditure"]
    )

    features["expenditure_per_completion"] = (
        features["expenditure"]
        /
        features["completion_percentage"].replace(0, 1)
    )

    features["remaining_completion"] = (
        100 - features["completion_percentage"]
    )

    features["high_value_project"] = (
        features["sanctioned_amount"] >= 1000000
    ).astype(int)

    features["zero_expenditure"] = (
        features["expenditure"] == 0
    ).astype(int)

    features["zero_completion"] = (
        features["completion_percentage"] == 0
    ).astype(int)

    features = features.replace(
        [float("inf"), float("-inf")],
        0
    )

    features = features.fillna(0)

    return features


def train_model():

    print("\nLoading MPLADS projects...")

    df = load_projects()

    print(
        f"Projects loaded: {len(df)}"
    )


    print("\nCreating ML features...")

    X = create_features(df)

    print(
        f"Features created: {X.shape[1]}"
    )


    print("\nFeatures used:")

    for column in X.columns:
        print(f"- {column}")


    print("\nTraining Isolation Forest...")


    model = IsolationForest(
        n_estimators=200,
        contamination=0.01,
        random_state=42,
        n_jobs=-1
    )


    model.fit(X)


    # Predictions

    predictions = model.predict(X)

    anomaly_scores = model.decision_function(X)


    df["ml_anomaly"] = (
        predictions == -1
    )


    df["ml_anomaly_score"] = (
        anomaly_scores
    )


    anomaly_count = (
        df["ml_anomaly"].sum()
    )


    print("\n" + "=" * 60)
    print("ML ANOMALY DETECTION RESULTS")
    print("=" * 60)


    print(
        f"Total projects : {len(df)}"
    )

    print(
        f"Anomalies      : {anomaly_count}"
    )

    print(
        f"Normal projects: {len(df)-anomaly_count}"
    )

    print(
        f"Anomaly rate   : "
        f"{(anomaly_count / len(df))*100:.2f}%"
    )


    print("\nMost anomalous projects:")


    display_columns = [
        "id",
        "project_name",
        "state",
        "sanctioned_amount",
        "expenditure",
        "completion_percentage",
        "ml_anomaly_score"
    ]


    available_columns = [
        column
        for column in display_columns
        if column in df.columns
    ]


    print(
        df[df["ml_anomaly"]]
        .sort_values(
            "ml_anomaly_score",
            ascending=True
        )
        [available_columns]
        .head(10)
        .to_string(index=False)
    )


    # Save model

    model_data = {
        "model": model,
        "features": list(X.columns)
    }


    joblib.dump(
        model_data,
        MODEL_PATH
    )


    print("\nModel saved to:")

    print(MODEL_PATH)


    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)



if __name__ == "__main__":

    train_model()