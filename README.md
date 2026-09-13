# IdentiCare

Biometric fraud prevention for BPJS Kesehatan claims. A participant proves at the
point of care that they are the person the card belongs to — face, liveness and a
hardware-attested fingerprint signature — and every claim leaves a permanent,
tamper-evident verification record that a fraud engine scores in real time.

Android app (Flutter) · FastAPI backend · MongoDB Atlas · Firebase Auth.

| | |
|---|---|
| **Problem** | BPJS loses an estimated Rp 20 T/year to claim fraud: card sharing, phantom claims, the same patient "treated" at two hospitals at once. |
| **Approach** | Verify the *person*, not the card. Bind every claim to a face match, an active liveness challenge, and a signature the phone's secure hardware will only produce after a real fingerprint. |
| **Status** | Working end to end on a physical Android device: link account → self-enrol → 4-step verification → receipt. 176 backend tests, 0 analyzer issues. |

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

## What makes it defensible

- **Biometric data never leaves the device in usable form.** Fingerprints stay in the sensor's secure path. Face embeddings are stored encrypted per document; 1:N search runs over vectors in a secret rotated basis, so a database dump cannot be matched against a public ArcFace gallery.
- **The fingerprint step is enforced by hardware, not by app code.** An EC P-256 key generated inside the Android TEE with `setUserAuthenticationRequired(true)`; the server reads the key's attestation certificate to decide what it is worth. A rooted phone or patched APK cannot fake it.
- **Enrolment has a 1:N de-duplication gate.** The same face cannot be enrolled under two BPJS numbers; the attempt is itself a critical fraud signal.
- **The override path is more expensive than the fraud.** Two distinct staff, a closed reason enum, encrypted photos of physical cards, and the override is recorded as `APPROVED_WITH_OVERRIDE` plus a fraud signal — forever distinguishable.
- **The system tells the truth about its own strength.** Software-only device keys, self-asserted enrolments, and unverified attestation chains are all recorded as exactly that and scored accordingly.

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
  tests/                 176 tests
deploy/huggingface/      Dockerfile + push script for a Hugging Face Space
docs/                    everything below
```

## Documentation

| Document | What it covers |
|---|---|
| [docs/TESTING.md](docs/TESTING.md) | Step-by-step: run everything locally and verify each feature on a phone, with the seeded demo identities |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | MongoDB Atlas, Firebase, the backend on Hugging Face Spaces, building the app against it |
| [docs/API.md](docs/API.md) | Every endpoint, auth model, response envelope, error codes |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, each control and the attack it closes, what is *not* yet proven |
| [docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md) | Why things are the way they are — thresholds, choreography, fallbacks, the bugs that shaped them |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Scaling and integration design: offline-first, vector DB, FHIR/SATUSEHAT, auditor console, desk scanners, UU PDP |
| [backend/README.md](backend/README.md) | Backend developer guide (Windows-first) |
| [backend/docs/SCHEMA.md](backend/docs/SCHEMA.md) | MongoDB collections, the encryption-vs-matching tension, indexes |

## Quick start

```bash
# backend (see backend/README.md for Windows specifics and model download)
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
cp .env.example .env            # fill MONGO_URI (Atlas) and run scripts/gen_keys.py
python scripts/use_atlas.py <cluster-host>
./start_backend.ps1

# app, pointed at the machine running the backend
flutter run --dart-define=API_BASE_URL=http://<lan-ip>:8000
```

Demo identity to link on first launch: BPJS `0001234567890`, NIK `3174050412010001`,
born 4 Dec 2001. Full walkthrough in [docs/TESTING.md](docs/TESTING.md).

## Stack

Flutter 3.41 / Dart 3.11 · camera, local_auth, provider, google_fonts ·
FastAPI, pymongo `AsyncMongoClient`, onnxruntime (SCRFD `det_500m`, ArcFace
`w600k_r50`), OpenCV, `cryptography` · MongoDB 7 / Atlas · Firebase Auth +
Firestore (chat, profile) · Android Keystore + BiometricPrompt.
