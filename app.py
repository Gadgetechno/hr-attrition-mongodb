"""app.py
Flask REST API backend for the HR Attrition MongoDB demo frontend.
Every route corresponds to a MongoDB operation or query from the project
modules (crud_operations, aggregations, indexing_demo, ml_model).
"""

import json
import time
from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
from bson import Decimal128, ObjectId
from flask import Flask, jsonify, render_template, request
from pymongo import MongoClient, TEXT, UpdateOne
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split

from config import (
    DB_NAME, MONGO_URI,
    COLL_EMPLOYEES, COLL_DEPARTMENTS, COLL_JOB_ROLES,
    COLL_PROJECTS, COLL_EXIT_INTERVIEWS, COLL_ML_MODELS, COLL_SANDBOX,
)

app = Flask(__name__, template_folder="templates", static_folder="static")

# ---------------------------------------------------------------------------
# MongoDB client (reuse one connection pool across all requests)
# ---------------------------------------------------------------------------
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client[DB_NAME]

# ---------------------------------------------------------------------------
# Model cache – trained once on demand, held in memory for fast predictions
# ---------------------------------------------------------------------------
_model_cache = {}

NUMERIC_FEATURES = [
    "age", "distance_from_home_km", "job_level",
    "compensation.monthly_income", "compensation.daily_rate",
    "compensation.hourly_rate", "compensation.monthly_rate",
    "compensation.percent_salary_hike", "compensation.stock_option_level",
    "satisfaction.environment", "satisfaction.job",
    "satisfaction.relationship", "satisfaction.work_life_balance",
    "satisfaction.job_involvement", "satisfaction.performance_rating",
    "satisfaction.overall_index",
    "career.total_working_years", "career.num_companies_worked",
    "career.years_at_company", "career.years_in_current_role",
    "career.years_since_last_promotion", "career.years_with_curr_manager",
    "career.training_times_last_year",
]
CATEGORICAL_FEATURES = [
    "gender", "marital_status", "business_travel",
    "department", "job_role", "education.field",
]
EXCLUDED_PROJECTION = {
    "_id": 0, "employee_id": 0, "age_group": 0, "hire_date": 0,
    "project_ids": 0, "engagement_history": 0, "exit_details": 0,
    "career.tenure_group": 0, "compensation.income_bracket": 0,
    "attrition": 0,
}


def _train_model():
    """Load employees from MongoDB, train RandomForest, cache everything."""
    employees = db[COLL_EMPLOYEES]
    docs = list(employees.find({}, EXCLUDED_PROJECTION))
    if len(docs) < 10:
        raise RuntimeError("Not enough employees in MongoDB to train (run ingest_data.py first).")

    df = pd.json_normalize(docs)
    y = df["attrition_flag"].astype(int)

    X = df[NUMERIC_FEATURES].copy()
    X["overtime"] = df["overtime"].astype(int)

    encoders = {}
    for col in CATEGORICAL_FEATURES:
        le = LabelEncoder()
        flat_col = col.replace(".", "_")  # after json_normalize dots become underscores
        # json_normalize converts 'education.field' -> 'education.field' (dot kept)
        src = col if col in df.columns else col.replace(".", ".")
        X[f"{col}_enc"] = le.fit_transform(df[col].astype(str))
        encoders[col] = le

    feature_cols = list(X.columns)
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)

    clf = RandomForestClassifier(
        n_estimators=200, random_state=42, n_jobs=-1, class_weight="balanced")
    clf.fit(X_tr, y_tr)

    importances = sorted(
        zip(feature_cols, clf.feature_importances_),
        key=lambda t: t[1], reverse=True
    )

    from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
    preds = clf.predict(X_te)
    proba = clf.predict_proba(X_te)[:, 1]
    metrics = {
        "accuracy": round(float(accuracy_score(y_te, preds)) * 100, 2),
        "f1": round(float(f1_score(y_te, preds, zero_division=0)) * 100, 2),
        "roc_auc": round(float(roc_auc_score(y_te, proba)), 3),
        "train_rows": int(len(X_tr)),
        "test_rows": int(len(X_te)),
    }

    _model_cache["model"] = clf
    _model_cache["encoders"] = encoders
    _model_cache["feature_cols"] = feature_cols
    _model_cache["importances"] = importances[:15]
    _model_cache["metrics"] = metrics
    _model_cache["trained_at"] = datetime.now(timezone.utc).isoformat()
    return _model_cache


