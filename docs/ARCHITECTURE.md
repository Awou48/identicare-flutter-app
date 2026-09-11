# IdentiCare — Architecture

**Biometric identity verification for BPJS Kesehatan claims.**

This is the engineering design record. It is written in English because it
references external specifications (HL7 FHIR, HNSW, WebAuthn, UU PDP) whose
terminology is English or legal-Indonesian; participant-facing copy, the data
layer doc ([`backend/docs/SCHEMA.md`](../backend/docs/SCHEMA.md)) and the refactor
audit ([`TODO.md`](../TODO.md)) stay in Indonesian. Domain terms keep their
Indonesian names throughout — *peserta*, *faskes*, *klaim*, *petugas*.

| Section | Status |
|---|---|
| [1. Enrolment identity proofing](#1-enrolment-identity-proofing) | **Implemented** |
| [2. Staff override / break-glass](#2-staff-override--break-glass) | **Implemented** |
| [3. Offline-first for 3T regions](#3-offline-first-for-3t-regions) | Designed |
| [4. Peripheral fingerprint scanners](#4-peripheral-fingerprint-scanners) | Designed |
| [5. Vector database and 1N scale](#5-vector-database-and-1n-scale) | Designed; interface in place |
| [6. HL7 FHIR and SATUSEHAT](#6-hl7-fhir-and-satusehat) | Designed |
| [7. Auditor console](#7-auditor-console) | Designed |
| [8. UU PDP compliance](#8-uu-pdp-compliance) | Designed |

---

## 0. What exists today

```
Flutter (Android)          FastAPI :8000                MongoDB
┌──────────────────┐      ┌────────────────────┐      ┌──────────────────┐
│ 4-step flow      │─────▶│ session state      │─────▶│ peserta          │
│  1 Scan Wajah    │      │   machine          │      │ biometric_       │
│  2 Scan Sidik    │      │ face_engine (ONNX) │      │   templates      │
│  3 Periksa Data  │      │ liveness           │      │ verification_    │
│  4 Verifikasi    │      │ matcher  1:1 / 1:N │      │   sessions       │
└──────────────────┘      │ fraud_rules (12)   │      │ verification_    │
         │                │ enrollment_service │      │   events         │
   Firebase Auth          │ override           │      │ fraud_signals    │
   (identity only)        └────────────────────┘      │ staff, consent … │
                                    │                 └──────────────────┘
                          keys/ kek.bin + rotation_v1.npy
                          models/ det_500m + w600k_r50 (ONNX)
```

**Two design decisions everything else rests on.**

*Hybrid datastore.* Firebase Auth stays the identity provider and Firestore keeps
the legacy `riwayat_konsultasi`. Everything BPJS and biometric lives in MongoDB
behind the Python API. `peserta.firebase_uid` is the only seam.

*Envelope encryption plus a secret rotation.* Each face template is 512 float32
sealed with AES-256-GCM under a per-document DEK, wrapped by a process-held KEK.
The GCM AAD binds the ciphertext to `{peserta_id}|{template_id}|v{version}`, so a
template cannot be transplanted onto another participant. Alongside it we store
`search_vector = R·v`, where `R` is a secret 512×512 orthogonal matrix derived
from the KEK via HKDF and never written to the database.

Because `R` is orthogonal:

```
(Rx)·(Ry) = xᵀRᵀRy = xᵀy       and      ‖Rx‖ = ‖x‖
⟹  cosine(Rx, Ry) ≡ cosine(x, y)      exactly, to float precision
```

So 1:N similarity search runs on rotated vectors with **zero decryptions and
identical scores**, while a database dump yields vectors in a basis that no
public ArcFace tool, no published embedding-inversion model and no other leaked
biometric database can consume.

> **State this honestly.** Rotation is distance-preserving *pseudonymisation*, not
> semantic security. An adversary holding ≥512 (plaintext, rotated) pairs recovers
> `R` by least squares. It is the same trick production face-recognition systems
> use for their search tier, and the AES-GCM blob — never `search_vector` — remains
> the record of truth for an accept/reject decision. Do not call it encryption.

---

## 1. Enrolment identity proofing

**Status: implemented.**

### The hole

Before this, `POST /api/v1/enrollment/face` required one shared static
`X-Api-Key` and performed **no duplicate check at all**. Anyone holding that key
could enrol their own face against someone else's `no_bpjs`.

That is the single most valuable attack against this system, and it is worse than
it first sounds: once the template is poisoned, every later verification succeeds
**correctly**. The biometric genuinely matches what is on file. Liveness passes.
The fraud rules see nothing anomalous. There is no artefact anywhere that says
anything is wrong. Every other control in the product — liveness, the state
machine, all twelve fraud rules — sits on top of enrolment, so poisoning it
defeats all of them at once and permanently.

### The design

Three controls, each independently useful.

**1. Mandatory 1:N de-duplication gate.** No template is activated until the face
has been swept against every active template. A hit above
`ENROLLMENT_DEDUP_THRESHOLD` belonging to a different participant is rejected
outright and raises a `critical` `DUPLICATE_ENROLLMENT_ATTEMPT` signal.

The sweep function already existed in
[`app/services/matcher.py`](../backend/app/services/matcher.py) — it simply was
never called on the enrolment path. This was a bug, not a missing feature.

The dedup threshold (0.45) is deliberately **stricter** than the in-claim
collision threshold (0.55). The costs are asymmetric: a false reject at enrolment
costs one retry, a false accept creates a permanently poisoned identity.

**2. Four-eyes.** Approval requires a different `staff_id` from the capturer,
checked server-side against the stored `captured_by`. A client asserting "I am a
different person" is worth nothing.

**3. Cooling-off.** A template younger than `ENROLLMENT_COOLING_HOURS` (24)
cannot underwrite a high-value claim. This bounds the damage even if 1 and 2 are
both defeated — a fraudulent enrolment cannot be monetised immediately.

### Assurance levels

Recorded on the template as `assurance`, with a claim ceiling per level.

| Level | How identity is proven | Ceiling |
|---|---|---|
| `SELF_ASSERTED` | App liveness burst + KTP photo, OCR the NIK, match the selfie against the KTP portrait | Rp 500,000 |
| `DUKCAPIL_VERIFIED` | NIK + face submitted to Dukcapil's national face-match service | none |
| `ASSISTED_DUAL_CONTROL` | At a faskes: one staff captures, a different supervisor approves; physical KTP and BPJS card photographed | none |

A template carrying **no** assurance predates this pipeline and is treated as
`SELF_ASSERTED` — the weakest level — rather than being silently granted full
trust. See `ceiling_for()` in
[`enrollment_service.py`](../backend/app/services/enrollment_service.py).

**Dukcapil is realistic, not aspirational.** Face-recognition verification against
the national population database went live at national scale in July 2026, when
SIM-card registration became biometric-only. An institutional face-match API and
an access-rights model therefore already exist; IdentiCare would use the same
pattern BPJS itself would use.

### State machine

```
draft → pending_dedup → pending_approval → approved → (template active)
               ↓                  ↓
      rejected_duplicate   rejected_review
```

A unique partial index on `enrollment_requests` allows only **one** in-flight
request per participant. Without it two concurrent requests could both clear the
dedup gate against a state that no longer held by the time either committed.

### Files

| File | Role |
|---|---|
| [`app/services/enrollment_service.py`](../backend/app/services/enrollment_service.py) | Gate, four-eyes, ceilings, cooling-off |
| [`app/routers/enrollment.py`](../backend/app/routers/enrollment.py) | `/enrollment/face` now gated; `/enrollment/face/probe` diagnostic |
| [`app/db_schema.py`](../backend/app/db_schema.py) | `enrollment_requests`, `assurance` on templates |

### Deferred

KTP OCR and the live Dukcapil call are stubbed as assurance levels but not
wired — both need credentials IdentiCare does not yet hold. The pipeline accepts
and records the level; a production deployment supplies the verifier.

### Top risk

The dedup gate is only as good as the threshold. Calibrate on real photographs
(`scripts/check_face_models.py --images DIR`) before trusting 0.45, and monitor
the rate of `DUPLICATE_ENROLLMENT_ATTEMPT` signals — a sudden cluster is either
an attack or a miscalibration, and the two must be distinguishable.

---

## 2. Staff override / break-glass

**Status: implemented.**

### The hole

Three failed face attempts rejected the session and that was the end of it. The
proposal itself names faces unscannable because of bruising or swelling, and
fingers unreadable after burns. So the system as built **denied care to exactly
the vulnerable groups it claims to serve.** In a trauma ward that is not an edge
case, it is Tuesday.

### Design principle

**The override must be more expensive and more visible than the happy path.**
Otherwise it stops being a safety valve and becomes the fraud mechanism — the
easiest route for an insider is always the one with the fewest checks.

### Flow

```
rejected ──request_override──▶ override_pending ──approve──▶ committed
  (petugas: reason + evidence)   (supervisor,      APPROVED_WITH_OVERRIDE
                                  must differ)
                                        └──reject──▶ override_rejected
```

`rejected` is therefore **no longer a terminal state**. `override_rejected` is.

Required to approve, all of them:

- an authenticated `petugas`,
- a **second, distinct** staff member holding `supervisor`,
- a `reason_code` from a closed enum — `CEDERA_WAJAH`, `LUKA_BAKAR_JARI`,
  `DISABILITAS`, `KEGAGALAN_PERANGKAT`, `PENCAHAYAAN_BURUK`, `LAINNYA`
  (free text mandatory, ≥10 characters, for `LAINNYA`),
- photographs of the physical BPJS card and KTP, AES-GCM encrypted with the AAD
  bound to the session,
- the already-recorded failed attempts in `verification_events`, snapshotted into
  `override.failed_evidence` so a reviewer does not have to reconstruct them.

A closed enum rather than free text alone is deliberate: spotting patterns across
staff and faskes is the entire reason for recording a reason, and free text is
unanalysable.

### The override is itself a fraud signal

| Rule | Severity | Weight | Fires when |
|---|---|---|---|
| `MANUAL_OVERRIDE` | high | 25 | any approved override |
| `STAFF_OVERRIDE_FREQUENCY` | **critical** | 35 | one staff member exceeds 5 overrides in 7 days |

Weight 25 alone still lands in `LOW`/`APPROVED` — an override is not an
accusation, and most are legitimate clinical reality. Combined with anything else
(arrears, a shared device) it crosses into `REVIEW`.

`STAFF_OVERRIDE_FREQUENCY` is **the** control that catches insider fraud. One
override is a bruised face. Twenty in a week from the same person is the override
being used as the mechanism, which is precisely the risk a break-glass path
introduces. Being `critical`, it forces `REJECTED` regardless of the arithmetic.

### Two details that matter

**The decision is `APPROVED_WITH_OVERRIDE`, never plain `APPROVED`.** A claim that
skipped biometric proof must stay distinguishable forever, in the audit log and
in BPJS reporting. Folding it into `APPROVED` would quietly erase the distinction
the whole feature exists to preserve.

**An override cannot overrule a fraud finding.** If the rules return `REJECTED` —
a duplicate claim, a face collision — the rejection stands. The override exists
for *failed biometrics*, not for overriding evidence of fraud.

**The approval window is extended to 30 minutes.** A nurse has to physically find
a supervisor; the normal 10-minute session TTL would make the feature unusable in
the exact situation it exists for. Requesting an override pushes `expires_at` out.

### Files

| File | Role |
|---|---|
| [`app/routers/override.py`](../backend/app/routers/override.py) | request / approve / reject / read |
| [`app/services/session_service.py`](../backend/app/services/session_service.py) | `override_pending`, `override_rejected`, `OVERRIDE_ELIGIBLE` |
| [`app/services/fraud_rules.py`](../backend/app/services/fraud_rules.py) | the two new rules |
| [`app/security/staff_auth.py`](../backend/app/security/staff_auth.py) | scrypt passwords, staff JWT, role grants |
| [`app/routers/staff.py`](../backend/app/routers/staff.py) | login, provisioning |

### Role model

Deliberately **not** a flat hierarchy. An `investigator` reads fraud cases but
must not approve a clinical override; a `petugas` must not read the investigator
console. A simple ordering would quietly grant both.

```
petugas       → {petugas}
supervisor    → {petugas, supervisor}
investigator  → {investigator}
admin         → everything
```

### Top risk

Override fatigue. If the biometric thresholds are too tight, staff will override
routinely, the signal will drown in noise, and the path becomes the default. Watch
the override rate per faskes in the auditor console (§7) and treat a rising rate
as a **threshold calibration problem**, not a staff discipline problem.

---

## 3. Offline-first for 3T regions

**Status: designed.**

### Correcting the premise

Two things in the original framing need fixing.

**"Biometric hashes" is the wrong concept.** Face embeddings are 512-dimensional
vectors compared by cosine similarity. They are not hashes — there is no exact
match, and you cannot look them up in a key-value store.

**Caching templates on the device to match offline is a severe regression.** It
turns a stolen phone into a stolen biometric database. Worse, it quietly destroys
the product's core claim: `SIMULTANEOUS_CLAIM`, `IMPOSSIBLE_TRAVEL` and
`FACE_COLLISION` all require the central database. A device matching locally
cannot detect that the same participant is claiming at two hospitals at once —
which is the fraud the system exists to stop.

### The design: store-and-forward with deferred verification

**No templates on the device. No local matching.** The risk is eliminated by
construction rather than mitigated.

```
offline:  capture → encrypt → queue locally → provisional receipt
online:   drain queue → full server pipeline (incl. ALL fraud rules)
          → confirmed | rejected_after_the_fact
```

- Flutter `sqflite` table `pending_verifications`: session payload, AES-GCM
  encrypted frames (key in Android Keystore), `captured_at_device`, device
  signature, faskes context.
- The claim issues a **provisional receipt**, visually and textually distinct
  (`VRF-P-…`), with copy stating that verification is pending.
- On reconnect the server runs the complete pipeline including every fraud rule.

### The question the brief skips

**What if deferred verification fails after care was already given?**

Care is never withheld and never retroactively denied — that is a clinical and
ethical line, not an engineering decision. The failure becomes a **financial**
dispute: a `DEFERRED_VERIFICATION_FAILED` case in the auditor console, with BPJS
recovering cost from the faskes, not from the patient. A system that could strand
a patient with a bill because a queue drained badly would be worse than no system.

### Bounds

| Control | Value | Why |
|---|---|---|
| Max queue age | 72 h | Provisional liability cannot grow without limit |
| Max queued claims | per-device cap | A device cannot mint unbounded provisional claims |
| Frame retention | deleted on verify or expiry | Biometric images must never accumulate on a handset |
| Clock | server records device **and** server timestamps | The device clock is untrusted; large skew is itself a signal |

### Acknowledged cost

Offline claims cannot detect simultaneous claims, impossible travel or face
collisions **at capture time** — only when the queue drains. That is the honest
trade for working in 3T regions, and the doc states it rather than hiding it. The
mitigation is that the window is bounded (72 h) and every deferred claim is
flagged for review, so the fraud is detected late rather than never.

---

## 4. Peripheral fingerprint scanners

**Status: designed. The original proposal for this one is technically wrong.**

### WebAuthn cannot do this

WebAuthn returns a signed **assertion** that *some* user authenticated to *an
origin* using a platform authenticator. It never exposes a fingerprint image, a
template, or minutiae. You therefore cannot:

- feed it into 1:N matching,
- prove *which* BPJS participant presented a finger,
- compare it against anything stored.

It authenticates a **session to a website**, not a **person to a biometric
record**. These are different problems.

WebAuthn *is* an excellent fit for **staff login to the auditor console** (§7) —
right tool, wrong problem.

### WebUSB is the wrong transport

- Chromium-only; no Firefox or Safari support.
- Requires an explicit user gesture per device, every session.
- Provides no driver stack — you would reimplement the vendor protocol.
- The scanners actually deployed in Indonesian faskes (Futronic FS80/FS88, HID
  U.are.U 4500, Mantra MFS100, Secugen Hamster) ship native Windows/Linux SDKs
  with no WebUSB-compatible interface.

There is also a modality mismatch worth naming: these devices emit **ISO 19794-2
/ ANSI-378 minutiae templates**, a fundamentally different representation from
our ArcFace face embeddings. They are not cosine-comparable. Fingerprint matching
needs its own matcher, not a reuse of the face pipeline.

### The realistic architecture: a signed native local agent

```
Browser ──https://agent.identicare.id:7443──▶ Local agent ──vendor SDK──▶ Scanner
   │         (real cert, DNS A → 127.0.0.1)        │
   └────────── pairing token from server ──────────┘
                                                   └──mTLS──▶ IdentiCare API
```

A small signed Windows service owns the vendor SDK and exposes localhost to the
browser. This is how every real Indonesian eKTP/BPJS fingerprint integration
works.

**The genuine engineering problem is localhost TLS.** Browsers will not trust a
self-signed localhost certificate, and `http://127.0.0.1` or `ws://localhost` are
blocked as mixed content from an HTTPS page. The only clean answer — the one
Zoom, Dropbox and commercial eKTP readers all use — is to ship a **genuine
certificate for a real domain whose public DNS A-record resolves to 127.0.0.1**.

The agent pairs to a desk session using a short-lived server-issued token, so an
arbitrary web page cannot drive the scanner.

### Recommendation

**Mobile-first via Platform Channels. The desk scanner is Phase 3.** The phone
already has a TEE-backed sensor with hardware-enforced user authentication — a
stronger guarantee than a USB scanner on a shared desktop, which cannot attest
that a human was present at all.

---

## 5. Vector database and 1:N scale

**Status: designed. `SearchBackend` interface implemented.**

### Honest numbers

| | |
|---|---|
| Embedding | 512-d float32 = **2,048 bytes** |
| BPJS participants | ~280,000,000 |
| Raw vectors | **≈ 573 GB** |
| Plus HNSW graph | ×1.5–2 → **~1 TB** |

The current implementation — `find()` over `biometric_templates` and cosine in
Python — is fine to roughly 100k templates, takes minutes at 1M, and is simply
impossible at 280M. The concern in the brief is correct.

### But 1:N is not on the claim critical path

This is the key insight the scaling concern usually misses. The normal claim flow
is **1:1**: the participant asserts a `no_bpjs` at session start, so the server
fetches exactly one document, decrypts it, computes one cosine (~8 ms) and wipes
the buffer. No search is involved.

1:N is needed for exactly two things:

| Use | Latency requirement |
|---|---|
| Enrolment de-duplication (§1) | Synchronous — it is a gate |
| Batch fraud sweeps | Asynchronous — can run nightly |

So **1:1 stays in MongoDB; only 1:N moves to a vector database.** That is a much
smaller change than "replace MongoDB".

### Qdrant, not Milvus

| | Qdrant | Milvus |
|---|---|---|
| Deployment | one Rust binary / one container | etcd + Pulsar + MinIO + coordinators |
| Ops burden | low | a cluster, not a dependency |
| Payload filtering | built in | built in |

For a solo-maintained project Milvus is the wrong shape. Qdrant gives HNSW and
filtered search with one container.

### The security property survives untouched

This is why the refactor is worth doing this way. We store **`R·v`**, not `v`.
Qdrant computes cosine on whatever vectors it is given, and cosine is invariant
under a shared orthogonal rotation, so:

- scores are **identical** to the current implementation,
- Qdrant never holds a canonical ArcFace embedding,
- a Qdrant breach yields basis-scrambled vectors,
- `R` stays in `backend/keys/`, outside the vector store entirely.

**Adopting a vector database costs zero security.** That is not obvious and is
worth stating explicitly.

### Parameters

```
collection: face_templates_rot_v1
vector:     size=512, distance=Cosine
hnsw:       m=32, ef_construct=256, ef_search=128
payload:    peserta_id, template_id, rotation_id, status, faskes_id
```

`rotation_id` must be a payload field and the collection name must be versioned,
because **a model upgrade or a re-rotation forces a full reindex** — vectors in
different bases are not comparable, and silently mixing them would produce
meaningless scores rather than an error.

### Interface

Already in place in
[`app/services/matcher.py`](../backend/app/services/matcher.py):

```python
class SearchBackend(Protocol):
    name: str
    async def upsert(self, *, template_id, peserta_id, rotated_vector) -> None: ...
    async def search(self, rotated_probe, *, threshold,
                     exclude_peserta_id=None, limit=5000) -> list[dict]: ...
```

`MongoScanBackend` is the default. `get_backend(db, rot, "qdrant")` currently
raises with a pointer to this section — a deliberate loud failure rather than a
silent fallback.

---

## 6. HL7 FHIR and SATUSEHAT

**Status: designed.**

SATUSEHAT is the Ministry of Health's national platform: a FHIR **R4** server
that facilities push clinical encounter data into.

| | |
|---|---|
| Sandbox | `https://api-satusehat-stg.dto.kemkes.go.id/fhir-r4/v1` |
| Production | `https://api-satusehat.kemkes.go.id/fhir-r4/v1` |
| Auth | OAuth2 client credentials |
| Scope | A mandated **subset** of FHIR resources, not all of it |

### Resource mapping

| IdentiCare | FHIR R4 | Note |
|---|---|---|
| `peserta` | `Patient` | `identifier` entries for the NIK and BPJS systems |
| membership (`kelas_rawat`, `jenis_peserta`, `status_kepesertaan`) | `Coverage` | |
| the claim / visit | `Encounter` | |
| `facilities` | `Organization` + `Location` | |
| **the verification event** | **`AuditEvent`** | see below |
| biometric consent | `Consent` | §8 |
| **`fraud_signals`** | **not transmitted** | see below |

**`AuditEvent`, not `Provenance`.** `Provenance` describes how a resource came to
be — its authorship and derivation. What we are recording is *an identity
verification was performed, by this agent, on this entity, with this outcome*,
which is exactly `AuditEvent`'s `agent` / `entity` / `outcome` / `recorded`
structure.

**Fraud signals are never sent.** They are BPJS-internal determinations, often
unconfirmed, frequently about *staff* rather than patients. Pushing them into the
national clinical record would be both inappropriate and potentially defamatory.
The boundary is deliberate.

### FHIR is a boundary, never in the domain

```
domain model ──▶ mappers.py ──▶ fhir_outbox ──▶ worker ──▶ SATUSEHAT
  (MongoDB)                    (MongoDB)                   (FHIR R4)
```

- `app/integrations/fhir/mappers.py` — pure functions, domain dict → FHIR dict.
- `app/integrations/fhir/client.py` — OAuth2 token cache, retry with backoff.
- `fhir_outbox` collection — `status`, `attempts`, `next_retry_at`, `payload`,
  `resource_type`, drained by a worker.

**The outbox is not optional.** SATUSEHAT availability must never block a claim
verification — a national platform having a bad afternoon cannot be allowed to
stop a patient being treated. At-least-once delivery with idempotency via
`Encounter.identifier`, plus an `fhir_resource_map` collection because SATUSEHAT
assigns its own resource IDs that we must correlate back to our ObjectIds.

### Top risk

Scope creep. Full FHIR conformance is enormous. Map the six resources above,
validate against the sandbox, and stop. Resist modelling anything SATUSEHAT does
not actually require.

---

## 7. Auditor console

**Status: designed.**

A web dashboard for BPJS investigators. The backend already exposes
`/fraud/signals`, `/fraud/check` and `/fraud/rules`.

**Stack:** Vite + React + TypeScript, TanStack Table for dense grids, Recharts
for charts, **MapLibre GL** for maps (open, no API key, unlike Mapbox).

### Views

**1. Triage queue.** Open signals sorted by severity × recency. Filter by rule,
faskes, date. Bulk assign.

**2. Case detail.** One session: the full `verification_events` timeline including
every failed attempt, biometric scores, the override record if any, and a map
showing both facilities for `SIMULTANEOUS_CLAIM` / `IMPOSSIBLE_TRAVEL`. Actions:
resolve, dismiss, escalate.

**3. Rule performance.** Per rule: fire count versus confirmed-vs-dismissed
ratio. **This is the most valuable view and the one people forget to build.** It
is what lets you tune the fraud weights with evidence instead of guesswork — a
rule that fires 400 times and is dismissed 395 times is not detecting fraud, it
is training investigators to ignore the queue.

**4. Faskes leaderboard.** Override rate, rejection rate, claims per participant,
ranked. This catches **institutional** fraud, which is the KPK's Rp 20 trillion
problem — individual participants defrauding BPJS one claim at a time does not
reach that figure; facilities systematically doing so does.

**5. Staff activity.** Per-staff override frequency, the UI surface for
`STAFF_OVERRIDE_FREQUENCY`.

### Endpoints to add

`GET /fraud/stats` · `GET /fraud/by-rule` · `GET /fraud/by-faskes` ·
`GET /fraud/by-staff` · case assignment and state transitions · staff CRUD
(partly exists in [`app/routers/staff.py`](../backend/app/routers/staff.py)).

### Auth

**WebAuthn** — a platform authenticator or hardware security key for investigator
login. This is the correct use of the API discussed in §4. Roles:
`investigator` (read, resolve assigned) · `supervisor` (reassign) ·
`admin` (staff and rule configuration).

---

## 8. UU PDP compliance

**Status: designed. Not raised in the original brief; included because omitting
it would be a serious gap for an Indonesian health system.**

**UU No. 27/2022 (Pelindungan Data Pribadi)** classifies biometric data as *data
pribadi spesifik* — alongside health, genetic and financial data — requiring
explicit, purpose-specific consent and stricter protection than ordinary personal
data. Biometric processing at this scale is high-risk processing by definition.

### Consent model

`consent` collection, per participant and per purpose:

| Field | Why |
|---|---|
| `purpose` | `biometric_enrollment` / `biometric_verification` / `fraud_analytics` — consent is purpose-specific, so one blanket flag is not compliant |
| `version`, `text_hash` | Proves **what** was agreed, not merely that something was. Without the hash you can show consent existed but not its content |
| `granted_at`, `granted_via`, `evidence` | Provenance of the consent itself |
| `revoked_at` | Revocation is a right, so it must be a first-class field |

Checked at enrolment **and** at every verification. A revoked consent hard-blocks.

### Erasure versus an immutable audit log

These appear to contradict: UU PDP grants a right to erasure, while fraud
investigation and health records require a durable audit trail.

**Resolved by crypto-shredding.** Delete the per-document DEK and the ciphertext
becomes unrecoverable — the biometric is genuinely gone — while the non-biometric
record that *a verification occurred at this time and place with this outcome*
survives. Both obligations are met.

The existing envelope design already makes this possible: because every template
carries its **own** DEK (see
[`app/security/crypto.py`](../backend/app/security/crypto.py)), one participant's
biometric can be destroyed without touching anyone else's. That was not an
accident.

### Retention

| Data | Retention |
|---|---|
| Face frames | **never stored** |
| Templates | until revocation |
| `verification_events` | 7 years (health record norm) |
| Consent records | permanent (needed to prove lawful basis) |

### Also required

- **72-hour breach notification** runbook, with a named responsible person.
- **DPIA** (*penilaian dampak pelindungan data*) before production — mandatory for
  high-risk processing.
- Data residency: biometric data for Indonesian citizens should remain in
  Indonesian jurisdiction.

---

## Roadmap

| Phase | Contents | Status |
|---|---|---|
| **1** | 4-step flow, ArcFace matching, liveness, 12 fraud rules, Android client | **Done** |
| **2** | Staff identity, enrolment proofing + dedup gate, break-glass override, `SearchBackend` interface | **Done** |
| **3** | Offline store-and-forward · auditor console · consent model | Next |
| **4** | Qdrant · FHIR/SATUSEHAT outbox · Tier B Keystore attestation | |
| **5** | Desk scanner agent · Dukcapil integration · DPIA and audit | |

## Known limitations

Stated plainly, because a design document that hides them is worse than none.

1. **Face thresholds are uncalibrated on real faces.** `FACE_MATCH_ACCEPT=0.42`
   is informed by the InsightFace defaults, not validated against a real
   population. Run `scripts/check_face_models.py --images DIR` on real
   photographs before any production or demo use.
2. **Fingerprint is Tier A (HMAC).** Honestly recorded as `security_level:
   SOFTWARE`, which raises `SOFTWARE_KEY_ONLY`. Tier B (Android Keystore EC P-256
   inside the TEE) is designed but not built.
3. **Liveness turn challenges are unvalidated on real devices.** The synthetic
   test fixtures cannot simulate head yaw; only `move_closer` and the negative
   cases are exercised. See the caveats in `scripts/_synth_faces.py`.
4. **Android only.** There is no `ios/` folder; web and desktop targets are gated
   off because `local_auth` and `camera` have no working implementation there.
5. **Firestore rules are written but not deployed,** and not yet tested against
   the emulator (no `firebase-tools`, no Java in the current environment).
6. **No load testing.** Latency figures here are single-request measurements on
   one laptop, not throughput under concurrency.
