# IdentiCare — Desain Skema MongoDB

Database: `identicare` · 9 koleksi · sumber tunggal kebenaran: [`app/db_schema.py`](../app/db_schema.py)

Dokumen ini menjelaskan **mengapa** skema berbentuk seperti ini. Definisi yang
dieksekusi ada di `app/db_schema.py`; kalau keduanya berbeda, kode yang benar.

---

## Konvensi

| Aturan | Alasan |
|---|---|
| Semua timestamp `BSON date` dalam **UTC** | Klien Flutter merender WIB. Menyimpan waktu lokal membuat aturan fraud lintas-zona (impossible travel) salah hitung. |
| `no_bpjs` dan NIK disimpan sebagai **string** | NIK 16 digit melebihi presisi `double` BSON. Sebagai angka, `3174050412010001` bisa berubah diam-diam menjadi `3174050412010000` — identitas yang salah, tanpa error. |
| Validator `validationLevel: "moderate"` | Menolak insert yang salah, tetapi tidak memblokir update pada dokumen lama saat skema berubah. |
| Field `seeded: true` pada data contoh | Agar `seed_peserta.py --reset` bisa membersihkan tanpa menyentuh data nyata. |

---

## 1. Ketegangan desain utama: enkripsi vs pencocokan

Ini keputusan terpenting dalam skema, dan satu-satunya yang benar-benar sulit.

**Masalahnya.** Proposal menjanjikan "penyimpanan data biometrik yang telah
dienkripsi". Tetapi verifikasi wajah adalah perhitungan *cosine similarity* antara
dua vektor 512 dimensi — dan **cosine tidak bisa dihitung di atas ciphertext AES**.
AES bukan skema homomorfik. Skema yang benar-benar homomorfik (CKKS/SEAL) adalah
proyek berminggu-minggu dengan latensi sekitar 100 kali lipat, dan itu berarti
tidak ada demo.

Sekaligus, mesin fraud harus bisa menjawab *"apakah wajah ini sudah terdaftar
dengan nomor BPJS lain?"* — yaitu sweep 1:N ke seluruh peserta terdaftar.
Mendekripsi seluruh koleksi untuk itu jelas menghapus manfaat enkripsinya.

**Penyelesaian, tiga bagian.**

### (1) Envelope encryption adalah catatan resmi

Setiap template menyimpan 512 float32 mentah (2048 byte, little-endian) yang
disegel dengan AES-256-GCM memakai **DEK acak per dokumen**, dan DEK itu sendiri
dibungkus oleh KEK yang dipegang proses (`backend/keys/kek.bin`, tidak pernah
masuk MongoDB).

AAD GCM-nya **mengikat ciphertext ke dokumen pemiliknya**:

```
aad = f"{peserta_id}|{template_id}|v{version}"
```

Konsekuensinya konkret: penyerang yang punya akses tulis ke MongoDB **tidak bisa**
memindahkan template Alice ke record Bob. Dekripsi akan gagal autentikasi, bukan
diam-diam berhasil. Tanpa AAD, serangan itu sepele dan fatal — orang lain bisa
mengklaim BPJS Bob dengan wajah Alice.

Diuji di [`tests/test_crypto_roundtrip.py`](../tests/test_crypto_roundtrip.py)
(`test_aad_binds_ciphertext_to_its_document`).

### (2) Verifikasi normal adalah 1:1, jadi hanya satu dekripsi terjadi

Peserta menyatakan identitasnya lebih dulu (nomor BPJS di awal sesi). Jadi server
mengambil **satu** dokumen, membuka DEK-nya, mendekripsi ke array NumPy di memori,
menghitung satu cosine, lalu menimpa buffer-nya (`crypto.wipe`).

Tidak ada table scan. Tidak ada plaintext yang tersimpan. Biayanya sekitar 0,1 ms.
Klaim "biometrik terenkripsi saat disimpan" sepenuhnya benar.

### (3) Untuk sweep 1:N, simpan search vector yang dirotasi

Di samping ciphertext, kita simpan `search_vector = R · v`, dengan `R` adalah
matriks ortogonal rahasia 512×512 (Q dari dekomposisi QR matriks Gaussian,
di-seed lewat `HKDF(KEK, "identicare-rotation-v1")`, disimpan di
`keys/rotation_v1.npy`, **tidak pernah di MongoDB**).

