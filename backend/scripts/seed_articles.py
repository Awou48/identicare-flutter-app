"""Seed artikel kesehatan.

    python scripts/seed_articles.py
    python scripts/seed_articles.py --reset

Menulis langsung ke MongoDB, jadi tidak perlu API berjalan. Semua dokumen
ditandai seeded: true supaya --reset dapat membersihkannya tanpa menyentuh
artikel asli.

Isinya sengaja berputar pada BPJS, verifikasi identitas, dan pencegahan fraud -
bukan artikel kesehatan generik - karena itulah konteks aplikasi ini.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime, timedelta

from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

import _bootstrap_path  # noqa: F401  (side effect: sys.path)
from app.config import get_settings

ARTICLES = [
    {
        "judul": "Mengapa Verifikasi Wajah Diperlukan untuk Klaim BPJS",
        "kategori": "Verifikasi",
        "featured": True,
        "ringkasan": "Komisi Pemberantasan Korupsi mencatat kerugian negara hingga "
        "Rp 20 triliun akibat fraud di bidang kesehatan. Verifikasi biometrik "
        "memastikan klaim hanya dapat diajukan oleh pemiliknya.",
        "penulis": "Tim IdentiCare",
        "image_url": "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=800",
        "konten": """Selama ini klaim BPJS diverifikasi dengan kartu dan nomor. Keduanya bisa berpindah tangan, dan di situlah celahnya.

Komisi Pemberantasan Korupsi mengungkap kerugian negara hingga Rp 20 triliun akibat kecurangan di bidang kesehatan. Sebagian berasal dari penyalahgunaan data peserta: identitas dipakai orang lain, atau dibuat data palsu yang seolah menunjukkan peserta aktif.

Verifikasi biometrik menutup celah itu dengan satu prinsip sederhana: yang diperiksa bukan lagi apa yang Anda bawa, melainkan siapa Anda.

**Bagaimana prosesnya bekerja**

Kamera mengambil beberapa gambar wajah Anda. Sistem mengubahnya menjadi representasi matematis dan membandingkannya dengan data yang sudah terdaftar. Yang disimpan bukan foto Anda, melainkan angka-angka hasil perhitungan yang tidak bisa dikembalikan menjadi wajah.

**Mengapa ada instruksi menoleh**

Sistem perlu memastikan yang ada di depan kamera adalah orang sungguhan, bukan foto cetak atau rekaman layar. Karena itu Anda diminta menoleh atau mendekat ke arah tertentu. Arahnya dipilih acak oleh server setiap kali, sehingga rekaman lama tidak dapat digunakan ulang.

**Sidik jari sebagai faktor kedua**

Wajah bisa gagal dipindai karena memar, bengkak, atau pencahayaan buruk. Sidik jari bisa gagal karena luka bakar. Menggunakan keduanya berarti satu dapat menggantikan yang lain, dan bila keduanya dipakai bersamaan tingkat keamanannya setara verifikasi dua langkah.

**Bila keduanya gagal**

Anda tidak akan ditolak. Petugas fasilitas kesehatan dapat mengajukan verifikasi manual yang disetujui oleh dua orang berbeda dan tercatat permanen. Layanan kesehatan tidak pernah ditahan karena alasan teknis.""",
    },
    {
        "judul": "Data Biometrik Anda: Apa yang Disimpan dan Apa yang Tidak",
        "kategori": "Privasi",
        "featured": False,
        "ringkasan": "Foto wajah Anda tidak pernah disimpan. Yang tersimpan adalah "
        "representasi matematis terenkripsi yang tidak dapat dikembalikan menjadi gambar.",
        "penulis": "Tim IdentiCare",
        "image_url": "https://images.unsplash.com/photo-1563986768609-322da13575f3?w=800",
        "konten": """Kekhawatiran yang paling sering muncul soal verifikasi wajah adalah: ke mana foto saya pergi?

