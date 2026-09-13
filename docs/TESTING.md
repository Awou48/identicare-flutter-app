# Panduan Pengujian IdentiCare

Urutan ini penting. Tiap bagian bergantung pada bagian sebelumnya, dan hampir
semua "error" di aplikasi sebenarnya adalah **satu** masalah: ponsel tidak bisa
menjangkau backend. Selesaikan bagian 0 dulu, atau semua yang lain akan
terlihat rusak padahal tidak.

---

## 0. Prasyarat — sekali saja

### 0.1 Database (MongoDB Atlas, bukan Docker)

Docker Desktop di mesin ini butuh hak administrator untuk berjalan. Atlas
menghilangkan ketergantungan itu sepenuhnya.

1. Di Atlas: **Network Access → Add IP Address → Allow access from anywhere**
   (`0.0.0.0/0`). Untuk pengembangan ini aman, dan satu-satunya pilihan yang
   bertahan saat IP publik hotspot ponsel berubah.
2. Di Atlas: cluster Anda → **Connect → Drivers** → salin bagian host dari
   connection string. Bentuknya `cluster0.ab12cd.mongodb.net`.
3. Jalankan:

```powershell
backend\.venv\Scripts\python.exe backend\scripts\use_atlas.py cluster0.ab12cd.mongodb.net
```

Skrip ini menulis host ke `backend/.env`, menguji koneksi, membuat 11 koleksi
beserta validator dan index-nya, lalu mengisi data contoh (4 faskes, 20
peserta, artikel kesehatan). Aman dijalankan ulang.

**Yang harus terlihat:** `[+] Atlas reachable` lalu tiga skrip seed berjalan
tanpa `[!]`. Setelah ini, database `identicare` muncul di Atlas.

**Kalau gagal:** pesannya menyebut penyebabnya. `Could not reach the cluster`
= IP belum di-allowlist. `Authentication failed` = password di `.env` salah.

### 0.2 Firestore

Aturan dan index harus di-deploy. Tanpa ini: chat `permission-denied`, profil
kosong.

```powershell
firebase deploy --only firestore:rules,firestore:indexes
```

Index komposit butuh beberapa menit untuk dibangun. Firebase Console →
Firestore → Indexes harus menunjukkan status **Enabled**, bukan *Building*.

### 0.3 Firewall Windows — sekali, sebagai administrator

Tanpa ini ponsel *timeout tanpa satu pun baris log di server*, karena paketnya
tidak pernah sampai. Ini penyebab nomor satu "Tidak dapat terhubung ke server".

```powershell
New-NetFirewallRule -DisplayName "IdentiCare API" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

---

## 1. Jalankan backend

```powershell
backend\start_backend.ps1
```

Skrip ini mencetak IP LAN Anda saat ini dan perintah `flutter run` yang persis.
**IP berubah setiap kali Anda berpindah antara Wi-Fi dan hotspot** — selalu
ambil dari keluaran skrip, jangan dari ingatan.

**Verifikasi:** buka `http://<ip>:8000/api/v1/health` di browser laptop. Harus
mengembalikan JSON dengan:

| Field | Nilai yang benar | Kalau salah |
|---|---|---|
| `mongo` | `ok` | Atlas belum terhubung — ulangi 0.1 |
| `face_models` | `loaded` | Model ONNX belum diunduh — lihat `backend/README.md` |
| `firebase_auth` | `google-public-keys` | Tidak boleh `dev-bypass` |
| `peserta_count` | `20` atau lebih | Seed belum jalan |

> `http://0.0.0.0:8000` **tidak akan pernah bisa dibuka** di browser. `0.0.0.0`
> adalah alamat *bind* ("dengarkan di semua interface"), bukan alamat tujuan.
> Gunakan `127.0.0.1:8000` dari laptop, atau IP LAN dari ponsel.

---

## 2. Jalankan aplikasi

