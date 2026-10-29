'''ingest_data.py
Unit II  - inserting documents (insert_many, batched writes)
Unit III - data modeling applied to the real IBM HR Attrition dataset:
           * Embedding    : compensation / satisfaction / career sub-documents,
                            engagement_history embedded array, exit_details 1:1
           * Referencing  : employees.dept_id -> departments, job_role_id -> job_roles
           * One-to-Many  : department -> employees, project -> team members
           * Many-to-Many : employees <-> projects (refs stored on both sides)
           * One-to-One   : employee -> exit_details (embedded) and
                            exit_interviews (separate collection, text-searchable)
'''

import csv
import random
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient

from config import (
    CSV_PATH,
    DB_NAME,
    MONGO_URI,
    COLL_DEPARTMENTS,
    COLL_EMPLOYEES,
    COLL_EXIT_INTERVIEWS,
    COLL_JOB_ROLES,
    COLL_PROJECTS,
    DEPT_CODES,
    ROLE_CODES,
    banner,
)

random.seed(42)  # deterministic synthetic fields

NOW = datetime.now(timezone.utc)

# ---------------------------------------------------------------------------
# Synthetic-but-realistic exit themes: derived from each employee's own data
# ---------------------------------------------------------------------------

def exit_theme(emp: dict) -> tuple[str, list]:
    """Pick the primary exit reason suggested by the employee's attributes."""
    tags = []
    if emp["overtime"]:
        tags.append("overtime")
    if emp["compensation"]["monthly_income"] < 3000:
        tags.append("salary")
    if emp["satisfaction"]["work_life_balance"] <= 2 or emp["distance_from_home_km"] > 20:
        tags.append("work-life-balance")
    if (emp["career"]["years_since_last_promotion"] >= 3
            or emp["job_level"] <= 2):
        tags.append("career-growth")
    if emp["satisfaction"]["relationship"] <= 2:
        tags.append("manager-relationship")
    if emp["satisfaction"]["overall_index"] <= 2.5:
        tags.append("low-engagement")
    if not tags:
        tags = ["career-growth"]
    return tags[0], tags


EXIT_COMMENTS = {
    "overtime": (
        "Worked long hours every sprint because of mandatory overtime; "
        "the burnout became unsustainable and other offers respected "
        "work-life balance better."
    ),
    "salary": (
        "Cited compensation below market for the role; monthly pay was the "
        "deciding factor and the counter-offer did not close the gap."
    ),
    "work-life-balance": (
        "Long commute plus rigid scheduling made work-life balance impossible; "
        "requested flexibility several times before resigning."
    ),
    "career-growth": (
        "No promotion or meaningful raise in recent years; accepted an offer "
        "with a clearer career path and a defined growth plan."
    ),
    "manager-relationship": (
        "Relationship with the reporting manager deteriorated; limited "
        "recognition and feedback drove the decision to leave."
    ),
    "low-engagement": (
        "Engagement scores were low for several consecutive quarters; felt "
        "disconnected from the team's goals and finally moved on."
    ),
}

INTERVIEWERS = ["Priya Nair", "Daniel Okafor", "Mei Chen", "Lucas Meyer"]

PROJECT_NAMES = [
    ("PRJ-001", "Workforce Analytics Platform", None),
    ("PRJ-002", "Campus Hiring Drive 2026", "HR"),
    ("PRJ-003", "Sales CRM Migration", "SALES"),
    ("PRJ-004", "Lab Automation Rollout", "RND"),
    ("PRJ-005", "Customer Retention Program", "SALES"),
    ("PRJ-006", "Benefits Redesign", "HR"),
    ("PRJ-007", "Product Prototype X2", "RND"),
    ("PRJ-008", "Regional Sales Expansion", "SALES"),
    ("PRJ-009", "Leadership Training Series", "HR"),
    ("PRJ-010", "Quality Audit Automation", "RND"),
    ("PRJ-011", "Partner Channel Launch", "SALES"),
    ("PRJ-012", "Cross-Functional Data Initiative", None),
]


