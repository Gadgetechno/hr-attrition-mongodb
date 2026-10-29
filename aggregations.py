'''aggregations.py
Unit IV - Aggregation Framework: real-world pipelines on the HR dataset.

Every stage of the syllabus pipeline concept appears here:
  $match -> $group -> $project -> $sort -> $limit
plus the multi-collection and multi-shape stages:
  $lookup, $unwind, $facet, $bucket, $bucketAuto, $addFields, $text, $slice.

Trick worth noticing: $avg of a 0/1 field IS the rate - we use that for
attrition rates everywhere instead of counting twice.
'''

from pymongo import MongoClient

from config import (
    DB_NAME,
    MONGO_URI,
    COLL_DEPARTMENTS,
    COLL_EMPLOYEES,
    COLL_EXIT_INTERVIEWS,
    banner,
)


def run(employees, title: str, pipeline: list) -> list:
    """Execute a pipeline and return the documents."""
    docs = list(employees.aggregate(pipeline))
    print(f"\n  pipeline: {title}")
    return docs


def print_rows(rows: list, fmt) -> None:
    for r in rows:
        print("   ", fmt(r))


# ---------------------------------------------------------------------------
# 1. Attrition rate per department ($group -> $project -> $sort + $lookup)
# ---------------------------------------------------------------------------

def attrition_by_department(employees) -> None:
    banner("Pipeline 1: Attrition rate per department ($group, $project, $lookup)")
    pipeline = [
        {"$group": {
            "_id": "$dept_id",
            "employees": {"$sum": 1},
            "attrited": {"$sum": "$attrition_flag"},
            "avg_income": {"$avg": "$compensation.monthly_income"},
        }},
        {"$project": {
            "_id": 0,
            "dept_id": "$_id",
            "employees": 1,
            "attrited": 1,
            "attrition_rate_pct": {"$round": [
                {"$multiply": [{"$divide": ["$attrited", "$employees"]}, 100]}, 1]},
            "avg_income": {"$round": ["$avg_income", 0]},
        }},
        {"$lookup": {                       # enrich with the departments collection
            "from": COLL_DEPARTMENTS,
            "localField": "dept_id",
            "foreignField": "dept_id",
            "as": "dept_info",
        }},
        {"$unwind": "$dept_info"},
        {"$project": {
            "dept_id": 1, "employees": 1, "attrited": 1,
            "attrition_rate_pct": 1, "avg_income": 1,
            "dept_name": "$dept_info.name",
        }},
        {"$sort": {"attrition_rate_pct": -1}},
    ]
    rows = run(employees, "attrition rate by department", pipeline)
    print_rows(rows, lambda r: f"{r['dept_name']:<26} n={r['employees']:>4}  "
                               f"attrited={r['attrited']:>3}  rate={r['attrition_rate_pct']:>5}%  "
                               f"avg income={r['avg_income']}")


# ---------------------------------------------------------------------------
# 2. Attrition by job level and by tenure bucket
# ---------------------------------------------------------------------------

def attrition_by_level_and_tenure(employees) -> None:
    banner("Pipeline 2: Attrition by job level and tenure group ($group, $sort)")
    by_level = run(employees, "attrition by job level", [
        {"$group": {
            "_id": "$job_level",
            "employees": {"$sum": 1},
            "rate": {"$avg": "$attrition_flag"},
            "avg_income": {"$avg": "$compensation.monthly_income"},
        }},
        {"$project": {
            "_id": 0, "job_level": "$_id", "employees": 1,
            "attrition_rate_pct": {"$round": [{"$multiply": ["$rate", 100]}, 1]},
            "avg_income": {"$round": ["$avg_income", 0]},
        }},
        {"$sort": {"job_level": 1}},
    ])
    print_rows(by_level, lambda r: f"level {r['job_level']}  n={r['employees']:>4}  "
                                   f"rate={r['attrition_rate_pct']:>5}%  avg income={r['avg_income']}")

    by_tenure = run(employees, "attrition by tenure group", [
        {"$group": {
            "_id": "$career.tenure_group",      # dotted path into embedded doc
            "employees": {"$sum": 1},
            "rate": {"$avg": "$attrition_flag"},
        }},
        {"$project": {
            "_id": 0, "tenure_group": "$_id", "employees": 1,
            "attrition_rate_pct": {"$round": [{"$multiply": ["$rate", 100]}, 1]},
        }},
        {"$sort": {"attrition_rate_pct": -1}},
    ])
    print_rows(by_tenure, lambda r: f"{r['tenure_group']:<26} n={r['employees']:>4}  rate={r['attrition_rate_pct']:>5}%")


# ---------------------------------------------------------------------------
# 3. Overtime impact ($group on boolean + $addFields)
# ---------------------------------------------------------------------------