Ponsel dan laptop harus di **jaringan yang sama**. Ponsel via hotspot dan laptop
via Wi-Fi rumah = dua jaringan berbeda = tidak akan pernah terhubung.

```powershell
flutter run --dart-define=API_BASE_URL=http://<ip-dari-langkah-1>:8000
```

Alternatif tanpa rebuild: **Pengaturan → Alamat server**, masukkan URL yang
sama, simpan. Berguna saat IP berubah di tengah pengujian.

**Verifikasi cepat:** buka tab **Beranda**. Lencana di bawah "Halo" harus
berubah dari *"Status biometrik belum dimuat"* menjadi *"Belum terdaftar"*
(atau *"Terverifikasi dalam BPJS"*). Kalau tetap "belum dimuat", ponsel tidak
menjangkau backend — cek jaringan dan firewall, **jangan** lanjut ke bagian
berikutnya.

---

## 3. Akun & profil

| Langkah | Yang harus terjadi |
|---|---|
| Daftar akun baru (email + kata sandi + nama) | Masuk ke Beranda, "Halo, NAMA" menampilkan nama Anda |
| Lihat kartu status di bawah sapaan | **"Tautkan nomor BPJS Anda"** — bisa diketuk. Akun login (Firebase) dan data peserta (MongoDB) memang dua hal terpisah; langkah ini yang menjahitnya |
| Tab **Profil** | Nama dan email tampil. Kalau akun dibuat sebelum versi ini, halaman akan menampilkan "Menyiapkan profil..." sebentar lalu memperbaikinya sendiri |
| Tab **Aktivitas → Verifikasi** | *"Akun belum tertaut BPJS"* dengan tombol **Tautkan Nomor BPJS** — bukan "Coba Lagi" |

### 3.1 Tautkan nomor BPJS — wajib sebelum verifikasi

Ketuk kartu status di Beranda (atau tombol di Aktivitas, atau tombol yang
muncul saat membuka Verifikasi Klaim BPJS — ketiganya membuka layar yang sama).
Isi persis data yang di-seed:

| Field | Nilai demo |
|---|---|
| Nomor Kartu BPJS | `0001234567890` |
| NIK (KTP) | `3174050412010001` |
| Tanggal Lahir | 4 Desember 2001 |

Ini identitas **Marcel Iliantino** dari `seed_peserta.py`. Untuk akun kedua
(uji wajah ganda di bagian 5) pakai Siti Nurhaliza: BPJS `0001234567891`,
NIK `3174054503920002`, lahir 5 Maret 1992.

| Langkah | Yang harus terjadi |
|---|---|
| Ketuk **Tautkan Akun** dengan data di atas | Kembali ke Beranda; kartu status berubah jadi *"Biometrik belum terdaftar"* |
| Coba lagi dengan NIK salah (akun lain) | *"Data tidak cocok dengan catatan BPJS"* + *Sisa percobaan: 4*. Pesan **tidak** menyebut field mana yang salah — itu disengaja, supaya endpoint ini bukan oracle untuk mencocokkan NIK dengan nomor BPJS |
| Salah 5 kali dalam sejam | `429` *"Terlalu banyak percobaan"*, bahkan untuk data yang benar |
| Akun kedua mencoba menautkan `0001234567890` yang sudah tertaut | *"sudah tertaut ke akun lain"* — dan di server muncul sinyal fraud `ACCOUNT_LINK_CONFLICT` (lihat bagian 7) |

Penautan hanya bisa **sekali**. Untuk memindahkan peserta ke akun lain saat
uji coba, kosongkan field-nya lewat `mongosh`/Compass:
`db.peserta.updateOne({no_bpjs:"0001234567890"},{$set:{firebase_uid:null}})`.

| Tab **Aktivitas → Verifikasi** (setelah tertaut) | *"Belum ada riwayat verifikasi"* — bukan error. Ini benar untuk akun baru |
| Ikon lonceng (Notifikasi) | Daftar notifikasi, atau "belum ada notifikasi" — bukan "Server tidak merespons" |
| Artikel Kesehatan di Beranda | Daftar artikel muncul |