Karena `R` ortogonal (`RᵀR = I`):

```
(Rx)·(Ry) = xᵀRᵀRy = xᵀy        dan        ‖Rx‖ = ‖x‖
⟹  cosine(Rx, Ry) ≡ cosine(x, y)     persis, sampai presisi float
```

Jadi pertanyaan *"apakah wajah ini sudah ada dengan `no_bpjs` lain?"* dijawab
dengan cosine scan biasa di atas `search_vector` — **skor identik, nol dekripsi**.
Dan karena bentuknya tetap array float biasa, ini pindah tanpa perubahan ke
`$vectorSearch` Atlas kalau nanti naik ke sana.

Diuji di [`tests/test_rotation_invariance.py`](../tests/test_rotation_invariance.py)
dengan toleransi 1e-6 atas 400 pasang vektor acak.

### Batasnya, dinyatakan terus terang

Rotasi adalah **pseudonimisasi yang mempertahankan jarak, bukan keamanan
semantik**. Jangan pernah menyebutnya "enkripsi" di presentasi.

- Penyerang yang memperoleh ≥512 pasang (plaintext, rotated) bisa memulihkan `R`
  lewat least squares.
- Penyerang yang punya `R` **dan** dump database memperoleh seluruh template asli.

Yang benar-benar dibeli oleh rotasi: dump yang bocor berisi vektor dalam basis
yang **tidak bisa dikonsumsi** oleh tool ArcFace publik mana pun, tidak bisa
dibalik oleh model embedding-inversion yang dipublikasikan, dan tidak bisa
di-cross-match dengan database biometrik bocor lainnya. Semua serangan itu
bergantung pada vektor berada di basis kanonik model. Itu properti nyata dan
berguna, dan ini persis lapisan yang dipakai sistem FRT produksi.

Maka aturannya:

- `R` hanya hidup di `keys/`, tidak pernah di database maupun backup database.
- Gambar sumber enrolment dan embedding plaintext **tidak pernah** disimpan.
- `R` dibuat ulang setiap kali versi model berubah.
- Blob AES-GCM — **bukan** `search_vector` — yang menjadi dasar keputusan
  terima/tolak.

Klaim yang jujur dan bisa dipertahankan: *"terenkripsi AES-256-GCM saat disimpan,
didekripsi di memori hanya untuk satu perbandingan 1:1, dengan index
ter-pseudonimisasi rotasi untuk sweep 1:N."*

### Kenapa NIK diperlakukan berbeda

NIK butuh **pencarian persis** (cari peserta berdasarkan NIK), yang tidak bisa
dilakukan atas ciphertext. Jadi NIK disimpan tiga kali dengan tiga tujuan:

| Field | Bentuk | Untuk apa |
|---|---|---|
| `nik_hash` | SHA-256(pepper + NIK) | Pencarian persis. Ber-index unik. |
| `nik_enc` | Envelope AES-256-GCM | Ditampilkan di langkah 3 setelah kedua faktor biometrik lolos. |
| `nik_last4` | 4 digit terakhir | Masking UI tanpa perlu dekripsi. |

**Pepper wajib, dan wajib di environment, bukan di database.** SHA-256 telanjang
atas NIK tidak berguna: ruangnya hanya 16 digit dengan struktur berat (kode
provinsi dan tanggal lahir ter-encode di dalamnya), jadi dump akan jatuh ke brute
force offline dalam hitungan detik. Dengan pepper di `.env`, dump database saja
tidak cukup.

> Mengubah `NIK_PEPPER` setelah ada data akan membatalkan **seluruh** `nik_hash`
> yang tersimpan. Tetapkan sekali, sebelum data nyata masuk.

---

## 2. Koleksi

### `peserta` — peserta BPJS

