'''indexing_demo.py
Unit IV - Indexing: single, compound and text indexes; measuring performance
with explain(); covered queries.

For every scenario we run explain("executionStats") BEFORE and AFTER creating
the index, so the COLLSCAN -> IXSCAN improvement is visible in real numbers:
  * COLLSCAN          : every document in the collection is examined
  * IXSCAN            : only the matching index keys are traversed
  * totalDocsExamined : how many documents MongoDB actually had to touch
  * totalKeysExamined : how many index keys were traversed
  * PROJECTION_COVERED: a covered query answered entirely from the index
'''

import time

from pymongo import MongoClient, TEXT

from config import DB_NAME, MONGO_URI, COLL_EMPLOYEES, COLL_EXIT_INTERVIEWS, banner


# ---------------------------------------------------------------------------
# explain() helpers
# ---------------------------------------------------------------------------

def explain_find(db, coll_name, filter=None, projection=None,
                 sort=None, limit=None) -> dict:
    cmd = {"find": coll_name}
    if filter:
        cmd["filter"] = filter
    if projection:
        cmd["projection"] = projection
    if sort:
        cmd["sort"] = dict(sort)  # the raw find command wants an object
    if limit:
        cmd["limit"] = limit
    return db.command("explain", cmd, verbosity="executionStats")


def stage_chain(plan: dict) -> list:
    """Flatten the winning plan into a list of stage names."""
    stages = []

    def walk(node):
        if not isinstance(node, dict):
            return
        if "queryPlan" in node:           # SBE wrapper (MongoDB 8.x)
            walk(node["queryPlan"])
            return
        if "stage" in node:
            stages.append(node["stage"])
        if "inputStage" in node:
            walk(node["inputStage"])
        if "inputStages" in node:
            for child in node["inputStages"]:
                walk(child)

    walk(plan.get("queryPlanner", {}).get("winningPlan", {}))
    return stages


def stats(res: dict) -> dict:
    ex = res.get("executionStats", {})
    return {
        "stages": " -> ".join(stage_chain(res)) or "(n/a)",
        "keys_examined": ex.get("totalKeysExamined"),
        "docs_examined": ex.get("totalDocsExamined"),
        "returned": ex.get("nReturned"),
        "ms": ex.get("executionTimeMillis"),
    }


def report(title: str, res: dict) -> None:
    s = stats(res)
    print(f"\n  {title}")
    print(f"    plan stages     : {s['stages']}")
    print(f"    keys examined   : {s['keys_examined']}")
    print(f"    docs examined   : {s['docs_examined']}")
    print(f"    docs returned   : {s['returned']}")
    print(f"    execution time  : {s['ms']} ms")


def wall_time(db, coll_name, filter=None, sort=None, limit=None, runs=20) -> float:
    """Average client-side wall time in microseconds (averaged over runs)."""
    coll = db[coll_name]

    def cursor_fn():
        cur = coll.find(filter, {"_id": 0, "employee_id": 1})
        if sort:
            cur = cur.sort(sort)
        if limit:
            cur = cur.limit(limit)
        return list(cur)

    cursor_fn()  # warm-up
    t0 = time.perf_counter()
    for _ in range(runs):
        cursor_fn()
    return (time.perf_counter() - t0) / runs * 1e6


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def single_field_index(db) -> None:
    banner("Scenario 1 - SINGLE field index (range query on monthly income)")
    employees = db[COLL_EMPLOYEES]
    q_filter = {"compensation.monthly_income": {"$gt": 12000}}

    report("BEFORE (no index on compensation.monthly_income)",
           explain_find(db, COLL_EMPLOYEES, filter=q_filter))

    employees.create_index("compensation.monthly_income")
    print("\n  -> created index: compensation.monthly_income_1")

    report("AFTER", explain_find(db, COLL_EMPLOYEES, filter=q_filter))
    print(f"\n  avg wall time after index (20 runs): "
          f"{wall_time(db, COLL_EMPLOYEES, filter=q_filter):.0f} us")


def compound_index(db) -> None:
    banner("Scenario 2 - COMPOUND index (equality + equality + sort)")
    employees = db[COLL_EMPLOYEES]
    q_filter = {"overtime": True, "gender": "Female"}
    q_sort = [("age", -1)]

    report("BEFORE (no index covers overtime/gender/age)",
           explain_find(db, COLL_EMPLOYEES, filter=q_filter, sort=q_sort))

    employees.create_index([("overtime", 1), ("gender", 1), ("age", -1)])
    print("\n  -> created compound index: overtime_1_gender_1_age_-1")

    report("AFTER (index gives both equality bounds AND the sort order)",
           explain_find(db, COLL_EMPLOYEES, filter=q_filter, sort=q_sort))

    # Prefix rule: a compound index also serves queries on its leading fields
    report("PREFIX query {overtime: true} reuses the same index",
           explain_find(db, COLL_EMPLOYEES, filter={"overtime": True}))


