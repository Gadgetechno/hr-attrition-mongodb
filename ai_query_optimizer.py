'''ai_query_optimizer.py
Unit V - AI-driven Query Optimization in NoSQL Databases (practical version).

A workload-aware index advisor: it observes the plans MongoDB actually picks
(via explain()), weighs each query by how often the application issues it,
and recommends compound indexes using the Equality-Sort-Range (ESR) rule.
Run with --apply to create the recommended indexes and re-measure.

This is the pattern AI-driven optimizers use in production: observe plans and
index statistics, model the workload cost, recommend or auto-create indexes.
Here the "model" is an interpretable heuristic so every recommendation can be
verified by re-running explain().
'''

import sys

from pymongo import MongoClient

from config import DB_NAME, MONGO_URI, COLL_EMPLOYEES, COLL_EXIT_INTERVIEWS, banner
from indexing_demo import explain_find, stage_chain  # reuse the explain helpers

# Workload: (label, collection, filter, sort, limit, queries per hour)
WORKLOAD = [
    {"label": "Department retention lookup",
     "coll": COLL_EMPLOYEES,
     "filter": {"dept_id": "SALES", "attrition_flag": 0},
     "sort": None, "limit": None, "per_hour": 40},
    {"label": "High-risk watchlist API (top-10)",
     "coll": COLL_EMPLOYEES,
     "filter": {"attrition_flag": 0},
     "sort": [("attrition_risk", -1)], "limit": 10, "per_hour": 25},
    {"label": "Role-specific retention query",
     "coll": COLL_EMPLOYEES,
     "filter": {"job_role_id": "LAB_TECHNICIAN", "attrition_flag": 0},
     "sort": None, "limit": None, "per_hour": 20},
    {"label": "Frequent-travel senior audit",
     "coll": COLL_EMPLOYEES,
     "filter": {"business_travel": "Travel_Frequently", "age": {"$gte": 40}},
     "sort": [("age", 1)], "limit": None, "per_hour": 15},
    {"label": "Exit interviews tagged 'salary'",
     "coll": COLL_EXIT_INTERVIEWS,
     "filter": {"theme_tags": "salary"},
     "sort": None, "limit": None, "per_hour": 10},
    {"label": "Exit interview text search",
     "coll": COLL_EXIT_INTERVIEWS,
     "filter": {"$text": {"$search": "salary pay compensation"}},
     "sort": None, "limit": 3, "per_hour": 10},
]


def parse_filter(filter: dict) -> tuple[list, list]:
    """Split a filter into (equality fields, range fields) - ESR input."""
    eq, rng = [], []
    for key, value in (filter or {}).items():
        if key == "$and":
            for sub in value:
                sub_eq, sub_rng = parse_filter(sub)
                eq += sub_eq
                rng += sub_rng
        elif key.startswith("$"):
            continue                      # $or / $text: no single-index fix
        elif isinstance(value, dict) and any(
                op in value for op in ("$gt", "$gte", "$lt", "$lte", "$ne", "$nin")):
            rng.append(key)
        else:                             # scalar or $in -> equality
            eq.append(key)
    return eq, rng


def suggest_keys(filter: dict, sort) -> list | None:
    """Equality-Sort-Range compound index suggestion."""
    eq, rng = parse_filter(filter)
    if not eq and not rng:
        return None
    keys = [(f, 1) for f in eq]
    seen = {f for f, _ in keys}
    for field, direction in (sort or []):
        keys.append((field, direction))
        seen.add(field)
    keys += [(f, 1) for f in rng if f not in seen]
    return keys


def keys_of(index_entry: dict) -> list:
    """Normalize an index key spec ($indexStats uses a slightly different
    shape than index_information())."""
    key = index_entry["key"]
    if isinstance(key, dict):
        items = list(key.items())
    elif key and isinstance(key[0], dict):        # [{'f': field, 'v': dir}, ...]
        items = [(k["f"], k["v"]) for k in key]
    else:
        items = list(key)
    return [(f, d) for f, d in items if not str(f).startswith("_fts")]


def analyze(db) -> list:
    rows = []
    for q in WORKLOAD:
        res = explain_find(db, q["coll"], filter=q["filter"],
                           sort=q["sort"], limit=q["limit"])
        stages = stage_chain(res)
        ex = res.get("executionStats", {})
        docs = ex.get("totalDocsExamined", 0)
        returned = ex.get("nReturned", 0)
        suggestion = None
        reason = None
        if "COLLSCAN" in stages:
            suggestion = suggest_keys(q["filter"], q["sort"])
            reason = "full collection scan"
        elif "IXSCAN" in stages and returned > 0 and docs >= 3 * returned and docs > 100:
            # index helps, but the wrong one: it scans far more keys than it
            # returns - a compound index matching the filter would do better
            suggestion = suggest_keys(q["filter"], q["sort"])
            reason = f"index scan examines {docs} docs for {returned} results"
        rows.append({
            **q,
            "stages": " -> ".join(stages),
            "docs_examined": docs,
            "returned": returned,
            "reason": reason,
            "daily_cost": q["per_hour"] * 24 * docs,
            "suggestion": suggestion,
        })
    return rows


def print_report(rows: list, title: str) -> None:
    banner(title)
    print(f"  {'workload query':<36}{'q/h':>5}  {'plan':<38}{'docs':>6}{'ret':>6}  {'x24h':>10}")
    print("  " + "-" * 100)
    for r in sorted(rows, key=lambda x: -x["daily_cost"]):
        print(f"  {r['label']:<36}{r['per_hour']:>5}  {r['stages']:<38}"
              f"{r['docs_examined']:>6}{r['returned']:>6}  {r['daily_cost']:>10,}")
        if r["suggestion"]:
            print(f"  {'  ^ ' + r['reason'] + ' - recommend:':<36}"
                  f"{r['suggestion']}")


def apply_recommendations(db, rows: list) -> None:
    banner("Applying recommended indexes and re-measuring")
    for r in rows:
        if not r["suggestion"]:
            continue
        coll = db[r["coll"]]
        name = coll.create_index(r["suggestion"])
        print(f"\n  created {name}")
        after = explain_find(db, r["coll"], filter=r["filter"],
                             sort=r["sort"], limit=r["limit"])
        stages = stage_chain(after)
        docs = after["executionStats"]["totalDocsExamined"]
        saved = r["docs_examined"] - docs
        print(f"    plan stages   : {' -> '.join(stages)}")
        print(f"    docs examined : {r['docs_examined']} -> {docs} "
              f"(saves {saved:,} docs per query, "
              f"~{saved * r['per_hour'] * 24:,} per day)")


def index_usage(db) -> None:
    banner("Index usage statistics ($indexStats)")
    for coll_name in [COLL_EMPLOYEES, COLL_EXIT_INTERVIEWS]:
        print(f"  {coll_name}:")
        stats = list(db[coll_name].aggregate([{"$indexStats": {}}]))
        for s in sorted(stats, key=lambda x: -x["accesses"]["ops"]):
            keys = keys_of(s)
            print(f"    {s['name']:<36} ops={s['accesses']['ops']:>6}  {keys}")


def main() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]

    rows = analyze(db)
    print_report(rows, "Workload analysis: what MongoDB actually does today")
    index_usage(db)

    if "--apply" in sys.argv:
        apply_recommendations(db, rows)
        rows_after = analyze(db)
        print_report(rows_after, "Workload AFTER applying recommendations")
    else:
        print("\n  (dry run - re-run with:  python ai_query_optimizer.py --apply)")

    print("\nDone.")
    client.close()


if __name__ == "__main__":
    main()
