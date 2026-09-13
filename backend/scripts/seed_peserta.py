from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

import numpy as np
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from app.config import get_settings
from app.security import crypto, rotation

FACILITIES = [
    {
        "kode_faskes": "0110R001",
        "nama": "RS Harapan Kita",
        "jenis": "RS_TIPE_A",
        "tingkat": 2,
        "alamat": "Jl. Letjen S. Parman Kav 87",
        "kota": "Jakarta Barat",
        "provinsi": "DKI Jakarta",
        "geo": {"type": "Point", "coordinates": [106.7996, -6.1789]},
    },
    {
        "kode_faskes": "0110R002",
        "nama": "RSUPN Dr. Cipto Mangunkusumo",
        "jenis": "RS_TIPE_A",
        "tingkat": 2,
        "alamat": "Jl. Pangeran Diponegoro No. 71",
        "kota": "Jakarta Pusat",
        "provinsi": "DKI Jakarta",
        "geo": {"type": "Point", "coordinates": [106.8451, -6.1958]},
    },
    {
        "kode_faskes": "0110P001",
        "nama": "Puskesmas Kebayoran Baru",
        "jenis": "PUSKESMAS",
        "tingkat": 1,
        "alamat": "Jl. Gandaria Tengah III No. 4",
        "kota": "Jakarta Selatan",
        "provinsi": "DKI Jakarta",
        "geo": {"type": "Point", "coordinates": [106.7970, -6.2410]},
    },
    {
        "kode_faskes": "3471P002",
        "nama": "Puskesmas Wamena",
        "jenis": "PUSKESMAS",
        "tingkat": 1,
        "alamat": "Jl. Trikora No. 12, Wamena",
        "kota": "Jayawijaya",
        "provinsi": "Papua Pegunungan",
        "geo": {"type": "Point", "coordinates": [138.9500, -4.0833]},
    },
]

