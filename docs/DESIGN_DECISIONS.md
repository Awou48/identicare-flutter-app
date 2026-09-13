# Design decisions

The "why" behind the code. Most of these were shaped by a specific failure on a
real device; where that is the case the failure is described, because the
numbers in the code only make sense next to it.

---

## Face pipeline

### Detection and embedding run through onnxruntime directly

`insightface` has no Python 3.12 wheel on Windows and needs MSVC + Cython to
build. Its ONNX model files (`det_500m.onnx`, `w600k_r50.onnx`) do not need the
package at all: SCRFD pre/post-processing and ArcFace alignment are ~200 lines
of NumPy. `dlib`, `face_recognition`, `deepface`, `mediapipe` were rejected for
the same class of reason — build toolchains or multi-gigabyte dependencies for
something two ONNX graphs already do.

### Frames are downscaled to 640 px on the phone

The server detects at 640 and needs a face ≥ 112 px. A 12 MP upload is slower
on facility Wi-Fi and gains nothing. This choice has a consequence for the
quality gate, below.

### The blur gate judges the face crop, not the whole frame

Original whole-frame threshold: Laplacian variance ≥ 100, the number every
tutorial quotes. On the first device test every capture was rejected before
detection ran: whole-frame variance measured **19, 38, 43, 70, 76** in good
light (brightness ~115), because a 640 px selfie against a plain wall is mostly
wall, and wall has no edges. Enrolment had worked because that path never
applied the gate.

Now: whole frame ≥ 8 is a covered-lens sanity check only; sharpness is measured
on the detected face crop (`MIN_FACE_SHARPNESS = 20`). `test_quality_gate.py`
pins the calibration to the observed phone numbers.

### Quality failures have their own budget

Blur, dark, no face, too small, multiple faces say nothing about *who* is in
front of the camera. Charging them to the three identity attempts turned "hold
the phone steadier" into "session rejected, ask a nurse" on the third shaky
capture. They now consume `steps.face.quality_retries` (limit 10) instead of
`steps.face.attempts` (limit 3). Both are bounded so a session cannot be used to
probe the detector indefinitely; only the second is fraud evidence.

### Embedding is computed once, on the best frame

Detection is ~20 ms, embedding ~90 ms. All frames are detected (liveness needs
them all); only the frame with the best `det_score × sharpness` is embedded.
Single biggest latency win in the request.

---

## Liveness

### Active challenge over a passive CNN

The server issues a random, single-use challenge *before* capture. A
pre-recorded video cannot satisfy a direction chosen after it was recorded;
that property — not texture heuristics — is what defeats replay. The open
passive model (MiniFASNet) exists only as unofficial PyTorch→ONNX conversions,
and an unvetted binary on the critical path of a fraud-prevention system was
judged the worse risk. `LivenessBackend` is a protocol so one can be dropped in
later.

### Weights

Challenge 0.35, motion 0.20, texture 0.15, moiré 0.15, colour 0.15; pass at
0.70. Challenge dominates because it is the only signal an attacker cannot
satisfy in advance.

### Capture choreography: neutral frame first, then the instruction

Liveness is scored on the *change* between frame 1 and frame 3. The original
capture took three frames in 0.7 s the instant the button was tapped. A user
who had already turned, or who was still reading the instruction, produced
identical frames and a challenge score of 0 — total 0.49–0.51 against 0.70,
the exact pattern in the failed sessions. Now: "face straight" → frame 1 (900 ms
hold) → instruction shown → 1.1 s to turn → frames 2–3. The pre-tap overlay
tells the user what they *will* be asked so they do not act early.

### Turn direction is scored by magnitude, for now

