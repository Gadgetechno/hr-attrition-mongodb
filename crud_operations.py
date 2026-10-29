'''crud_operations.py
Unit II - MongoDB Basics and CRUD Operations, demonstrated with real data:
  * Databases / Collections / Documents: create, list, drop
  * BSON data types: ObjectId, Date, String, Int32, Double, Boolean,
                     Array, Embedded document, Decimal128, Timestamp, Null
  * Create : insert_one, insert_many
  * Read   : find, filters, operators ($gt, $in, $and, $or, $regex),
             projection, sort, limit, skip, count_documents, distinct
  * Update : update_one, update_many ($set, $inc, $push), upsert,
             find_one_and_update
  * Delete : delete_one, delete_many

Everything destructive happens inside a throwaway `crud_sandbox` collection
and a throwaway `temp_demo_db` database, both dropped at the end.
'''

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from bson import Decimal128
from bson.decimal128 import Decimal128 as D128  # noqa: F401  (import shown for teaching)
from pymongo import MongoClient

from config import (
    DB_NAME,
    MONGO_URI,
    COLL_EMPLOYEES,
    COLL_SANDBOX,
    banner,
)


def p(label: str, value) -> None:
    """Pretty-print one demo step."""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, default=str, indent=None)[:150]
    else:
        text = str(value)[:150]
    print(f"  {label:<46} {text}")


def bson_type_demo(db) -> None:
    """Every common BSON type in one document, then read back with $type."""
    banner("Unit II: BSON data types")
    doc = {
        "string_type":  "HR analytics",                          # String
        "int32_type":   42,                                      # 32-bit Integer
        "double_type":  5993.50,                                 # Double
        "boolean_type": True,                                    # Boolean
        "date_type":    datetime.now(timezone.utc),              # Date
        "null_type":    None,                                    # Null
        "array_type":   [1, 2, 3],                               # Array
        "embedded_doc": {"level": 2, "field": "Life Sciences"},  # Embedded document
        "decimal128_type": Decimal128(Decimal("19999.99")),      # Decimal128
        "objectid_type": None,  # ObjectId is set automatically as _id
    }
    sandbox = db[COLL_SANDBOX]
    result = sandbox.insert_one(doc)
    p("insert_one returned _id (ObjectId)", result.inserted_id)

    stored = sandbox.find_one({"_id": result.inserted_id})
    types = sandbox.aggregate([
        {"$match": {"_id": result.inserted_id}},
        {"$project": {
            "bson_types": {
                "$map": {
                    "input": {"$objectToArray": "$$ROOT"},
                    "in": {"k": "$$this.k", "t": {"$type": "$$this.v"}},
                }
            }
        }},
    ])
    for entry in list(types)[0]["bson_types"]:
        if entry["k"] != "_id":
            p(f"  {entry['k']}", entry["t"])
    p("_id auto-generated type", type(stored["_id"]).__name__)

    # $type query: find documents where a field has a specific BSON type
    p("count $type 'double' on double_type",
      sandbox.count_documents({"double_type": {"$type": "double"}}))
    sandbox.delete_many({})


def create_demo(db) -> None:
    banner("CREATE: insert_one / insert_many")
    sandbox = db[COLL_SANDBOX]
    one = sandbox.insert_one({
        "doc_type": "single", "note": "created by insert_one",
        "created_at": datetime.now(timezone.utc),
    })
    p("insert_one -> inserted_id", one.inserted_id)

    many = sandbox.insert_many([
        {"doc_type": "batch", "batch_no": i, "value": i * 10}
        for i in range(1, 6)
    ])
    p("insert_many -> inserted_ids", len(many.inserted_ids))
    p("documents in sandbox now", sandbox.count_documents({}))