PESERTA_SEED = [
    ("Marcel Iliantino", "3174050412010001", "0001234567890", "L", "2001-12-04", 1, "PPU", "AKTIF", 0),
    ("Siti Nurhaliza", "3174054503920002", "0001234567891", "P", "1992-03-05", 2, "PBPU", "AKTIF", 0),
    ("Budi Hartono", "3173011508850003", "0001234567892", "L", "1985-08-15", 3, "PBI", "AKTIF", 0),
    ("Dewi Lestari", "3174052209780004", "0001234567893", "P", "1978-09-22", 1, "PPU", "AKTIF", 0),
    ("Agus Salim", "3175031103660005", "0001234567894", "L", "1966-03-11", 3, "PBI", "AKTIF", 0),
    ("Rina Kartika", "3171040107950006", "0001234567895", "P", "1995-07-01", 2, "PBPU", "MENUNGGAK", 3),
    ("Hendra Wijaya", "3174052812880007", "0001234567896", "L", "1988-12-28", 2, "PPU", "AKTIF", 0),
    ("Ani Yudhoyono", "3172061906720008", "0001234567897", "P", "1972-06-19", 1, "PPU", "AKTIF", 0),
    ("Eko Prasetyo", "3173022404900009", "0001234567898", "L", "1990-04-24", 3, "PBI", "AKTIF", 0),
    ("Maya Sari", "3174051701990010", "0001234567899", "P", "1999-01-17", 2, "PBPU", "AKTIF", 0),
    ("Joko Widodo", "3374010506610011", "0001234567900", "L", "1961-06-05", 1, "PPU", "AKTIF", 0),
    ("Tri Handayani", "3171050308830012", "0001234567901", "P", "1983-08-03", 3, "PBI", "AKTIF", 0),
    ("Bambang Sutrisno", "3175041209750013", "0001234567902", "L", "1975-09-12", 2, "PBPU", "NONAKTIF", 0),
    ("Fitri Ramadhani", "3174053006960014", "0001234567903", "P", "1996-06-30", 2, "PPU", "AKTIF", 0),
    ("Yusuf Maulana", "9471010211020015", "0001234567904", "L", "2002-11-02", 3, "PBI", "AKTIF", 0),
    ("Kartini Wulandari", "9471012104870016", "0001234567905", "P", "1987-04-21", 3, "PBI", "AKTIF", 0),
    ("Rizky Febrian", "3173030902000017", "0001234567906", "L", "2000-02-09", 2, "PBPU", "AKTIF", 0),
    ("Nurul Aini", "3174051512910018", "0001234567907", "P", "1991-12-15", 1, "PPU", "AKTIF", 0),
    ("Dimas Anggara", "3172060703940019", "0001234567908", "L", "1994-03-07", 2, "PBPU", "MENUNGGAK", 1),
    ("Lestari Handoko", "3171041808690020", "0001234567909", "P", "1969-08-18", 3, "PBI", "AKTIF", 0),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo BPJS data.")
    parser.add_argument("--reset", action="store_true", help="Delete seeded docs first.")
    parser.add_argument(
        "--no-biometrics",
        action="store_true",
        help="Skip the random placeholder templates.",
    )
    args = parser.parse_args()

    settings = get_settings()
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except ServerSelectionTimeoutError:
        print("[!] Cannot reach MongoDB. Run: docker compose -f backend/docker-compose.yml up -d")
        return 1
    db = client[settings.mongo_db]

    try:
        kek = crypto.load_kek(settings.kek_file)
        rot = rotation.load_rotation(settings.rotation_file)
    except FileNotFoundError as exc:
        print(f"[!] {exc}")
        return 1

    if settings.nik_pepper.startswith("CHANGE_ME") or "change-me" in settings.nik_pepper:
        print("[!] NIK_PEPPER is still the placeholder. Seeding anyway (dev), but set a")
        print("    real value in backend/.env before any real data exists - changing the")
        print("    pepper later invalidates every stored nik_hash.")

    if args.reset:
        for coll in ("peserta", "biometric_templates", "facilities"):
            deleted = db[coll].delete_many({"seeded": True}).deleted_count
            print(f"[-] {coll}: removed {deleted} seeded docs")

    now = datetime.now(UTC)

    faskes_ids: dict[str, object] = {}
    for fac in FACILITIES:
        doc = {**fac, "active": True, "seeded": True}
        db.facilities.update_one({"kode_faskes": fac["kode_faskes"]}, {"$set": doc}, upsert=True)
        found = db.facilities.find_one({"kode_faskes": fac["kode_faskes"]}, {"_id": 1})
        faskes_ids[fac["kode_faskes"]] = found["_id"]
    print(f"[+] facilities: {len(FACILITIES)} upserted")

    default_faskes_kode = "0110P001"
    default_faskes = db.facilities.find_one({"kode_faskes": default_faskes_kode})

    rng = np.random.default_rng(20260908)
    inserted = updated = templates = 0

    for i, (nama, nik, no_bpjs, sex, birth, kelas, jenis, status, tunggakan) in enumerate(PESERTA_SEED):
        doc = {
            "no_bpjs": no_bpjs,
            "nik_hash": crypto.hash_nik(nik, settings.nik_pepper),
            "nik_last4": nik[-4:],
            "nama_lengkap": nama,
            "tanggal_lahir": datetime.strptime(birth, "%Y-%m-%d").replace(tzinfo=UTC),
            "jenis_kelamin": sex,
            "alamat": {
                "jalan": f"Jl. Contoh No. {i + 1}",
                "kelurahan": "Gandaria Utara",
                "kecamatan": "Kebayoran Baru",
                "kota": "Jakarta Selatan",
                "provinsi": "DKI Jakarta",
                "kode_pos": "12140",
            },
            "kelas_rawat": kelas,
            "jenis_peserta": jenis,
            "faskes_tingkat1": {
                "faskes_id": faskes_ids[default_faskes_kode],
                "nama": default_faskes["nama"],
            },
            "status_kepesertaan": status,
            "tunggakan_bulan": tunggakan,
            "eligibility_score": 100 - tunggakan * 15,
            "firebase_uid": None,
            "biometric_enrolled": False,
            "biometric_enrolled_at": None,
            "updated_at": now,
            "schema_version": 1,
            "seeded": True,
        }

        existing = db.peserta.find_one({"no_bpjs": no_bpjs}, {"_id": 1})
        if existing:
            peserta_id = existing["_id"]
            db.peserta.update_one({"_id": peserta_id}, {"$set": doc})
            updated += 1
        else:
            doc["created_at"] = now
            result = db.peserta.insert_one(doc)
            peserta_id = result.inserted_id
            inserted += 1

        nik_aad = crypto.build_aad(peserta_id, "nik", 1)
        db.peserta.update_one(
            {"_id": peserta_id},
            {"$set": {"nik_enc": crypto.encrypt_blob(kek, nik.encode("utf-8"), nik_aad)}},
        )

        if args.no_biometrics or i >= 15:
            continue

        template_id = db.biometric_templates.find_one(
            {"peserta_id": peserta_id, "modality": "face"}, {"_id": 1}
        )
        if template_id:
            continue

        vec = rotation.l2_normalize(rng.standard_normal(settings.face_embedding_dim))
        placeholder = db.biometric_templates.insert_one(
            {
                "peserta_id": peserta_id,
                "modality": "face",
                "status": "active",
                "created_at": now,
                "seeded": True,
            }
        ).inserted_id

        aad = crypto.build_aad(peserta_id, placeholder, 1)
        db.biometric_templates.update_one(
            {"_id": placeholder},
            {
                "$set": {
                    "version": 1,
                    "model": {
                        "name": "PLACEHOLDER_random_unit_vector",
                        "dim": settings.face_embedding_dim,
                        "normalized": True,
                    },
                    "enc": crypto.encrypt_embedding(kek, vec, aad),
                    "search_vector": rotation.apply_rotation(rot, vec).tolist(),
                    "rotation_id": rotation.ROTATION_ID,
                    "quality": {},
                    "enroll_meta": {"source": "seed_peserta.py", "synthetic": True},
                    "revoked_at": None,
                    "schema_version": 1,
                }
            },
        )
        db.peserta.update_one(
            {"_id": peserta_id},
            {"$set": {"biometric_enrolled": True, "biometric_enrolled_at": now}},
        )
        templates += 1

    print(f"[+] peserta: {inserted} inserted, {updated} updated")
    print(f"[+] biometric_templates: {templates} placeholder templates")

    sample = db.peserta.find_one({"no_bpjs": PESERTA_SEED[0][2]})
    aad = crypto.build_aad(sample["_id"], "nik", 1)
    recovered = crypto.decrypt_blob(kek, sample["nik_enc"], aad).decode("utf-8")
    assert recovered == PESERTA_SEED[0][1], "NIK round trip failed"
    print(f"[+] NIK round trip OK for {sample['nama_lengkap']}: {crypto.mask_nik(recovered)}")

    tmpl = db.biometric_templates.find_one({"peserta_id": sample["_id"], "modality": "face"})
    if tmpl:
        t_aad = crypto.build_aad(sample["_id"], tmpl["_id"], 1)
        plain = crypto.decrypt_embedding(kek, tmpl["enc"], t_aad, settings.face_embedding_dim)
        rotated = np.asarray(tmpl["search_vector"], dtype=np.float32)
        direct = rotation.cosine(plain, plain)
        via_rot = rotation.cosine(rotated, rotated)
        print(f"[+] Template round trip OK. self-cosine plain={direct:.6f} rotated={via_rot:.6f}")
        crypto.wipe(plain)

    print()
    print("[!] Seeded embeddings are RANDOM VECTORS, not faces. They will never match")
    print("    a real photo. Real enrolment happens in Step 3 via /enrollment/face.")
    print()
    print("    Inspect at http://localhost:8081 (mongo-express)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