def overtime_impact(employees) -> None:
    banner("Pipeline 3: Does overtime drive attrition? ($group + $addFields)")
    pipeline = [
        {"$group": {
            "_id": "$overtime",
            "employees": {"$sum": 1},
            "rate": {"$avg": "$attrition_flag"},
            "avg_satisfaction": {"$avg": "$satisfaction.overall_index"},
        }},
        {"$project": {
            "_id": 0, "overtime": "$_id", "employees": 1,
            "attrition_rate_pct": {"$round": [{"$multiply": ["$rate", 100]}, 1]},
            "avg_satisfaction": {"$round": ["$avg_satisfaction", 2]},
        }},
        {"$addFields": {"cohort": {"$cond": [{"$eq": ["$overtime", True]},
                                             "works overtime", "no overtime"]}}},
        {"$sort": {"overtime": 1}},
    ]
    rows = run(employees, "overtime vs attrition", pipeline)
    print_rows(rows, lambda r: f"{r['cohort']:<15} n={r['employees']:>4}  "
                               f"attrition={r['attrition_rate_pct']:>5}%  avg satisfaction={r['avg_satisfaction']}")


# ---------------------------------------------------------------------------
# 4. Income distribution ($bucket with fixed boundaries)
# ---------------------------------------------------------------------------

def income_distribution(employees) -> None:
    banner("Pipeline 4: Monthly income distribution ($bucket)")
    pipeline = [
        {"$bucket": {
            "groupBy": "$compensation.monthly_income",
            "boundaries": [0, 3000, 6000, 10000, 15000, 20000],
            "default": "20000+",
            "output": {
                "employees": {"$sum": 1},
                "rate": {"$avg": "$attrition_flag"},
            },
        }},
        {"$project": {
            "_id": 1, "employees": 1,
            "attrition_rate_pct": {"$round": [{"$multiply": ["$rate", 100]}, 1]},
        }},
    ]
    rows = run(employees, "income buckets", pipeline)
    bounds = {0: "0-3k", 3000: "3k-6k", 6000: "6k-10k",
              10000: "10k-15k", 15000: "15k-20k", "20000+": "20k+"}
    print_rows(rows, lambda r: f"income {bounds.get(r['_id'], r['_id']):<8} n={r['employees']:>4}  "
                               f"attrition={r['attrition_rate_pct']:>5}%")


# ---------------------------------------------------------------------------
# 5. $facet: a whole dashboard in ONE round trip
# ---------------------------------------------------------------------------

def dashboard_facet(employees) -> None:
    banner("Pipeline 5: $facet - five dashboard panels in a single query")
    pipeline = [
        {"$facet": {
            "totals": [{"$group": {"_id": None,
                                   "employees": {"$sum": 1},
                                   "attrited": {"$sum": "$attrition_flag"}}}],
            "by_department": [
                {"$group": {"_id": "$dept_id", "n": {"$sum": 1},
                            "rate": {"$avg": "$attrition_flag"}}},
                {"$project": {"n": 1,
                              "attrition_rate_pct": {"$round": [{"$multiply": ["$rate", 100]}, 1]}}},
                {"$sort": {"attrition_rate_pct": -1}}],
            "income_stats": [{"$group": {"_id": None,
                                         "min": {"$min": "$compensation.monthly_income"},
                                         "max": {"$max": "$compensation.monthly_income"},
                                         "avg": {"$avg": "$compensation.monthly_income"}}},
                             {"$project": {"min": 1, "max": 1,
                                           "avg": {"$round": ["$avg", 0]}}}],
            "travel_impact": [
                {"$group": {"_id": "$business_travel", "n": {"$sum": 1},
                            "rate": {"$avg": "$attrition_flag"}}},
                {"$project": {"n": 1,
                              "attrition_rate_pct": {"$round": [{"$multiply": ["$rate", 100]}, 1]}}},
                {"$sort": {"attrition_rate_pct": -1}}],
            "top_risk_roles": [
                {"$group": {"_id": "$job_role", "n": {"$sum": 1},
                            "rate": {"$avg": "$attrition_flag"}}},
                {"$project": {"n": 1,
                              "attrition_rate_pct": {"$round": [{"$multiply": ["$rate", 100]}, 1]}}},
                {"$sort": {"attrition_rate_pct": -1}},
                {"$limit": 3}],
        }},
    ]
    result = list(employees.aggregate(pipeline))[0]

    t = result["totals"][0]
    rate = round(100.0 * t["attrited"] / t["employees"], 1)
    print(f"  totals        : {t['employees']} employees, {t['attrited']} attrited ({rate}%)")
    i = result["income_stats"][0]
    print(f"  income stats  : min={i['min']}  avg={i['avg']}  max={i['max']}")
    print("  by department :")
    print_rows(result["by_department"], lambda r: f"{r['_id']:<6} n={r['n']:>4}  rate={r['attrition_rate_pct']:>5}%")
    print("  by travel     :")
    print_rows(result["travel_impact"], lambda r: f"{r['_id']:<18} n={r['n']:>4}  rate={r['attrition_rate_pct']:>5}%")
    print("  top-risk roles:")
    print_rows(result["top_risk_roles"], lambda r: f"{r['_id']:<28} n={r['n']:>4}  rate={r['attrition_rate_pct']:>5}%")


