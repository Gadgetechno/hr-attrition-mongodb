# HR Attrition Analytics — MongoDB Project

> A full-stack demonstration of MongoDB's capabilities applied to real-world HR data.  
> Covers every major MongoDB concept from schema design through aggregation pipelines, indexing, and ML integration — all visible through an interactive web dashboard.

---

## Table of Contents

1. [What This Project Is](#1-what-this-project-is)
2. [Quick Start](#2-quick-start)
3. [Project Structure](#3-project-structure)
4. [The Dataset](#4-the-dataset)
5. [MongoDB Schema Design](#5-mongodb-schema-design)
6. [Collections Reference](#6-collections-reference)
7. [Document Schemas (with examples)](#7-document-schemas-with-examples)
8. [BSON Types Used](#8-bson-types-used)
9. [CRUD Operations](#9-crud-operations)
10. [Aggregation Pipelines](#10-aggregation-pipelines)
11. [Indexing Strategy](#11-indexing-strategy)
12. [Machine Learning Integration](#12-machine-learning-integration)
13. [Flask REST API](#13-flask-rest-api)
14. [Web Dashboard — Sections Guide](#14-web-dashboard--sections-guide)
15. [AI Query Optimizer](#15-ai-query-optimizer)
16. [MongoDB Concepts Covered](#16-mongodb-concepts-covered)

---

## 1. What This Project Is

This project uses the **IBM HR Attrition dataset** (1,470 employees) as a vehicle to demonstrate every significant MongoDB feature in a working, production-style application.

### The Data Story
IBM wants to understand **why employees leave**. The data contains demographics, compensation, satisfaction scores, career history, and whether each employee left (`attrition = Yes`). The goal is to:

- Store this data in MongoDB with a thoughtful schema
- Explore it with aggregation pipelines
- Speed queries with the right indexes
- Train an ML model to predict future attrition risk
- Write risk scores *back* into MongoDB and query the watchlist

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Database | MongoDB Community / Atlas |
| Python driver | PyMongo 4.6+ |
| ML | scikit-learn (RandomForest, LogisticRegression) |
| Data wrangling | pandas, numpy |
| Web backend | Flask 3 |
| Frontend | Vanilla HTML / CSS / JavaScript |

---

## 2. Quick Start

### Prerequisites
- Python 3.9+
- MongoDB running on `localhost:27017` (or set `MONGO_URI` env variable)
- The CSV file in `data/IBM_HR_Attrition_Enhanced.csv`

### Install dependencies
```bash
pip install -r requirements.txt
```

### Run in order
```bash
# Step 1 — Create database, collections, and $jsonSchema validators
python setup_database.py

# Step 2 — Load CSV → MongoDB (embedding, referencing, BSON types)
python ingest_data.py

# Step 3 — Train ML model and write risk scores back to MongoDB
python ml_model.py

# Step 4 — Start the interactive web dashboard
python app.py
# → Open http://localhost:5000
```

### Connect to Atlas instead of local
```bash
set MONGO_URI=mongodb+srv://<user>:<pass>@cluster0.xxxxx.mongodb.net/
python app.py
```

---

## 3. Project Structure

```
hr_attrition_mongodb/
│
├── config.py               ← Shared constants (URI, DB name, collection names)
├── setup_database.py       ← Creates collections + $jsonSchema validators
├── ingest_data.py          ← Loads CSV data into MongoDB
├── crud_operations.py      ← CRUD demos (insert/find/update/delete)
├── aggregations.py         ← 9 aggregation pipelines (the analytics core)
├── indexing_demo.py        ← explain() before/after index creation
├── ml_model.py             ← RandomForest training + bulk_write risk scores
├── ai_query_optimizer.py   ← Workload analyzer & index advisor
│
├── app.py                  ← Flask REST API (bridges frontend ↔ MongoDB)
├── templates/
│   └── index.html          ← Single-page dashboard (8 tabs)
├── static/
│   ├── style.css           ← Design system (warm dark theme)
│   └── app.js              ← All dashboard JavaScript
│
├── data/
│   └── IBM_HR_Attrition_Enhanced.csv
└── requirements.txt
```

### What each file does

| File | Responsibility |
|------|---------------|
| `config.py` | Single source of truth for `MONGO_URI`, `DB_NAME`, all collection name constants, and dept/role code mappings |
| `setup_database.py` | Drops + recreates `hr_analytics` db, creates each collection with `$jsonSchema` validation, seeds departments/job-role reference documents |
| `ingest_data.py` | Reads CSV, transforms rows into nested MongoDB documents (embedding + referencing), inserts in bulk |
| `crud_operations.py` | Demonstrates all four CRUD operations with real operators (`$gt`, `$in`, `$regex`, `$set`, `$push`, upsert, etc.) |
| `aggregations.py` | Nine standalone aggregation pipelines covering every stage type in the syllabus |
| `indexing_demo.py` | Runs `explain("executionStats")` before and after three different index creation scenarios |
| `ml_model.py` | Reads employees from MongoDB → pandas, trains two models, evaluates them, writes risk scores back via `bulk_write`, creates a `ml_models` registry entry |
| `ai_query_optimizer.py` | Analyses query workload patterns and recommends optimal indexes following the ESR rule |
| `app.py` | Flask server that exposes all of the above as REST endpoints consumed by the frontend |

---

## 4. The Dataset

**Source:** IBM HR Analytics Employee Attrition & Performance dataset  
**Records:** 1,470 employees  
**Attrition rate:** ~16% (237 employees left)

### Key fields

| Field | Type | Description |
|-------|------|-------------|
| `Age` | int | 18–60 |
| `Attrition` | string | `"Yes"` / `"No"` — the target variable |
| `Department` | string | Sales, Research & Development, Human Resources |
| `JobRole` | string | 9 unique roles |
| `JobLevel` | int | 1 (entry) – 5 (executive) |
| `MonthlyIncome` | float | $1,009 – $19,999 |
| `OverTime` | bool | Whether the employee works overtime |
| `JobSatisfaction` | int | 1 (low) – 4 (high) |
| `YearsAtCompany` | int | Tenure |
| `TotalWorkingYears` | int | Full career experience |

---

## 5. MongoDB Schema Design

The project deliberately demonstrates **three relationship patterns** from Unit III side by side.

### Pattern 1 — Embedding (one-to-one / one-to-few)
Used for data that is always retrieved together and belongs to one entity.

```
employee
  └── compensation   { monthly_income, daily_rate, hourly_rate, … }
  └── satisfaction   { environment, job, relationship, work_life_balance, … }
  └── career         { years_at_company, total_working_years, years_since_last_promotion, … }
  └── education      { level, field }
```

**Why embed?** These sub-objects are always read with the employee. There is no unbounded growth. Embedding avoids extra round-trips.

### Pattern 2 — Referencing (one-to-many via foreign key)
Used for shared lookup data that many employees point to.

```
employee.dept_id    → departments.dept_id
employee.job_role_id → job_roles.role_id
```

**Why reference?** Department/role data is shared and rarely changes. If the department name changes, we update one document, not 1,470.

### Pattern 3 — Many-to-Many (array of references)
Used for projects, where one employee works on many projects and one project has many employees.

```
employee.project_ids = ["PROJ_001", "PROJ_003"]   → projects collection
```

### Pattern 4 — Embedded arrays (one-to-many inside document)
Used for engagement history — each employee has a small, bounded list of quarterly scores.

```json
"engagement_history": [
  { "quarter": "2023-Q1", "score": 3.8 },
  { "quarter": "2023-Q2", "score": 3.5 }
]
```

`$unwind` then lets us aggregate across all quarters across all employees.

---

## 6. Collections Reference

| Collection | Documents | Purpose |
|-----------|-----------|---------|
| `employees` | 1,470 | Main collection — one doc per employee |
| `departments` | 3 | Reference docs: SALES, RND, HR |
| `job_roles` | 9 | Reference docs: one per job title |
| `projects` | ~12 | Many-to-many target collection |
| `exit_interviews` | ~237 | Text-searchable exit comments (attrited employees) |
| `ml_models` | grows | Model registry — one doc per training run |
| `crud_sandbox` | temporary | Used only by CRUD demos, cleaned up after each run |
| `prediction_log` | grows | Audit trail of every live prediction from the dashboard |

---

## 7. Document Schemas (with examples)

### `employees` — the core document

```json
{
  "_id": ObjectId("..."),
  "employee_number": 1,
  "employee_id": "EMP0001",
  "age": 41,
  "gender": "Female",
  "marital_status": "Single",
  "business_travel": "Travel_Rarely",
  "distance_from_home_km": 1,
  "dept_id": "SALES",
  "department": "Sales",
  "job_role_id": "SALES_EXECUTIVE",
  "job_role": "Sales Executive",
  "job_level": 2,
  "overtime": true,
  "attrition": "Yes",
  "attrition_flag": 1,
  "hire_date": ISODate("2019-03-14"),
  "age_group": "36-45",

  "education": {
    "level": 2,
    "field": "Life Sciences"
  },

  "compensation": {
    "monthly_income": 5993.0,
    "daily_rate": 1102,
    "hourly_rate": 94,
    "monthly_rate": 19479,
    "percent_salary_hike": 11,
    "stock_option_level": 0,
    "income_bracket": "5k-10k"
  },

  "satisfaction": {
    "environment": 2,
    "job": 4,
    "relationship": 1,
    "work_life_balance": 1,
    "job_involvement": 3,
    "performance_rating": 3,
    "overall_index": 2.33
  },

  "career": {
    "total_working_years": 8,
    "num_companies_worked": 8,
    "years_at_company": 6,
    "years_in_current_role": 4,
    "years_since_last_promotion": 0,
    "years_with_curr_manager": 5,
    "training_times_last_year": 0,
    "tenure_group": "4-6 yrs"
  },

  "project_ids": ["PROJ_003", "PROJ_007"],

  "engagement_history": [
    { "quarter": "2023-Q1", "score": 3.2, "responded": true },
    { "quarter": "2023-Q2", "score": 2.8, "responded": true }
  ],

  "attrition_risk": 0.8243,
  "risk_tier": "High",
  "predicted_attrition": true
}
```

### `departments` — reference document

```json
{
  "_id": ObjectId("..."),
  "dept_id": "SALES",
  "name": "Sales",
  "head_count_target": 350,
  "location": "Chicago"
}
```

### `exit_interviews` — text-searchable

```json
{
  "_id": ObjectId("..."),
  "employee_id": "EMP0001",
  "department": "Sales",
  "exit_date": ISODate("2023-06-30"),
  "reason": "Better opportunity",
  "theme_tags": ["compensation", "growth"],
  "comments": "I felt the overtime demands were unsustainable and compensation did not reflect the workload."
}
```

### `ml_models` — model registry

```json
{
  "_id": ObjectId("..."),
  "algorithm": "RandomForestClassifier",
  "trained_at": ISODate("2024-01-15T10:30:00Z"),
  "features": ["age", "compensation.monthly_income", "overtime", ...],
  "top_features": [
    { "name": "career.total_working_years", "importance": 0.142 },
    { "name": "compensation.monthly_income", "importance": 0.118 }
  ],
  "metrics": {
    "accuracy": 0.88,
    "f1": 0.76,
    "roc_auc": 0.91
  },
  "selection_rule": "highest_roc_auc",
  "n_employees_scored": 1470
}
```

### `prediction_log` — audit trail

```json
{
  "source": "web_tester",
  "attrition_risk": 0.7812,
  "risk_tier": "High",
  "predicted_at": ISODate("2024-01-15T11:05:00Z"),
  "inputs": { "age": 25, "overtime": true, ... }
}
```

---

## 8. BSON Types Used

MongoDB's BSON format is richer than JSON. This project uses all of these:

| BSON Type | Where used | Example |
|-----------|-----------|---------|
| `objectId` | Every `_id` field | `ObjectId("507f1f77...")` |
| `string` | `employee_id`, `gender`, `job_role`, `attrition` | `"EMP0001"` |
| `int32` | `age`, `job_level`, `attrition_flag` | `41` |
| `double` | `compensation.monthly_income`, `attrition_risk` | `5993.0` |
| `bool` | `overtime` | `true` |
| `date` | `hire_date`, `trained_at`, `predicted_at` | `ISODate(...)` |
| `array` | `project_ids`, `engagement_history`, `theme_tags` | `["PROJ_001", "PROJ_003"]` |
| `object` | `compensation`, `satisfaction`, `career`, `education` | `{ "monthly_income": 5993.0, ... }` |
| `null` | Optional fields not present | `null` |
| `decimal128` | Demo in BSON Types tab | `Decimal128("19999.99")` |

The **BSON Types** tab in the dashboard inserts a document containing every type, runs `{ $type: "$$this.v" }` via aggregation to inspect each field's stored type, then deletes the document.

---

## 9. CRUD Operations

All operations are in `crud_operations.py` and exposed via `/api/crud/*`.

### CREATE
```python
# insert_one — returns InsertOneResult with inserted_id
result = employees.insert_one({ "employee_id": "EMP9999", ... })

# insert_many — returns InsertManyResult with list of ids
result = employees.insert_many([{...}, {...}, {...}])
```

### READ — operators demonstrated
```python
# Comparison
employees.find({"compensation.monthly_income": {"$gt": 15000}})

# $in — match multiple values
employees.find({"dept_id": {"$in": ["SALES", "HR"]}})

# $and with multiple conditions
employees.find({"$and": [{"overtime": True}, {"age": {"$gte": 50}}]})

# $regex — pattern matching
employees.find({"job_role": {"$regex": "^Research"}})

# distinct — unique values
employees.distinct("job_role")

# Projection + sort + skip + limit (pagination)
employees.find({}, {"_id": 0, "employee_id": 1, "job_role": 1}) \
         .sort("compensation.monthly_income", -1) \
         .skip(0).limit(25)
```

### UPDATE
```python
# $set — update specific fields
employees.update_one({"employee_id": "EMP0001"}, {"$set": {"status": "reviewed"}})

# $inc — increment numeric field
employees.update_many({}, {"$inc": {"compensation.monthly_income": 200}})

# $push — append to an array
employees.update_one({"employee_id": "EMP0001"}, {"$push": {"audit_log": "reviewed"}})

# upsert — insert if not found
employees.update_one({"employee_id": "EMP9999"}, {"$set": {...}}, upsert=True)

# find_one_and_update — atomic read-modify
employees.find_one_and_update({"employee_id": "EMP0001"}, {"$set": {"flagged": True}}, return_document=True)
```

### DELETE
```python
employees.delete_one({"counter": 0})              # removes first match
employees.delete_many({"counter": {"$gt": 2}})    # removes all matches
```

---

## 10. Aggregation Pipelines

All nine pipelines are in `aggregations.py`. Each demonstrates specific aggregation stages.

### Pipeline 1 — Attrition by Department
**Stages:** `$group` → `$project` → `$lookup` → `$unwind` → `$sort`

Calculates attrition rate per department using the `$avg` of `attrition_flag` (0/1) trick, then enriches with department names via `$lookup`.

```javascript
// The $avg trick: avg(0 or 1) = rate
{ "$avg": "$attrition_flag" }   // → 0.166 = 16.6% attrition rate
```

### Pipeline 2 — Attrition by Job Level
**Stages:** `$group` → `$project` → `$sort`

Shows whether seniority affects attrition. Entry-level (1) consistently shows the highest rate.

### Pipeline 3 — Overtime Impact
**Stages:** `$group` → `$project` → `$addFields` → `$cond` → `$sort`

Compares attrition rates between employees who work overtime and those who do not. `$cond` converts the boolean `overtime` field into a human-readable label.

### Pipeline 4 — Income Distribution
**Stages:** `$bucket`

Groups employees into predefined salary ranges ($0-3k, 3k-6k, 6k-10k, 10k-15k, 15k-20k, 20k+) to see how compensation correlates with attrition.

```javascript
{ "$bucket": {
    "groupBy": "$compensation.monthly_income",
    "boundaries": [0, 3000, 6000, 10000, 15000, 20000],
    "default": "20000+"
}}
```

### Pipeline 5 — $facet Dashboard
**Stages:** `$facet` (5 sub-pipelines in ONE query)

The most powerful pipeline. A single MongoDB round-trip returns:
- Overall totals
- Attrition by department
- Income statistics (min/max/avg)
- Business travel impact
- Top 5 highest-risk job roles

```javascript
{ "$facet": {
    "totals":        [...],
    "by_department": [...],
    "income_stats":  [...],
    "travel_impact": [...],
    "top_risk_roles": [...]
}}
```

### Pipeline 6 — Engagement by Quarter
**Stages:** `$unwind` → `$group` → `$project` → `$sort`

`$unwind` explodes the `engagement_history` embedded array so we can group across all employees by quarter. Shows whether company engagement improved over time.

### Pipeline 7 — Top 3 Earners per Department
**Stages:** `$sort` → `$group` with `$push` → `$project` with `$slice`

Sorts all employees, groups by department accumulating them into arrays via `$push`, then uses `$slice` to keep only the top 3.

### Pipeline 8 — Age Bands
**Stages:** `$match` → `$bucketAuto`

Unlike `$bucket` (manual boundaries), `$bucketAuto` automatically finds 4 equal-frequency age ranges. Useful when you don't know the data distribution in advance.

### Pipeline 9 — Exit Interview Text Search
**Stages:** `$match` with `$text` → `$group` → `$sort`

Uses MongoDB's full-text search index on `exit_interviews.comments` to find exits matching keywords like `"overtime"`, `"burnout"`, `"hours"`, then groups results by department.

```javascript
// Requires a text index:
exits.create_index([("comments", TEXT)])

// Then:
{ "$match": { "$text": { "$search": "overtime burnout" } } }
```

---

## 11. Indexing Strategy

Implemented in `indexing_demo.py`, demonstrated live in the **Indexing** tab.

### The three scenarios

#### Scenario 1 — Single Field Index
```python
# Query: find employees earning over $12,000
filter = {"compensation.monthly_income": {"$gt": 12000}}

# BEFORE: MongoDB scans ALL 1,470 documents (COLLSCAN)
# AFTER:  MongoDB walks the B-tree index (IXSCAN), examines only matching entries
employees.create_index("compensation.monthly_income")
```

#### Scenario 2 — Compound Index (ESR Rule)
```python
# Query: female employees on overtime, sorted by age descending
# ESR: Equality → Sort → Range
filter = {"overtime": True, "gender": "Female"}
sort  = [("age", -1)]

# Index follows the ESR rule:
employees.create_index([("overtime", 1), ("gender", 1), ("age", -1)])
# This index also satisfies the sort without a separate in-memory sort step
```

#### Scenario 3 — Covered Query
```python
# Query: dept_id + attrition_flag only — no need to load documents!
projection = {"_id": 0, "dept_id": 1, "attrition_flag": 1}

employees.create_index([("dept_id", 1), ("attrition_flag", 1)])
# A covered query: MongoDB answers entirely from the index.
# docsExamined = 0 in explain() output
```

### Reading `explain()` output

```
BEFORE:  COLLSCAN → FETCH          (reads every document)
AFTER:   IXSCAN → FETCH            (reads only index entries, then matching docs)
AFTER:   IXSCAN                    (covered — no FETCH needed at all)

Key metrics to watch:
  totalKeysExamined  ← how many index entries were read
  totalDocsExamined  ← how many full documents were loaded (0 = covered!)
  executionTimeMillis ← wall-clock time
```

---

## 12. Machine Learning Integration

**File:** `ml_model.py`  
**Dashboard tab:** ML Predictions → Steps 1, 2, 3

### The complete ML pipeline

```
MongoDB employees collection
        ↓  (PyMongo → pandas via json_normalize)
Feature engineering (flatten embedded docs, LabelEncode categoricals)
        ↓
Stratified 80/20 train-test split
        ↓
Train RandomForestClassifier + LogisticRegression (with pipelines)
        ↓
Evaluate: accuracy / F1 / precision / recall / ROC-AUC / confusion matrix
        ↓  (pick best model by ROC-AUC)
Publish results back to MongoDB:
  • ml_models collection ← model metadata + top feature importances
  • employees collection  ← attrition_risk (0-1), risk_tier, predicted_attrition
        ↓  (via bulk_write UpdateOne operations — single round trip)
Create index on attrition_risk
        ↓
Watchlist query: retained employees sorted by risk descending
```

### Features used (29 total)

**Numeric (23):**
```
age, distance_from_home_km, job_level,
compensation.monthly_income, daily_rate, hourly_rate, monthly_rate,
percent_salary_hike, stock_option_level,
satisfaction.environment, job, relationship, work_life_balance,
job_involvement, performance_rating, overall_index,
career.total_working_years, num_companies_worked, years_at_company,
years_in_current_role, years_since_last_promotion,
years_with_curr_manager, training_times_last_year
```

**Categorical (6, label-encoded):**
```
gender, marital_status, business_travel, department, job_role, education.field
```

**Boolean (1):**
```
overtime  (converted to 0/1)
```

### Risk tiers

| Tier | Probability threshold | Action |
|------|----------------------|--------|
| High | ≥ 70% | Immediate intervention |
| Medium | 40% – 69% | Monitor closely |
| Low | < 40% | Normal |

### `bulk_write` — how risk scores are written back

```python
# Build one UpdateOne operation per employee
operations = [
    UpdateOne(
        {"employee_id": emp_id},
        {"$set": {
            "attrition_risk": float(proba),
            "risk_tier": tier,
            "predicted_attrition": proba >= 0.5
        }}
    )
    for emp_id, proba, tier in zip(ids, probabilities, tiers)
]

# Send them all in a single round trip
result = employees.bulk_write(operations, ordered=False)
# result.modified_count == 1470
```

### Live prediction from the dashboard (Step 2)

When you click **Predict Attrition Risk** in the dashboard:
1. JavaScript reads all 29 form fields
2. `POST /api/ml/predict` is called with the JSON body
3. Flask calls `get_model()` — trains on first call, returns cache on subsequent calls
4. The trained model runs `predict_proba()` on the single-row DataFrame
5. Result (`risk_pct`, `risk_tier`, `top_drivers`) is returned as JSON
6. The prediction + inputs are saved to `prediction_log` in MongoDB
7. The dashboard renders the result card with an animated risk gauge

---

## 13. Flask REST API

**File:** `app.py`

All routes follow the pattern: read from MongoDB → return JSON. The `MongoEncoder` class handles serialisation of `ObjectId`, `datetime`, and `Decimal128`.

### Full endpoint list

| Method | Endpoint | What it does |
|--------|----------|-------------|
| `GET` | `/` | Serves `index.html` |
| `GET` | `/api/health` | `server_info()`, `list_database_names()`, document counts |
| `GET` | `/api/overview` | Per-collection document count + sample |
| `POST` | `/api/bson-types` | Insert BSON doc, inspect with `$type`, delete |
| `POST` | `/api/crud/create` | `insert_one` + `insert_many` demo |
| `GET` | `/api/crud/read` | `find` with `$gt`, `$in`, `$and`, `$regex`, `distinct` |
| `POST` | `/api/crud/update` | `update_one/many`, `$set`, `$inc`, `$push`, upsert |
| `POST` | `/api/crud/delete` | `delete_one`, `delete_many` |
| `GET` | `/api/aggregations/by-department` | Pipeline 1 |
| `GET` | `/api/aggregations/by-job-level` | Pipeline 2 |
| `GET` | `/api/aggregations/overtime-impact` | Pipeline 3 |
| `GET` | `/api/aggregations/income-distribution` | Pipeline 4 |
| `GET` | `/api/aggregations/dashboard-facet` | Pipeline 5 (`$facet`) |
| `GET` | `/api/aggregations/engagement-by-quarter` | Pipeline 6 |
| `GET` | `/api/aggregations/top-earners` | Pipeline 7 |
| `GET` | `/api/aggregations/age-bands` | Pipeline 8 |
| `GET` | `/api/aggregations/exit-text-search?q=...` | Pipeline 9 (`$text`) |
| `GET` | `/api/indexing/explain` | `explain()` before/after 3 index scenarios |
| `GET` | `/api/indexing/inventory` | `index_information()` for all collections |
| `POST` | `/api/ml/train` | Train RandomForest from MongoDB, cache in memory |
| `GET` | `/api/ml/model-info` | Return cached model metrics + feature importances |
| `POST` | `/api/ml/predict` | Run single prediction, log to `prediction_log` |
| `GET` | `/api/ml/prediction-log` | Last 20 predictions from MongoDB |
| `GET` | `/api/ml/watchlist` | Top 10 at-risk retained employees |
| `GET` | `/api/employees` | Paginated employee list with filters |
| `GET` | `/api/employees/<id>` | Single employee with exit interview join |
| `GET` | `/api/projects` | All projects |

---

## 14. Web Dashboard — Sections Guide

Open **http://localhost:5000** after running `python app.py`.

### 📊 Dashboard (Overview tab)
Auto-loads 6 charts from aggregation pipelines the moment you open the page:
- **Stat cards** — live document counts from `count_documents()`
- **Attrition by Department** — Pipeline 1 result as bar chart
- **Income Distribution** — Pipeline 4 `$bucket` result
- **Overtime Impact** — Pipeline 3 cohort comparison cards
- **Engagement by Quarter** — Pipeline 6 `$unwind` result
- **Top Risk Roles** — Pipeline 5 `$facet` sub-result
- **Attrition by Job Level** — Pipeline 2 result

### 👥 Employees tab
- **Paginated table** — 25 per page, `find().sort().skip().limit()`
- **Filters** — Department, Attrition status, Role text search
- **Click any row** — Opens a modal with full employee detail + exit interview (two-collection join)

### 📁 Projects tab
- Displays the `projects` collection — demonstrates the many-to-many referencing pattern
- Shows project name, department, member count, budget, start date

### 🔢 BSON Types tab
- Click **Run BSON Type Demo**
- Inserts a document with 9 BSON types, uses `$type` aggregation to inspect them, deletes the document
- Shows the actual type names MongoDB stores internally

### ✏️ CRUD Ops tab
Four buttons, each triggering a live MongoDB operation:
- **Create** — `insert_one` + `insert_many` into `crud_sandbox`
- **Read** — `find` with 5 different query operators on `employees`
- **Update** — `$set`, `$inc`, `$push`, upsert, `find_one_and_update`
- **Delete** — `delete_one` and `delete_many`

### ⚙️ Aggregations tab
Nine individual pipeline runners. Each has a **Run** button that executes the pipeline live and shows the raw JSON result. See section 10 for what each pipeline does.

### ⚡ Indexing tab
- **Run Explain Demo** — Creates three indexes and shows `explain()` output in side-by-side BEFORE / AFTER cards. Watch COLLSCAN flip to IXSCAN.
- **Load Inventory** — Shows `index_information()` for every collection.

### 🤖 ML Predictions tab

**Step 1 — Train the Model**
- Click **Train Model from MongoDB**
- Flask reads all 1,470 employees directly from MongoDB into pandas
- Trains RandomForest with 200 trees, stratified 80/20 split
- Shows Accuracy, F1, ROC-AUC and top feature importances

**Step 2 — Predict Attrition Risk**
- Fill in 29 employee attributes (grouped: Demographics, Job, Compensation, Satisfaction, Career)
- Use **High-Risk Profile** / **Low-Risk Profile** buttons to auto-fill example profiles
- Click **Predict** — model runs `predict_proba()`, result is displayed with:
  - Risk percentage and animated gauge bar
  - Risk tier (High / Medium / Low) with colour coding
  - Top feature importance bars
  - Automatic save to `prediction_log` in MongoDB

**Step 3 — Attrition Risk Watchlist**
- Shows the top 10 retained employees (`attrition_flag = 0`) with the highest predicted risk
- Risk scores were written by `ml_model.py` via `bulk_write`
- Includes a tier distribution summary (High / Medium / Low counts)

**Prediction Audit Log**
- Loads the `prediction_log` collection
- Shows timestamp, risk score, tier for every prediction made from the dashboard

---

## 15. AI Query Optimizer

**File:** `ai_query_optimizer.py`

A standalone tool that analyses actual query patterns and recommends indexes. It follows the **ESR Rule** (Equality → Sort → Range):

1. **Equality fields** go first in a compound index (highest cardinality reduces the set the most)
2. **Sort fields** go in the middle (the index can satisfy `sort` without an in-memory step)
3. **Range fields** go last (range predicates can still use the index for filtering)

```python
# Example: a query like
{ "dept_id": "SALES", "age": {"$gte": 30}, "sort": "monthly_income" }

# ESR recommendation:
create_index([("dept_id", 1), ("compensation.monthly_income", 1), ("age", 1)])
#              ↑ equality        ↑ sort                              ↑ range
```

---

## 16. MongoDB Concepts Covered

| Unit | Concept | Where in project |
|------|---------|-----------------|
| **I** | Server connection, `server_info()`, lazy database creation | `setup_database.py`, `/api/health` |
| **I** | Connection pooling | `MongoClient` reused across all Flask requests |
| **II** | Databases, Collections, Documents | All files |
| **II** | BSON types | `crud_operations.py`, BSON Types tab |
| **II** | `insert_one`, `insert_many` | `crud_operations.py`, CREATE demo |
| **II** | `find`, `$gt`, `$in`, `$and`, `$regex`, `distinct` | `crud_operations.py`, READ demo |
| **II** | `update_one/many`, `$set`, `$inc`, `$push`, upsert | `crud_operations.py`, UPDATE demo |
| **II** | `delete_one`, `delete_many` | `crud_operations.py`, DELETE demo |
| **III** | `$jsonSchema` validation | `setup_database.py` |
| **III** | Embedding (1:1, 1:few) | `compensation`, `satisfaction`, `career` sub-docs |
| **III** | Referencing (1:N) | `dept_id` → `departments`, `job_role_id` → `job_roles` |
| **III** | Many-to-many | `project_ids` array → `projects` collection |
| **III** | Denormalization | `department`, `job_role` fields copied into employee doc |
| **IV** | `$group`, `$project`, `$sort`, `$match`, `$limit` | All pipelines |
| **IV** | `$lookup` (join) | Pipeline 1 |
| **IV** | `$unwind` | Pipeline 6 |
| **IV** | `$bucket` | Pipeline 4 |
| **IV** | `$bucketAuto` | Pipeline 8 |
| **IV** | `$facet` | Pipeline 5 |
| **IV** | `$addFields`, `$cond` | Pipeline 3 |
| **IV** | `$push`, `$slice` | Pipeline 7 |
| **IV** | `$text` full-text search | Pipeline 9 |
| **IV** | Single field index | `indexing_demo.py`, Scenario 1 |
| **IV** | Compound index + ESR rule | `indexing_demo.py`, Scenario 2 |
| **IV** | Covered query | `indexing_demo.py`, Scenario 3 |
| **IV** | `explain("executionStats")` | `indexing_demo.py`, `/api/indexing/explain` |
| **V** | Read data from MongoDB into pandas | `ml_model.py` |
| **V** | Train ML model | `ml_model.py` (RandomForest + LogisticRegression) |
| **V** | Write predictions back to MongoDB | `bulk_write` in `ml_model.py` |
| **V** | Model registry in MongoDB | `ml_models` collection |
| **V** | Live prediction logging | `prediction_log` collection, `/api/ml/predict` |
| **V** | Index on ML output field | `attrition_risk` index for watchlist sort |

---

## Requirements

```
pymongo>=4.6
pandas>=2.0
scikit-learn>=1.3
flask>=3.0
numpy>=1.24
```

Install: `pip install -r requirements.txt`

---

*Dataset source: IBM HR Analytics Employee Attrition & Performance (Kaggle). Enhanced with synthetic engagement history, exit interviews, and project assignments for demonstration purposes.*
# hr-attrition-mongodb