Jawabannya: tidak ke mana-mana. Gambar yang diambil kamera hanya hidup selama proses verifikasi berlangsung, lalu dibuang.

**Yang benar-benar disimpan**

Yang tersimpan adalah deretan angka hasil perhitungan dari wajah Anda. Angka-angka itu dienkripsi dengan AES-256-GCM, standar yang sama yang dipakai untuk melindungi data perbankan.

Enkripsinya diikat ke dokumen pemiliknya. Artinya, seseorang yang berhasil masuk ke basis data pun tidak bisa memindahkan data biometrik Anda ke rekam milik orang lain - dekripsinya akan gagal.

**Nomor Induk Kependudukan**

NIK tidak disimpan apa adanya. Untuk pencarian, yang disimpan adalah hasil hash yang tidak dapat dibalik. Untuk ditampilkan saat pemeriksaan data, ada salinan terenkripsi yang hanya dibuka setelah kedua faktor biometrik lolos - dan bahkan saat itu pun NIK tetap ditampilkan sebagian: 3174********0001.

**Hak Anda menurut UU PDP**

Undang-Undang Nomor 27 Tahun 2022 menggolongkan data biometrik sebagai data pribadi spesifik. Pemrosesannya wajib memiliki persetujuan eksplisit dari Anda, untuk tujuan yang disebutkan secara jelas.

Anda berhak menarik persetujuan itu. Bila ditarik, kunci enkripsi data biometrik Anda dihapus sehingga isinya tidak dapat dibaca lagi selamanya. Catatan bahwa suatu verifikasi pernah terjadi tetap ada untuk keperluan audit, tetapi tanpa data biometriknya.""",
    },
    {
        "judul": "Persiapan Sebelum Scan Wajah agar Berhasil Sekali Coba",
        "kategori": "Panduan",
        "featured": False,
        "ringkasan": "Pencahayaan, jarak, dan kestabilan tangan menentukan keberhasilan "
        "pemindaian. Lima hal sederhana yang membuat prosesnya lancar.",
        "penulis": "Tim IdentiCare",
        "image_url": "https://images.unsplash.com/photo-1584515933487-779824d29309?w=800",
        "konten": """Sebagian besar kegagalan pemindaian bukan karena sistemnya, melainkan karena kondisi pengambilan gambar. Lima hal berikut mengatasi hampir semuanya.

**1. Cari cahaya yang merata**

Hindari membelakangi jendela atau lampu terang - wajah Anda akan menjadi siluet. Cahaya dari depan jauh lebih baik daripada cahaya dari belakang.

**2. Lepas yang menutupi wajah**

Masker, kacamata hitam, dan topi bertepi lebar menghalangi titik-titik yang dibaca sistem. Kacamata bening umumnya tidak masalah.

**3. Jaga jarak sekitar 30 sentimeter**

Terlalu jauh membuat wajah terlalu kecil untuk dibaca. Terlalu dekat membuat proporsinya menyimpang. Ikuti bingkai oval di layar.

**4. Tahan ponsel dengan stabil**

Sistem memerlukan tiga gambar berurutan. Guncangan membuat gambar buram dan pemindaian ditolak sebelum sempat diproses. Bila memungkinkan, sandarkan siku.

**5. Ikuti instruksi gerakan**

Bila diminta menoleh ke kiri, tolehkan kepala - bukan menggeser ponsel. Gerakannya tidak perlu ekstrem, cukup jelas terlihat.

**Bila tetap gagal**

Anda memiliki tiga kali percobaan. Setelahnya, petugas dapat mengajukan verifikasi manual. Jangan ragu meminta bantuan petugas - jalur itu memang disediakan untuk keadaan seperti ini.""",
    },
    {
        "judul": "Mengenali Modus Kecurangan Klaim BPJS",
        "kategori": "Fraud",
        "featured": False,
        "ringkasan": "Klaim ganda, identitas pinjam pakai, dan manipulasi diagnosis. "
        "Kenali polanya agar Anda tidak ikut terseret.",
        "penulis": "Tim IdentiCare",
        "image_url": "https://images.unsplash.com/photo-1450101499163-c8848c66ca85?w=800",
        "konten": """Kecurangan klaim bukan selalu perbuatan peserta. Sering kali peserta justru tidak tahu identitasnya sedang dipakai.

