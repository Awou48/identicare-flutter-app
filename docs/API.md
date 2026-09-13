# IdentiCare API

Base path: `/api/v1`. Interactive docs at `/docs` (Swagger UI) when the server
is running. All user-facing messages are Indonesian; all codes are stable
machine strings.

## Authentication

Four principals, four headers. A request may legitimately carry more than one.

| Header | Principal | Issued by | Used for |
|---|---|---|---|
| `Authorization: Bearer <Firebase ID token>` | Participant | Firebase Auth (the app) | Anything about *my* account: linking, self-enrolment, sessions, history |
| `X-Session-Token` | A verification session | `POST /verification/sessions` | Every step of that session |
| `X-Api-Key` (facility) | A faskes | `FACILITY_API_KEYS` env | Starting a session at that facility |
| `X-Api-Key` (operator) | Operator / scripts | `OPERATOR_API_KEY` env | Enrolment by operator, fraud console, staff CRUD, articles |
| `X-Staff-Token` | Staff member | `POST /staff/login` | Override request / approval |

Firebase tokens are verified against Google's public keys (RS256, audience =
project id, issuer = `https://securetoken.google.com/<project>`, 60 s leeway).
No service account is required. In `IDENTICARE_ENV=dev` and only then,
`Bearer dev:<uid>` is accepted so scripts can act as a user.

## Response envelope

Success:

```json
{ "status": "ok", ... }
```

Protocol error (4xx/5xx) — the client did something wrong or the session is in
the wrong state:

```json
{ "status": "error", "error_code": "STEP_OUT_OF_ORDER", "message": "Langkah verifikasi tidak berurutan.",
  "request_id": "a1b2c3d4e5f6", "details": { "current_status": "created", "expected_step": "face" } }
```

Business outcome (HTTP **200**) — the system worked and said no. Rendered by
the app with scores and remaining attempts, never as "something went wrong":

```json
{ "status": "ok", "step": "face", "result": "failed", "error_code": "FACE_MISMATCH",
  "message": "Wajah tidak cocok dengan data peserta. Sisa percobaan: 2.",
  "match_score": 0.31, "threshold": 0.42, "attempts_left": 2, "next_step": "face" }
```

Every response carries `X-Request-Id`; it appears in server logs and audit rows.

## Endpoints

### Health

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/health` | — | Mongo ping, template count, model status, auth method, thresholds |

### Participant account

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/peserta/me` | Firebase | Status of the linked participant. `404 PESERTA_NOT_FOUND` when the account is not linked. Returns full `no_bpjs` (caller is the owner), masked form, membership status, `biometric_enrolled` derived from the live template, `assurance`. |
| POST | `/peserta/link` | Firebase | Body `{no_bpjs, nik, tanggal_lahir}`. Proof of possession of the physical cards. Uniform `403 IDENTITY_MISMATCH` for any wrong field (`details.attempts_left`); `429 TOO_MANY_ATTEMPTS` after 5 failures/hour; `409 BPJS_ALREADY_LINKED` raises fraud signal `ACCOUNT_LINK_CONFLICT`; `409 ACCOUNT_ALREADY_LINKED` when this account already holds another participant. |

