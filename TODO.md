# TODO — Refactor IdentiCare menuju Sistem Anti-Fraud Berbasis AI

Dokumen ini memetakan seluruh logika hardcoded, konfigurasi rusak, dan utang teknis
pada codebase Flutter saat ini yang harus dibereskan sebelum sistem verifikasi
biometrik dinamis (face recognition + liveness + sidik jari) dapat dibangun di atasnya.

**Temuan utama:** alur verifikasi 4 langkah (Scan Wajah → Scan Sidik Jari → Periksa Ulang
Data → Verifikasi Data) **belum ada sama sekali** di repo ini. Pencarian `scan`, `wajah`,
`sidik jari`, `biometric`, `Stepper`, `camera`, `local_auth`, `BPJS`, `NIK` di seluruh
`lib/` menghasilkan **nol hasil**, dan `pubspec.yaml` tidak memuat satu pun plugin kamera
atau biometrik. Backend Python juga tidak ada di repo ini maupun di direktori induk.
Jadi alur verifikasi adalah pekerjaan baru (greenfield), bukan refactor.

Skala saat ini: 26 file Dart, ~2.120 baris, 1 commit.

---

## 0. Status Setelah Step 4

Dokumen ini ditulis pada Step 1 sebagai audit. Setelah backend (Step 2-3) dan
integrasi Flutter (Step 4), berikut yang **sudah selesai** dan yang **masih
tersisa**.

### Sudah diperbaiki

| Item | Perbaikan |
|---|---|
| 1.1 `displayName` hardcoded | Form pendaftaran kini meminta nama lengkap + nomor BPJS asli ([auth_page.dart](lib/pages/auth_page.dart), [auth_service.dart](lib/services/auth_service.dart)) |
| 1.2 fallback `'MARCEL SEBASTIAN'` | Dihapus; header menampilkan "Halo," saja saat data belum tiba |
| 1.6 SnackBar `"(Simulasi)"` | Tidak lagi mengaku berhasil — kini menyatakan fiturnya belum tersedia |
| 1.12 42 gejala hardcoded | Diambil dari `GET /api/v1/symptoms/catalog`, daftar lama jadi cadangan offline |
| 2.1 `INTERNET` hilang di manifest rilis | Ditambahkan ke manifest `main` |
| 2.2 IP LAN hardcoded | [app_config.dart](lib/config/app_config.dart): `--dart-define` + override debug tanpa rebuild |
| 2.3 tidak ada network security config | Ditambah untuk `main` (tolak cleartext) dan `debug` (izinkan LAN saja) |
| 2.4 `signOut()` paksa tiap cold start | Dihapus dari [main.dart](lib/main.dart) |
| 2.8 `DateFormat('id_ID')` tanpa init | `initializeDateFormatting('id_ID')` di `main()` |
| 2.10 state tab hilang | `IndexedStack` menggantikan `_pages.elementAt` |
| 3.1, 3.2 widget mati | `feature_card.dart` dan `upcoming_appointment_card.dart` dihapus |
| 3.3 `widget_test.dart` template counter | Diganti 19 test atas model verifikasi dan payload kanonik |
| 4.2 tidak ada lapisan model | `lib/models/` dibuat: `ApiResult`, `VerificationSession`, hasil tiap langkah, riwayat |
| 4.3 `notifyListeners()` tak pernah dipanggil | `AuthService` kini mengikuti `authStateChanges` dan memberi notifikasi |
| 4.5 error tak terstruktur | Semua jaringan lewat [IdenticareApiClient](lib/services/identicare_api_client.dart) dengan kode error + request id |
| 2.7 font Poppins tidak ada | Paket `google_fonts` dipakai di `_buildTheme()` ([main.dart](lib/main.dart)). Juga menghapus `background:` yang sudah deprecated |
| 2.9 index Firestore | [firestore.indexes.json](firestore.indexes.json) mendeklarasikan index komposit `userId + timestamp desc` |
| 4.1 **tidak ada `firestore.rules`** | [firestore.rules](firestore.rules) ditulis: tolak-semua secara default, pengguna hanya bisa menyentuh dokumennya sendiri, riwayat append-only. **Belum di-deploy** - lihat catatan di bawah |

### Masih tersisa (sengaja, di luar cakupan sistem biometrik)

