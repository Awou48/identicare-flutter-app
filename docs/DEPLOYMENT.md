# Deployment

Three pieces: MongoDB Atlas (data), Firebase (login, chat, profile), and the
FastAPI backend — on your laptop for a demo over Wi-Fi, or on a Hugging Face
Space so the phone can reach it from anywhere. The Android app is built
against whichever backend URL you choose.

## 1. MongoDB Atlas

1. Create a free M0 cluster.
2. **Network Access → Add IP Address → Allow access from anywhere** (`0.0.0.0/0`). Required for Hugging Face (its egress IPs are not fixed) and for a laptop on a phone hotspot.
3. **Database Access** → a user with read/write on `identicare`.
4. Connect → Drivers → copy the host part of the URI (`cluster0.ab12cd.mongodb.net`).

Bootstrap collections, validators, indexes and demo data from your machine:

```powershell
backend\.venv\Scripts\python.exe backend\scripts\use_atlas.py cluster0.ab12cd.mongodb.net
```

Safe to re-run. It rewrites `MONGO_URI` in `backend/.env`, pings the cluster, and
runs `bootstrap.py`, `seed_peserta.py`, `seed_articles.py`.

## 2. Firebase

The project id (`identicare-591e3`) is already in `lib/firebase_options.dart`
and `android/app/google-services.json`. The backend verifies ID tokens against
Google's public keys, so **no service-account JSON is needed anywhere**.

Deploy Firestore rules and the composite index once:

```bash
firebase deploy --only firestore:rules,firestore:indexes
```

Wait for the index to show **Enabled** in the console before testing chat.

## 3. Key material

```powershell
backend\.venv\Scripts\python.exe backend\scripts\gen_keys.py
```

Writes `backend/keys/kek.bin` (32 bytes) and `rotation_v1.npy`, and prints a
`NIK_PEPPER` for `.env`. **Back up `kek.bin` separately from the database**;
without it every stored template is unreadable. The rotation matrix is derived
from the KEK and can always be regenerated from it.

## 4. Backend — option A: your laptop (demo over LAN)

```powershell
backend\start_backend.ps1
```

Checks the venv and `.env`, prints your LAN IP and the exact `flutter run` line,
and starts uvicorn on `0.0.0.0:8000`. Once, as administrator, open the port:

```powershell
New-NetFirewallRule -DisplayName "IdentiCare API" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

Phone and laptop must be on the same network. The LAN IP changes when you
switch between Wi-Fi and a hotspot; re-run the script to get the new one.

## 5. Backend — option B: Hugging Face Space (Docker)

`deploy/huggingface/` contains a Dockerfile that installs the backend, downloads
the two ONNX models from the InsightFace release at build time, and serves on
port 7860 as an unprivileged user. The image was built and run locally against
Atlas with secrets supplied only through the environment; `/api/v1/health`
reported models loaded and the derived rotation matrix identical to the one on
Windows.

### 5.1 Create and push

```powershell
hf auth login                       # once; needs a token with write access
deploy\huggingface\push_space.ps1 -Space <your-username>/identicare-api -Create
```

Subsequent deploys: the same command without `-Create`. The script stages
`Dockerfile`, the Space card, `backend/app`, `backend/scripts`,
`requirements.txt` and `ruff.toml` into a temp folder and uploads it with
`hf upload`; nothing from `.env`, `keys/`, `models/` or `tests/` leaves your
machine.

### 5.2 Secrets

Space → **Settings → Variables and secrets**. Values come from your local
`backend/.env` and `backend/keys/`:

| Secret | Value |
|---|---|
| `MONGO_URI` | the `mongodb+srv://…` line from `.env` |
| `KEK_B64` | `python -c "import base64;print(base64.b64encode(open('backend/keys/kek.bin','rb').read()).decode())"` — **must** be your existing KEK if the database already holds templates |
| `NIK_PEPPER` | from `.env`, must match what seeded the database |
| `OPERATOR_API_KEY` | from `.env` |
| `FACILITY_API_KEYS` | from `.env` (the app presents `abc123` for `rs-harapan` by default) |
| `FIREBASE_PROJECT_ID` | `identicare-591e3` |

Optional variables: `SESSIONS_PER_HOUR` (default 5), `FACE_MATCH_ACCEPT`,
`LIVENESS_MIN_SCORE`, `CORS_ORIGINS`. `IDENTICARE_ENV` is `prod` in the image,
which disables the dev auth bypass.

The rotation matrix is not uploaded: `app/db.py` derives it from the KEK when
`keys/rotation_v1.npy` is absent.

### 5.3 Verify

```
https://<username>-identicare-api.hf.space/api/v1/health
https://<username>-identicare-api.hf.space/docs
```

Expect `"mongo": "ok"`, `"face_models": "loaded"`, `"firebase_auth": "google-public-keys"`, `"keys_loaded": true`.

### 5.4 Limits to know

- Free Spaces sleep after inactivity; the first request after sleep takes ~30 s while models load. Open `/health` before a demo.
- 2 vCPU: face step ≈ 0.5–1 s per attempt, fine for a demo, not for a hospital.
- No persistent disk. Everything durable is in Atlas; nothing is written to the container.
- HTTPS is terminated by Hugging Face; the app needs no cleartext-traffic exception for this URL.

## 6. The Android app

Build against whichever backend you chose:

```bash
# laptop
flutter run --dart-define=API_BASE_URL=http://192.168.0.100:8000

# Hugging Face
flutter run --dart-define=API_BASE_URL=https://<username>-identicare-api.hf.space

# release APK
flutter build apk --release --dart-define=API_BASE_URL=https://<username>-identicare-api.hf.space
```

Other defines: `FASKES_API_KEY` (default `abc123`), `KODE_FASKES` (default
`0110R001`). The Settings page inside the app can override the base URL at
runtime for debugging.

A physical Android device is required: the flow needs a camera and a
fingerprint sensor with at least one fingerprint enrolled, and Tier B
attestation needs a TEE (any phone from the last several years).

Release builds still sign with the debug key; create `android/key.properties`
and a `signingConfigs.release` block before distributing.

## 7. Operations

| Task | How |
|---|---|
| Rotate the operator / facility keys | Change the secret, restart |
| Rotate Atlas credentials | Change in Atlas, update `MONGO_URI` |
| Reset a participant's enrolment | `DELETE /api/v1/enrollment/face/{peserta_id}` with the operator key |
| Move a participant to another login | `db.peserta.updateOne({no_bpjs:"…"},{$set:{firebase_uid:null}})` |
| Create staff for the override demo | `POST /api/v1/staff` with the operator key, one `petugas` and one `supervisor` |
| Look at fraud signals | `GET /api/v1/fraud/signals` with the operator key |
| Backend logs on the Space | Space page → Logs tab; `X-Request-Id` ties a log line to an audit row |