def get_model():
    """Return cached model or train on first call."""
    if "model" not in _model_cache:
        _train_model()
    return _model_cache


# ---------------------------------------------------------------------------
# JSON serialiser – handles ObjectId, datetime, Decimal128
# ---------------------------------------------------------------------------
class MongoEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Decimal128):
            return float(o.to_decimal())
        return super().default(o)


def mongo_json(data, status=200):
    return app.response_class(
        json.dumps(data, cls=MongoEncoder),
        status=status,
        mimetype="application/json",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def safe(fn):
    """Wrap a route body and return {error: ...} on exception."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            return mongo_json({"error": str(exc)}, 500)
    wrapper.__name__ = fn.__name__
    return wrapper


# ===========================================================================
#  PAGES
# ===========================================================================
@app.route("/")
def index():
    return render_template("index.html")


# ===========================================================================
#  HEALTH / CONNECTION
# ===========================================================================
@app.route("/api/health")
@safe
def health():
    info = client.server_info()
    dbs = client.list_database_names()
    colls = db.list_collection_names()
    counts = {c: db[c].count_documents({}) for c in colls}
    return mongo_json({
        "status": "connected",
        "mongo_version": info["version"],
        "databases": dbs,
        "collections": colls,
        "document_counts": counts,
    })


# ===========================================================================
#  COLLECTION OVERVIEW
# ===========================================================================
@app.route("/api/overview")
@safe
def overview():
    colls = db.list_collection_names()
    result = []
    for c in colls:
        result.append({
            "collection": c,
            "count": db[c].count_documents({}),
            "sample": list(db[c].find({}, {"_id": 0}).limit(1)),
        })
    return mongo_json(result)


# ===========================================================================
#  BSON TYPE DEMO
# ===========================================================================
@app.route("/api/bson-types", methods=["POST"])
@safe
def bson_types():
    sandbox = db[COLL_SANDBOX]
    doc = {
        "string_type":      "HR analytics",
        "int32_type":       42,
        "double_type":      5993.50,
        "boolean_type":     True,
        "date_type":        datetime.now(timezone.utc),
        "null_type":        None,
        "array_type":       [1, 2, 3],
        "embedded_doc":     {"level": 2, "field": "Life Sciences"},
        "decimal128_type":  Decimal128(Decimal("19999.99")),
    }
    result = sandbox.insert_one(doc)
    inserted_id = result.inserted_id

    types_cursor = sandbox.aggregate([
        {"$match": {"_id": inserted_id}},
        {"$project": {
            "bson_types": {
                "$map": {
                    "input": {"$objectToArray": "$$ROOT"},
                    "in": {"k": "$$this.k", "t": {"$type": "$$this.v"}},
                }
            }
        }},
    ])
    bson_types_list = list(types_cursor)[0]["bson_types"]
    sandbox.delete_one({"_id": inserted_id})
    return mongo_json({
        "inserted_id": str(inserted_id),
        "bson_types": [e for e in bson_types_list if e["k"] != "_id"],
        "message": "Document inserted, types inspected, then deleted."
    })


# ===========================================================================
#  CRUD  – CREATE
# ===========================================================================
@app.route("/api/crud/create", methods=["POST"])
@safe
def crud_create():
    sandbox = db[COLL_SANDBOX]
    one = sandbox.insert_one({
        "doc_type": "single", "note": "created by insert_one via API",
        "created_at": datetime.now(timezone.utc),
    })
    many = sandbox.insert_many([
        {"doc_type": "batch", "batch_no": i, "value": i * 10}
        for i in range(1, 6)
    ])
    count = sandbox.count_documents({})
    return mongo_json({
        "insert_one_id": str(one.inserted_id),
        "insert_many_ids": [str(i) for i in many.inserted_ids],
        "total_in_sandbox": count,
    })


# ===========================================================================
#  CRUD  – READ  (employees collection)
# ===========================================================================
@app.route("/api/crud/read")
@safe
def crud_read():
    employees = db[COLL_EMPLOYEES]
    proj = {"_id": 0, "employee_id": 1, "job_role": 1,
            "department": 1, "compensation.monthly_income": 1,
            "attrition": 1, "attrition_flag": 1}

    # top-5 earners
    top_earners = list(
        employees.find({}, proj)
        .sort("compensation.monthly_income", -1)
        .limit(5)
    )

    # various operator counts
    gt_15k   = employees.count_documents({"compensation.monthly_income": {"$gt": 15000}})
    in_sales  = employees.count_documents({"dept_id": {"$in": ["SALES", "HR"]}})
    overtime50 = employees.count_documents({"$and": [{"overtime": True}, {"age": {"$gte": 50}}]})
    regex_res  = employees.count_documents({"job_role": {"$regex": "^Research"}})
    attrited   = employees.count_documents({"attrition_flag": 1})
    distinct_roles = sorted(employees.distinct("job_role"))

    return mongo_json({
        "top_5_earners": top_earners,
        "counts": {
            "income_gt_15000": gt_15k,
            "dept_sales_or_hr": in_sales,
            "overtime_and_age_gte_50": overtime50,
            "job_role_starts_research": regex_res,
            "attrited": attrited,
        },
        "distinct_job_roles": distinct_roles,
    })


# ===========================================================================
#  CRUD  – UPDATE
# ===========================================================================
@app.route("/api/crud/update", methods=["POST"])
@safe
def crud_update():
    sandbox = db[COLL_SANDBOX]
    sandbox.delete_many({})
    sandbox.insert_many([{"counter": i} for i in range(3)])

    r1 = sandbox.update_one({"counter": 1}, {"$set": {"status": "reviewed"}})
    r2 = sandbox.update_many({}, {"$inc": {"counter": 100}})
    r3 = sandbox.update_one({"counter": 999}, {"$set": {"created_by_upsert": True}}, upsert=True)
    sandbox.update_one({"counter": 101}, {"$push": {"audit_log": "first touch"}})
    sandbox.update_one({"counter": 101}, {"$push": {"audit_log": "second touch"}})
    doc_101 = sandbox.find_one({"counter": 101}, {"_id": 0})
    updated = sandbox.find_one_and_update(
        {"counter": 102}, {"$set": {"flagged": True}}, return_document=True)

    sandbox.delete_many({})
    return mongo_json({
        "update_one_matched": r1.matched_count,
        "update_one_modified": r1.modified_count,
        "update_many_modified": r2.modified_count,
        "upsert_created_new": r3.upserted_id is not None,
        "audit_log_after_push": doc_101.get("audit_log", []),
        "find_one_and_update_flagged": updated.get("flagged") if updated else None,
    })


# ===========================================================================
#  CRUD  – DELETE
# ===========================================================================
@app.route("/api/crud/delete", methods=["POST"])
@safe
def crud_delete():
    sandbox = db[COLL_SANDBOX]
    sandbox.delete_many({})
    sandbox.insert_many([{"counter": i} for i in range(5)])
    r1 = sandbox.delete_one({"counter": 0})
    r2 = sandbox.delete_many({"counter": {"$gt": 2}})
    remaining = sandbox.count_documents({})
    sandbox.delete_many({})
    return mongo_json({
        "delete_one_removed": r1.deleted_count,
        "delete_many_removed": r2.deleted_count,
        "remaining_docs": remaining,
    })


# ===========================================================================
#  AGGREGATIONS
# ===========================================================================
@app.route("/api/aggregations/by-department")
@safe
def agg_by_department():
    employees = db[COLL_EMPLOYEES]
    pipeline = [
        {"$group": {
            "_id": "$dept_id",
            "employees": {"$sum": 1},
            "attrited": {"$sum": "$attrition_flag"},
            "avg_income": {"$avg": "$compensation.monthly_income"},
        }},
        {"$project": {
            "_id": 0, "dept_id": "$_id", "employees": 1, "attrited": 1,
            "attrition_rate_pct": {"$round": [
                {"$multiply": [{"$divide": ["$attrited", "$employees"]}, 100]}, 1]},
            "avg_income": {"$round": ["$avg_income", 0]},
        }},
        {"$lookup": {
            "from": COLL_DEPARTMENTS, "localField": "dept_id",
            "foreignField": "dept_id", "as": "dept_info",
        }},
        {"$unwind": "$dept_info"},
        {"$project": {
            "dept_id": 1, "employees": 1, "attrited": 1,
            "attrition_rate_pct": 1, "avg_income": 1,
            "dept_name": "$dept_info.name",
        }},
        {"$sort": {"attrition_rate_pct": -1}},
    ]
    return mongo_json(list(employees.aggregate(pipeline)))


@app.route("/api/aggregations/by-job-level")
@safe
def agg_by_level():
    employees = db[COLL_EMPLOYEES]
    rows = list(employees.aggregate([
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
    ]))
    return mongo_json(rows)


@app.route("/api/aggregations/overtime-impact")
@safe
def agg_overtime():
    employees = db[COLL_EMPLOYEES]
    rows = list(employees.aggregate([
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
    ]))
    return mongo_json(rows)


@app.route("/api/aggregations/income-distribution")
@safe
def agg_income():
    employees = db[COLL_EMPLOYEES]
    rows = list(employees.aggregate([
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
    ]))
    bounds = {0: "0-3k", 3000: "3k-6k", 6000: "6k-10k",
              10000: "10k-15k", 15000: "15k-20k", "20000+": "20k+"}
    for r in rows:
        r["range_label"] = bounds.get(r["_id"], str(r["_id"]))
    return mongo_json(rows)


@app.route("/api/aggregations/dashboard-facet")
@safe
def agg_facet():
    employees = db[COLL_EMPLOYEES]
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
                {"$limit": 5}],
        }},
    ]
    result = list(employees.aggregate(pipeline))[0]
    return mongo_json(result)


@app.route("/api/aggregations/engagement-by-quarter")
@safe
def agg_engagement():
    employees = db[COLL_EMPLOYEES]
    rows = list(employees.aggregate([
        {"$unwind": "$engagement_history"},
        {"$group": {
            "_id": "$engagement_history.quarter",
            "avg_score": {"$avg": "$engagement_history.score"},
            "responses": {"$sum": 1},
        }},
        {"$project": {"_id": 1, "responses": 1,
                      "avg_score": {"$round": ["$avg_score", 2]}}},
        {"$sort": {"_id": 1}},
    ]))
    return mongo_json(rows)


@app.route("/api/aggregations/top-earners")
@safe
def agg_top_earners():
    employees = db[COLL_EMPLOYEES]
    rows = list(employees.aggregate([
        {"$sort": {"dept_id": 1, "compensation.monthly_income": -1}},
        {"$group": {
            "_id": "$dept_id",
            "top3": {"$push": {"employee_id": "$employee_id",
                               "role": "$job_role",
                               "income": "$compensation.monthly_income"}},
        }},
        {"$project": {"top3": {"$slice": ["$top3", 3]}, "_id": 0, "dept_id": "$_id"}},
        {"$sort": {"dept_id": 1}},
    ]))
    return mongo_json(rows)


@app.route("/api/aggregations/age-bands")
@safe
def agg_age_bands():
    employees = db[COLL_EMPLOYEES]
    rows = list(employees.aggregate([
        {"$match": {"attrition": {"$in": ["Yes", "No"]}}},
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
    ]))
    for r in rows:
        r["range_label"] = f"{r['_id']['min']}-{r['_id']['max']}"
    return mongo_json(rows)


@app.route("/api/aggregations/exit-text-search")
@safe
def agg_exit_search():
    q = request.args.get("q", "overtime burnout hours")
    exits = db[COLL_EXIT_INTERVIEWS]
    # ensure text index exists
    existing = exits.index_information()
    if not any("text" in str(v.get("key", {})) for v in existing.values()):
        exits.create_index([("comments", TEXT)])
    rows = list(exits.aggregate([
        {"$match": {"$text": {"$search": q}}},
        {"$group": {"_id": "$department", "exits": {"$sum": 1}}},
        {"$sort": {"exits": -1}},
    ]))
    return mongo_json({"query": q, "results": rows})


# ===========================================================================
#  INDEXING DEMO
# ===========================================================================
@app.route("/api/indexing/explain")
@safe
def indexing_explain():
    """Return explain stats for a predefined set of queries."""
    employees = db[COLL_EMPLOYEES]

    def ex(filter_q, sort=None, proj=None, limit=None):
        cmd = {"find": COLL_EMPLOYEES, "filter": filter_q}
        if proj:
            cmd["projection"] = proj
        if sort:
            cmd["sort"] = dict(sort)
        if limit:
            cmd["limit"] = limit
        res = db.command("explain", cmd, verbosity="executionStats")
        s = res.get("executionStats", {})
        stages = []
        def walk(node):
            if not isinstance(node, dict):
                return
            if "queryPlan" in node:
                walk(node["queryPlan"])
                return
            if "stage" in node:
                stages.append(node["stage"])
            if "inputStage" in node:
                walk(node["inputStage"])
            if "inputStages" in node:
                for child in node["inputStages"]:
                    walk(child)
        walk(res.get("queryPlanner", {}).get("winningPlan", {}))
        return {
            "stages": " → ".join(stages) or "(n/a)",
            "keys_examined": s.get("totalKeysExamined"),
            "docs_examined": s.get("totalDocsExamined"),
            "returned": s.get("nReturned"),
            "ms": s.get("executionTimeMillis"),
        }

    # query 1: range on income
    q1_before = ex({"compensation.monthly_income": {"$gt": 12000}})
    employees.create_index("compensation.monthly_income")
    q1_after = ex({"compensation.monthly_income": {"$gt": 12000}})

    # query 2: compound (equality + sort)
    q2_before = ex({"overtime": True, "gender": "Female"}, sort=[("age", -1)])
    employees.create_index([("overtime", 1), ("gender", 1), ("age", -1)])
    q2_after = ex({"overtime": True, "gender": "Female"}, sort=[("age", -1)])

    # query 3: covered
    q3_before = ex({"dept_id": "SALES", "attrition_flag": 0},
                   proj={"_id": 0, "dept_id": 1, "attrition_flag": 1})
    employees.create_index([("dept_id", 1), ("attrition_flag", 1)])
    q3_after = ex({"dept_id": "SALES", "attrition_flag": 0},
                  proj={"_id": 0, "dept_id": 1, "attrition_flag": 1})

    return mongo_json({
        "range_query_income_gt_12000": {"before": q1_before, "after": q1_after},
        "compound_overtime_female_sort_age": {"before": q2_before, "after": q2_after},
        "covered_query_dept_attrition": {"before": q3_before, "after": q3_after},
    })


@app.route("/api/indexing/inventory")
@safe
def indexing_inventory():
    result = {}
    for coll_name in db.list_collection_names():
        result[coll_name] = {
            name: {"key": info["key"], "unique": info.get("unique", False)}
            for name, info in db[coll_name].index_information().items()
        }
    return mongo_json(result)


# ===========================================================================
#  ML MODEL
# ===========================================================================
@app.route("/api/ml/train", methods=["POST"])
@safe
def ml_train():
    """Force re-train (or train on first call) and return metrics."""
    _model_cache.clear()
    cache = _train_model()
    return mongo_json({
        "status": "trained",
        "trained_at": cache["trained_at"],
        "metrics": cache["metrics"],
        "top_features": [{"name": n, "importance": round(float(s), 4)}
                         for n, s in cache["importances"]],
    })


@app.route("/api/ml/model-info")
@safe
def ml_model_info():
    if "model" not in _model_cache:
        return mongo_json({"trained": False,
                           "message": "Model not yet trained. Click 'Train Model' first."})
    c = _model_cache
    return mongo_json({
        "trained": True,
        "trained_at": c["trained_at"],
        "metrics": c["metrics"],
        "top_features": [{"name": n, "importance": round(float(s), 4)}
                         for n, s in c["importances"]],
        "feature_count": len(c["feature_cols"]),
    })


@app.route("/api/ml/predict", methods=["POST"])
@safe
def ml_predict():
    """Accept employee feature JSON, return predicted attrition risk."""
    cache = get_model()
    clf        = cache["model"]
    encoders   = cache["encoders"]
    feat_cols  = cache["feature_cols"]
    body = request.get_json(force=True)

    # Build feature row in exactly the same order as training
    row = {}
    # Numeric
    for f in NUMERIC_FEATURES:
        row[f] = float(body.get(f, 0))
    # Boolean
    row["overtime"] = 1.0 if body.get("overtime", False) else 0.0
    # Categorical (label-encode using fitted encoders)
    for col in CATEGORICAL_FEATURES:
        val = str(body.get(col, ""))
        le = encoders[col]
        if val in le.classes_:
            row[f"{col}_enc"] = float(le.transform([val])[0])
        else:
            # unseen label → use most frequent class (index 0)
            row[f"{col}_enc"] = 0.0

    X = pd.DataFrame([row])[feat_cols]
    proba = float(clf.predict_proba(X)[0, 1])
    tier = "High" if proba >= 0.7 else "Medium" if proba >= 0.4 else "Low"

    # Log the prediction to MongoDB (optional audit trail)
    audit = {
        "source": "web_tester",
        "inputs": body,
        "attrition_risk": round(proba, 4),
        "risk_tier": tier,
        "predicted_at": datetime.now(timezone.utc),
    }
    db["prediction_log"].insert_one(audit)

    # Build per-feature contribution for display
    importances_map = dict(cache["importances"])
    top_impact = sorted(
        [(f, importances_map.get(f, 0)) for f in feat_cols],
        key=lambda t: t[1], reverse=True
    )[:8]

    return mongo_json({
        "attrition_risk": round(proba, 4),
        "risk_pct": round(proba * 100, 1),
        "risk_tier": tier,
        "prediction": "Likely to Leave" if proba >= 0.5 else "Likely to Stay",
        "confidence": round(max(proba, 1 - proba) * 100, 1),
        "top_drivers": [{"feature": n, "importance": round(float(s), 4)}
                        for n, s in top_impact],
        "logged_to_mongodb": True,
    })


@app.route("/api/ml/prediction-log")
@safe
def ml_prediction_log():
    """Return the last 20 predictions stored in MongoDB."""
    docs = list(db["prediction_log"].find(
        {}, {"_id": 0, "inputs": 0}
    ).sort("predicted_at", -1).limit(20))
    return mongo_json(docs)


@app.route("/api/ml/watchlist")
@safe
def ml_watchlist():
    employees = db[COLL_EMPLOYEES]
    # check if risk scores exist
    has_risk = employees.count_documents({"attrition_risk": {"$exists": True}})
    if not has_risk:
        return mongo_json({"error": "Run ml_model.py first to score employees."}, 400)

    watchlist = list(employees.find(
        {"attrition_flag": 0, "attrition_risk": {"$exists": True}},
        {"_id": 0, "employee_id": 1, "department": 1, "job_role": 1,
         "job_level": 1, "compensation.monthly_income": 1,
         "attrition_risk": 1, "risk_tier": 1, "overtime": 1}
    ).sort("attrition_risk", -1).limit(10))

    tiers = list(employees.aggregate([
        {"$group": {"_id": "$risk_tier", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]))
    flagged = employees.count_documents(
        {"attrition_flag": 0, "predicted_attrition": True})
    model_meta = list(db[COLL_ML_MODELS].find(
        {}, {"_id": 0}).sort("trained_at", -1).limit(1))

    return mongo_json({
        "watchlist": watchlist,
        "risk_tiers": tiers,
        "flagged_leavers": flagged,
        "last_model": model_meta[0] if model_meta else None,
    })


# ===========================================================================
#  EMPLOYEES – search / browse
# ===========================================================================
@app.route("/api/employees")
@safe
def employees_list():
    page = int(request.args.get("page", 1))
    size = int(request.args.get("size", 20))
    dept  = request.args.get("dept", "")
    role  = request.args.get("role", "")
    attr  = request.args.get("attrition", "")

    filt = {}
    if dept:
        filt["dept_id"] = dept
    if role:
        filt["job_role"] = role
    if attr in ("0", "1"):
        filt["attrition_flag"] = int(attr)

    employees = db[COLL_EMPLOYEES]
    total = employees.count_documents(filt)
    docs = list(
        employees.find(filt, {
            "_id": 0, "employee_id": 1, "age": 1, "gender": 1,
            "department": 1, "job_role": 1, "job_level": 1,
            "compensation.monthly_income": 1, "attrition": 1,
            "overtime": 1, "attrition_risk": 1, "risk_tier": 1,
        })
        .sort("compensation.monthly_income", -1)
        .skip((page - 1) * size)
        .limit(size)
    )
    return mongo_json({"total": total, "page": page, "size": size, "data": docs})


@app.route("/api/employees/<employee_id>")
@safe
def employee_detail(employee_id):
    doc = db[COLL_EMPLOYEES].find_one(
        {"employee_id": employee_id}, {"_id": 0})
    if not doc:
        return mongo_json({"error": "Not found"}, 404)
    # join exit interview
    exit_doc = db[COLL_EXIT_INTERVIEWS].find_one(
        {"employee_id": employee_id}, {"_id": 0})
    doc["exit_interview"] = exit_doc
    return mongo_json(doc)


# ===========================================================================
#  PROJECTS
# ===========================================================================
@app.route("/api/projects")
@safe
def projects_list():
    docs = list(db[COLL_PROJECTS].find({}, {"_id": 0})
                .sort("member_count", -1))
    return mongo_json(docs)


# ===========================================================================
#  RUN
# ===========================================================================
if __name__ == "__main__":
    app.run(debug=True, port=5000)