def read_demo(db) -> None:
    banner("READ: find with filters, operators, projection, sort, pagination")
    employees = db[COLL_EMPLOYEES]

    p("find().limit(1) - full document keys",
      list(employees.find_one({}, {"engagement_history": 0}).keys()))

    # comparison operators
    p("$gt: income > 15000",
      employees.count_documents({"compensation.monthly_income": {"$gt": 15000}}))
    p("$in: dept in [SALES, HR]",
      employees.count_documents({"dept_id": {"$in": ["SALES", "HR"]}}))
    p("$and: overtime AND age >= 50",
      employees.count_documents({"$and": [
          {"overtime": True}, {"age": {"$gte": 50}}]}))
    p("$or: income < 2000 OR income > 18000",
      employees.count_documents({"$or": [
          {"compensation.monthly_income": {"$lt": 2000}},
          {"compensation.monthly_income": {"$gt": 18000}}]}))
    p("$regex: job_role starts with 'Research'",
      employees.count_documents({"job_role": {"$regex": "^Research"}}))

    # projection: include only some fields (nested projection works too)
    proj = {"_id": 0, "employee_id": 1, "job_role": 1,
            "compensation.monthly_income": 1}
    p("projection on one Sales Executive",
      employees.find_one({"job_role": "Sales Executive", "dept_id": "SALES"}, proj))

    # sort + limit + skip (pagination)
    page = list(employees.find({}, {"_id": 0, "employee_id": 1,
                                    "compensation.monthly_income": 1})
                .sort("compensation.monthly_income", -1)
                .skip(0).limit(3))
    for d in page:
        p(f"  top-paid {d['employee_id']}", d["compensation"]["monthly_income"])

    # count and distinct
    p("count_documents(attrition_flag=1)",
      employees.count_documents({"attrition_flag": 1}))
    p("distinct job roles", sorted(employees.distinct("job_role")))


def update_demo(db) -> None:
    banner("UPDATE: update_one / update_many / upsert / find_one_and_update")
    sandbox = db[COLL_SANDBOX]

    sandbox.insert_many([{"counter": i} for i in range(3)])
    res = sandbox.update_one({"counter": 1}, {"$set": {"status": "reviewed"}})
    p("update_one matched/modified", (res.matched_count, res.modified_count))

    res = sandbox.update_many({}, {"$inc": {"counter": 100}})
    p("update_many $inc all docs", res.modified_count)

    # upsert: update if exists, insert if not
    res = sandbox.update_one({"counter": 999},
                             {"$set": {"created_by_upsert": True}},
                             upsert=True)
    p("upsert inserted new _id", res.upserted_id is not None)

    # $push appends to an embedded array
    sandbox.update_one({"counter": 101}, {"$push": {"audit_log": "first touch"}})
    sandbox.update_one({"counter": 101}, {"$push": {"audit_log": "second touch"}})
    p("$push grew audit_log array",
      sandbox.find_one({"counter": 101})["audit_log"])

    updated = sandbox.find_one_and_update(
        {"counter": 102}, {"$set": {"flagged": True}},
        return_document=True)
    p("find_one_and_update returned doc", updated["flagged"])


def delete_demo(db) -> None:
    banner("DELETE: delete_one / delete_many")
    sandbox = db[COLL_SANDBOX]
    res = sandbox.delete_one({"counter": 999})
    p("delete_one removed", res.deleted_count)
    res = sandbox.delete_many({"counter": {"$gt": 100}})
    p("delete_many removed", res.deleted_count)
    p("sandbox docs left", sandbox.count_documents({}))


def create_drop_demo(client) -> None:
    banner("Creating and dropping databases / collections (Unit II)")
    temp = client["temp_demo_db"]
    temp["scratch"].insert_one({"demo": True})
    print(f"  databases now include temp_demo_db : "
          f"{'temp_demo_db' in client.list_database_names()}")
    print(f"  collections in temp_demo_db        : {temp.list_collection_names()}")
    temp["scratch"].drop()
    temp2 = client["temp_demo_db"]
    temp2["other"].insert_one({})
    temp2.drop_collection("other")
    client.drop_database("temp_demo_db")
    print(f"  after drop: temp_demo_db exists    : "
          f"{'temp_demo_db' in client.list_database_names()}")
    print(f"  sandbox dropped                    : ", end="")
    client[DB_NAME][COLL_SANDBOX].drop()
    print(COLL_SANDBOX not in client[DB_NAME].list_collection_names())


def main() -> None:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]
    banner(f"CRUD operations on database '{DB_NAME}'")
    print(f"  collections: {db.list_collection_names()}")

    bson_type_demo(db)
    create_demo(db)
    read_demo(db)
    update_demo(db)
    delete_demo(db)
    create_drop_demo(client)

    print("\nDone.")
    client.close()


if __name__ == "__main__":
    main()