# ---------------------------------------------------------------------------
# 6. $unwind on the embedded engagement array
# ---------------------------------------------------------------------------

def engagement_by_quarter(employees) -> None:
    banner("Pipeline 6: $unwind the embedded engagement_history array")
    pipeline = [
        {"$unwind": "$engagement_history"},
        {"$group": {
            "_id": "$engagement_history.quarter",
            "avg_score": {"$avg": "$engagement_history.score"},
            "responses": {"$sum": 1},
        }},
        {"$project": {"_id": 1, "responses": 1,
                      "avg_score": {"$round": ["$avg_score", 2]}}},
        {"$sort": {"_id": 1}},
    ]
    rows = run(employees, "average engagement per quarter", pipeline)
    print_rows(rows, lambda r: f"{r['_id']}  avg={r['avg_score']:<5} responses={r['responses']}")


# ---------------------------------------------------------------------------
# 7. Top-3 earners per department ($sort + $group + $push + $slice)
# ---------------------------------------------------------------------------

def top_earners(employees) -> None:
    banner("Pipeline 7: Top-3 earners per department ($group + $push + $slice)")
    pipeline = [
        {"$sort": {"dept_id": 1, "compensation.monthly_income": -1}},
        {"$group": {
            "_id": "$dept_id",
            "top3": {"$push": {"employee_id": "$employee_id",
                               "role": "$job_role",
                               "income": "$compensation.monthly_income"}},
        }},
        {"$project": {"top3": {"$slice": ["$top3", 3]}, "_id": 0, "dept_id": "$_id"}},
        {"$sort": {"dept_id": 1}},
    ]
    rows = run(employees, "top 3 earners per department", pipeline)
    for r in rows:
        print(f"   {r['dept_id']}:")
        for e in r["top3"]:
            print(f"     {e['employee_id']}  {e['role']:<28} {e['income']}")


# ---------------------------------------------------------------------------
# 8. $bucketAuto: attrition across automatically computed age bands
# ---------------------------------------------------------------------------

def age_bands(employees) -> None:
    banner("Pipeline 8: $bucketAuto - attrition across age bands")
    pipeline = [
        {"$match": {"attrition": {"$in": ["Yes", "No"]}}},   # early $match = good practice
        {"$bucketAuto": {
            "groupBy": "$age",
            "buckets": 4,
            "output": {
                "employees": {"$sum": 1},
                "rate": {"$avg": "$attrition_flag"},
                "avg_income": {"$avg": "$compensation.monthly_income"},
            },
        }},
        {"$project": {
            "employees": 1,
            "attrition_rate_pct": {"$round": [{"$multiply": ["$rate", 100]}, 1]},
            "avg_income": {"$round": ["$avg_income", 0]},
        }},
    ]
    rows = run(employees, "age bands (auto buckets)", pipeline)
    print_rows(rows, lambda r: f"ages {r['_id']['min']}-{r['_id']['max']}  n={r['employees']:>4}  "
                               f"attrition={r['attrition_rate_pct']:>5}%  avg income={r['avg_income']}")


# ---------------------------------------------------------------------------
# 9. Text-search aggregation on exit interviews ($text + $group)
# ---------------------------------------------------------------------------

def exit_theme_search(db) -> None:
    banner("Pipeline 9: $text search on exit interviews -> themes by department")
    exits = db[COLL_EXIT_INTERVIEWS]
    pipeline = [
        {"$match": {"$text": {"$search": "overtime burnout hours"}}},
        {"$group": {"_id": "$department", "exits": {"$sum": 1}}},
        {"$sort": {"exits": -1}},
    ]
    docs = list(exits.aggregate(pipeline))
    total = sum(d["exits"] for d in docs)
    print(f"\n  pipeline: $text 'overtime burnout hours' -> {total} exit interviews mentioning these themes")
    print_rows(docs, lambda r: f"{r['_id']:<26} {r['exits']:>3} exits")


def main() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]
    employees = db[COLL_EMPLOYEES]
    if employees.count_documents({}) == 0:
        raise SystemExit("No employees found - run setup_database.py and ingest_data.py first")

    attrition_by_department(employees)
    attrition_by_level_and_tenure(employees)
    overtime_impact(employees)
    income_distribution(employees)
    dashboard_facet(employees)
    engagement_by_quarter(employees)
    top_earners(employees)
    age_bands(employees)
    exit_theme_search(db)

    print("\nDone.")
    client.close()


if __name__ == "__main__":
    main()
