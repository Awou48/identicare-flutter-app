---
title: IdentiCare API
emoji: 🩺
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Biometric BPJS claim verification backend (FastAPI)
---

# IdentiCare API

FastAPI backend for the IdentiCare Android app: face recognition (SCRFD + ArcFace
via onnxruntime), active-challenge liveness, TEE-attested fingerprint signatures,
a server-side four-step claim state machine and a fraud-rule engine, all on
MongoDB Atlas with per-document AES-256-GCM envelope encryption.

Source and documentation: <https://github.com/Awou48/identicare-flutter-app>

## Secrets this Space needs

Set these under **Settings → Variables and secrets**:

| Secret | Purpose |
|---|---|
| `MONGO_URI` | Atlas connection string (`mongodb+srv://...`). Atlas Network Access must allow `0.0.0.0/0`. |
| `KEK_B64` | 32-byte key-encryption key, base64. Generate: `python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"`. Use the same value as your local `keys/kek.bin` if the database already holds templates. |
| `NIK_PEPPER` | Random string used to hash NIKs. Must match whatever seeded the database. |
| `OPERATOR_API_KEY` | Key for operator-only endpoints. |
| `FACILITY_API_KEYS` | `kode_faskes:key,...` pairs the app presents when starting a session. |
| `FIREBASE_PROJECT_ID` | Firebase project whose ID tokens are accepted (`identicare-591e3`). |

Optional: `SESSIONS_PER_HOUR`, `FACE_MATCH_ACCEPT`, `LIVENESS_MIN_SCORE`, `CORS_ORIGINS`.

The rotation matrix used for privacy-preserving 1:N search is derived from the
KEK at startup, so no file upload is needed.

## Endpoints

`GET /api/v1/health` · Swagger UI at `/docs`.
