'''ml_model.py
Unit V - MongoDB Integration for AI-based Predictive Analytics.

Flow (everything starts from MongoDB - no CSV is touched here):
  1. READ      : PyMongo loads employee documents into pandas
  2. PREPARE   : flatten embedded documents, encode categoricals
  3. TRAIN     : stratified 80/20 split, RandomForest vs LogisticRegression
  4. EVALUATE  : accuracy / precision / recall / F1 / ROC-AUC / confusion matrix
  5. PUBLISH   : model metadata -> ml_models collection (a model registry),
                 per-employee risk scores written back to employees with bulk_write,
                 index on attrition_risk, then a "watchlist" query of the
                 current employees most likely to leave.
'''

from datetime import datetime, timezone

import numpy as np
import pandas as pd
from pymongo import MongoClient, UpdateOne
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, classification_report,
                             confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler

from config import DB_NAME, MONGO_URI, COLL_EMPLOYEES, COLL_ML_MODELS, banner

NUMERIC_FEATURES = [
    "age",
    "distance_from_home_km",
    "job_level",
    "compensation.monthly_income",
    "compensation.daily_rate",
    "compensation.hourly_rate",
    "compensation.monthly_rate",
    "compensation.percent_salary_hike",
    "compensation.stock_option_level",
    "satisfaction.environment",
    "satisfaction.job",
    "satisfaction.relationship",
    "satisfaction.work_life_balance",
    "satisfaction.job_involvement",
    "satisfaction.performance_rating",
    "satisfaction.overall_index",
    "career.total_working_years",
    "career.num_companies_worked",
    "career.years_at_company",
    "career.years_in_current_role",
    "career.years_since_last_promotion",
    "career.years_with_curr_manager",
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
    # 'attrition' string is redundant with the 0/1 label we train on
    "attrition": 0,
}