### Enrolment

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/enrollment/peserta` | Operator | Upsert a participant record (seeding, faskes desk). |
| POST | `/enrollment/self` | Firebase | Multipart `frames[]` (3 JPEGs). Self-asserted enrolment for the linked participant. Runs the shared pipeline: consistency check, **1:N dedup gate**, activation. Returns `assurance`, `claim_ceiling`, `dedup.templates_checked`. `409 ALREADY_ENROLLED` unless the active template is a seeded placeholder. |
| POST | `/enrollment/face` | Operator | Same pipeline; `no_bpjs` + `replace` form fields. |
| POST | `/enrollment/face/probe` | Operator | Score frames against every template. Diagnostics. |
| DELETE | `/enrollment/face/{peserta_id}` | Operator | Right to erasure: ciphertext and search vector zeroed. |
| POST | `/enrollment/device` | Firebase | Register the phone's signing key. Tier B: `method=android_keystore_ec_p256`, `public_key_der_b64`, `attestation_chain_b64[]`; the server parses the chain (see [SECURITY.md](SECURITY.md)). Tier A: `method=hmac_sha256_shared_secret`, `shared_secret_b64`. Idempotent upsert, stamped with the token's uid. |

### Verification session

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/verification/sessions` | Firebase + facility key | Body `{no_bpjs, kode_faskes, claim{jenis_layanan, poli, estimasi_biaya}, device{...}}`. `201` with `session_id`, `session_token`, `nonce`, masked preview, `expires_at`. `409 BIOMETRIC_NOT_ENROLLED`, `403 PESERTA_NONAKTIF`, `429 TOO_MANY_SESSIONS` (per-hour limit, `SESSIONS_PER_HOUR`). |
| GET | `/verification/sessions/{id}` | Firebase + session | Resume: current status and next step. |
| POST | `/verification/sessions/{id}/liveness/challenge` | Session | Issues (or re-returns while valid) a random single-use challenge: `turn_left`, `turn_right`, `move_closer`. 120 s TTL. |
| POST | `/verification/sessions/{id}/face` | Session | Multipart `frames[]` + `meta` JSON (`challenge_id`). Pipeline in [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md). Outcomes: `LOW_QUALITY_BLUR`, `LOW_QUALITY_LIGHT`, `NO_FACE_DETECTED`, `FACE_TOO_SMALL`, `MULTIPLE_FACES` (quality budget, 10), `LIVENESS_FAILED`, `FACE_MISMATCH` (identity budget, 3), `MAX_ATTEMPTS` (session rejected). On pass returns `match_score`, `liveness`, a fresh `nonce`. |
| POST | `/verification/sessions/{id}/fingerprint` | Session | Body `{method, key_alias, nonce, timestamp, signature_b64, device_uid}`. Canonical payload `identicare-v1|session_id|nonce|device_uid|no_bpjs|timestamp`. Nonce consumed **before** verification. Outcomes: `NONCE_REUSED`, `NONCE_EXPIRED`, `DEVICE_NOT_ENROLLED`, `KEY_MISMATCH`, `SIGNATURE_INVALID`. Returns `security_level` (`TEE` / `STRONGBOX` / `SOFTWARE`). |
| GET | `/verification/sessions/{id}/review` | Session | Unmasked name, masked NIK, both biometric results. First time the name is shown. |
| POST | `/verification/sessions/{id}/review` | Session | `{confirmed: true}`. |
| POST | `/verification/sessions/{id}/commit` | Session | Runs all fraud rules, decides, issues receipt `VRF-…`. `decision` ∈ `APPROVED`, `REVIEW`, `REJECTED`, `APPROVED_WITH_OVERRIDE`. |
| POST | `/verification/sessions/{id}/cancel` | Session | Terminal. |

### Staff override (break-glass)

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/staff/login` | — | `{nip, password}` → 8 h staff token. 5 failures per NIP → 15 min lockout, unknown NIPs counted identically. |
| GET | `/staff/me` | Staff | |
| POST | `/staff` · GET `/staff` · POST `/staff/{id}/deactivate` | Operator | Staff CRUD. Roles: `petugas`, `supervisor`, `investigator`, `admin`. |
| POST | `/verification/sessions/{id}/override/request` | Staff (petugas) + session | Multipart: `reason_code` (closed enum), `note` (required for `LAINNYA`), `evidence_bpjs`, `evidence_ktp` (encrypted at rest). Only from `rejected`. 30 min approval window. |
| POST | `/verification/sessions/{id}/override/approve` | Staff (supervisor) + session | Must be a **different** staff member (`403` otherwise). Commits as `APPROVED_WITH_OVERRIDE`; raises `MANUAL_OVERRIDE` and, past the weekly limit, `STAFF_OVERRIDE_FREQUENCY` (critical). |
| POST | `/verification/sessions/{id}/override/reject` | Staff (supervisor) | |
| GET | `/verification/sessions/{id}/override` | Session | Status of the request. |

### History

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/verification/history?cursor&status` | Firebase | The caller's own sessions, cursor-paginated. `404 PESERTA_NOT_FOUND` when unlinked. |
| GET | `/verification/history/{session_id}` | Firebase | Detail, owner only. |

