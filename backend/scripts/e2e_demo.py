"""Drive the whole 4-step flow over HTTP, then attack it.

    python scripts/e2e_demo.py                 # against http://127.0.0.1:8000
    python scripts/e2e_demo.py --url http://192.168.0.101:8000

Exercises the happy path AND the failure paths that matter: out-of-order steps,
replayed nonces, forged signatures, challenge re-rolls, and a still photo held up
to the camera. A green happy path proves very little on its own - what matters is
that the attacks are refused.

NOTE on liveness: the synthetic faces in _synth_faces.py score ~0.68, because
their colour and texture statistics are not skin, and they cannot simulate a head
turn at all. Run the server with LIVENESS_MIN_SCORE=0.55 for this script. The
production default of 0.70 is calibrated for REAL faces and must not be lowered
for a demo.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import secrets
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta

import _synth_faces as synth
import httpx

import _bootstrap_path  # noqa: F401  (side effect: sys.path)

PASS, FAIL = "[+]", "[!]"
results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    results.append((ok, label))
    print(f"  {PASS if ok else FAIL} {label}{(' - ' + detail) if detail else ''}")
    return ok


class Client:
    def __init__(self, base: str, uid: str) -> None:
        self.base = base.rstrip("/")
        self.http = httpx.Client(timeout=120.0)
        self.auth = {"Authorization": f"Bearer dev:{uid}"}
        self.operator = {"X-Api-Key": "dev-operator-key"}
        # Identifies the faskes starting a session. Distinct role from the
        # operator key even though both travel in X-Api-Key.
        self.faskes = {"X-Api-Key": "abc123"}

    def close(self) -> None:
        self.http.close()


def sign_hmac(
    secret: bytes, session_id: str, nonce: str, device_uid: str, no_bpjs: str, ts: int
) -> str:
    payload = f"identicare-v1|{session_id}|{nonce}|{device_uid}|{no_bpjs}|{ts}"
    return base64.b64encode(hmac.new(secret, payload.encode(), hashlib.sha256).digest()).decode()


def mint_nonce(session_id: str) -> str:
    """Insert a fresh nonce directly, standing in for the app requesting one.

    The API mints a nonce when the face step passes; this script burns that one
    on the forged-signature and replay checks.
    """
    from bson import ObjectId
    from pymongo import MongoClient

    from app.config import get_settings

    s = get_settings()
    db = MongoClient(s.mongo_uri)[s.mongo_db]
    nonce = secrets.token_hex(32)
    now = datetime.now(UTC)
    db.nonces.insert_one({
        "_id": nonce,
        "session_id": ObjectId(session_id),
        "purpose": "fingerprint",
        "used": False,
        "issued_at": now,
        "expires_at": now + timedelta(seconds=s.nonce_ttl_seconds),
    })
    return nonce


def start_session(
    c: Client, api: str, no_bpjs: str, device_uid: str, preview_check: bool = False
) -> tuple[str, str]:
    r = c.http.post(
        f"{api}/verification/sessions",
        json={
            "no_bpjs": no_bpjs,
            "kode_faskes": "0110R001",
            "claim": {
                "jenis_layanan": "RAWAT_JALAN",
                "poli": "Penyakit Dalam",
                "estimasi_biaya": 450000,
            },
            "device": {
                "device_uid": device_uid,
                "platform": "android",
                "app_version": "1.1.0+3",
            },
        },
        headers={**c.auth, **c.faskes},
    )
    if r.status_code != 201:
        raise SystemExit(f"session start failed: {r.status_code} {r.text[:300]}")
    sess = r.json()
    check(True, "session created", sess["session_id"])
    if preview_check:
        prev = sess["peserta_preview"]
        check(
            "*" in prev["nama_masked"] and "*" in prev["no_bpjs_masked"],
            "peserta data masked before biometrics pass",
            f"{prev['nama_masked']} / {prev['no_bpjs_masked']}",
        )
    return sess["session_id"], sess["session_token"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--no-bpjs", default="0001234567890")
    args = parser.parse_args()

    api = f"{args.url}/api/v1"
    uid = f"e2e-{uuid.uuid4().hex[:8]}"
    device_uid = hashlib.sha256(uid.encode()).hexdigest()
    device_secret = secrets.token_bytes(32)
    c = Client(args.url, uid)

    print()
    print("=== IdentiCare end-to-end ===")
    print(f"  target {args.url}")
    print(f"  uid    {uid}")

    # ------------------------------------------------------------------ #
    print()
    print("[1] Health")
    r = c.http.get(f"{api}/health")
    body = r.json()
    check(r.status_code == 200 and body["checks"]["mongo"] == "ok", "server healthy")
    if body["checks"]["face_models"] != "loaded":
        print(f"  {FAIL} face models not loaded - cannot continue")
        return 1
    check(True, "face models loaded", f"dim={body['checks']['embedding_dim']}")
    live_min = body["checks"]["thresholds"]["liveness_min"]
    print(f"      server liveness threshold = {live_min}")
    if live_min > 0.60:
        print("      NOTE: synthetic faces score ~0.68 (their colour/texture is not")
        print("      skin). Run the server with LIVENESS_MIN_SCORE=0.55 for this test.")
        print("      The production default 0.70 is for REAL faces - do not lower it.")

    # ------------------------------------------------------------------ #
    print()
    print("[2] Enrolment (operator)")
    peserta_payload = {
        "nik": "3174050412010001",
        "no_bpjs": args.no_bpjs,
        "nama_lengkap": "Marcel Iliantino",
        "tanggal_lahir": "2001-12-04",
        "jenis_kelamin": "L",
        "kelas_rawat": 1,
        "jenis_peserta": "PPU",
        "kode_faskes_tingkat1": "0110P001",
        "status_kepesertaan": "AKTIF",
        "firebase_uid": uid,
    }
    r = c.http.post(f"{api}/enrollment/peserta", json=peserta_payload, headers=c.operator)
    check(r.status_code == 200, "peserta upserted", r.text[:120] if r.status_code != 200 else "")

    r = c.http.post(f"{api}/enrollment/peserta", json=peserta_payload)
    check(r.status_code == 403, "enrolment refused without operator key", f"got {r.status_code}")

    r = c.http.post(
        f"{api}/enrollment/device",
        json={
            "device_uid": device_uid,
            "method": "hmac_sha256_shared_secret",
            "shared_secret_b64": base64.b64encode(device_secret).decode(),
            "firebase_uid": uid,
            "platform": "android",
            "model": "SM-A546E",
            "app_version": "1.1.0+3",
        },
        headers=c.auth,
    )
    check(r.status_code == 200, "device enrolled", f"level={r.json().get('security_level')}")

    r = c.http.post(
        f"{api}/enrollment/device",
        json={"device_uid": device_uid, "shared_secret_b64": base64.b64encode(b"x" * 32).decode()},
    )
    check(r.status_code == 401, "device enrolment refused without a signed-in user", f"got {r.status_code}")

    r = c.http.post(
        f"{api}/enrollment/face",
        data={"no_bpjs": args.no_bpjs, "replace": "true"},
        files=[
            ("frames", (f"e{i}.jpg", f, "image/jpeg"))
            for i, f in enumerate(synth.burst("andi", None, seed=100))
        ],
        headers=c.operator,
    )
    detail = f"frames={r.json().get('frames_used')}" if r.status_code == 200 else r.text[:160]
    check(r.status_code == 200, "face enrolled", detail)

    mixed = synth.burst("andi", None, seed=100)[:1] + synth.burst("budi", None, seed=300)[:2]
    r = c.http.post(
        f"{api}/enrollment/face",
        data={"no_bpjs": args.no_bpjs, "replace": "true"},
        files=[("frames", (f"m{i}.jpg", f, "image/jpeg")) for i, f in enumerate(mixed)],
        headers=c.operator,
    )
    # Informational, NOT an assertion. Synthetic "different people" score ~0.79
    # against each other (real strangers score ~0.1), which is above the 0.60
    # ENROLL_CONSISTENCY_MIN floor - so these fixtures cannot trip the check.
    # Lowering that floor to make a cartoon fail would weaken a real safeguard.
    if r.status_code == 400 and r.json().get("error_code") == "ENROLL_FRAMES_INCONSISTENT":
        check(True, "mixed-identity enrolment refused")
    else:
        print("  [~] mixed-identity enrolment NOT exercised - synthetic faces are too")
        print("      similar to each other to trip ENROLL_CONSISTENCY_MIN. Needs real photos.")

    # Re-enrol cleanly after the rejected attempt.
    c.http.post(
        f"{api}/enrollment/face",
        data={"no_bpjs": args.no_bpjs, "replace": "true"},
        files=[
            ("frames", (f"e{i}.jpg", f, "image/jpeg"))
            for i, f in enumerate(synth.burst("andi", None, seed=100))
        ],
        headers=c.operator,
    )

    # ------------------------------------------------------------------ #
    # Session A exercises the challenge mechanism and spoof rejection, then is
    # discarded. Synthetic faces cannot satisfy a TURN challenge, so the happy
    # path uses a separate session that never requests one.
    print()
    print("[3] Liveness challenge + spoof rejection (session A)")
    sid_a, stoken_a = start_session(c, api, args.no_bpjs, device_uid)
    sh_a = {**c.auth, "X-Session-Token": stoken_a}

    r1 = c.http.post(f"{api}/verification/sessions/{sid_a}/liveness/challenge", headers=sh_a)
    r2 = c.http.post(f"{api}/verification/sessions/{sid_a}/liveness/challenge", headers=sh_a)
    check(
        r1.status_code == 200,
        "liveness challenge issued",
        f"{r1.json()['challenge']} / {r1.json()['instruction']}",
    )
    check(
        r1.json()["challenge_id"] == r2.json()["challenge_id"],
        "re-request returns the SAME challenge (no re-roll attack)",
        f"{r1.json()['challenge']} == {r2.json()['challenge']}",
    )

    r = c.http.post(
        f"{api}/verification/sessions/{sid_a}/face",
        files=[
            ("frames", (f"s{i}.jpg", f, "image/jpeg"))
            for i, f in enumerate(synth.still("andi", seed=100))
        ],
        data={"meta": "{}"},
        headers=sh_a,
    )
    body = r.json()
    live = body.get("liveness") or {}
    check(r.status_code == 200, "spoof returns HTTP 200 (business outcome)", f"got {r.status_code}")
    check(
        body.get("result") == "failed" and body.get("error_code") == "LIVENESS_FAILED",
        "printed-photo spoof rejected by liveness",
        f"score={live.get('score')} motion={live.get('signals', {}).get('motion')}",
    )
    c.http.post(f"{api}/verification/sessions/{sid_a}/cancel", headers=sh_a)

    # ------------------------------------------------------------------ #
    print()
    print("[4] Session start (session B - happy path)")
    sid, stoken = start_session(c, api, args.no_bpjs, device_uid, preview_check=True)
    sh = {**c.auth, "X-Session-Token": stoken}

    # ------------------------------------------------------------------ #
    print()
    print("[5] Ordering guards")
    r = c.http.post(
        f"{api}/verification/sessions/{sid}/fingerprint",
        json={
            "method": "hmac_sha256_shared_secret",
            "nonce": "x",
            "signature_b64": "AA==",
            "device_uid": device_uid,
            "timestamp": 0,
        },
        headers=sh,
    )
    check(
        r.status_code == 409 and r.json().get("error_code") == "STEP_OUT_OF_ORDER",
        "fingerprint before face -> 409 STEP_OUT_OF_ORDER",
        f"got {r.status_code}",
    )

    r = c.http.get(f"{api}/verification/sessions/{sid}/review", headers=sh)
    check(r.status_code == 409, "review before biometrics -> 409", f"got {r.status_code}")

    r = c.http.get(
        f"{api}/verification/sessions/{sid}",
        headers={**c.auth, "X-Session-Token": "wrong" * 10},
    )
    check(r.status_code == 403, "wrong session token -> 403", f"got {r.status_code}")

    # ------------------------------------------------------------------ #
    print()
    print("[6] Step 1 - Scan Wajah")
    t0 = time.perf_counter()
    r = c.http.post(
        f"{api}/verification/sessions/{sid}/face",
        files=[
            ("frames", (f"f{i}.jpg", f, "image/jpeg"))
            for i, f in enumerate(synth.burst("andi", None, seed=200))
        ],
        data={"meta": '{"front_camera": true}'},
        headers=sh,
    )
    body = r.json()
    ok = body.get("result") == "passed"
    check(
        ok,
        "live burst accepted",
        f"score={body.get('match_score')} "
        f"liveness={(body.get('liveness') or {}).get('score')} "
        f"{(time.perf_counter() - t0) * 1000:.0f} ms round trip",
    )
    if not ok:
        print(f"      {body}")
        return 1
    fp_nonce = body["nonce"]
    check(bool(fp_nonce), "fresh nonce issued after face", fp_nonce[:12] + "...")

    # ------------------------------------------------------------------ #
    print()
    print("[7] Step 2 - Scan Sidik Jari")
    ts = int(datetime.now(UTC).timestamp())
    bad = base64.b64encode(b"not-a-real-signature-0123456789ab").decode()
    r = c.http.post(
        f"{api}/verification/sessions/{sid}/fingerprint",
        json={
            "method": "hmac_sha256_shared_secret",
            "nonce": fp_nonce,
            "timestamp": ts,
            "signature_b64": bad,
            "device_uid": device_uid,
        },
        headers=sh,
    )
    check(
        r.json().get("error_code") == "SIGNATURE_INVALID",
        "forged signature rejected",
        r.json().get("error_code"),
    )

    r = c.http.get(f"{api}/verification/sessions/{sid}", headers=sh)
    check(
        r.status_code == 200,
        "session still resumable after a failed attempt",
        f"status={r.json()['status']}",
    )

    r = c.http.post(f"{api}/verification/sessions/{sid}/liveness/challenge", headers=sh)
    check(
        r.status_code == 409,
        "cannot request a face challenge after face passed",
        f"got {r.status_code}",
    )

    sig = sign_hmac(device_secret, sid, fp_nonce, device_uid, args.no_bpjs, ts)
    r = c.http.post(
        f"{api}/verification/sessions/{sid}/fingerprint",
        json={
            "method": "hmac_sha256_shared_secret",
            "nonce": fp_nonce,
            "timestamp": ts,
            "signature_b64": sig,
            "device_uid": device_uid,
        },
        headers=sh,
    )
    check(
        r.json().get("error_code") in {"NONCE_REUSED", "NONCE_EXPIRED"},
        "replayed nonce refused even with a VALID signature",
        r.json().get("error_code"),
    )

    fresh = mint_nonce(sid)
    ts = int(datetime.now(UTC).timestamp())
    wrong_bpjs_sig = sign_hmac(device_secret, sid, fresh, device_uid, "0009999999999", ts)
    r = c.http.post(
        f"{api}/verification/sessions/{sid}/fingerprint",
        json={
            "method": "hmac_sha256_shared_secret",
            "nonce": fresh,
            "timestamp": ts,
            "signature_b64": wrong_bpjs_sig,
            "device_uid": device_uid,
        },
        headers=sh,
    )
    check(
        r.json().get("error_code") == "SIGNATURE_INVALID",
        "signature bound to no_bpjs - wrong participant rejected",
        r.json().get("error_code"),
    )

    fresh = mint_nonce(sid)
    ts = int(datetime.now(UTC).timestamp())
    sig = sign_hmac(device_secret, sid, fresh, device_uid, args.no_bpjs, ts)
    r = c.http.post(
        f"{api}/verification/sessions/{sid}/fingerprint",
        json={
            "method": "hmac_sha256_shared_secret",
            "nonce": fresh,
            "timestamp": ts,
            "signature_b64": sig,
            "device_uid": device_uid,
            "key_alias": "identicare_bpjs_v1",
        },
        headers=sh,
    )
    body = r.json()
    ok = body.get("result") == "passed"
    check(ok, "valid HMAC signature accepted", f"level={body.get('security_level')}")
    if not ok:
        print(f"      {body}")
        return 1
    check(
        body.get("security_level") == "SOFTWARE",
        "Tier A honestly recorded as SOFTWARE, not TEE",
    )

    # ------------------------------------------------------------------ #
    print()
    print("[8] Step 3 - Periksa Ulang Data")
    r = c.http.get(f"{api}/verification/sessions/{sid}/review", headers=sh)
    review = r.json()
    check(r.status_code == 200, "review data returned")
    p = review["peserta"]
    check(p["nama_lengkap"] == "Marcel Iliantino", "full name revealed only now", p["nama_lengkap"])
    check(
        "*" in p["nik_masked"] and p["nik_masked"].endswith("0001"),
        "NIK still masked even after both factors",
        p["nik_masked"],
    )
    check(
        review["biometrik"]["wajah"]["passed"] and review["biometrik"]["sidik_jari"]["passed"],
        "both biometric factors reported as passed",
    )

    r = c.http.post(
        f"{api}/verification/sessions/{sid}/review", json={"confirmed": False}, headers=sh
    )
    check(r.status_code == 400, "unconfirmed review refused", f"got {r.status_code}")

    r = c.http.post(
        f"{api}/verification/sessions/{sid}/review",
        json={"confirmed": True, "corrections": {}},
        headers=sh,
    )
    check(r.status_code == 200, "review confirmed")

    # ------------------------------------------------------------------ #
    print()
    print("[9] Step 4 - Verifikasi Data")
    key = str(uuid.uuid4())
    r = c.http.post(
        f"{api}/verification/sessions/{sid}/commit", json={"idempotency_key": key}, headers=sh
    )
    commit = r.json()
    check(r.status_code == 200, "commit succeeded", r.text[:200] if r.status_code != 200 else "")
    check(
        commit["decision"] in {"APPROVED", "REVIEW", "REJECTED"},
        f"decision = {commit['decision']}",
        f"risk={commit['risk']['score']} band={commit['risk']['band']}",
    )
    receipt = commit.get("receipt_no")
    print(f"      receipt {receipt} | {commit['summary']}")
    for s in commit["risk"]["signals"]:
        print(f"      signal {s['rule_id']} ({s['severity']}, +{s['weight']}) {s['title']}")

    r2 = c.http.post(
        f"{api}/verification/sessions/{sid}/commit", json={"idempotency_key": key}, headers=sh
    )
    check(
        r2.status_code == 200 and r2.json().get("receipt_no") == receipt,
        "commit is idempotent - same key returns the same receipt",
    )

    r3 = c.http.post(
        f"{api}/verification/sessions/{sid}/commit",
        json={"idempotency_key": str(uuid.uuid4())},
        headers=sh,
    )
    check(r3.status_code == 409, "commit with a DIFFERENT key refused", f"got {r3.status_code}")

    # ------------------------------------------------------------------ #
    print()
    print("[10] History")
    r = c.http.get(f"{api}/verification/history?limit=5", headers=c.auth)
    hist = r.json()
    check(r.status_code == 200 and hist["items"], f"history returned {len(hist['items'])} item(s)")
    if hist["items"]:
        it = hist["items"][0]
        check(
            bool(it["metode"]) and bool(it["lokasi"]["faskes"]),
            "history carries date, method, status and location",
            f"{it['status']} | {','.join(it['metode'])} | {it['lokasi']['faskes']}",
        )

    r = c.http.get(f"{api}/verification/history/{sid}", headers=c.auth)
    detail_body = r.json()
    events = detail_body.get("events", [])
    check(r.status_code == 200 and len(events) >= 4, f"audit trail has {len(events)} events")
    for e in events:
        print(f"      #{e['seq']} {e['step']:<12} {e['outcome']:<8} {e.get('error_code') or ''}")
    check(
        any(e["outcome"] == "failed" for e in events),
        "failed attempts are recorded, not just successes",
    )

    other = f"other-{uuid.uuid4().hex[:6]}"
    r = c.http.get(f"{api}/verification/history", headers={"Authorization": f"Bearer dev:{other}"})
    check(r.status_code == 404, "another user cannot read this history", f"got {r.status_code}")

    # ------------------------------------------------------------------ #
    print()
    print("[11] Fraud engine")
    r = c.http.post(f"{api}/fraud/check", json={"session_id": sid}, headers=c.operator)
    check(
        r.status_code == 200,
        "fraud check ran",
        f"score={r.json().get('score')} band={r.json().get('band')}",
    )
    r = c.http.get(f"{api}/fraud/rules", headers=c.operator)
    check(r.status_code == 200 and len(r.json()["rules"]) == 10, "10 rules registered")

    # ------------------------------------------------------------------ #
    print()
    print("[12] Legacy symptom endpoint (revived)")
    r = c.http.post(f"{args.url}/analyze_symptoms", json={"gejala": ["Demam", "Batuk"]})
    check(
        r.status_code == 200 and r.json().get("status") == "ok",
        "POST /analyze_symptoms answers the old contract",
        f"engine={r.json().get('engine')}",
    )
    r = c.http.get(f"{api}/symptoms/catalog")
    check(
        r.status_code == 200 and len(r.json()["gejala"]) == 42,
        "symptom catalog served from the server, not hardcoded in Flutter",
    )

    c.close()

    passed = sum(1 for ok, _ in results if ok)
    print()
    print(f"=== {passed}/{len(results)} checks passed ===")
    for ok, label in results:
        if not ok:
            print(f"  {FAIL} {label}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