```jsonc
{
  "no_bpjs": "0001234567890",                   // 13 digit, unik
  "nik_hash": "hex sha256(pepper + nik)",       // unik, tidak reversibel
  "nik_enc":  { /* envelope AES-256-GCM */ },
  "nik_last4": "0001",
  "nama_lengkap": "Marcel Iliantino",
  "tanggal_lahir": ISODate("2001-12-04"),
  "jenis_kelamin": "L",                          // L | P
  "alamat": { "jalan", "kelurahan", "kecamatan", "kota", "provinsi", "kode_pos" },
  "no_hp_enc": { /* envelope */ },
  "kelas_rawat": 1,                              // 1 | 2 | 3
  "jenis_peserta": "PPU",                        // PBI | PPU | PBPU | BP
  "faskes_tingkat1": { "faskes_id": ObjectId, "nama": "Puskesmas Kebayoran Baru" },
  "status_kepesertaan": "AKTIF",                 // AKTIF | NONAKTIF | MENUNGGAK
  "tunggakan_bulan": 0,
  "eligibility_score": 100,                      // 0-100
  "firebase_uid": "abc123",                      // nullable; jembatan ke Firebase Auth
  "biometric_enrolled": true,
  "biometric_enrolled_at": ISODate,
  "created_at": ISODate, "updated_at": ISODate, "schema_version": 1
}
```

Index: `no_bpjs` unik · `nik_hash` unik · `firebase_uid` unik partial (hanya saat
bertipe string, supaya banyak peserta boleh `null`) · `faskes_tingkat1.faskes_id +
status_kepesertaan` · text index `nama_lengkap` untuk pencarian admin.

`firebase_uid` adalah **satu-satunya titik jahit** antara Firebase Auth dan
MongoDB. Ini yang membuat keputusan database hibrida bekerja: login tetap di
Firebase, seluruh data BPJS dan biometrik di MongoDB.

### `biometric_templates`

Dua bentuk dokumen dibedakan oleh `modality`.

**`modality: "face"`** — rahasia, jadi dienkripsi:

```jsonc
{
  "peserta_id": ObjectId, "modality": "face", "version": 1,
  "model": { "name": "arcface_w600k_r50", "dim": 512, "normalized": true },
  "enc": {                                   // (1) catatan resmi
    "alg": "AES-256-GCM", "kek_id": "kek-v1",
    "dek_wrapped": BinData, "dek_nonce": BinData(12),
    "nonce": BinData(12), "ciphertext": BinData(2048 + 16),
    "aad": "6712ab...|6712cd...|v1"
  },
  "search_vector": [Double x 512],            // (3) R.v — cosine-ekuivalen
  "rotation_id": "rot-v1",
  "quality": { "det_score": 0.97, "blur_var": 214.5, "face_px": 312, "yaw": -3.1 },
  "enroll_meta": { "frames_used": 3, "device_id": ObjectId, "operator_uid": "..." },
  "status": "active",                          // active | revoked | superseded
  "created_at": ISODate, "revoked_at": null
}
```

**`modality: "fingerprint_key"`** — hanya kunci **publik**, jadi tidak ada yang
perlu dienkripsi:

```jsonc
{
  "peserta_id": ObjectId, "modality": "fingerprint_key",
  "device_id": ObjectId, "public_key_der": BinData, "curve": "P-256",
  "attestation": { "security_level": "TEE", "verified_boot": "GREEN",
                   "user_auth_required": true, "chain_verified": true },
  "status": "active"
}
```

Kunci privatnya dibuat **di dalam TEE perangkat dan tidak bisa diekspor**. Server
tidak pernah melihatnya, dan memang tidak perlu.

Index: `{peserta_id, modality, status}` untuk lookup 1:1 · `{status, modality}`
untuk sweep 1:N · `{created_at: -1}`.

### `devices`

`device_uid` = `sha256(ANDROID_ID + salt instalasi)`. Field `peserta_ids` adalah
array: **lebih dari satu peserta pada satu perangkat memicu sinyal fraud
`SHARED_DEVICE`**. Menyimpannya sebagai array, bukan field tunggal, adalah yang
membuat aturan itu mungkin sama sekali.

`trust_level`: `hardware` (attestation Keystore terverifikasi) | `software`
(jalur HMAC Tier A) | `untrusted`.

### `facilities` — **dari sinilah "lokasi" berasal**

Requirement meminta log verifikasi mencatat lokasi. Sumbernya bukan GPS ponsel
(mudah dipalsukan, dan sering tidak tersedia di dalam gedung rumah sakit), tetapi
faskes tempat klaim diajukan.