### Fraud console

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/fraud/signals?status&severity` | Operator | Open signals. |
| POST | `/fraud/signals/{id}/resolve` | Operator | `{resolution, note}`. |
| GET | `/fraud/rules` | Operator | Rule catalogue with weights. |
| POST | `/fraud/check` | Operator | Dry-run rules against a session. |

### Content

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/articles?category&cursor` · GET `/articles/categories` · GET `/articles/{slug}` | — | Health articles. |
| POST | `/articles` · DELETE `/articles/{slug}` | Operator | |
| GET | `/symptoms/catalog` · POST `/symptoms/analyze` | — | Symptom checker; uses Ollama when reachable, otherwise a keyword fallback that says so. |

## Fraud rules

Weighted signals summed at commit. `≥ 70` → `REJECTED`, `≥ 40` → `REVIEW`, any
`critical` signal → `REJECTED` regardless of score.

| Rule | Severity / weight | Fires when |
|---|---|---|
| `SIMULTANEOUS_CLAIM` | critical | Same participant, different faskes, within 4 h |
| `IMPOSSIBLE_TRAVEL` | critical | Implied speed between two claims exceeds what a vehicle could do |
| `FACE_COLLISION` | critical | Probe matches another participant's template above threshold |
| `HIGH_FREQUENCY_CLAIM` | high | Too many claims in a rolling window |
| `REPEATED_FAILED_ATTEMPTS` | high | Failed biometric attempts across recent sessions |
| `MANUAL_OVERRIDE` | high / 25 | The claim was approved by override |
| `STAFF_OVERRIDE_FREQUENCY` | critical | One staff member over `OVERRIDE_STAFF_WEEKLY_LIMIT` in 7 days |
| `ACCOUNT_LINK_CONFLICT` | high / 30 | Someone tried to link an already-linked participant |
| `LOW_MATCH_MARGIN` | medium | Face score inside the review band |
| `SHARED_DEVICE` | medium | Device has been used by several participants |
| `PESERTA_MENUNGGAK` | medium, scales | Membership in arrears |
| `OFF_HOURS` | low | Non-emergency poli outside opening hours |
| `SOFTWARE_KEY_ONLY` | low / 10 | Fingerprint verified with a Tier A (HMAC) key |

## Error codes

Protocol: `PESERTA_NOT_FOUND`, `BIOMETRIC_NOT_ENROLLED`, `PESERTA_NONAKTIF`,
`SESSION_NOT_FOUND`, `SESSION_EXPIRED`, `SESSION_CLOSED`, `STEP_OUT_OF_ORDER`,
`INVALID_SESSION_TOKEN`, `UNAUTHENTICATED`, `FORBIDDEN`, `INVALID_API_KEY`,
`FASKES_NOT_FOUND`, `DEVICE_BLOCKED`, `DEVICE_NOT_ENROLLED`, `TOO_MANY_SESSIONS`,
`TOO_MANY_ATTEMPTS`, `IDENTITY_MISMATCH`, `BPJS_ALREADY_LINKED`,
`ACCOUNT_ALREADY_LINKED`, `IMAGE_TOO_LARGE`, `NO_FRAMES`, `MODEL_UNAVAILABLE`,
`ALREADY_ENROLLED`, `DUPLICATE_FACE`, `VALIDATION_ERROR`, `INTERNAL_ERROR`.

Business outcomes: `FACE_MISMATCH`, `NO_FACE_DETECTED`, `MULTIPLE_FACES`,
`LOW_QUALITY_BLUR`, `LOW_QUALITY_LIGHT`, `FACE_TOO_SMALL`, `LIVENESS_FAILED`,
`SPOOF_SUSPECTED`, `ENROLL_FRAMES_INCONSISTENT`, `MAX_ATTEMPTS`,
`SIGNATURE_INVALID`, `NONCE_REUSED`, `NONCE_EXPIRED`, `KEY_MISMATCH`,
`BIOMETRIC_CANCELLED`, `NO_BIOMETRIC_HARDWARE`, `ATTESTATION_FAILED`,
`REVIEW_NOT_CONFIRMED`, `STEPS_INCOMPLETE`.
