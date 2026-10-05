# IdentiCare

Biometric fraud prevention for BPJS Kesehatan claims. A participant proves at the
point of care that they are the person the card belongs to — face, liveness and a
hardware-attested fingerprint signature — and every claim leaves a verification
record that a fraud-rule engine scores in real time.

Android app (Flutter) · FastAPI backend · MongoDB Atlas · Firebase Auth.

> **Hackathon prototype, archived.** Built for Hackathon 8.0 at TechnoScape
> (BNCC), May 2025, where it placed as a **Top 10 finalist**. It is a working
> prototype, **not** a production or national healthcare system, and must not be
> presented as one. Development has stopped; this repository is kept as a record
> of the work. See [Known limitations](#known-limitations) for what was and was
> not proven.

| | |
|---|---|
| **Problem** | BPJS claim fraud: card sharing, phantom claims, the same patient "treated" at two facilities at once. |
| **Approach** | Verify the *person*, not the card. Bind every claim to a face match, an active liveness challenge, and a signature the phone's secure hardware will only produce after a real fingerprint. |
| **Status** | Core flow demonstrated on a physical Android device: link account → self-enrol → 4-step verification → receipt. |

---

## How a claim is verified

```
 participant's phone                          IdentiCare API                     MongoDB Atlas
 ───────────────────                          ──────────────                     ─────────────
 1. Face burst (3 frames)  ──── POST /face ──▶ quality gate → SCRFD detect      biometric_templates
    frame 1 straight,                          → liveness (challenge, motion,   (AES-256-GCM, per-doc DEK)
    frames 2-3 turned                            texture, moiré, colour)
                                               → ArcFace 512-d → cosine 1:1
                                               → 1:N collision sweep
 2. Fingerprint            ──── POST /fingerprint ─▶ nonce consumed once       devices (public key +
    TEE signs nonce                            → ECDSA verify vs enrolled key   attestation chain)
    after BiometricPrompt                      → security level from cert
 3. Review masked data     ──── POST /review ──▶ participant confirms
 4. Commit                 ──── POST /commit ──▶ 12 fraud rules → score        verification_sessions
                                               → APPROVED / REVIEW / REJECTED   verification_events
                                               → receipt VRF-…                  fraud_signals
```

The server holds the state machine (`created → face_passed → fingerprint_passed
→ reviewed → committed`). A step posted out of order is refused with 409; a
business outcome such as a face mismatch is HTTP 200 with `result: "failed"`, so
the app can show the score and remaining attempts instead of a generic error.

## Design properties

- **Biometric data is not stored in usable form.** Fingerprints stay in the sensor's secure path and never reach the server. Face embeddings are encrypted per document; 1:N search runs over vectors in a secret rotated basis derived from the KEK.
- **The fingerprint step is enforced by hardware, not app code.** An EC P-256 key generated inside the Android TEE with `setUserAuthenticationRequired(true)`; the server reads the key's attestation certificate to decide what the key is worth.
- **Enrolment has a 1:N de-duplication gate.** The same face cannot be enrolled under two BPJS numbers; the attempt is recorded as a critical fraud signal.
- **The staff override is costed.** Two distinct staff members, a closed reason enum, encrypted photos of the physical cards, and the decision is recorded as `APPROVED_WITH_OVERRIDE` plus a fraud signal rather than a clean approval.
- **Weak paths are labelled, not hidden.** Software-only device keys, self-asserted enrolments, and attestation chains that were parsed but not validated to the Google root are each recorded as such and scored accordingly.

## Repository

```
lib/                     Flutter app (Android)
  pages/verification/    4-step flow, self-enrolment, account linking, override
  services/              API client, camera burst, TEE keystore bridge, attestation
  state/                 VerificationFlowController (server session mirror)
android/app/src/main/kotlin/.../KeystoreSigner.kt   TEE key + BiometricPrompt signing
backend/
  app/routers/           FastAPI endpoints
  app/services/          face engine, liveness, matcher, fraud rules, session state machine
  app/security/          envelope crypto, rotation, attestation, Firebase/staff auth, nonces
  scripts/               bootstrap, seeding, key generation, e2e demo
  tests/                 176 tests (141 run without a database, 35 require MongoDB)
deploy/huggingface/      Dockerfile + push script for a Hugging Face Space
docs/                    see below
TODO.md                  historical audit snapshot from the start of the rebuild
```

## Documentation

| Document | What it covers |
|---|---|
| [docs/TESTING.md](docs/TESTING.md) | Step-by-step: run everything locally and verify each feature on a phone, with the seeded demo identities |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | MongoDB Atlas, Firebase, the backend on Hugging Face Spaces, building the app against it |
| [docs/API.md](docs/API.md) | Every endpoint, auth model, response envelope, error codes |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, each control and the attack it closes, what is *not* proven |
| [docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md) | Why thresholds, capture choreography and fallbacks are what they are |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Design notes for scaling and integration directions that were explored but not built |
| [backend/README.md](backend/README.md) | Backend developer guide (Windows-first) |
| [backend/docs/SCHEMA.md](backend/docs/SCHEMA.md) | MongoDB collections, the encryption-vs-matching tension, indexes |

## Requirements

| | |
|---|---|
| Flutter | 3.41 / Dart 3.11, Android only (no iOS target in this repository) |
| Device | **Physical Android phone**, minSdk 24, with a camera and at least one fingerprint enrolled. The emulator cannot complete the flow. |
| Python | 3.12 |
| Database | MongoDB 7, local or Atlas |
| Firebase | A project with Email/Password auth and Firestore enabled |

## Local setup

```bash
# 1. Backend dependencies
cd backend
py -3.12 -m venv .venv
.venv/Scripts/pip install -r requirements.txt

# 2. Key material (writes keys/kek.bin and keys/rotation_v1.npy, prints a NIK_PEPPER)
.venv/Scripts/python scripts/gen_keys.py

# 3. Face models (~170 MB, not in Git) — see backend/README.md
#    det_500m.onnx from buffalo_s.zip, w600k_r50.onnx from buffalo_l.zip
.venv/Scripts/python scripts/check_face_models.py

# 4. Configure and seed
cp .env.example .env
.venv/Scripts/python scripts/use_atlas.py <cluster-host>
# or, with a local MongoDB: docker compose up -d mongo && .venv/Scripts/python scripts/bootstrap.py

# 5. Run
./start_backend.ps1
```

```bash
# App, pointed at whatever is running the backend
flutter pub get
flutter run --dart-define=API_BASE_URL=http://<lan-ip>:8000
```

Demo identity to link on first launch: BPJS `0001234567890`, NIK `3174050412010001`,
born 4 Dec 2001. Full walkthrough in [docs/TESTING.md](docs/TESTING.md).

## Environment variables

`backend/.env`, copied from `backend/.env.example`. Never committed.

| Variable | Required | Purpose |
|---|---|---|
| `MONGO_URI` | yes | `mongodb://…` or `mongodb+srv://…`. Atlas needs Network Access open to the backend's egress IP. |
| `MONGO_DB` | no | Database name, default `identicare` |
| `NIK_PEPPER` | yes | Pepper for NIK hashing. Changing it orphans every stored NIK hash. |
| `KEK_PATH` / `ROTATION_PATH` | no | Default `./keys/…`. **Losing the KEK makes every stored face template permanently unreadable.** |
| `KEK_B64` | containers | The KEK as base64 instead of a file. The rotation matrix is then derived from it at startup. |
| `FIREBASE_PROJECT_ID` | yes | ID tokens are verified against Google's public keys; no service-account file is used. |
| `OPERATOR_API_KEY` | yes | Operator-only endpoints (enrolment by operator, fraud console, staff CRUD) |
| `FACILITY_API_KEYS` | yes | `kode_faskes:key,…` pairs the app presents when starting a session |
| `FACE_DET_MODEL` / `FACE_REC_MODEL` | no | Paths to the two ONNX files |
| `FACE_MATCH_ACCEPT`, `FACE_MATCH_REVIEW`, `LIVENESS_MIN_SCORE`, `SESSIONS_PER_HOUR` | no | Thresholds and rate limits; defaults in `.env.example` |
| `IDENTICARE_ENV` | no | `dev` enables the `Bearer dev:<uid>` auth bypass for scripts. Anything else disables it. |
| `CORS_ORIGINS` | no | Comma-separated. The Android app does not need CORS; this exists for browser callers. |

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest tests -q
.venv/Scripts/python -m ruff check app scripts tests
.venv/Scripts/python scripts/check_face_models.py
.venv/Scripts/python scripts/e2e_demo.py
```

```bash
flutter analyze
flutter test
flutter build apk --debug
```

176 tests are collected. The 35 that need a live MongoDB skip rather than fail
when none is reachable. `e2e_demo.py` drives the whole flow over HTTP against a
running backend with **synthetic drawn faces**, which cannot validate the match
threshold — the caveats are at the top of `scripts/_synth_faces.py`.

## Deployment

The backend is packaged for a free Hugging Face Space in `deploy/huggingface/`:
a Dockerfile that installs the API, fetches both ONNX models at build time, and
serves on port 7860 as an unprivileged user.

```powershell
hf auth login
deploy\huggingface\push_space.ps1 -Space <username>/identicare-api -Create
```

Then set `MONGO_URI`, `KEK_B64`, `NIK_PEPPER`, `OPERATOR_API_KEY`,
`FACILITY_API_KEYS` and `FIREBASE_PROJECT_ID` as Space secrets and build the app
against the Space URL. Full instructions in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

**Deployment status:** the image was built locally and run against MongoDB Atlas
with secrets supplied only through the environment; `/api/v1/health` reported the
database reachable, both models loaded and the key material derived correctly.
**No public Space has been published** — that requires the owner's Hugging Face
account, so there is no live URL and none is claimed here.

## Known limitations

These are real and were not solved. The project is archived with them.

- **Key attestation is parsed, not chain-validated.** The server reads the Android key attestation certificate and checks that it certifies the exact public key presented, carries this device's challenge, and requires a fingerprint — but it does not validate the chain up to the Google Hardware Attestation Root. `chain_verified` is stored as `false`. On a stock phone the TEE's claim is strong; on a rooted phone with a patched keystore it is not.
- **Thresholds are uncalibrated.** `FACE_MATCH_ACCEPT = 0.42` comes from ArcFace literature, not from measurement on any population. No false-accept or false-reject rate has been measured, and none is claimed.
- **Liveness is heuristic.** An active challenge plus motion, texture, moiré and colour signals; no passive anti-spoof model. It was tested against a printed photo and a screen replay, not against a determined attacker.
- **Turn direction is scored by magnitude, not sign.** `STRICT_TURN_DIRECTION = False`, because front-camera mirroring differs between camera stacks and was never confirmed across devices. A replayed video containing a head turn can satisfy both turn challenges.
- **The staff override UI lives on the participant's phone.** There is no faskes desk application. Every override control is enforced server-side, but in a real deployment that screen belongs on a staff terminal.
- **Enrolment is self-asserted.** The `DUKCAPIL_VERIFIED` and `ASSISTED_DUAL_CONTROL` assurance levels exist in the data model and are enforced where present, but no Dukcapil integration was built. Self-asserted enrolments carry a claim ceiling.
- **The hardware paths cannot be verified without a physical Android device.** TEE key generation, `BiometricPrompt` signing and the camera burst have no emulator equivalent, so neither CI nor a deployed backend can prove them.
- **Face photos used for manual enrolment testing exist in the Git history.** `my_photos/` is now untracked and ignored, but earlier commits still contain the images. History was deliberately not rewritten.
- **FHIR/SATUSEHAT, offline-first, the vector database and the auditor console are design notes only.** `docs/ARCHITECTURE.md` describes them; none is implemented.

## Attribution

IdentiCare was a **team project** for Hackathon 8.0 at TechnoScape (BNCC), May 2025.

This repository does not record a per-member contribution breakdown, and its Git
history reflects only the repository owner's commits. No claim is made here about
which team member built which part, and no individual role is asserted — the
team's work is not reducible to this commit log.

## Stack

Flutter 3.41 / Dart 3.11 · camera, local_auth, provider, google_fonts ·
FastAPI, pymongo `AsyncMongoClient`, onnxruntime (SCRFD `det_500m`, ArcFace
`w600k_r50`), OpenCV, `cryptography` · MongoDB 7 / Atlas · Firebase Auth +
Firestore (chat, profile) · Android Keystore + BiometricPrompt.
