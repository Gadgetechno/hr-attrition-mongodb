'''setup_database.py
Unit I  - MongoDB architecture in practice: connect to the server (mongod),
          inspect server info, list databases.
Unit II - Databases, Collections, Documents; creating collections.
Unit III- Schema design with $jsonSchema validation rules and constraints.

Run order: this script FIRST (it drops and rebuilds the hr_analytics database),
then ingest_data.py to load the CSV.
'''

import sys

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import WriteError

from config import (
    DB_NAME,
    MONGO_URI,
    COLL_DEPARTMENTS,
    COLL_EMPLOYEES,
    COLL_EXIT_INTERVIEWS,
    COLL_JOB_ROLES,
    COLL_PROJECTS,
    banner,
)


def get_client() -> MongoClient:
    """Unit I: one client per process; the driver pools connections to mongod."""
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)


# ---------------------------------------------------------------------------
# $jsonSchema validators  (Unit III: Validation Rules and Constraints)
# ---------------------------------------------------------------------------

EMPLOYEE_SCHEMA = {
    "bsonType": "object",
    "required": [
        "employee_number", "employee_id", "age", "gender", "dept_id",
        "department", "job_role_id", "job_role", "job_level",
        "compensation", "satisfaction", "career",
        "overtime", "attrition", "attrition_flag",
    ],
    "properties": {
        # ---- identifiers: int32 + string (two BSON types) ----
        "employee_number": {"bsonType": "int", "minimum": 1},
        "employee_id":     {"bsonType": "string", "pattern": "^EMP\\d{4}$"},

        # ---- demographics with enum + range constraints ----
        "age":            {"bsonType": "int", "minimum": 18, "maximum": 60},
        "gender":         {"enum": ["Male", "Female"]},
        "marital_status": {"enum": ["Single", "Married", "Divorced"]},
        "business_travel": {"enum": ["Non-Travel", "Travel_Rarely", "Travel_Frequently"]},

        # ---- references to other collections (Unit III: referencing) ----
        "dept_id":     {"enum": ["SALES", "RND", "HR"]},
        "job_role_id": {"bsonType": "string"},

        # ---- flattened convenience fields (denormalized, Unit III) ----
        "department": {"bsonType": "string"},
        "job_role":   {"bsonType": "string"},
        "job_level":  {"bsonType": "int", "minimum": 1, "maximum": 5},
        "overtime":   {"bsonType": "bool"},

        # ---- embedded sub-documents (Unit III: embedding) ----
        "education": {
            "bsonType": "object",
            "required": ["level", "field"],
            "properties": {
                "level": {"bsonType": "int", "minimum": 1, "maximum": 5},
                "field": {"bsonType": "string"},
            },
        },
        "compensation": {
            "bsonType": "object",
            "required": ["monthly_income"],
            "properties": {
                "monthly_income":      {"bsonType": "double", "minimum": 0},
                "daily_rate":          {"bsonType": "double", "minimum": 0},
                "hourly_rate":         {"bsonType": "double", "minimum": 0},
                "monthly_rate":        {"bsonType": "double", "minimum": 0},
                "percent_salary_hike": {"bsonType": ["int", "double"], "minimum": 0},
                "stock_option_level":  {"bsonType": "int", "minimum": 0, "maximum": 3},
                "income_bracket":      {"enum": ["Low", "Medium", "High", "Very High"]},
            },
        },
        "satisfaction": {
            "bsonType": "object",
            "required": ["environment", "job", "relationship", "work_life_balance"],
            "properties": {
                "environment":       {"bsonType": "int", "minimum": 1, "maximum": 4},
                "job":               {"bsonType": "int", "minimum": 1, "maximum": 4},
                "relationship":      {"bsonType": "int", "minimum": 1, "maximum": 4},
                "work_life_balance": {"bsonType": "int", "minimum": 1, "maximum": 4},
                "job_involvement":   {"bsonType": "int", "minimum": 1, "maximum": 4},
                "performance_rating": {"bsonType": "int", "minimum": 1, "maximum": 4},
                "overall_index":     {"bsonType": "double", "minimum": 1, "maximum": 5},
            },
        },
        "career": {
            "bsonType": "object",
            "required": ["years_at_company", "total_working_years"],
            "properties": {
                "total_working_years":       {"bsonType": "int", "minimum": 0},
                "num_companies_worked":      {"bsonType": "int", "minimum": 0},
                "years_at_company":          {"bsonType": "int", "minimum": 0},
                "years_in_current_role":     {"bsonType": "int", "minimum": 0},
                "years_since_last_promotion": {"bsonType": "int", "minimum": 0},
                "years_with_curr_manager":   {"bsonType": "int", "minimum": 0},
                "training_times_last_year":  {"bsonType": "int", "minimum": 0},
                "tenure_group":              {"bsonType": "string"},
            },
        },

        # ---- embedded array: one-to-many inside the document ----
        "engagement_history": {
            "bsonType": "array",
            "items": {
                "bsonType": "object",
                "required": ["quarter", "score", "survey_date"],
                "properties": {
                    "quarter":     {"bsonType": "string", "pattern": "^\\d{4}-Q[1-4]$"},
                    "score":       {"bsonType": "double", "minimum": 1, "maximum": 5},
                    "survey_date": {"bsonType": "date"},
                },
            },
        },

        # ---- many-to-many references to the projects collection ----
        "project_ids": {"bsonType": "array", "items": {"bsonType": "string"}},

        # ---- BSON Date type ----
        "hire_date": {"bsonType": "date"},

        # ---- target labels ----
        "attrition":      {"enum": ["Yes", "No"]},
        "attrition_flag": {"bsonType": "int", "minimum": 0, "maximum": 1},

        # ---- embedded one-to-one (only present for attrited employees) ----
        "exit_details": {
            "bsonType": "object",
            "required": ["exit_date", "exit_reason", "rehire_eligible"],
            "properties": {
                "exit_date":       {"bsonType": "date"},
                "exit_reason":     {"bsonType": "string"},
                "rehire_eligible": {"bsonType": "bool"},
            },
        },
    },
}

