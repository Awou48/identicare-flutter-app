from __future__ import annotations

import argparse
import sys

from pymongo import MongoClient
from pymongo.errors import CollectionInvalid, OperationFailure, ServerSelectionTimeoutError

from app.config import get_settings
from app.db_schema import COLLECTIONS, INDEXES, VALIDATORS


def ensure_collection(db, name: str) -> str:
    """Create the collection if absent; either way apply the current validator."""
    validator = {"$jsonSchema": VALIDATORS[name]}
    created = False
    try:
        db.create_collection(name)
        created = True
    except CollectionInvalid:
        pass

    db.command(
        {
            "collMod": name,
            "validator": validator,
            "validationLevel": "moderate",
            "validationAction": "error",
        }
    )
    return "created" if created else "exists"


def ensure_indexes(db, name: str) -> tuple[int, list[str]]:
    """Create indexes. Reports conflicts rather than silently leaving them wrong."""
    models = INDEXES.get(name, [])
    if not models:
        return 0, []

    problems: list[str] = []
    try:
        db[name].create_indexes(models)
        return len(models), problems
    except OperationFailure:
        made = 0
        for model in models:
            try:
                db[name].create_indexes([model])
                made += 1
            except OperationFailure as exc:
                idx_name = model.document.get("name", "?")
                problems.append(f"{name}.{idx_name}: {exc.details.get('errmsg', exc)}")
        return made, problems


def verify_partial_ttl(db) -> bool:
    """The one index whose misconfiguration silently destroys the audit log."""
    for idx in db["verification_sessions"].list_indexes():
        if idx.get("name") != "ttl_abandoned_only":
            continue
        has_ttl = "expireAfterSeconds" in idx
        pfe = idx.get("partialFilterExpression")
        ok = has_ttl and pfe == {"status": "created"}
        if ok:
            print("    [+] TTL is partial (status='created') - completed sessions are safe")
        else:
            print(f"    [!] TTL index is WRONG: expireAfterSeconds={has_ttl} pfe={pfe}")
            print("        A non-partial TTL here deletes committed sessions, which are")
            print("        the permanent verification audit log. Drop and re-run.")
        return ok
    print("    [!] ttl_abandoned_only index missing entirely")
    return False


def check_models(settings) -> None:
    """Face models are downloaded manually; fail loudly rather than at request time."""
    missing = [p for p in (settings.face_det_model, settings.face_rec_model) if not p.exists()]
    if not missing:
        print("[+] Face ONNX models present.")
        return
    print()
    print("[!] Face models missing (needed in Step 3, not for the schema):")
    for path in missing:
        print(f"      {path}")
    print("    Download the InsightFace release zips and unzip into backend/models/:")
    print("      det_500m.onnx   <- buffalo_s.zip")
    print("      w600k_r50.onnx  <- buffalo_l.zip")
    print("    https://github.com/deepinsight/insightface/releases/tag/v0.7")
    print("    Do NOT pip install insightface - it has no cp312 wheel and will try")
    print("    to compile against MSVC. We only need the .onnx files.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the IdentiCare MongoDB.")
    parser.add_argument("--drop", action="store_true", help="Drop the database first. Dev only.")
    args = parser.parse_args()

    settings = get_settings()
    print(f"[*] Connecting to {settings.mongo_uri.split('@')[-1]} db={settings.mongo_db}")

    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except ServerSelectionTimeoutError:
        print("[!] Cannot reach MongoDB. Start it with:")
        print("      docker compose -f backend/docker-compose.yml up -d")
        return 1

    if args.drop:
        print(f"[!] Dropping database {settings.mongo_db}")
        client.drop_database(settings.mongo_db)

    db = client[settings.mongo_db]

    print()
    total_indexes = 0
    all_problems: list[str] = []
    for name in COLLECTIONS:
        state = ensure_collection(db, name)
        made, problems = ensure_indexes(db, name)
        total_indexes += made
        all_problems.extend(problems)
        print(f"[{'+' if state == 'created' else '=':1}] {name:<24} {state:<8} indexes: {made}")
        if name == "verification_sessions":
            verify_partial_ttl(db)

    print()
    print(f"[+] {len(COLLECTIONS)} collections, {total_indexes} indexes ensured.")

    if all_problems:
        print()
        print("[!] Index conflicts (an existing index has different options):")
        for problem in all_problems:
            print(f"      {problem}")
        print("    Drop the offending index and re-run, or use --drop in dev.")
        return 1

    if not settings.kek_file.exists():
        print()
        print("[!] No KEK yet. Run: python scripts/gen_keys.py")

    check_models(settings)

    print()
    print("[*] Next: python scripts/seed_peserta.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