```jsonc
{ "kode_faskes": "0110R001", "nama": "RS Harapan Kita", "jenis": "RS_TIPE_A",
  "tingkat": 2, "kota": "Jakarta Barat", "provinsi": "DKI Jakarta",
  "geo": { "type": "Point", "coordinates": [106.7996, -6.1789] },   // [lng, lat]
  "api_key_hash": "...", "active": true }
```

> GeoJSON memakai urutan **[longitude, latitude]** — kebalikan dari cara orang
> menyebutnya. Tertukar akan menempatkan Jakarta di Samudra Hindia dan membuat
> `IMPOSSIBLE_TRAVEL` menyala terus.

Index `2dsphere` pada `geo` yang membuat cek impossible travel cukup satu
`$geoNear`. Data seed sengaja memuat Puskesmas Wamena (Papua Pegunungan) supaya
aturan itu bisa didemokan dengan jarak nyata ~3.500 km.

### `verification_sessions` — objek yang menyatukan 4 langkah

```jsonc
{
  "_id": ObjectId,                     // = session_id yang dilihat Flutter
  "session_token": "hex 32",           // bearer buram, unik, tidak bisa ditebak
  "status": "created",
  "peserta_id": ObjectId, "no_bpjs": "0001234567890",
  "claim": { "claim_ref", "jenis_layanan", "poli", "estimasi_biaya" },
  "context": {
    "faskes_id": ObjectId, "kode_faskes": "0110R001",
    "channel": "mobile_app", "device_id": ObjectId, "device_uid": "...",
    "firebase_uid": "...", "app_version": "1.1.0+3", "ip": "192.168.0.44",
    "location": { "source": "faskes",              // faskes | gps | ip
                  "geo": {"type":"Point","coordinates":[106.7996,-6.1789]},
                  "label": "RS Harapan Kita, Jakarta Barat" }
  },
  "required_steps": ["face", "fingerprint", "review"],
  "nonce": "hex 32", "nonce_expires_at": ISODate,
  "steps": {
    "face":        { "status":"passed", "at":ISODate, "attempts":1,
                     "match_score":0.514, "threshold":0.42,
                     "liveness_score":0.88, "liveness_method":"active_challenge_v1",
                     "template_id":ObjectId, "latency_ms":186 },
    "fingerprint": { "status":"passed", "method":"android_keystore_ec_p256",
                     "security_level":"TEE", "signature_verified":true },
    "review":      { "status":"passed", "fields_shown":[...], "confirmed_by":"peserta" },
    "commit":      { "status":"passed", "decision":"APPROVED" }
  },
  "risk": { "score": 12, "band": "LOW", "signals": [] },
  "result": { "decision":"APPROVED", "reason_code":null,
              "receipt_no":"VRF-20260908-000123", "decided_at":ISODate },
  "created_at": ISODate, "updated_at": ISODate, "expires_at": ISODate
}
```

State machine:

```
created ──face──> face_passed ──fp──> fingerprint_passed ──review──> reviewed ──commit──> committed
   │                    │                      │                        │
   └────────────────────┴──────────────────────┴────────────────────────┴──> rejected | expired | cancelled
```

Alasan state ada di server, bukan di klien: kalau empat layar Flutter sekadar
memanggil empat endpoint independen, penyerang cukup **tidak memanggil** endpoint
liveness. Setiap endpoint langkah dijaga `require_state()`; memanggil
`/fingerprint` saat `status == "created"` menghasilkan `409 STEP_OUT_OF_ORDER`.
Klien hanya membawa `session_id` + `session_token`.

#### ⚠ Perangkap TTL

```js
{ expires_at: 1 },
{ expireAfterSeconds: 0, partialFilterExpression: { status: "created" } }
```

`partialFilterExpression` di sini **wajib**. TTL biasa akan menghapus sesi yang
sudah `committed` — yaitu log audit verifikasi permanen, satu-satunya hal yang
produk ini seharusnya hasilkan. Tidak ada error yang muncul; riwayat hanya
perlahan kosong. Diassert di
[`tests/test_schema_indexes.py`](../tests/test_schema_indexes.py)
(`test_ttl_on_sessions_is_partial`).

Sebaliknya `nonces` memang TTL penuh: nonce kedaluwarsa tidak punya nilai audit,
karena `verification_events` sudah mencatat bahwa ia dipakai.

### `verification_events` — log forensik append-only

