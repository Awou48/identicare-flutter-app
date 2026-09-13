# Security

What the system protects, how, and — just as important — what it does not yet
prove. Every control below names the attack it closes. Where a control is
partial, the gap is stated rather than implied away.

## Assets and adversaries

| Asset | Why it matters |
|---|---|
| Face templates (512-d ArcFace embeddings) | A biometric cannot be reissued. A leaked template is a permanent identifier and, against a public gallery, a re-identification key. |
| NIKs | 16-digit national ids; the space is small enough to brute-force offline from an unpeppered hash. |
| Device signing keys | Whoever holds one can pass the second factor. |
| The verification log | The product's output. If it can be altered or emptied, nothing else matters. |
| Staff credentials | The override path. |

Adversaries, in order of how much the design worries about them:

1. **The card-sharer** — a participant lending their card, or an impostor presenting it.
2. **The insider at a faskes** — staff enrolling a wrong face, or laundering claims through overrides.
3. **The rooted phone** — an attacker controlling the app process on their own device.
4. **The database thief** — a dump of Atlas, with or without the application server.
5. **The network attacker** — replaying or forging requests.

## Controls

### Face verification

| Control | Closes |
|---|---|
| ArcFace 1:1 cosine against the participant's own template, threshold 0.42 accept / 0.30 review | Impostor with the victim's card |
| 1:N sweep at every verification (`FACE_COLLISION`, critical) | The same face passing under two identities |
| Active liveness: server-issued **random, single-use** challenge, checked as change between frame 1 and frame 3 | Pre-recorded video (cannot know the direction chosen after recording); static photo (no motion, no challenge) |
| Motion, texture, moiré and colour signals | Printed photo, screen replay |
| Quality gate before inference | Wastes no attempts on unusable frames; separate budget so a shaky hand is not "three strikes" |
| 3 identity attempts per session, then `rejected` | Trying several faces |
| 5 sessions per participant per hour | Abandoning sessions to get unlimited attempts and nonces |

Not yet: a passive anti-spoof CNN. The available open model ships as an
unofficial PyTorch conversion; an unvetted binary on the critical path was
judged a worse risk than the one it mitigates. `LivenessBackend` is an
interface so one can be added without touching the router.

### Fingerprint (second factor)

The fingerprint is never captured, transmitted or stored. It is a **gate** on a
signature.

| Control | Closes |
|---|---|
| Canonical payload `identicare-v1\|session_id\|nonce\|device_uid\|no_bpjs\|timestamp` | Replaying a signature in another session, for another participant, from another device |
| Nonce consumed **before** signature verification, 120 s TTL, 60 s clock skew | Probing signatures against a still-valid nonce; replay |
| **Tier B**: EC P-256 key generated in the Android TEE, `setUserAuthenticationRequired(true)`, per-operation timeout, `BIOMETRIC_STRONG`, `setInvalidatedByBiometricEnrollment(true)`; signing only via `BiometricPrompt` `CryptoObject` | A patched APK or rooted process returning "authenticated" — the hardware, not the app, refuses to sign; adding a new finger to the phone destroys the key |
| Server evaluates the key attestation chain: leaf certifies **this** public key, challenge equals **this** `device_uid`, TEE-enforced list requires a fingerprint (`noAuthRequired` absent, `userAuthType` includes fingerprint) | A genuine TEE chain from a different key sent alongside a software key; a chain lifted from another device; a hardware key that signs without a biometric |
| **Tier A** fallback (HMAC, secret in secure storage) recorded as `security_level: SOFTWARE` and scored by `SOFTWARE_KEY_ONLY` | Presenting a software key as a hardware guarantee |
| Fallback only on *structural* failure, never on user cancel or lockout | "Press Batal" as a downgrade path |
| `/enrollment/device` requires a signed-in user; record stamped with the token's uid | Anyone who learns a `device_uid` overwriting its key with their own |

**Not yet proven:** the attestation chain is parsed but **not validated to the
Google Hardware Attestation Root**. `chain_verified` is stored as `false`. On a
stock phone the TEE's claim is strong; on a rooted phone with a patched
keystore it is worthless, and root validation is exactly what would catch
that. The next hardening step, and the docs and the database say so.

### Enrolment

| Control | Closes |
|---|---|
| **1:N de-duplication gate** before any template is activated; threshold 0.45, stricter than the in-claim 0.55 | Enrolling one face under two BPJS numbers — the poisoned enrolment that makes later fraud invisible |
| Duplicate attempt raises a **critical** `DUPLICATE_FACE` signal whether or not it succeeded | Silent retry until it passes |
| Pairwise frame consistency ≥ 0.70 | Two people in one burst |
| Assurance levels `SELF_ASSERTED` / `DUKCAPIL_VERIFIED` / `ASSISTED_DUAL_CONTROL`; self-asserted carries a claim ceiling | Self-enrolment underwriting a high-value claim |
| Cooling-off: template younger than 24 h cannot support a high-value claim | Enrol-and-claim in one visit |
| Four-eyes on assisted enrolment: approver ≠ capturer, enforced server-side | One insider doing both |
| Seeded placeholder templates (`PLACEHOLDER_*`) never count as enrolment anywhere | A participant "enrolled" against random noise |

### Account linking

Firebase Auth (login) and MongoDB `peserta` (BPJS record) are joined by
`peserta.firebase_uid`. Setting it is the one step that lets a login act as a
participant.