| Item | Kenapa belum |
|---|---|
| 1.4, 1.5, 1.7 dokter & jadwal dummy | Belum ada endpoint penjadwalan di backend. Sistem biometrik tidak membutuhkannya; membuatnya sekarang adalah perluasan cakupan. |
| 1.8 chat palsu | Butuh backend chat/telemedicine tersendiri. |
| 1.9, 1.10, 1.11 rekam medis dummy | Butuh integrasi SATUSEHAT atau endpoint rekam medis. |
| 1.15 profil rumah sakit hardcoded | Data faskes sudah ada di MongoDB (`facilities`), tetapi belum ada endpoint publiknya. |
| 2.5 rilis pakai kunci debug | Butuh keystore rilis; `android/key.properties` sudah masuk `.gitignore`. |
| 2.6 `applicationId com.example.*` | Sengaja tidak diubah: terikat `google-services.json`. |
| 4.4 tidak ada named route | Konsisten dengan pola `Navigator.push` yang sudah ada di 15 halaman. |

> **Aturan Firestore belum aktif sampai di-deploy.** Berkasnya sudah ada di repo
> dan sudah didaftarkan di `firebase.json`, tetapi project masih memakai aturan
> lama sampai dijalankan:
>
> ```
> firebase deploy --only firestore:rules,firestore:indexes
> ```
>
> Aturannya juga **belum diuji dengan emulator** (butuh firebase-tools + Java,
> keduanya belum terpasang di mesin ini). Uji sebelum mengandalkannya:
> `firebase emulators:start --only firestore`.

---

## 1. Data Palsu / Hardcoded

Semua item di bawah ini menampilkan data karangan yang tidak berasal dari sumber data mana pun.

| # | Lokasi | Masalah |
|---|---|---|
| 1.1 | [`lib/services/auth_service.dart:28`](lib/services/auth_service.dart:28) | **Paling kritis.** Setiap akun baru ditulis dengan `'displayName': 'Marcel Sebastian'` tanpa memandang siapa yang mendaftar. Identitas adalah inti produk ini — nama pengguna tidak boleh dikarang. |
| 1.2 | [`lib/pages/home_page.dart:97`](lib/pages/home_page.dart:97), [`:99`](lib/pages/home_page.dart:99) | `String userName = 'MARCEL SEBASTIAN'` sebagai nilai awal **dan** sebagai fallback `??`. Akibatnya pengguna lain tetap melihat nama tersebut saat Firestore lambat merespons. |
| 1.3 | [`lib/pages/profile_page.dart:53`](lib/pages/profile_page.dart:53) | `_buildInfoRow('Telepon', 'Belum diatur')` — nilai literal, tidak pernah dibaca dari Firestore, padahal `phoneNumber` ditulis di `auth_service.dart:29`. |
| 1.4 | [`lib/pages/appointment_page.dart:14-19`](lib/pages/appointment_page.dart:14) | `allDoctors`: 4 dokter karangan lengkap dengan rating (`Dr. Budi Santoso`, `Dr. Siti Aminah`, `Dr. Eko Prasetyo`, `Dr. Rina Wulandari`). Daftar spesialisasi juga hardcoded di `:51`. |
| 1.5 | [`lib/pages/doctor_detail_page.dart:82`](lib/pages/doctor_detail_page.dart:82) | Jadwal praktik hardcoded `['09:00','10:00','11:00','14:00','15:00','16:00']`, chip `selected: false` dengan `onSelected` kosong — tidak bisa dipilih. Rating `'(120 ulasan)'` di `:42` juga karangan. |
| 1.6 | [`lib/pages/doctor_detail_page.dart:71`](lib/pages/doctor_detail_page.dart:71) | Tombol "Buat Janji Temu" hanya menampilkan SnackBar `'Janji temu berhasil dibuat! (Simulasi)'`. **Tidak ada data yang disimpan** — pengguna diberi tahu sesuatu berhasil padahal tidak terjadi apa-apa. |
| 1.7 | [`lib/pages/telemedicine_page.dart:9-15`](lib/pages/telemedicine_page.dart:9) | Komentar `// Data dummy dokter telemedicine`, 4 dokter dengan status `Online`/`Offline`/`Sedang Konsultasi` yang tidak pernah berubah. |
| 1.8 | [`lib/pages/chat_page.dart:12-14`](lib/pages/chat_page.dart:12), [`:22-27`](lib/pages/chat_page.dart:22) | Chat palsu. Komentar `// Simulasi balasan dokter`, balasan tetap `'Baik, saya mengerti. Bisa ceritakan lebih detail?'` setelah `Duration(seconds: 2)`. Tidak ada backend. |
| 1.9 | [`lib/pages/medical_records_page.dart:13-20`](lib/pages/medical_records_page.dart:13) | Komentar `// Data dummy untuk daftar rekam medis`, 5 entri dengan tanggal mati (`01 Jul 2025`, `28 Jun 2025`, `15 Mei 2025`, `10 Jan 2025`). |
| 1.10 | `lib/pages/medical_records/` (5 file) | `diagnosis_detail_page.dart`, `lab_result_detail_page.dart`, `prescription_detail_page.dart`, `radiology_detail_page.dart`, `vaccination_detail_page.dart` — semuanya `StatelessWidget` **tanpa parameter**, isi 100% literal: hasil lab `'Hemoglobin 14.5 g/dL'`, nomor resep `'E-RX-20250628-001'`, batch vaksin `'PFZ-B1-12345'`, diagnosa `'Influenza (Flu) - J11'`. Halaman detail apa pun yang dibuka menampilkan isi yang persis sama. |
| 1.11 | `lib/pages/medical_records/radiology_detail_page.dart:13` | Gambar X-Ray diambil dari `NetworkImage('https://i.ibb.co/6g2Z1k8/xray.jpg')` — hosting pihak ketiga, dikomentari sendiri sebagai `// Gambar X-Ray dummy`. |
| 1.12 | [`lib/pages/symptom_checker_page.dart:19-28`](lib/pages/symptom_checker_page.dart:19) | 42 gejala hardcoded di sisi klien. Model AI di backend tidak bisa menambah/mengubah gejala tanpa rilis aplikasi baru. |
| 1.13 | [`lib/pages/home_page.dart:160-165`](lib/pages/home_page.dart:160) | Grid layanan 2×2 hardcoded, termasuk widget halaman tujuan di dalam list data — data dan navigasi tercampur. |
| 1.14 | [`lib/pages/home_page.dart:196`](lib/pages/home_page.dart:196), [`:207`](lib/pages/home_page.dart:207), [`:212`](lib/pages/home_page.dart:212) | Artikel kesehatan hardcoded (`'Pentingnya Hidrasi untuk Tubuh'`) dengan gambar dari Unsplash. `onTap` di `:192` kosong. |
| 1.15 | `lib/pages/hospital_info_page.dart` (`:26,34,49,60,71,88,95,147-152,186`) | Seluruh profil rumah sakit karangan: `'RS IdentiCare Sehat'`, `'Jl. Kesehatan No. 123, Jakarta Sehat'`, telepon `'(021) 123-4567'`, jam besuk, daftar fasilitas, daftar poli. |
| 1.16 | `lib/widgets/upcoming_appointment_card.dart:29,35,36,51,58` | `'Dr. Budi Santoso'`, `'Besok, 07 Jul 2025'`, `'10:00 WIB'` — hardcoded, dan widget-nya sendiri sudah mati (lihat §3). |