DEPARTMENT_SCHEMA = {
    "bsonType": "object",
    "required": ["dept_id", "name"],
    "properties": {
        "dept_id":     {"bsonType": "string"},
        "name":        {"bsonType": "string"},
        "description": {"bsonType": "string"},
        "created_at":  {"bsonType": "date"},
    },
}

JOB_ROLE_SCHEMA = {
    "bsonType": "object",
    "required": ["role_id", "title"],
    "properties": {
        "role_id": {"bsonType": "string"},
        "title":   {"bsonType": "string"},
        "dept_id": {"bsonType": "string"},
    },
}

PROJECT_SCHEMA = {
    "bsonType": "object",
    "required": ["project_id", "name", "member_ids"],
    "properties": {
        "project_id":  {"bsonType": "string", "pattern": "^PRJ-\\d{3}$"},
        "name":        {"bsonType": "string"},
        "dept_id":     {"bsonType": ["string", "null"]},
        "start_date":  {"bsonType": "date"},
        "end_date":    {"bsonType": "date"},
        "budget_usd":  {"bsonType": "double", "minimum": 0},
        "member_ids":  {"bsonType": "array", "items": {"bsonType": "int"}},
        "member_count": {"bsonType": "int", "minimum": 0},
    },
}

EXIT_INTERVIEW_SCHEMA = {
    "bsonType": "object",
    "required": ["employee_number", "interview_date", "comments"],
    "properties": {
        "employee_number": {"bsonType": "int"},
        "employee_id":     {"bsonType": "string"},
        "department":      {"bsonType": "string"},
        "interview_date":  {"bsonType": "date"},
        "interviewer":     {"bsonType": "string"},
        "comments":        {"bsonType": "string"},
        "theme_tags":      {"bsonType": "array", "items": {"bsonType": "string"}},
    },
}


def ensure_collection(db: Database, name: str, schema: dict) -> None:
    """Create the collection with a validator, or update an existing one."""
    if name in db.list_collection_names():
        db.command("collMod", name, validator={"$jsonSchema": schema},
                   validationLevel="strict", validationAction="error")
    else:
        db.create_collection(
            name,
            validator={"$jsonSchema": schema},
            validationLevel="strict",
            validationAction="error",
        )


def demo_validation_rejection(employees) -> None:
    """Prove the validator is active: try to insert a bad document (Unit III)."""
    banner("Validation rules in action - bad document must be rejected")
    bad_doc = {
        "employee_number": 999999,          # int OK
        "employee_id": "BAD-1",             # fails ^EMP\d{4}$ pattern
        "age": 17,                          # below minimum 18
        "gender": "Unknown",                # not in enum
        "dept_id": "FINANCE",               # not in enum
        "attrition": "Maybe",               # not in enum
        "attrition_flag": 5,                # above maximum 1
        "job_role_id": "X", "job_role": "X", "job_level": 9,
        "department": "Ghost", "overtime": "yes-not-a-bool",
        "compensation": {"monthly_income": -100},
        "satisfaction": {"environment": 1, "job": 1, "relationship": 1,
                         "work_life_balance": 1},
        "career": {"years_at_company": 0, "total_working_years": 0},
    }
    try:
        employees.insert_one(bad_doc)
        print("  UNEXPECTED: invalid document was accepted!")
    except WriteError as exc:
        print("  insert_one(bad_doc) rejected by $jsonSchema validator, as expected.")
        print(f"  Server said: {exc.details.get('errmsg', str(exc))[:120]}...")