def covered_query(db) -> None:
    banner("Scenario 3 - COVERED QUERY (answer comes from the index alone)")
    employees = db[COLL_EMPLOYEES]
    q_filter = {"dept_id": "SALES", "attrition_flag": 0}
    q_proj = {"_id": 0, "dept_id": 1, "attrition_flag": 1}

    report("BEFORE (only dept_id_1 exists -> must fetch full documents)",
           explain_find(db, COLL_EMPLOYEES, filter=q_filter, projection=q_proj))

    employees.create_index([("dept_id", 1), ("attrition_flag", 1)])
    print("\n  -> created compound index: dept_id_1_attrition_flag_1")

    res = explain_find(db, COLL_EMPLOYEES, filter=q_filter, projection=q_proj)
    report("AFTER", res)
    s = stats(res)
    covered = s["docs_examined"] == 0 and s["returned"] > 0
    print(f"\n  COVERED QUERY: {covered} "
          f"(docs_examined=0 means every result came straight from index keys)")
    print("  Note: dept_id_1 is now redundant - it is a prefix of the compound index.")


def text_index(db) -> None:
    banner("Scenario 4 - TEXT index (free-text search on exit interviews)")
    exits = db[COLL_EXIT_INTERVIEWS]
    exits.create_index([("comments", TEXT)])
    print("  -> created text index on exit_interviews.comments")

    q_filter = {"$text": {"$search": "salary compensation pay"}}
    proj = {"_id": 0, "employee_id": 1, "department": 1, "comments": 1,
            "score": {"$meta": "textScore"}}
    top = list(exits.find(q_filter, proj).sort([("score", {"$meta": "textScore"})]).limit(3))
    print(f"\n  $text search 'salary compensation pay' -> "
          f"{exits.count_documents(q_filter)} matching exit interviews; top 3 by relevance:")
    for d in top:
        print(f"    [{d['score']:.2f}] {d['employee_id']} ({d['department']}): "
              f"{d['comments'][:70]}...")

    report("explain() of the text query",
           explain_find(db, COLL_EXIT_INTERVIEWS, filter=q_filter, projection=proj, limit=3))


def sort_optimization(db) -> None:
    banner("Scenario 5 - SORT optimization (index avoids in-memory sort)")
    employees = db[COLL_EMPLOYEES]
    q_sort = [("hire_date", -1)]

    report("BEFORE (no index on hire_date -> COLLSCAN + in-memory SORT)",
           explain_find(db, COLL_EMPLOYEES, sort=q_sort, limit=5))

    employees.create_index("hire_date")
    print("\n  -> created index: hire_date_1")

    report("AFTER (index scanned in reverse: no SORT stage at all)",
           explain_find(db, COLL_EMPLOYEES, sort=q_sort, limit=5))


def final_inventory(db) -> None:
    banner("Index inventory after this demo")
    for coll_name in [COLL_EMPLOYEES, COLL_EXIT_INTERVIEWS]:
        for name, keys in db[coll_name].index_information().items():
            print(f"  {coll_name:<16} {name:<34} {keys}")


def reset_demo_indexes(db) -> None:
    """Drop every index this demo creates, so the BEFORE states are honest
    even when the script is re-run."""
    drop_map = {
        COLL_EMPLOYEES: [
            "compensation.monthly_income_1",
            "overtime_1_gender_1_age_-1",
            "dept_id_1_attrition_flag_1",
            "hire_date_1",
        ],
        COLL_EXIT_INTERVIEWS: ["comments_text"],
    }
    for coll_name, names in drop_map.items():
        coll = db[coll_name]
        existing = set(coll.index_information())
        for name in names:
            if name in existing:
                coll.drop_index(name)
    print("  (demo indexes dropped - clean BEFORE state guaranteed)")


def main() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]
    if db[COLL_EMPLOYEES].count_documents({}) == 0:
        raise SystemExit("No employees found - run setup_database.py and ingest_data.py first")

    print("=" * 64)
    print("  Preparing: re-runnable demo state")
    print("=" * 64)
    reset_demo_indexes(db)

    single_field_index(db)
    compound_index(db)
    covered_query(db)
    text_index(db)
    sort_optimization(db)
    final_inventory(db)
    print("\nDone.")
    client.close()


if __name__ == "__main__":
    main()