> **Catatan:** satu-satunya layar yang benar-benar terhubung ke data nyata adalah
> [`lib/pages/history_page.dart`](lib/pages/history_page.dart) (query Firestore `riwayat_konsultasi`).

---

## 2. Konfigurasi Rusak

| # | Lokasi | Masalah | Dampak |
|---|---|---|---|
| 2.1 | [`android/app/src/main/AndroidManifest.xml`](android/app/src/main/AndroidManifest.xml) | **Permission `INTERNET` tidak ada di manifest `main`.** Hanya dideklarasikan di `src/debug/AndroidManifest.xml:5` dan `src/profile/AndroidManifest.xml:5`. | **Build release tidak punya akses jaringan sama sekali.** Seluruh fitur verifikasi biometrik mati total di APK rilis. Perbaikan satu baris, prioritas tertinggi. |
| 2.2 | [`lib/services/api_service.dart:5`](lib/services/api_service.dart:5) | `final String _baseUrl = "http://192.168.0.101:5000";` — IP LAN privat hardcoded. Tidak ada `.env`, tidak ada `--dart-define`. | Aplikasi mati begitu berpindah jaringan. Di lokasi lomba dengan subnet berbeda, satu-satunya perbaikan adalah rebuild. |
| 2.3 | Android 9+ (API 28+) | Tidak ada `network_security_config.xml`. | HTTP cleartext ke `http://192.168.x.x` **diblokir diam-diam** oleh Android meskipun `INTERNET` sudah ditambahkan. Butuh config khusus untuk debug, dan HTTPS (mis. Cloudflare Tunnel) untuk demo. |
| 2.4 | [`lib/main.dart:14`](lib/main.dart:14) | `await AuthService().signOut();` dipanggil setiap cold start. | Pengguna dipaksa login ulang setiap membuka aplikasi. Sisa kode development; akan terlihat seperti bug saat demo. |
| 2.5 | [`android/app/build.gradle.kts:35-37`](android/app/build.gradle.kts:35) | `release { signingConfig = signingConfigs.getByName("debug") }` | Build release ditandatangani dengan kunci debug — tidak bisa didistribusikan ke Play Store. |
| 2.6 | [`android/app/build.gradle.kts:27`](android/app/build.gradle.kts:27) | `applicationId = "com.example.identicare_mobile"` — masih package template. | **Jangan diubah dulu:** `google-services.json` dan `firebase.json` terikat pada ID ini; mengubahnya akan merusak Firebase Auth secara diam-diam. Ganti hanya lewat pendaftaran app Android kedua di Firebase Console. |
| 2.7 | [`lib/main.dart:36`](lib/main.dart:36), [`:44`](lib/main.dart:44) | `fontFamily: 'Poppins'` diset, tetapi `pubspec.yaml` **tidak punya blok `fonts:`**. | Aplikasi diam-diam dirender dengan Roboto. Tampilan tidak sesuai desain. Pilih: tambahkan TTF ke `assets/fonts/`, pakai `google_fonts`, atau hapus dua baris tersebut. |
| 2.8 | [`lib/pages/history_page.dart:71`](lib/pages/history_page.dart:71), [`lib/pages/profile_page.dart:54`](lib/pages/profile_page.dart:54) | `DateFormat(..., 'id_ID')` dipakai tanpa `initializeDateFormatting('id_ID')` di `main()`. | Berpotensi melempar `LocaleDataException` saat runtime. |
| 2.9 | [`lib/pages/history_page.dart:32-36`](lib/pages/history_page.dart:32) | Query composite (`where userId` + `orderBy timestamp desc`) membutuhkan index Firestore, tetapi tidak ada `firestore.indexes.json` di repo. | Query gagal di project Firebase yang bersih sampai index dibuat manual. |
| 2.10 | [`lib/main_navigator.dart:24-28`](lib/main_navigator.dart:24) | `_pages.elementAt(index)` alih-alih `IndexedStack`. | State tiap tab hilang setiap kali pengguna berpindah tab. |