**Klaim ganda**

Satu identitas dipakai untuk mengajukan klaim di dua fasilitas kesehatan dalam waktu berdekatan. Sistem memeriksa hal ini secara otomatis: bila ada klaim lain atas nama Anda di faskes berbeda dalam rentang empat jam, klaim ditandai dan ditolak.

**Perpindahan lokasi yang mustahil**

Klaim di Jakarta pukul sembilan pagi, lalu di Papua pukul sebelas. Jarak dan waktunya diperiksa; bila kecepatan yang tersirat melebihi 120 km/jam, itu menjadi sinyal.

**Identitas pinjam pakai**

Kartu BPJS dipinjamkan kepada kerabat yang tidak tertanggung. Niatnya mungkin menolong, tetapi akibatnya rekam medis Anda tercampur dengan riwayat penyakit orang lain - dan itu berbahaya bila suatu saat Anda butuh penanganan darurat.

**Satu wajah, dua nomor peserta**

Saat pendaftaran biometrik, wajah diperiksa terhadap seluruh peserta terdaftar. Bila wajah yang sama sudah terdaftar dengan nomor BPJS berbeda, pendaftaran ditolak.

**Apa yang bisa Anda lakukan**

Periksa riwayat verifikasi Anda secara berkala di menu Aktivitas. Bila ada verifikasi yang tidak Anda lakukan, laporkan ke fasilitas kesehatan atau BPJS Kesehatan. Riwayat itu ada justru supaya Anda dapat mengawasinya sendiri.""",
    },
    {
        "judul": "Layanan Kesehatan di Daerah 3T dan Keterbatasan Jaringan",
        "kategori": "Akses",
        "featured": False,
        "ringkasan": "Verifikasi tetap dapat dilakukan meski internet tidak tersedia. "
        "Klaim diproses sebagai provisional dan diselesaikan saat koneksi pulih.",
        "penulis": "Tim IdentiCare",
        "image_url": "https://images.unsplash.com/photo-1469474968028-56623f02e42e?w=800",
        "konten": """Di daerah Tertinggal, Terdepan, dan Terluar, koneksi internet tidak dapat diandalkan. Sistem yang mensyaratkan koneksi terus-menerus akan gagal justru di tempat yang paling membutuhkannya.

**Tangkap sekarang, verifikasi kemudian**

Ketika koneksi terputus, proses pemindaian tetap berjalan. Gambar dienkripsi dan disimpan sementara di perangkat, lalu dikirim begitu jaringan tersedia.

Klaim Anda diberi status provisional - tercatat, tetapi verifikasinya belum selesai. Nomor buktinya berbeda agar jelas terlihat.

**Mengapa tidak diverifikasi langsung di perangkat**

Ini pertanyaan yang wajar. Jawabannya menyangkut keamanan dan kegunaan sekaligus.

Untuk mencocokkan wajah secara lokal, data biometrik peserta harus disimpan di ponsel itu. Ponsel yang hilang kemudian menjadi basis data biometrik yang hilang.

Selain itu, pemeriksaan klaim ganda justru membutuhkan data terpusat. Verifikasi lokal tidak akan pernah tahu bahwa ada klaim lain atas nama yang sama di faskes sebelah.

**Bila verifikasi kemudian gagal**