Semua baris di atas gagal dengan pesan server yang sama kalau bagian 0-2 belum
beres. Itu bukan lima bug; itu satu.

---

## 4. Verifikasi Klaim BPJS — alur utama

Ini butuh **ponsel Android fisik**. Emulator tidak punya sensor sidik jari.

### 4.1 Pendaftaran biometrik (pertama kali)

1. Beranda → **Verifikasi Klaim BPJS**.
2. Karena wajah belum terdaftar, layar menampilkan *"Biometrik belum
   terdaftar"* dengan tombol **Daftarkan Biometrik Sekarang** — bukan
   "Coba Lagi" yang tak berguna. Ketuk.
3. Centang persetujuan, ketuk **Daftarkan Wajah Saya**. Kamera mengambil 3
   frame.
4. **Yang harus terlihat:** "Biometrik Terdaftar", tingkat jaminan
   `SELF_ASSERTED`, dan berapa template lain yang diperiksa (dedup).
5. Ketuk **Selesai** — alur verifikasi otomatis dimulai ulang.

**Kalau "Wajah tidak terdeteksi":** pencahayaan dari depan, wajah memenuhi
oval, jangan terlalu jauh.

### 4.2 Langkah 1 — Scan Wajah

Liveness dinilai dari **perubahan** antara frame pertama dan terakhir, jadi
urutannya penting:

1. Di atas oval tertulis apa yang *nanti* diminta, mis. *"Siap? Nanti Anda
   diminta: palingkan wajah ke kanan"*. Jangan menoleh dulu.
2. Ketuk **Mulai Scan Wajah** → *"Hadapkan wajah lurus ke kamera"* (~1 detik,
   frame 1 diambil).
3. Instruksi berganti menjadi *"Palingkan wajah ke kanan - sekarang!"* →
   **baru menoleh**, tahan sampai hitungan 3/3.
   Untuk *"Dekatkan wajah"*: majukan ponsel ~10 cm.
4. **Yang harus terlihat:** oval hijau, lanjut ke langkah 2.

Gambar buram / gelap / wajah tidak terdeteksi **tidak** mengurangi 3
percobaan — hanya wajah tidak cocok dan liveness gagal yang dihitung. Kalau
liveness gagal, sisi server menyimpan rinciannya: `mongosh` →
`db.verification_sessions.find({},{ "steps.face.liveness_signals":1 }).sort({created_at:-1}).limit(1)`.

Dua hal yang saya ingin tahu dari Anda di sini, karena keduanya belum pernah
diuji dengan wajah manusia sungguhan:

- **Apakah wajah Anda cocok?** Ambang 0.42 belum dikalibrasi. Kalau ditolak
  dengan skor mendekati (mis. 0.35-0.41), ambangnya yang salah, bukan Anda —
  itu satu angka di `backend/.env` (`FACE_MATCH_ACCEPT`).
- **Apakah tantangan palingkan-wajah lolos?** Kalau *move_closer* lolos tetapi
  *turn_left/right* selalu gagal, ambang yaw yang perlu diturunkan
  (`YAW_SHIFT_REQUIRED` di `backend/app/services/liveness.py`).

### 4.3 Langkah 2 — Sidik Jari

1. Ketuk **Pindai Sidik Jari**. Prompt sensor Android muncul.
2. Sentuh sensor.
3. **Yang harus terlihat:** lolos, dengan catatan *"perangkat belum terikat
   TEE"* — ini jujur: jalur saat ini Tier A (HMAC), dan itu memang menaikkan
   skor risiko 10 poin.

### 4.4 Langkah 3 — Periksa Ulang Data

**Yang harus terlihat:** nama lengkap tampil untuk **pertama kalinya** (sebelum
ini semua bertopeng), NIK tetap `3174********0001`, kedua faktor biometrik
hijau. Centang konfirmasi, lanjutkan.