`yaw_proxy()` is signed in image coordinates. Whether the front camera's still
is mirrored relative to the preview depends on the camera stack (Camera2 vs
CameraX vs vendor HAL), and a turn the wrong way scores as no turn. Until the
sign is confirmed on real devices the magnitude is scored
(`STRICT_TURN_DIRECTION = False`) and the signed shift is persisted in the
liveness signals on every failure so it can be confirmed from production data.
Cost while relaxed: a replayed video with a head turn satisfies both turn
challenges (2 of 3) — it still cannot satisfy `move_closer`, still has to pass
the other four signals, and still cannot be a static photo.

### Motion is a plateau, not a peak

A hand-held phone moves keypoints 2–8 px between frames 340 ms apart; a photo
on a stand moves 0. An earlier curve peaked at 20 px and scored real captures at
0.15. Everything from a steady hand to a lively one is equally alive, so the
score is flat across that band and falls off only at the implausible extremes
(< 0.5 px: printed photo; > 40 px: a cut or swapped image).

### Per-signal breakdown is persisted on failure

A liveness score of "0.49" is undiagnosable. `steps.face.liveness_signals` now
keeps every component plus the raw yaw shift and area growth, and the failure
reason names the weakest signal.

---

## Fingerprint

### A boolean is not a second factor

`local_auth.authenticate()` returns `true`/`false`. A boolean over the network
can be produced by any process that controls the app. So the sensor is a *gate*
on a *signature* over a server nonce, and what the server verifies is the
signature.

### Tier A → Tier B

Tier A (HMAC with a secret in secure storage) proved the flow but the secret is
extractable, so the server records it as `SOFTWARE` and scores it. Tier B puts
the key in the TEE and lets the hardware enforce the biometric. Tier A remains
as a fallback for structural failures only — never on user cancel or lockout,
which would make "press Batal" a way to lower the security level.

### What the server trusts about the key comes from the certificate

The app *says* it set `setUserAuthenticationRequired(true)`. The server reads
the TEE-enforced authorization list in the attestation certificate instead:
`noAuthRequired` (tag 503) or `userAuthType` (tag 504) with the fingerprint
bit. It also checks the leaf certifies the exact public key that was sent and
carries this `device_uid` as its challenge. The KeyDescription parser is a
hand-written DER walker because pyasn1's schema-less decoder rejects the empty
`AuthorizationList` sequences real keys carry.

### `MainActivity` is a `FlutterFragmentActivity`

`BiometricPrompt` can only be shown from a `FragmentActivity`. With a plain
`FlutterActivity`, `authenticate()` threw `no_fragment_activity` before any
prompt appeared, and a catch-all mapped it to "dibatalkan". Every platform code
now has its own message, and the raw code is kept for logs.

### The device key is registered at every session start

`POST /enrollment/device` is an idempotent upsert, cheap enough to call each
time. A "registered" flag on the phone would go stale the moment the server
database was reset — which, during development, it was.

---

## Sessions and outcomes

### Business outcomes are HTTP 200

A face mismatch is the system working correctly. Returned as 4xx it is
swallowed by generic error handling and the user sees "something went wrong"
instead of a score and remaining attempts. Protocol errors (wrong state,
missing token) are 4xx; outcomes are `200 {result: "failed"}`.

### The state machine lives on the server

Every step calls `require_state`; advancing is a conditional update on the
state that was read. The UI uses an `IndexedStack`, never a `PageView`, so a
swipe cannot skip a step — but the guard is server-side, and the client's job
is only to mirror it. One consequence: `IndexedStack` builds all children, so
steps 3 and 4 must check `currentStep` before auto-fetching, or they fire
`review`/`commit` against a `created` session and the 409 lands on the face
screen.

### Sessions per hour is a setting

Five per participant per hour is right for production (it caps fresh nonces and
attempts for someone abandoning sessions) and wrong for a developer on a phone.
`SESSIONS_PER_HOUR`, 30 in the dev `.env`.

---

## Identity and enrolment

### Account linking is proof of possession

