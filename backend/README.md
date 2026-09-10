# IdentiCare Backend

Python API for biometric BPJS claim verification. FastAPI + MongoDB, face
recognition via ONNX (ArcFace + SCRFD), fingerprint via Android Keystore
attestation.

**Android-only.** There is no `ios/` folder in the Flutter app, and the camera and
`local_auth` plugins have no working web or desktop implementation. See
`../TODO.md` §6.

---

## Quick start (Windows / PowerShell)

```powershell
# 1. MongoDB (Docker Desktop must be running)
docker compose -f backend/docker-compose.yml up -d

# 2. Virtualenv
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt

# 3. Config + keys (one time)
copy backend\.env.example backend\.env
python backend\scripts\gen_keys.py          # writes keys/kek.bin + rotation_v1.npy
#    paste the suggested NIK_PEPPER into backend\.env

# 4. Schema + demo data
python backend\scripts\bootstrap.py         # idempotent, safe to re-run
python backend\scripts\seed_peserta.py

# 5. Tests
pytest backend\tests -q

# 6. Serve. 0.0.0.0 so a phone on the LAN can reach it.
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir backend

# 7. Verify (server must be running)
python backend\scripts\check_face_models.py     # ONNX pipeline
python backend\scripts\e2e_demo.py              # full flow + attack cases
```

Swagger UI: <http://localhost:8000/docs> · mongo-express: <http://localhost:8081>

---

## Windows gotchas

These are the ones that actually cost time.

**Windows Defender Firewall.** The first `uvicorn --host 0.0.0.0` triggers a UAC
prompt. If it is dismissed, the phone gets a connection timeout and **the server
logs nothing at all** — there is no failed request to see, because the packet
never arrives. This is the number one cause of "why won't my phone connect".
Pre-add the rule from an admin shell:

