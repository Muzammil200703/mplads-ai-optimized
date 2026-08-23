import sys
import os

sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)

from database import SessionLocal
from models import Project, RiskScore
from ml.predictor import predict_risk


def generate_scores():

    db = SessionLocal()

    try:

        print("Loading projects...")

        projects = db.query(Project).all()

        print(
            f"Projects found: {len(projects)}"
        )


        # clear old scores

        db.query(RiskScore).delete()

        db.commit()


        print("Generating risk scores...")


        count = 0


        for project in projects:

            risk = predict_risk(project)


            score = RiskScore(

                project_id=project.id,

                ml_anomaly=risk["ml_anomaly"],

                ml_score=risk["ml_score"],

                risk_score=risk["risk_score"],

                risk_level=risk["risk_level"],

                reasons=", ".join(
                    risk["reasons"]
                )
            )


            db.add(score)


            count += 1


            if count % 1000 == 0:
                print(
                    f"Processed {count} projects"
                )

                db.commit()



        db.commit()


        print(
            "Risk generation completed"
        )

    finally:

        db.close()



if __name__ == "__main__":

    generate_scores()