Firebase Auth and the BPJS record are joined by one field, and before
`/peserta/link` existed only the operator endpoint could set it — every real
user ended at "Akun belum tertaut BPJS" on three screens with a retry button
that could never succeed. The link asks for the triple printed on the physical
cards (the same triple Mobile JKN asks at registration). It is not strong
evidence on its own; the strength is in what surrounds it: one-time, rate
limited, uniform error, conflict → fraud signal, and a link grants nothing until
a face passes the dedup gate.

### Seeded placeholders are not enrolments

`seed_peserta.py` writes a random unit vector per participant so the
encrypt/rotate/search pipeline can be exercised before any real face exists.
On the first device test the linked participant therefore showed "enrolled",
was never offered self-enrolment, and every match scored cosine ~0.05. Anything
tagged `PLACEHOLDER_*` is now excluded by `get_active_template()` and the 1:N
sweep; enrolment status comes from the template, not the `biometric_enrolled`
flag; self-enrolment may overwrite a placeholder.

### Dedup at enrolment is stricter than collision at claim

0.45 vs 0.55. A false reject at enrolment costs one retry; a false accept
creates a permanently poisoned identity.

### Missing assurance is the weakest assurance

Templates enrolled before the assurance pipeline carry no level. They are
treated as `SELF_ASSERTED` rather than silently granted full trust.

---

## Cryptography

### Envelope encryption with AAD

Per-document DEK under a KEK, AAD `peserta_id|template_id|version`. The AAD is
what stops a sealed template being moved between records. Per-document DEKs
also make crypto-shredding (delete the DEK, the ciphertext is gone) free —
which is how erasure and an immutable audit log coexist.

### Rotated search vectors

Cosine is invariant under a shared orthogonal rotation, so storing `R·v` gives
identical 1:N scores while a dump yields basis-scrambled vectors. `R` is
derived from the KEK by HKDF-seeded QR, so it can be regenerated from the KEK
alone; a container with only `KEK_B64` derives it at startup, and it was
verified bit-identical between Windows and Linux NumPy builds.

### NIK: HMAC with a pepper in env

16 digits is a brute-forceable space. The pepper never touches the database, so
a dump alone cannot be reversed. Last 4 digits are stored in clear for display.

---

## App

### Buttons had zero horizontal padding

The theme set `padding: symmetric(vertical: 16)` on Filled/Elevated/Outlined
buttons. Full-width buttons hid it; any button sized to its label ("Login
Petugas", "Ajukan Override") looked cramped. Fixed once in the theme.

### The camera preview must be clipped

`FittedBox.cover` scales the preview past its box and, unclipped, paints over
the step indicator and app bar. `Clip.hardEdge`.

### Nested `GridView` gets `padding: EdgeInsets.zero`

A scroll view without explicit padding absorbs the `MediaQuery` safe-area
inset — on a phone with a status bar, ~48 px of blank space under "Layanan".

### The override screen says who it is for

It lives on the participant's phone because there is no desk app yet. The
banner says "serahkan ponsel ke petugas", and every control is server-side so
the screen's location does not matter to security.

### Localisation

`flutter_localizations` with `id_ID` so Material widgets (date picker, dialogs)
are Indonesian. Required `intl ^0.20`.

---

## Things deliberately not done

- **Templates on the device / local matching** for offline use. A stolen phone would be a stolen biometric database. Offline is store-and-forward with deferred verification (ARCHITECTURE.md §3).
- **WebAuthn for fingerprint capture.** It returns a signed assertion, never a template; it cannot feed 1:N matching. Right tool for staff login to the console, wrong tool for this.
- **WebUSB for desk scanners.** Chromium-only, a gesture per device, no driver stack. A signed native local agent is the realistic path.
- **Milvus.** A cluster (etcd + Pulsar + MinIO) for a solo developer. Qdrant is one binary, and `SearchBackend` is the seam.
- **Fraud signals in FHIR.** Fraud determinations are BPJS-internal; the national clinical record is not the place for them.