def quarters_back(n: int = 4) -> list[tuple[str, datetime]]:
    """Return the last n quarter labels with their start dates."""
    out = []
    q = ((NOW.month - 1) // 3) + 1
    year, quarter = NOW.year, q
    while len(out) < n:
        start = datetime(year, 3 * quarter - 2, 1, tzinfo=timezone.utc)
        out.append((f"{year}-Q{quarter}", start))
        quarter -= 1
        if quarter == 0:
            quarter = 4
            year -= 1
    return list(reversed(out))


def build_employee_doc(row: dict, assignments: dict[str, list[str]]) -> dict:
    """Transform one CSV row into an employee document (schema from Unit III)."""
    years_at_company = int(row["YearsAtCompany"])
    overall = float(row["OverallSatisfactionIndex"])

    engagement = [
        {
            "quarter": label,
            "score": round(min(5.0, max(1.0, overall + random.uniform(-0.4, 0.4))), 2),
            "survey_date": start + timedelta(days=random.randint(5, 20)),
        }
        for label, start in quarters_back(4)
    ]

    attrited = row["Attrition"] == "Yes"

    doc = {
        # ---- identifiers ----
        "employee_number": int(row["EmployeeNumber"]),
        "employee_id": f"EMP{int(row['EmployeeNumber']):04d}",
        # ---- demographics ----
        "age": int(row["Age"]),
        "age_group": row["AgeGroup"],
        "gender": row["Gender"],
        "marital_status": row["MaritalStatus"],
        "distance_from_home_km": int(row["DistanceFromHome"]),
        "business_travel": row["BusinessTravel"],
        # ---- references (Unit III: referencing pattern) ----
        "dept_id": DEPT_CODES[row["Department"]],
        "job_role_id": ROLE_CODES[row["JobRole"]],
        # ---- denormalized copies for fast reads ----
        "department": row["Department"],
        "job_role": row["JobRole"],
        "job_level": int(row["JobLevel"]),
        # ---- embedded one-to-one sub-documents (Unit III: embedding) ----
        "education": {
            "level": int(row["Education"]),
            "field": row["EducationField"],
        },
        "compensation": {
            "monthly_income": float(row["MonthlyIncome"]),
            "daily_rate": float(row["DailyRate"]),
            "hourly_rate": float(row["HourlyRate"]),
            "monthly_rate": float(row["MonthlyRate"]),
            "percent_salary_hike": int(row["PercentSalaryHike"]),
            "stock_option_level": int(row["StockOptionLevel"]),
            "income_bracket": row["MonthlyIncomeBracket"],
        },
        "satisfaction": {
            "environment": int(row["EnvironmentSatisfaction"]),
            "job": int(row["JobSatisfaction"]),
            "relationship": int(row["RelationshipSatisfaction"]),
            "work_life_balance": int(row["WorkLifeBalance"]),
            "job_involvement": int(row["JobInvolvement"]),
            "performance_rating": int(row["PerformanceRating"]),
            "overall_index": overall,
        },
        "career": {
            "total_working_years": int(row["TotalWorkingYears"]),
            "num_companies_worked": int(row["NumCompaniesWorked"]),
            "years_at_company": years_at_company,
            "years_in_current_role": int(row["YearsInCurrentRole"]),
            "years_since_last_promotion": int(row["YearsSinceLastPromotion"]),
            "years_with_curr_manager": int(row["YearsWithCurrManager"]),
            "training_times_last_year": int(row["TrainingTimesLastYear"]),
            "tenure_group": row["TenureGroup"],
        },
        # ---- scalar flags ----
        "overtime": row["OverTime"] == "Yes",
        # ---- BSON Date derived from tenure ----
        "hire_date": NOW - timedelta(days=365 * years_at_company + random.randint(0, 300)),
        # ---- many-to-many refs to projects ----
        "project_ids": assignments[str(row["EmployeeNumber"])],
        # ---- embedded one-to-many array ----
        "engagement_history": engagement,
        # ---- target labels ----
        "attrition": row["Attrition"],
        "attrition_flag": 1 if attrited else 0,
    }

    # Embedded one-to-one exit details for attrited employees only
    if attrited:
        theme, tags = exit_theme(doc)
        doc["exit_details"] = {
            "exit_date": NOW - timedelta(days=random.randint(10, 365)),
            "exit_reason": theme,
            "rehire_eligible": overall >= 3.0,
        }
    return doc


def build_exit_interview(emp: dict) -> dict:
    """One-to-one companion document, kept separate so text indexes shine."""
    theme, tags = exit_theme(emp)
    return {
        "employee_number": emp["employee_number"],
        "employee_id": emp["employee_id"],
        "department": emp["department"],
        "interview_date": emp.get("exit_details", {}).get(
            "exit_date", NOW - timedelta(days=30)) + timedelta(days=random.randint(1, 14)),
        "interviewer": random.choice(INTERVIEWERS),
        "comments": EXIT_COMMENTS[theme],
        "theme_tags": tags,
    }


def main() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]
    if COLL_EMPLOYEES not in db.list_collection_names():
        raise SystemExit("Collection 'employees' missing - run setup_database.py first")

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    banner(f"Ingesting {len(rows)} employees from {CSV_PATH.name}")

    # ------------------------------------------------------------------
    # Step 1: many-to-many project assignments (employees <-> projects)
    # ------------------------------------------------------------------
    assignments: dict[str, list[str]] = {}
    for row in rows:
        n_projects = random.choices([0, 1, 2, 3], weights=[15, 40, 30, 15])[0]
        picked = random.sample([p[0] for p in PROJECT_NAMES], n_projects)
        assignments[row["EmployeeNumber"]] = picked

    # ------------------------------------------------------------------
    # Step 2: build + insert employee documents (references & embedding)
    # ------------------------------------------------------------------
    employees = db[COLL_EMPLOYEES]
    docs = [build_employee_doc(row, assignments) for row in rows]

    attrited = [d for d in docs if d["attrition_flag"] == 1]
    interviews = [build_exit_interview(e) for e in attrited]

    try:
        employees.insert_many(docs, ordered=False)
    except Exception as exc:
        print(f"  bulk insert reported: {str(exc)[:200]}")
    print(f"  employees         : {employees.count_documents({})} documents inserted")

    # ------------------------------------------------------------------
    # Step 3: projects collection with back-references (many-to-many)
    # ------------------------------------------------------------------
    projects = db[COLL_PROJECTS]
    start = NOW - timedelta(days=120)
    for pid, name, dept in PROJECT_NAMES:
        members = sorted(
            int(en) for en, plist in assignments.items() if pid in plist
        )
        if not members:
            continue
        projects.insert_one({
            "project_id": pid,
            "name": name,
            "dept_id": dept,           # None = cross-functional
            "start_date": start,
            "end_date": start + timedelta(days=365),
            "budget_usd": float(random.randint(50, 500) * 1000),
            "member_ids": members,
            "member_count": len(members),
        })
    print(f"  projects          : {projects.count_documents({})} documents")

    # ------------------------------------------------------------------
    # Step 4: exit interviews (one-to-one, text-searchable)
    # ------------------------------------------------------------------
    db[COLL_EXIT_INTERVIEWS].insert_many(interviews, ordered=False)
    print(f"  exit_interviews   : {db[COLL_EXIT_INTERVIEWS].count_documents({})} documents "
          f"(one per attrited employee)")

    # ------------------------------------------------------------------
    # Step 5: quick verification of the relationships
    # ------------------------------------------------------------------
    banner("Schema verification")
    sample = employees.find_one({"attrition_flag": 1},
                                {"_id": 0, "employee_id": 1, "dept_id": 1,
                                 "job_role_id": 1, "compensation.monthly_income": 1,
                                 "engagement_history": 1, "exit_details": 1,
                                 "project_ids": 1})
    print("  Sample attrited employee document (embedded sub-documents visible):")
    for key, value in sample.items():
        if isinstance(value, dict):
            print(f"    {key:<20} -> embedded doc with keys {list(value.keys())}")
        elif isinstance(value, list):
            print(f"    {key:<20} -> embedded array with {len(value)} items")
        else:
            print(f"    {key:<20} = {value}")

    joined = employees.aggregate([
        {"$lookup": {"from": COLL_DEPARTMENTS, "localField": "dept_id",
                     "foreignField": "dept_id", "as": "dept"}},
        {"$unwind": "$dept"},
        {"$group": {"_id": "$dept.name", "employees": {"$sum": 1},
                    "avg_income": {"$avg": "$compensation.monthly_income"}}},
        {"$sort": {"employees": -1}},
    ])
    print("\n  Referenced join check (employees -> departments via $lookup):")
    for d in joined:
        print(f"    {d['_id']:<25} {d['employees']:>5} employees, "
              f"avg income {d['avg_income']:.0f}")

    mm = projects.find_one({"member_count": {"$gt": 1}}, {"_id": 0,
                            "project_id": 1, "name": 1, "member_count": 1})
    print(f"\n  Many-to-many check: {mm['project_id']} '{mm['name']}' has "
          f"{mm['member_count']} members")

    print("\nDone. Collections ready for queries, aggregations and ML.")
    client.close()


if __name__ == "__main__":
    main()