def load_dataframe(employees) -> pd.DataFrame:
    """Step 1: read from MongoDB into a flat DataFrame."""
    docs = list(employees.find({}, EXCLUDED_PROJECTION))
    df = pd.json_normalize(docs)
    print(f"  loaded {len(df)} employee documents from MongoDB")
    print(f"  flattened columns: {len(df.columns)}")
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Step 2: numeric passthrough + label-encoded categoricals."""
    X = df[NUMERIC_FEATURES].copy()
    X["overtime"] = df["overtime"].astype(int)
    for col in CATEGORICAL_FEATURES:
        X[f"{col}_enc"] = LabelEncoder().fit_transform(df[col].astype(str))
    return X


def evaluate(name: str, model, X_te, y_te) -> dict:
    preds = model.predict(X_te)
    proba = model.predict_proba(X_te)[:, 1]
    return {
        "model": model,
        "algorithm": name,
        "accuracy": round(float(accuracy_score(y_te, preds)) * 100, 2),
        "precision": round(float(precision_score(y_te, preds, zero_division=0)) * 100, 2),
        "recall": round(float(recall_score(y_te, preds, zero_division=0)) * 100, 2),
        "f1": round(float(f1_score(y_te, preds, zero_division=0)) * 100, 2),
        "roc_auc": round(float(roc_auc_score(y_te, proba)), 3),
        "preds": preds,
        "proba": proba,
    }


def main() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]
    employees = db[COLL_EMPLOYEES]
    if employees.count_documents({}) == 0:
        raise SystemExit("No employees found - run setup_database.py and ingest_data.py first")

    banner("Unit V: Attrition prediction - train, evaluate, publish to MongoDB")

    df = load_dataframe(employees)
    y = df["attrition_flag"].astype(int)
    X = build_features(df)
    feature_cols = list(X.columns)
    print(f"  features used   : {len(feature_cols)}")
    print(f"  class balance   : attrited={int(y.sum())} ({100 * y.mean():.1f}%), "
          f"retained={int((1 - y).sum())}")

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)
    print(f"  train/test rows : {len(X_tr)} / {len(X_te)} (stratified)")

    # ------------------------------------------------------------------
    # Step 3: two candidate models (class-weighted - the target is imbalanced)
    # ------------------------------------------------------------------
    candidates = {
        "RandomForestClassifier": RandomForestClassifier(
            n_estimators=300, random_state=42, n_jobs=-1, class_weight="balanced"),
        "LogisticRegression": Pipeline([
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced",
                                       random_state=42)),
        ]),
    }

    banner("Model comparison on the stratified hold-out set")
    results = {}
    for name, model in candidates.items():
        model.fit(X_tr, y_tr)
        results[name] = evaluate(name, model, X_te, y_te)
        r = results[name]
        print(f"  {name:<26} acc={r['accuracy']:>5}%  precision={r['precision']:>5}%  "
              f"recall={r['recall']:>5}%  F1={r['f1']:>5}%  ROC-AUC={r['roc_auc']:.3f}")

    best_name = max(results, key=lambda k: results[k]["f1"])
    best = results[best_name]
    print(f"\n  selected model (best F1): {best_name}")
    print("\n  classification report (selected model):")
    print(classification_report(y_te, best["preds"], target_names=["Retained", "Attrited"],
                                zero_division=0))
    cm = confusion_matrix(y_te, best["preds"], labels=[0, 1])
    print("  confusion matrix:            predicted")
    print("                        Retained  Attrited")
    print(f"    actual Retained   {cm[0][0]:>8}  {cm[0][1]:>8}")
    print(f"    actual Attrited   {cm[1][0]:>8}  {cm[1][1]:>8}")

    # feature importance / coefficient ranking
    if hasattr(best["model"], "feature_importances_"):
        scores = best["model"].feature_importances_
    else:
        scores = np.abs(best["model"].named_steps["clf"].coef_[0])
    top_features = sorted(zip(feature_cols, scores), key=lambda t: t[1], reverse=True)[:10]
    print("\n  top-10 drivers of predicted attrition:")
    for fname, score in top_features:
        print(f"    {fname:<38} {score:.4f}")

    # ------------------------------------------------------------------
    # Step 5a: model registry -> ml_models collection
    # ------------------------------------------------------------------
    db[COLL_ML_MODELS].insert_one({
        "model_name": "attrition_classifier",
        "algorithm": best_name,
        "selection_rule": "best F1 on stratified 20% hold-out",
        "trained_at": datetime.now(timezone.utc),
        "data_source": f"{DB_NAME}.{COLL_EMPLOYEES}",
        "train_rows": int(len(X_tr)), "test_rows": int(len(X_te)),
        "metrics": {k: results[k]["f1"] for k in results} | {"detail": {
            k: {m: results[k][m] for m in ("accuracy", "precision", "recall", "f1", "roc_auc")}
            for k in results}},
        "features": feature_cols,
        "top_features": [{"name": n, "importance": round(float(s), 4)}
                         for n, s in top_features],
    })
    print(f"\n  model registry: saved to {COLL_ML_MODELS} "
          f"({db[COLL_ML_MODELS].count_documents({})} registered model runs)")

    # ------------------------------------------------------------------
    # Step 5b: score every employee and write predictions back (bulk_write)
    # ------------------------------------------------------------------
    proba_all = best["model"].predict_proba(X)
    idx_of_1 = list(best["model"].classes_).index(1)
    risk = proba_all[:, idx_of_1]

    def tier(p: float) -> str:
        return "High" if p >= 0.7 else "Medium" if p >= 0.4 else "Low"

    ops = [
        UpdateOne(
            {"employee_number": int(num)},
            {"$set": {
                "attrition_risk": round(float(p), 4),
                "risk_tier": tier(p),
                "predicted_attrition": bool(p >= 0.5),
                "scored_by_model": best_name,
                "scored_at": datetime.now(timezone.utc),
            }})
        for num, p in zip(df["employee_number"], risk)
    ]
    bulk = employees.bulk_write(ops, ordered=False)
    print(f"  write-back    : {bulk.modified_count} employee documents updated "
          f"with attrition_risk / risk_tier")

    employees.create_index("attrition_risk")
    print("  index created : attrition_risk_1")

    # ------------------------------------------------------------------
    # Step 5c: the payoff query - current employees most likely to leave
    # ------------------------------------------------------------------
    banner("Watchlist: retained employees with the highest predicted risk")
    watchlist = list(employees.find(
        {"attrition_flag": 0,
         "attrition_risk": {"$exists": True}},
        {"_id": 0, "employee_id": 1, "department": 1, "job_role": 1,
         "job_level": 1, "compensation.monthly_income": 1,
         "attrition_risk": 1, "risk_tier": 1, "overtime": 1}
    ).sort("attrition_risk", -1).limit(10))
    print(f"  {'employee':<10}{'department':<26}{'role':<26}{'income':>7}  {'risk':>5}  tier")
    for w in watchlist:
        print(f"  {w['employee_id']:<10}{w['department']:<26}{w['job_role']:<26}"
              f"{w['compensation']['monthly_income']:>7.0f}  {w['attrition_risk']:>5.2f}  {w['risk_tier']}")

    tiers = list(employees.aggregate([
        {"$group": {"_id": "$risk_tier", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]))
    print("\n  workforce risk distribution: "
          + ", ".join(f"{t['_id']}: {t['n']}" for t in tiers))
    flagged = employees.count_documents(
        {"attrition_flag": 0, "predicted_attrition": True})
    print(f"  retained employees flagged as likely leavers by the model: {flagged}")

    print("\nDone.")
    client.close()


if __name__ == "__main__":
    main()