---

## 3. Kode Mati

| # | Lokasi | Masalah |
|---|---|---|
| 3.1 | `lib/widgets/feature_card.dart` (46 baris) | Tidak pernah di-`import` di mana pun. Hapus. |
| 3.2 | `lib/widgets/upcoming_appointment_card.dart` (68 baris) | Tidak pernah di-`import` di mana pun, dan seluruh isinya hardcoded. Hapus. |
| 3.3 | [`test/widget_test.dart`](test/widget_test.dart) | Masih template counter bawaan Flutter — mencari `find.text('0')` dan menekan `Icons.add`. **Tidak akan pernah lolos** terhadap `MyApp`. Satu-satunya test di repo, dan test suite gagal hari ini. Ganti, jangan diperbaiki. |
| 3.4 | `.metadata`, [`lib/firebase_options.dart:51-58`](lib/firebase_options.dart:51), `firebase.json` | Masih mendaftarkan platform/appId **iOS padahal folder `ios/` sudah dihapus**. `flutter build ios` mustahil dijalankan. Bersihkan entri `ios` dari `.metadata` dan nyatakan Android-only di README. |
| 3.5 | [`android/app/src/main/AndroidManifest.xml:3`](android/app/src/main/AndroidManifest.xml:3) | Permission `CAMERA` **sudah dideklarasikan tetapi tidak ada satu pun kode atau plugin yang memakainya**. Ditambahkan untuk fitur yang belum pernah dibangun. Akan terpakai setelah alur Scan Wajah ada. |

---

## 4. Keamanan & Arsitektur