```powershell
New-NetFirewallRule -DisplayName "IdentiCare API" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

**`uvloop` is skipped, and that is fine.** `uvicorn[standard]` declares it with a
`sys_platform != 'win32'` marker, so pip silently omits it on Windows. Not an
error. `httptools` and `watchfiles` do have Windows wheels and are installed.

**`--reload` reloads the ONNX models** on every file save, roughly 2 seconds each
time. Keep it while writing routers; drop it before demoing.

**Docker Desktop must be running before `docker compose`.** Starting
`com.docker.service` requires administrator rights, so if the engine is down,
launch Docker Desktop from the Start menu rather than from a script.

**No native `mongod`.** Mongo runs only in Docker here. `docker compose down`
keeps your data (it lives in the named volume `identicare_mongo_data`);
`docker compose down -v` destroys it.

---

## Face models — download manually

Not committed (~170 MB) and **not** installed via pip. Put these in
`backend/models/`:

| File | From | Size |
|---|---|---|
| `det_500m.onnx` | `buffalo_s.zip` | ~2.5 MB |
| `w600k_r50.onnx` | `buffalo_l.zip` | ~166 MB |

<https://github.com/deepinsight/insightface/releases/tag/v0.7>

> **Do not `pip install insightface`.** It has no cp312 wheel, so pip falls back
> to a source build that needs MSVC Build Tools and Cython — the classic Windows
> failure. We load the two `.onnx` graphs directly through `onnxruntime`, which
> needs no face-recognition package at all. Same models, none of the build pain.

`bootstrap.py` warns if they are missing, and `/health` reports
`face_models: unavailable` - the rest of the API still boots, only the face
endpoints return `MODEL_UNAVAILABLE`.

If `w600k_r50` is too slow on your CPU, swap `FACE_REC_MODEL` in `.env` to
`w600k_mbf.onnx` (MobileFaceNet, ~4 MB, also 512-d, roughly 4x faster, modest
accuracy cost).

---

## Key material

`backend/keys/` is gitignored. Three things live there and they are not equal:

| File | If lost | Recovery |
|---|---|---|
| `rotation_v1.npy` | 1:N fraud sweep stops working; 1:1 verification still fine | Re-derive from the KEK — deterministic, byte-identical |
| `kek.bin` | **Every stored template and NIK is permanently unreadable** | None |
| `NIK_PEPPER` (in `.env`) | Every `nik_hash` stops matching; NIK lookup dies | None without the original NIKs |

Back up `kek.bin` **separately from any database backup**. Together in one place,
they undo the entire encryption scheme.

`gen_keys.py` refuses to overwrite an existing KEK unless you pass `--force`.

---

## Layout

```
backend/
├─ app/
│  ├─ main.py            FastAPI app, lifespan, error handlers
│  ├─ config.py          pydantic-settings, reads .env
│  ├─ db.py  deps.py     async Mongo handle, DI dependencies
│  ├─ db_schema.py       collections, $jsonSchema validators, indexes
│  ├─ routers/           health enrollment sessions face fingerprint
│  │                     history fraud symptoms
│  ├─ services/          face_engine liveness matcher session_service
│  │                     fraud_rules audit
│  ├─ schemas/           pydantic request/response models
│  ├─ utils/             images errors geo
│  └─ security/
│     ├─ crypto.py       AES-256-GCM envelope encryption, NIK hashing/masking
│     ├─ rotation.py     secret orthogonal matrix for the 1:N search index
│     ├─ firebase_auth.py  Firebase ID token verification (+ dev bypass)
│     ├─ attestation.py    HMAC (Tier A) and EC P-256 Keystore (Tier B)
│     └─ nonce.py          atomic single-use nonce consumption
├─ scripts/
│  ├─ gen_keys.py        KEK + rotation matrix
│  ├─ bootstrap.py       create collections/validators/indexes (idempotent)
│  ├─ seed_peserta.py    4 faskes, 20 peserta, 15 placeholder templates
│  ├─ check_face_models.py  prove the ONNX pipeline works (run this FIRST)
│  ├─ enroll_me.py          enrol a REAL face so the demo works
│  ├─ e2e_demo.py           drive the whole flow over HTTP, then attack it
│  └─ _synth_faces.py       synthetic fixtures - READ ITS CAVEATS
├─ tests/
│  ├─ test_crypto_roundtrip.py       encryption + AAD document binding
│  ├─ test_rotation_invariance.py    cos(Rx,Ry) == cos(x,y)
│  ├─ test_session_state_machine.py  ordering, fraud rules, attestation, liveness
│  └─ test_schema_indexes.py         live-DB checks (skips without Mongo)
└─ docs/SCHEMA.md         why the schema looks like this
```

## API

Base `/api/v1`. Swagger at `/docs`. Peserta endpoints take
`Authorization: Bearer <Firebase ID token>`; flow steps additionally require
`X-Session-Token`; facility and operator endpoints take `X-Api-Key`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | model + db readiness |
| POST | `/enrollment/peserta` `/face` `/device` | operator enrolment |
| DELETE | `/enrollment/face/{peserta_id}` | revoke (right to erasure) |
| POST | `/verification/sessions` | **start** |
| GET | `/verification/sessions/{id}` | resume |
| POST | `/verification/sessions/{id}/liveness/challenge` | issue challenge |
| POST | `/verification/sessions/{id}/face` | **step 1** (multipart) |
| POST | `/verification/sessions/{id}/fingerprint` | **step 2** |
| GET/POST | `/verification/sessions/{id}/review` | **step 3** |
| POST | `/verification/sessions/{id}/commit` | **step 4** (idempotent) |
| POST | `/verification/sessions/{id}/cancel` | abort |
| GET | `/verification/history[/{id}]` | cursor-paginated log |
| POST/GET | `/fraud/check` `/fraud/signals` `/fraud/rules` | operator |
| POST | `/analyze_symptoms` | legacy compat, revived via Ollama |

### Two response conventions worth knowing

**A failed biometric step returns HTTP 200**, with `result: "failed"` and an
`error_code`. A face mismatch is the system working correctly, and the UI has to
render the score and the remaining attempts. A 4xx would be swallowed by
Flutter's generic error handling and the user would see "terjadi kesalahan"
instead of the real reason. 4xx is reserved for protocol errors: 409 for a step
out of order, 410 for an expired session, 403 for a bad token.

**Participant data is masked until step 3.** Session start returns only
`Marcel I******** / 000*******890`. The full record is revealed only after BOTH
biometric factors pass - otherwise anyone who guesses a BPJS number could read
someone's record.

## Dev-mode auth

With no `keys/firebase-adminsdk.json` present AND `IDENTICARE_ENV=dev`, the API
accepts `Authorization: Bearer dev:<uid>`. It is refused in any other
environment and every use is logged as a warning. Drop the real service-account
JSON in to switch to genuine Firebase verification - no code change.

## What is verified, and what is not

`scripts/e2e_demo.py` runs 44 checks covering the happy path and the attacks:
out-of-order steps, a wrong session token, a forged signature, a replayed nonce,
a signature bound to the wrong participant, a challenge re-roll, a printed-photo
spoof, a double commit, and cross-user history access.

It runs against **synthetic drawn faces**, which has hard limits - see the
caveats at the top of `scripts/_synth_faces.py`:

- ArcFace collapses cartoons into one region: different synthetic "people" score
  ~0.79 against each other where real strangers score ~0.1. So the fixtures
  **cannot validate FACE_MATCH_ACCEPT**, and cannot trip
  `ENROLL_CONSISTENCY_MIN` either.
- They cannot simulate head yaw at all, so `turn_left`/`turn_right` are
  unexercised. Only `move_closer` and the negative cases work.
- They score ~0.68 on liveness, so the e2e needs `LIVENESS_MIN_SCORE=0.55`.

## Enrolling a real face

The seeded participants carry random vectors, so they can never match a photo.
To demo with your own face:

```powershell
# from photos you took with your phone (3 shots, slightly different angles)
python backend\scripts\enroll_me.py --images path\to\photos --nama "Nama Anda"

# or straight from the webcam - needs the GUI OpenCV build:
#   pip install opencv-python
python backend\scripts\enroll_me.py --webcam --nama "Nama Anda"
```

Pass `--firebase-uid <uid>` to link the participant to the account you sign into
the app with; without it the app cannot load that participant's history. You can
also just sign up in the app using the same BPJS number.

Check an enrolment against a fresh photo at any time:

```powershell
python backend\scripts\enroll_me.py --verify path\to\another_photo.jpg
```

That calls `POST /api/v1/enrollment/face/probe`, which scores the photo against
**every** enrolled template and reports the full ranking. Two participants
scoring high against one face is the `FACE_COLLISION` case - much better found
here than mid-demo.

**Before any demo, calibrate on real photographs:**

```powershell
python backend\scripts\check_face_models.py --images path\to\photos
```

Name them `<person>_<n>.jpg`. It prints same-person and different-person score
distributions and suggests a threshold. Do not lower the production thresholds
to make a fixture pass - that tunes a security control to fit a test artefact.

---

## Reading order

Start with [`docs/SCHEMA.md`](docs/SCHEMA.md) §1 — the encryption-versus-matching
tension is the only genuinely hard design decision here, and everything else
follows from how it is resolved.
