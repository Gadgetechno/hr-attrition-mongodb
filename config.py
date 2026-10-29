'''config.py
Shared settings for the HR Attrition MongoDB project.

- MONGO_URI can be overridden with an environment variable so the same code
  runs against a local MongoDB Community server or a MongoDB Atlas cluster:
      set MONGO_URI=mongodb+srv://<user>:<pass>@cluster0.xxxxx.mongodb.net/
- DB_NAME is the database every script uses.
'''

import os
from pathlib import Path

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "hr_analytics")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CSV_PATH = DATA_DIR / "IBM_HR_Attrition_Enhanced.csv"

# Collection names
COLL_EMPLOYEES = "employees"
COLL_DEPARTMENTS = "departments"
COLL_JOB_ROLES = "job_roles"
COLL_PROJECTS = "projects"
COLL_EXIT_INTERVIEWS = "exit_interviews"
COLL_ML_MODELS = "ml_models"
COLL_SANDBOX = "crud_sandbox"

# Reference-code mappings (Unit III: referencing pattern)
DEPT_CODES = {
    "Sales": "SALES",
    "Research & Development": "RND",
    "Human Resources": "HR",
}

ROLE_CODES = {
    "Sales Executive": "SALES_EXECUTIVE",
    "Research Scientist": "RESEARCH_SCIENTIST",
    "Laboratory Technician": "LAB_TECHNICIAN",
    "Manufacturing Director": "MFG_DIRECTOR",
    "Healthcare Representative": "HEALTHCARE_REP",
    "Manager": "MANAGER",
    "Sales Representative": "SALES_REPRESENTATIVE",
    "Research Director": "RESEARCH_DIRECTOR",
    "Human Resources": "HR_SPECIALIST",
}


def banner(title: str) -> None:
    """Print a section banner so console output is easy to read."""
    print("\n" + "=" * 64)
    print(f"  {title}")
    print("=" * 64)