| # | Masalah | Detail |
|---|---|---|
| 4.1 | **Tidak ada `firestore.rules` di repo** | `firebase.json` hanya berisi blok `flutter.platforms`. Project kemungkinan besar berjalan dalam mode test → koleksi `riwayat_konsultasi` (berisi gejala kesehatan pengguna) **dapat dibaca siapa saja**. Ini paparan data terbesar yang sedang aktif di repo saat ini. Minimal: batasi baca ke `request.auth.uid == resource.data.userId`. |
| 4.2 | **Tidak ada lapisan model sama sekali** | Tidak ada direktori `lib/models/`. Semua data dioper sebagai `Map<String, dynamic>` mentah — mis. `DoctorDetailPage({required this.doctor})` di [`doctor_detail_page.dart:4`](lib/pages/doctor_detail_page.dart:4). Tidak ada type safety, tidak ada validasi, salah ketik nama field baru ketahuan saat runtime. Data biometrik dan skor fraud **tidak boleh** ditangani dengan pola ini. |
| 4.3 | **`AuthService` tidak pernah memanggil `notifyListeners()`** | [`lib/services/auth_service.dart:5`](lib/services/auth_service.dart:5) meng-extend `ChangeNotifier` tetapi tidak pernah memberi notifikasi. Provider di sini efektif hanya berfungsi sebagai service locator (`listen: false` di semua call site). Kalau status verifikasi biometrik nanti perlu menggerakkan UI, wiring Provider yang ada **tidak akan mempropagasi perubahan**. |
| 4.4 | **Tidak ada named route / route guard** | Semua navigasi memakai `Navigator.push(MaterialPageRoute(...))` inline. Tidak ada cara memasang guard "peserta belum enroll biometrik". |
| 4.5 | **Tidak ada penanganan error terpusat** | [`api_service.dart:20-22`](lib/services/api_service.dart:20) menelan semua exception menjadi satu string bahasa Indonesia. Tidak ada kode error, tidak ada request id, tidak ada cara membedakan timeout dari 500. |
| 4.6 | **Kredensial Firebase ter-commit** | `android/app/google-services.json` dan API key di `firebase_options.dart` ada di git. Ini normal untuk client key Firebase, **tetapi berarti keamanan sepenuhnya bergantung pada Firestore rules yang belum ada** (§4.1). |

---

## 5. Yang Dibutuhkan Sistem Anti-Fraud Dinamis

Untuk setiap item: kondisi sekarang → harus menjadi apa → endpoint pengganti.

### 5.1 Identitas peserta
- **Sekarang:** nama hardcoded (`auth_service.dart:28`), tidak ada konsep NIK, nomor BPJS, kelas rawat, status kepesertaan, atau faskes. Nol referensi `BPJS`/`NIK`/`peserta` di seluruh repo.
- **Harus menjadi:** entitas `Peserta` bertipe kuat dengan `no_bpjs`, NIK (di-hash untuk pencarian, dienkripsi untuk tampilan, dimasking di UI), `status_kepesertaan`, `tunggakan_bulan`, `faskes_tingkat1`, `biometric_enrolled`.
- **Endpoint:** `POST /api/v1/enrollment/peserta`, `GET /api/v1/verification/sessions/{id}/review`.

### 5.2 Alur verifikasi 4 langkah
- **Sekarang:** tidak ada. Tidak ada stepper, tidak ada layar scan, tidak ada plugin kamera/biometrik.
- **Harus menjadi:** shell alur dengan state machine sisi server. Klien **hanya membawa `session_id` + `session_token`**; klien tidak pernah memajukan langkahnya sendiri. Kalau alur dijahit di sisi klien, penyerang cukup melewati panggilan liveness.
- **Endpoint:** `POST /verification/sessions` → `/face` → `/fingerprint` → `/review` → `/commit`.

### 5.3 Data biometrik
- **Sekarang:** tidak ada.
- **Harus menjadi:** embedding wajah 512-dimensi (ArcFace) terenkripsi AES-256-GCM di MongoDB, plus search vector ter-rotasi untuk sweep 1:N tanpa dekripsi. Gambar mentah **tidak pernah** disimpan.
- **Endpoint:** `POST /api/v1/enrollment/face`, `DELETE /api/v1/enrollment/face/{peserta_id}` (hak penghapusan).

### 5.4 Sidik jari
- **Sekarang:** tidak ada. Perlu ditegaskan: kamera ponsel **tidak bisa** melakukan pencocokan minutiae sidik jari yang sesungguhnya.
- **Harus menjadi:** sensor sidik jari asli perangkat via `local_auth`, dengan tanda tangan ECDSA P-256 dari Android Keystore. `local_auth` sendiri hanya mengembalikan `bool`, dan **boolean yang melintasi jaringan bukan faktor kedua** — perangkat yang di-root mengembalikan `true` gratis. Tanda tangan harus berasal dari TEE.
- **Endpoint:** `POST /api/v1/enrollment/device`, `POST /verification/sessions/{id}/fingerprint`.