Satu dokumen per percobaan, **termasuk yang gagal**. Ini disengaja: scan wajah
yang gagal justru sinyal yang paling dicari mesin fraud, sedangkan
`verification_sessions.steps` hanya menyimpan percobaan terakhir.

`{session_id, seq}` unik → mencegah duplikasi event saat retry jaringan.
Index `2dsphere` pada `geo` → agregasi peta sebaran percobaan gagal.

### `fraud_signals`

Satu dokumen per aturan yang menyala, dengan `weight` yang menyumbang ke skor
0–100 dan `status` untuk antrean triase petugas (`open → reviewing → confirmed |
dismissed`).

| rule_id | Kondisi | Bobot |
|---|---|---|
| `SIMULTANEOUS_CLAIM` | sesi lain peserta sama, faskes beda, < 4 jam | 40 (critical) |
| `FACE_COLLISION` | sweep 1:N menemukan cosine ≥ 0.55 di peserta lain | 35 (critical) |
| `IMPOSSIBLE_TRAVEL` | jarak `$geoNear` / waktu > 120 km/jam | 30 |
| `HIGH_FREQUENCY_CLAIM` | > 8 sesi disetujui dalam 30 hari | 25 |
| `SHARED_DEVICE` | satu `device_uid` untuk ≥ 3 peserta dalam 7 hari | 20 |
| `PESERTA_MENUNGGAK` | `tunggakan_bulan > 0` | 15 |
| `REPEATED_FAILED_ATTEMPTS` | ≥ 5 event wajah gagal dalam 24 jam | 15 |
| `LOW_MATCH_MARGIN` | skor di pita 0.30–0.42 | 10 |
| `SOFTWARE_KEY_ONLY` | sidik jari `security_level: SOFTWARE` | 10 |
| `OFF_HOURS` | commit 00:00–05:00 WIB di poli non-darurat | 5 |

Band: 0–39 LOW → APPROVED · 40–69 MEDIUM → REVIEW · ≥70 atau ada critical → REJECTED.

### `nonces` dan `audit_log`

`nonces`: `_id` **adalah** nonce hex-nya, sehingga konsumsi menjadi satu operasi
atomik dan itulah pertahanan replay:

```js
findOneAndUpdate({ _id: nonce, used: false }, { $set: { used: true } })
```

Kembali `null` → nonce sudah dipakai → `NONCE_REUSED`. Tanpa keunikan `_id`, dua
request paralel bisa sama-sama lolos.

`audit_log`: setiap dekripsi template biometrik atau NIK dicatat (siapa, untuk
apa, sesi mana). Tanpa ini, klaim "kami melindungi data biometrik" tidak bisa
dibuktikan ke auditor mana pun.

---

## 3. Menjalankan

```bash
docker compose -f backend/docker-compose.yml up -d
python backend/scripts/gen_keys.py
python backend/scripts/bootstrap.py          # idempoten; jalankan dua kali
python backend/scripts/seed_peserta.py
pytest backend/tests -q
```

`bootstrap.py` memakai `collMod`, jadi mengubah validator di `app/db_schema.py`
lalu menjalankan ulang akan menerapkan perubahannya tanpa migrasi manual.

Inspeksi visual: <http://localhost:8081> (mongo-express).

> Embedding hasil seed adalah **vektor acak, bukan wajah**. Vektor itu menguji
> jalur enkripsi, rotasi dan penyimpanan; ia tidak akan pernah cocok dengan foto
> asli. Enrolment sungguhan datang di Step 3 lewat `POST /api/v1/enrollment/face`.

## 4. Kehilangan kunci

| Yang hilang | Akibat | Pemulihan |
|---|---|---|
| `keys/rotation_v1.npy` | Sweep 1:N mati; verifikasi 1:1 tetap jalan | Turunkan ulang dari KEK — deterministik, hasilnya identik |
| `keys/kek.bin` | **Seluruh template dan NIK tidak dapat dibaca selamanya** | Tidak ada. Backup terpisah dari backup database. |
| `NIK_PEPPER` | Semua `nik_hash` jadi tidak cocok; pencarian NIK mati | Tidak ada tanpa NIK asli. Tetapkan sekali di awal. |

KEK dan backup database **tidak boleh** disimpan di tempat yang sama — kalau
keduanya bocor bersamaan, seluruh skema ini tidak ada gunanya.