| Control | Closes |
|---|---|
| Proof of possession: BPJS number + NIK + date of birth, all printed on the physical cards | Linking to a number you merely know |
| One uniform `IDENTITY_MISMATCH` message for every wrong field, including "no such BPJS number" | Using the endpoint as an oracle to pair NIKs with BPJS numbers |
| 5 failures per account per hour | Walking the NIK space |
| One-time: a linked record cannot be re-linked from the app | Takeover of an existing account |
| A correct triple against an already-linked record raises `ACCOUNT_LINK_CONFLICT` (high) | The takeover attempt going unrecorded |
| Linking grants nothing by itself: claims still need a face that passes the dedup gate | Linking as a shortcut |

### Staff override

Designed so that the override is more expensive and more visible than the
fraud it could enable.

| Control | Closes |
|---|---|
| Two distinct authenticated staff; approver must hold `supervisor` | One stolen credential |
| Closed reason enum, free text mandatory for `LAINNYA` | Unanalysable overrides |
| Encrypted photographs of the physical KTP and BPJS card | Override without physical evidence |
| Decision recorded as `APPROVED_WITH_OVERRIDE`, never `APPROVED` | Laundering an override into a clean approval |
| Every override raises `MANUAL_OVERRIDE` (high, 25); `STAFF_OVERRIDE_FREQUENCY` escalates to critical past 5/week | A nurse overriding twenty times a day *is* the fraud, and this catches it |
| 30 min approval window; 8 h staff tokens | Stale requests |
| Staff login: 5 failures per NIP → 15 min lockout, unknown NIPs counted identically | Brute force from the participant's phone, where the login form is rendered; enumeration |

**Known weakness:** the override form lives on the participant's phone because
there is no faskes desk app yet. Every control above is server-side precisely
so the screen's location does not matter, but in production it belongs on a
staff terminal bound to a registered device (ARCHITECTURE.md §2).

### Data at rest

| Control | Closes |
|---|---|
| Per-document AES-256-GCM: each template sealed under its own DEK, DEK wrapped by a KEK that lives only in `keys/` or `KEK_B64`, never in the database | A database dump yields ciphertext only |
| AAD = `peserta_id\|template_id\|version` | Moving Alice's sealed template onto Bob's record and having it decrypt |
| 1:N search vectors stored as `R·v` for a secret orthogonal `R` derived from the KEK (HKDF-seeded QR); cosine is rotation-invariant | Matching a dumped search vector against a public ArcFace gallery; a Qdrant/vector-DB breach |
| NIK stored as `HMAC(pepper, nik)` with the pepper in env, plus last 4 digits for display | Offline brute force of 16-digit NIKs from a dump |
| Right to erasure zeroes ciphertext and search vector; crypto-shredding by DEK deletion is available by construction | Retention obligations under UU PDP 27/2022 |
| Sensitive keys redacted from logs | Templates in crash reports |

### Session integrity

| Control | Closes |
|---|---|
| Server-side state machine; every step calls `require_state`; advancing is a conditional update on the state that was read | Skipping the face step, replaying a passed step, two concurrent requests both advancing |
| Session tokens 32+ bytes, never in `GET` responses after creation | Guessing or leaking |
| Append-only `verification_events`; `session.steps` keeps only the last attempt, events keep them all | Editing history |
| Schema validators on every collection | Malformed writes from a bug |

### Authentication

| Control | Closes |
|---|---|
| Firebase ID tokens verified against Google's public keys: RS256 only, audience and issuer pinned, `kid` refreshed on unknown key, `auth_time` sanity | `alg: none`, tokens from another project, forged keys |
| Dev bypass (`Bearer dev:<uid>`) only when `IDENTICARE_ENV=dev`, logged loudly | Accidental deployment with the bypass live |
| Staff passwords scrypt with per-hash parameters | Rainbow tables; raising cost later without breaking old hashes |
| Role model is a set of permissions, not an ordering | A petugas reading the investigator console because "higher" |

## Secrets and their handling

| Secret | Where | Rotation consequence |
|---|---|---|
| `KEK` | `backend/keys/kek.bin` (gitignored) or `KEK_B64` | Losing it makes every stored template unreadable. Back it up separately from any database backup. |
| `NIK_PEPPER` | env | Changing it orphans every stored NIK hash. |
| `OPERATOR_API_KEY`, `FACILITY_API_KEYS` | env | Rotate freely. |
| Atlas credentials | `backend/.env` (gitignored) | Rotate in Atlas; nothing else stores them. |
| Firebase project id | not secret | Verification relies on Google's public keys, not on a service account. |

`backend/.env` and `backend/keys/` have never been committed. `firebase_options.dart` and `google-services.json` contain public client configuration only.

## What a reviewer should push on

These are the honest open items, in the order they should be closed:

1. Attestation chain validation to the Google root, plus verified-boot state from the same certificate.
2. A passive anti-spoof model behind `LivenessBackend`, and confirming the front-camera mirroring sign so turn direction can be made strict again (`STRICT_TURN_DIRECTION`).
3. Threshold calibration on a real population — 0.42 was chosen from ArcFace literature, not measured here.
4. Move the override UI to a registered staff device.
5. Dukcapil face-match integration for `DUKCAPIL_VERIFIED` enrolment.