def create_indexes(db: Database) -> None:
    """Unit II/IV baseline indexes. More are added by indexing_demo.py."""
    employees = db[COLL_EMPLOYEES]
    employees.create_index("employee_number", unique=True)
    employees.create_index("employee_id", unique=True)
    employees.create_index("dept_id")
    employees.create_index("attrition_flag")

    db[COLL_DEPARTMENTS].create_index("dept_id", unique=True)
    db[COLL_JOB_ROLES].create_index("role_id", unique=True)
    db[COLL_PROJECTS].create_index("project_id", unique=True)
    db[COLL_EXIT_INTERVIEWS].create_index("employee_number", unique=True)


def main() -> None:
    client = get_client()

    banner(f"Connected to MongoDB at {MONGO_URI}")
    info = client.server_info()
    print(f"  Server version : {info['version']}  (mongod)")
    print(f"  Databases      : {client.list_database_names()}")

    db = client[DB_NAME]
    print(f"\n  Unit I: databases are created lazily - '{DB_NAME}' does not")
    print(f"  exist yet ({DB_NAME in client.list_database_names()}), it appears on first insert.")

    banner(f"Dropping and rebuilding database '{DB_NAME}'")
    client.drop_database(DB_NAME)

    # --- create collections with validators ---
    ensure_collection(db, COLL_DEPARTMENTS, DEPARTMENT_SCHEMA)
    ensure_collection(db, COLL_JOB_ROLES, JOB_ROLE_SCHEMA)
    ensure_collection(db, COLL_EMPLOYEES, EMPLOYEE_SCHEMA)
    ensure_collection(db, COLL_PROJECTS, PROJECT_SCHEMA)
    ensure_collection(db, COLL_EXIT_INTERVIEWS, EXIT_INTERVIEW_SCHEMA)
    print(f"  Collections created with $jsonSchema validators: {db.list_collection_names()}")

    # --- reference collections get their seed data here ---
    from datetime import datetime, timezone

    db[COLL_DEPARTMENTS].insert_many([
        {"dept_id": "SALES", "name": "Sales",
         "description": "Direct and inside sales, account management",
         "created_at": datetime.now(timezone.utc)},
        {"dept_id": "RND", "name": "Research & Development",
         "description": "Product research, labs and development teams",
         "created_at": datetime.now(timezone.utc)},
        {"dept_id": "HR", "name": "Human Resources",
         "description": "People operations, hiring and employee relations",
         "created_at": datetime.now(timezone.utc)},
    ])
    roles = [
        ("SALES_EXECUTIVE", "Sales Executive", "SALES"),
        ("SALES_REPRESENTATIVE", "Sales Representative", "SALES"),
        ("RESEARCH_SCIENTIST", "Research Scientist", "RND"),
        ("LAB_TECHNICIAN", "Laboratory Technician", "RND"),
        ("MFG_DIRECTOR", "Manufacturing Director", "RND"),
        ("RESEARCH_DIRECTOR", "Research Director", "RND"),
        ("HEALTHCARE_REP", "Healthcare Representative", "RND"),
        ("MANAGER", "Manager", "RND"),
        ("HR_SPECIALIST", "Human Resources", "HR"),
    ]
    db[COLL_JOB_ROLES].insert_many([
        {"role_id": rid, "title": title, "dept_id": dept}
        for rid, title, dept in roles
    ])
    print(f"  Seed data: {db[COLL_DEPARTMENTS].count_documents({})} departments, "
          f"{db[COLL_JOB_ROLES].count_documents({})} job roles")

    demo_validation_rejection(db[COLL_EMPLOYEES])

    create_indexes(db)
    banner("Indexes created (Unit II: Indexes & Query Optimization)")
    for coll_name in db.list_collection_names():
        for name, keys in db[coll_name].index_information().items():
            print(f"  {coll_name:<16} {name:<26} {keys}")

    print("\nDone. Next step: python ingest_data.py")
    client.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