### 5.5 Riwayat verifikasi (tanggal, metode, status, lokasi)
- **Sekarang:** hanya ada `riwayat_konsultasi` di Firestore (gejala + hasil AI). Tidak ada konsep lokasi, metode, atau status verifikasi.
- **Harus menjadi:** log append-only di MongoDB dengan timestamp UTC, metode (`wajah`/`sidik_jari`), keputusan (`APPROVED`/`REVIEW`/`REJECTED`), faskes + koordinat geo, device, skor kecocokan, dan skor liveness — termasuk **percobaan yang gagal**, karena scan wajah yang gagal justru sinyal fraud yang paling berguna.
- **Endpoint:** `GET /api/v1/verification/history`.
- **UI:** tab "Aktivitas" di [`lib/main_navigator.dart`](lib/main_navigator.dart) dipecah jadi dua: "Konsultasi" (Firestore, sudah ada) + "Verifikasi" (MongoDB, baru).

### 5.6 Deteksi fraud
- **Sekarang:** tidak ada.
- **Harus menjadi:** mesin aturan sisi server yang dijalankan ulang saat `commit` — klaim ganda simultan di dua faskes, tabrakan wajah 1:N, impossible travel, frekuensi klaim berlebih, perangkat dipakai bersama, kunci software-only. Skor 0–100 → APPROVED / REVIEW / REJECTED.
- **Endpoint:** `POST /api/v1/fraud/check`, `GET /api/v1/fraud/signals`.

### 5.7 Konfigurasi backend
- **Sekarang:** IP LAN hardcoded (`api_service.dart:5`), satu endpoint (`/analyze_symptoms`), dan **tidak ada kode Python di repo ini maupun di direktori induk**.
- **Harus menjadi:** `lib/config/app_config.dart` dengan `String.fromEnvironment('API_BASE_URL')` + override `SharedPreferences` khusus debug, sehingga base URL bisa diarahkan ulang di lokasi lomba tanpa rebuild.
- **Endpoint:** seluruh permintaan melewati satu `IdenticareApiClient`.

### 5.8 Katalog gejala
- **Sekarang:** 42 string hardcoded di `symptom_checker_page.dart:19-28`.
- **Harus menjadi:** diambil dari server agar model AI bisa berubah tanpa rilis aplikasi.
- **Endpoint:** `GET /api/v1/symptoms/catalog`.

---

## 6. Batasan yang Harus Diakui Sejak Awal

Hal-hal berikut **tidak bisa** dikerjakan pada codebase ini apa adanya — dicatat agar tidak dijanjikan di presentasi.

- **iOS mati.** Folder `ios/` tidak ada, dan membuatnya ulang tetap membutuhkan mesin macOS + Xcode. Nyatakan Android-only.
- **Target web dan desktop akan rusak di langkah 2.** `local_auth` tidak punya implementasi web (`MissingPluginException`), `camera` tidak punya implementasi desktop. Folder `web/`, `windows/`, `linux/`, `macos/` semuanya ada dan tetap ter-compile. Seluruh alur harus digerbang dengan `!kIsWeb && Platform.isAndroid`.
- **Tidak ada pencocokan cosine homomorfik di atas ciphertext.** AES bukan homomorfik, dan CKKS/SEAL adalah proyek berminggu-minggu dengan latensi ~100×. Klaim yang jujur dan dapat dipertahankan: terenkripsi AES-256-GCM saat disimpan, didekripsi di memori hanya untuk satu perbandingan 1:1, dengan index ter-pseudonimisasi rotasi untuk sweep 1:N. Itulah yang dilakukan sistem biometrik sungguhan.
- **Dashboard operator/rumah sakit** yang disebut di proposal adalah **klien kedua**, bukan bagian dari aplikasi Flutter ini. Di luar cakupan; endpoint operator disiapkan agar bisa dibangun kemudian.
- **Emulator tidak bisa menguji sidik jari sungguhan.** Pengujian langkah 2 wajib memakai perangkat Android fisik.

---

## 7. Kebersihan Repo

- Working tree saat ini kotor: 8 file `generated_plugin_registrant` (linux/macos/windows) + `pubspec.lock` termodifikasi akibat `pub get`. Commit atau buang dulu agar diff fitur biometrik terbaca.
- `.gitignore` perlu tambahan: `backend/.venv/`, `backend/**/__pycache__/`, `backend/.env`, `backend/keys/`, `backend/models/*.onnx`, `android/key.properties`.