Layanan kesehatan tidak pernah ditarik kembali. Yang sudah diberikan tetap diberikan. Persoalannya menjadi urusan administrasi antara BPJS dan fasilitas kesehatan, bukan tagihan kepada pasien.""",
    },
    {
        "judul": "Apa yang Terjadi Ketika Wajah Tidak Dapat Dipindai",
        "kategori": "Panduan",
        "featured": False,
        "ringkasan": "Memar, bengkak, luka bakar, atau perangkat bermasalah. "
        "Verifikasi manual oleh petugas adalah jalur resminya.",
        "penulis": "Tim IdentiCare",
        "image_url": "https://images.unsplash.com/photo-1631217868264-e5b90bb7e133?w=800",
        "konten": """Ada keadaan di mana biometrik memang tidak bisa bekerja. Pasien dengan memar berat di wajah. Korban luka bakar yang sidik jarinya tidak lagi terbaca. Penyandang disabilitas yang kesulitan mengikuti instruksi gerakan. Perangkat yang rusak.

Sistem yang baik harus punya jawaban untuk semua itu, dan jawabannya bukan menolak pasien.

**Verifikasi manual oleh petugas**

Setelah tiga kali percobaan gagal, petugas dapat mengajukan verifikasi manual. Prosesnya sengaja dibuat lebih berat daripada jalur biasa:

- Dua petugas berbeda harus terlibat; yang mengajukan tidak boleh menyetujui permintaannya sendiri.
- Alasannya dipilih dari daftar baku, bukan diketik bebas.
- Kartu BPJS dan KTP fisik difoto sebagai bukti.
- Seluruhnya tercatat permanen dan otomatis masuk antrean tinjauan.

**Mengapa dipersulit**

Karena jalur termudah selalu menjadi jalur yang paling sering dipakai. Bila verifikasi manual lebih gampang daripada memindai wajah, semua orang akan memakainya, dan sistem biometriknya menjadi hiasan.

Frekuensi penggunaan override per petugas juga dipantau. Satu kali dalam sebulan adalah wajah yang memar. Dua puluh kali dalam seminggu adalah pola yang perlu diperiksa.

**Hak Anda sebagai pasien**

Anda berhak mendapatkan layanan meski verifikasi biometrik gagal. Bila petugas menyatakan Anda tidak dapat dilayani semata karena pemindaian gagal, itu keliru - mintalah verifikasi manual.""",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed artikel kesehatan.")
    parser.add_argument("--reset", action="store_true", help="Hapus artikel seed dulu.")
    args = parser.parse_args()

    settings = get_settings()
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except ServerSelectionTimeoutError:
        print("[!] MongoDB tidak terjangkau. Jalankan:")
        print("    docker compose -f backend/docker-compose.yml up -d")
        return 1
    db = client[settings.mongo_db]

    if args.reset:
        removed = db.articles.delete_many({"seeded": True}).deleted_count
        print(f"[-] {removed} artikel seed dihapus")

    now = datetime.now(UTC)
    inserted = updated = 0

    for i, article in enumerate(ARTICLES):
        slug = re.sub(r"[^a-z0-9]+", "-", article["judul"].lower()).strip("-")[:80]
        konten = article["konten"]
        doc = {
            **article,
            "slug": slug,
            "published": True,
            "sumber": None,
            "reading_minutes": max(1, round(len(konten.split()) / 200)),
            "updated_at": now,
            "seeded": True,
        }

        existing = db.articles.find_one({"slug": slug}, {"_id": 1, "views": 1})
        if existing:
            db.articles.update_one({"_id": existing["_id"]}, {"$set": doc})
            updated += 1
        else:
            # Tanggal terbit dimundurkan bertahap supaya urutan "terbaru" terlihat
            # masuk akal alih-alih semuanya terbit pada detik yang sama.
            doc["published_at"] = now - timedelta(days=i * 3)
            doc["views"] = 0
            db.articles.insert_one(doc)
            inserted += 1

    print(f"[+] artikel: {inserted} ditambahkan, {updated} diperbarui")
    featured = db.articles.count_documents({"featured": True, "published": True})
    print(f"[+] {featured} artikel unggulan (tampil di beranda)")
    print(f"[+] kategori: {sorted(c for c in db.articles.distinct('kategori') if c)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
