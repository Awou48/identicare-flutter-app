"""Status peserta dan penautan akun untuk pengguna yang sedang login.

Sengaja TIDAK menerima no_bpjs sebagai parameter pada /me. Peserta diambil dari
firebase_uid milik token pemanggil, sehingga tidak ada cara bagi seseorang untuk
menanyakan status orang lain hanya dengan menebak nomor BPJS. Endpoint yang
menerima no_bpjs dan mengembalikan status pendaftaran biometriknya adalah
oracle enumerasi gratis.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.deps import CurrentUserDep, DbDep, SettingsDep
from app.security import crypto
from app.services import audit, matcher
from app.utils.errors import ApiError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/peserta", tags=["peserta"])

# Lima tebakan NIK+tanggal lahir per jam per akun. Cukup longgar untuk salah
# ketik, cukup ketat supaya menebak identitas orang lain tidak praktis.
LINK_MAX_FAILURES = 5
LINK_WINDOW = timedelta(hours=1)


@router.get("/me")
async def my_status(db: DbDep, user: CurrentUserDep) -> dict:
    peserta = await db.peserta.find_one({"firebase_uid": user.uid})
    if not peserta:
        raise ApiError(
            "PESERTA_NOT_FOUND",
            404,
            message="Akun ini belum tertaut dengan data peserta BPJS.",
        )

    template = await matcher.get_active_template(db, peserta["_id"])

    return {
        "status": "ok",
        "nama_lengkap": peserta["nama_lengkap"],
        # Nomor penuh dikembalikan karena pemanggil ADALAH pemiliknya - ia
        # dibutuhkan untuk memulai sesi verifikasi. Yang bertopeng untuk tampilan.
        "no_bpjs": peserta["no_bpjs"],
        "no_bpjs_masked": crypto.mask_bpjs(peserta["no_bpjs"]),
        "status_kepesertaan": peserta.get("status_kepesertaan"),
        "kelas_rawat": peserta.get("kelas_rawat"),
        "jenis_peserta": peserta.get("jenis_peserta"),
        "tunggakan_bulan": peserta.get("tunggakan_bulan", 0),
        "faskes_tingkat1": (peserta.get("faskes_tingkat1") or {}).get("nama"),
        # From the template, not the flag - see matcher.get_active_template.
        "biometric_enrolled": template is not None,
        "biometric_enrolled_at": (template or {}).get("created_at"),
        # Tingkat jaminan ditampilkan supaya pengguna tahu pendaftarannya
        # lemah (mandiri) atau kuat (terverifikasi Dukcapil / berbantuan).
        "assurance": (template or {}).get("assurance"),
        "linked_via": peserta.get("linked_via"),
    }


class LinkRequest(BaseModel):
    no_bpjs: str = Field(pattern=r"^[0-9]{13}$")
    nik: str = Field(pattern=r"^[0-9]{16}$")
    tanggal_lahir: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.post("/link")
async def link_account(
    payload: LinkRequest, db: DbDep, settings: SettingsDep, user: CurrentUserDep
) -> dict:
    """Tautkan akun login ini ke satu peserta BPJS.

    Ini langkah yang sebelumnya tidak ada. Login dikelola Firebase, data BPJS
    ada di MongoDB, dan keduanya dijahit oleh peserta.firebase_uid - tetapi
    satu-satunya yang pernah mengisi field itu adalah endpoint operator. Setiap
    pengguna sungguhan yang mendaftar berakhir di PESERTA_NOT_FOUND di semua
    layar, tanpa satu pun jalan keluar dari dalam aplikasi.

    Bukti kepemilikan: nomor BPJS + NIK + tanggal lahir, ketiganya tercetak di
    kartu fisik KTP dan BPJS. Ini tripel yang sama yang diminta Mobile JKN saat
    registrasi. Bukan bukti yang kuat - orang dalam yang memegang datanya bisa
    lolos - tetapi cukup untuk menghentikan penautan sembarangan, dan tiga
    pengaman lain yang membatasi kerusakannya:

      1. Sekali tertaut, tidak bisa ditaut ulang dari sini. Mengambil alih akun
         yang sudah tertaut wajib lewat operator dengan kontrol ganda.
      2. Percobaan yang salah dibatasi 5 per jam per akun - NIK tidak bisa
         ditebak dengan brute force.
      3. Menautkan saja tidak memberi apa-apa. Klaim tetap butuh wajah yang
         lolos gerbang deduplikasi 1:N, dan pendaftaran mandiri membawa batas
         nilai klaim (SELF_ASSERTED).

    Pesan kegagalan sengaja tidak menyebut field mana yang salah: menyebutnya
    menjadikan endpoint ini oracle untuk mencocokkan NIK dengan nomor BPJS.
    """
    now = datetime.now(UTC)

    # --- pembatas percobaan --------------------------------------------- #
    recent_failures = await db.audit_log.count_documents(
        {
            "who": user.uid,
            "what": "link_account_failed",
            "at": {"$gte": now - LINK_WINDOW},
        }
    )
    if recent_failures >= LINK_MAX_FAILURES:
        raise ApiError(
            "TOO_MANY_ATTEMPTS",
            429,
            message="Terlalu banyak percobaan penautan yang gagal. Coba lagi dalam satu jam.",
        )

    peserta = await db.peserta.find_one({"no_bpjs": payload.no_bpjs})

    # Verifikasi kepemilikan. Semua cabang gagal memakai pesan yang SAMA.
    identity_ok = False
    if peserta:
        nik_ok = crypto.constant_time_equals(
            crypto.hash_nik(payload.nik, settings.nik_pepper), peserta.get("nik_hash", "")
        )
        dob = peserta.get("tanggal_lahir")
        dob_ok = dob is not None and dob.strftime("%Y-%m-%d") == payload.tanggal_lahir
        identity_ok = nik_ok and dob_ok

    if not identity_ok:
        await audit.record(
            db,
            who=user.uid,
            what="link_account_failed",
            peserta_id=peserta["_id"] if peserta else None,
            purpose="penautan_akun",
        )
        raise ApiError(
            "IDENTITY_MISMATCH",
            403,
            message="Data tidak cocok dengan catatan BPJS. Periksa nomor BPJS, NIK, "
            "dan tanggal lahir Anda.",
            details={"attempts_left": LINK_MAX_FAILURES - recent_failures - 1},
        )

    # --- sudah tertaut? -------------------------------------------------- #
    existing = peserta.get("firebase_uid")
    if existing and existing != user.uid:
        # Seseorang yang tahu tripel identitas mencoba menautkan peserta yang
        # sudah punya akun. Itu persis pola pengambilalihan akun, jadi ia
        # dicatat sebagai sinyal fraud, bukan sekadar ditolak.
        await db.fraud_signals.insert_one(
            {
                "peserta_id": peserta["_id"],
                "session_id": None,
                "rule_id": "ACCOUNT_LINK_CONFLICT",
                "severity": "high",
                "weight": 30,
                "title": "Percobaan menautkan peserta yang sudah tertaut ke akun lain",
                "detail": {"attempted_by": user.uid},
                "status": "open",
                "detected_at": now,
                "resolved_at": None,
                "resolved_by": None,
            }
        )
        await audit.record(
            db,
            who=user.uid,
            what="link_account_conflict",
            peserta_id=peserta["_id"],
            purpose="penautan_akun",
        )
        raise ApiError(
            "BPJS_ALREADY_LINKED",
            409,
            message="Nomor BPJS ini sudah tertaut ke akun lain. Hubungi petugas "
            "faskes untuk memindahkannya.",
        )

    if existing == user.uid:
        return {"status": "ok", "linked": True, "already": True, "no_bpjs": peserta["no_bpjs"]}

    # Sama seperti kondisi di atas, sebuah akun Firebase hanya boleh memegang
    # satu peserta.
    other = await db.peserta.find_one({"firebase_uid": user.uid}, {"no_bpjs": 1})
    if other:
        raise ApiError(
            "ACCOUNT_ALREADY_LINKED",
            409,
            message="Akun ini sudah tertaut ke nomor BPJS lain.",
        )

    await db.peserta.update_one(
        {"_id": peserta["_id"], "firebase_uid": None},
        {
            "$set": {
                "firebase_uid": user.uid,
                "linked_at": now,
                "linked_via": "self",
                "updated_at": now,
            }
        },
    )
    await audit.record(
        db,
        who=user.uid,
        what="link_account",
        peserta_id=peserta["_id"],
        purpose="penautan_akun",
    )
    log.info("peserta %s linked to firebase uid %s", peserta["no_bpjs"], user.uid)

    return {
        "status": "ok",
        "linked": True,
        "already": False,
        "no_bpjs": peserta["no_bpjs"],
        "nama_lengkap": peserta["nama_lengkap"],
        "biometric_enrolled": bool(peserta.get("biometric_enrolled")),
    }
