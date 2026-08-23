import os
import sys
import pandas as pd

# Allow importing from the backend directory
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)

from database import SessionLocal
from models import Project


def analyze_projects():

    db = SessionLocal()

    try:
        print("\nLoading project data...")

        projects = db.query(Project).all()

        if not projects:
            print("No project data found.")
            return

        data = [
            {
                column.name: getattr(project, column.name)
                for column in Project.__table__.columns
            }
            for project in projects
        ]

        df = pd.DataFrame(data)

        print("\n" + "=" * 60)
        print("MPLADS PROJECT DATA ANALYSIS")
        print("=" * 60)

        # Dataset size
        print("\n1. DATASET SIZE")
        print("-" * 60)
        print(f"Rows    : {df.shape[0]}")
        print(f"Columns : {df.shape[1]}")

        # Columns
        print("\n2. COLUMNS")
        print("-" * 60)

        for column in df.columns:
            print(f"- {column}")

        # Data types
        print("\n3. DATA TYPES")
        print("-" * 60)
        print(df.dtypes)

        # Missing values
        print("\n4. MISSING VALUES")
        print("-" * 60)

        missing = df.isnull().sum()

        for column, count in missing.items():
            if count > 0:
                percentage = (count / len(df)) * 100
                print(
                    f"{column}: {count} "
                    f"({percentage:.2f}%)"
                )

        # Numeric statistics
        print("\n5. NUMERIC STATISTICS")
        print("-" * 60)

        numeric_columns = df.select_dtypes(
            include="number"
        ).columns

        if len(numeric_columns) > 0:
            print(
                df[numeric_columns].describe()
            )

        # Status distribution
        if "status" in df.columns:
            print("\n6. PROJECT STATUS")
            print("-" * 60)
            print(
                df["status"]
                .value_counts(dropna=False)
            )

        # Project type distribution
        if "project_type" in df.columns:
            print("\n7. PROJECT TYPES")
            print("-" * 60)
            print(
                df["project_type"]
                .value_counts(dropna=False)
            )

        # State distribution
        if "state" in df.columns:
            print("\n8. STATES")
            print("-" * 60)
            print(
                df["state"]
                .value_counts(dropna=False)
                .head(20)
            )

        # Completion statistics
        if "completion_percentage" in df.columns:
            print("\n9. COMPLETION PERCENTAGE")
            print("-" * 60)
            print(
                df["completion_percentage"]
                .describe()
            )

        # Financial statistics
        financial_columns = [
            "sanctioned_amount",
            "expenditure"
        ]

        existing_financial = [
            column
            for column in financial_columns
            if column in df.columns
        ]

        if existing_financial:
            print("\n10. FINANCIAL DATA")
            print("-" * 60)
            print(
                df[existing_financial].describe()
            )

        # Correlation
        print("\n11. NUMERIC CORRELATION")
        print("-" * 60)

        if len(numeric_columns) > 1:
            print(
                df[numeric_columns]
                .corr()
                .round(2)
            )

        print("\n" + "=" * 60)
        print("ANALYSIS COMPLETE")
        print("=" * 60)

    finally:
        db.close()


if __name__ == "__main__":
    analyze_projects()