### 4.5 Langkah 4 — Verifikasi Data

**Yang harus terlihat:** *"Klaim Terverifikasi"*, nomor bukti
`VRF-YYYYMMDD-NNNNNN`, skor risiko rendah dengan satu sinyal
`SOFTWARE_KEY_ONLY` (+10). Tab **Aktivitas → Verifikasi** kini menampilkan
entri ini dengan tanggal, metode, status, dan lokasi faskes.

---

## 5. Uji kegagalan — ini yang membuktikan sistemnya bekerja

Alur yang lolos membuktikan sedikit. Yang penting: serangan ditolak.

| Uji | Cara | Yang harus terjadi |
|---|---|---|
| **Foto cetak** | Langkah 1: pegang foto wajah Anda (di layar HP lain) ke kamera | `LIVENESS_FAILED`, skor liveness rendah, motion ≈ 0 |
| **Orang lain** | Minta orang lain melakukan langkah 1 dengan akun Anda | `FACE_MISMATCH` dengan skor. Ini yang **wajib** gagal |
| **Batas percobaan** | Gagalkan langkah 1 tiga kali | *"Batas percobaan tercapai"* dengan tombol **Minta Override Petugas** — bukan jalan buntu |
| **Override** | Ketuk tombol itu → login petugas → alasan → supervisor menyetujui | Keputusan `APPROVED_WITH_OVERRIDE`, dua sinyal fraud baru |
| **Override oleh orang yang sama** | Petugas mencoba menyetujui permohonannya sendiri | Ditolak 403 — four-eyes dicek server, bukan klien |
| **Daftar ulang wajah yang sama ke nomor BPJS lain** | Buat akun kedua, tautkan ke Siti Nurhaliza (data di 3.1), daftarkan wajah yang sama | `DUPLICATE_FACE` — kotak kuning, bukan merah, karena ini laporan fraud, bukan kesalahan pengguna |

Untuk override, buat akun petugas dulu dari Swagger (`/docs`) →
`POST /api/v1/staff` dengan `X-Api-Key: dev-operator-key`; buat satu `petugas`
dan satu `supervisor`.

---

## 6. Konsultasi Online (chat)

1. Beranda → **Konsultasi Online** → pilih dokter.
2. Kirim pesan.

**Yang harus terlihat:** pesan tersimpan dan balasan otomatis muncul.
**Kalau `permission-denied`:** index Firestore untuk `messages` masih
*Building* — tunggu, lalu coba lagi. Kalau tetap gagal setelah *Enabled*, aturan
belum di-deploy (bagian 0.2).

---

## 7. Cek dari sisi server

Selagi menguji, perhatikan jendela backend. Tiap permintaan tercatat dengan
kode status dan durasi. Yang perlu diwaspadai:

- `401` di endpoint selain login → token Firebase ditolak. `/health` harus
  menunjukkan `firebase_auth: google-public-keys`.
- **Tidak ada baris sama sekali** saat ponsel mencoba → paket tidak sampai.
  Firewall (0.3) atau beda jaringan (bagian 2).
- `MODEL_UNAVAILABLE` → model ONNX belum ada di `backend/models/`.

Setelah alur selesai, cek Atlas: koleksi `verification_sessions` punya satu
dokumen `committed`, dan `verification_events` mencatat **setiap** percobaan
termasuk yang gagal — kegagalan justru sinyal fraud yang paling berharga.

---

## 8. Uji otomatis (tanpa ponsel)

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -q     # 123 lolos
flutter test                                                      # 19 lolos
backend\.venv\Scripts\python.exe backend\scripts\e2e_demo.py      # 44 cek, butuh backend jalan
```

`e2e_demo.py` memakai wajah sintetis: ia membuktikan **pipa**-nya utuh dan
serangan ditolak, tetapi **tidak** bisa memvalidasi ambang kecocokan wajah.
Hanya bagian 4-5 dengan wajah sungguhan yang bisa.
