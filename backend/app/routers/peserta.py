"""Status peserta untuk pengguna yang sedang login.

Sengaja TIDAK menerima no_bpjs sebagai parameter. Peserta diambil dari
firebase_uid milik token pemanggil, sehingga tidak ada cara bagi seseorang untuk
menanyakan status orang lain hanya dengan menebak nomor BPJS. Endpoint yang
menerima no_bpjs dan mengembalikan status pendaftaran biometriknya adalah
oracle enumerasi gratis.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import CurrentUserDep, DbDep
from app.security import crypto
from app.utils.errors import ApiError

router = APIRouter(prefix="/peserta", tags=["peserta"])


@router.get("/me")
async def my_status(db: DbDep, user: CurrentUserDep) -> dict:
    peserta = await db.peserta.find_one({"firebase_uid": user.uid})
    if not peserta:
        raise ApiError(
            "PESERTA_NOT_FOUND",
            404,
            message="Akun ini belum tertaut dengan data peserta BPJS.",
        )

    template = await db.biometric_templates.find_one(
        {"peserta_id": peserta["_id"], "modality": "face", "status": "active"},
        {"created_at": 1, "assurance": 1, "model": 1},
    )

    return {
        "status": "ok",
        "nama_lengkap": peserta["nama_lengkap"],
        "no_bpjs_masked": crypto.mask_bpjs(peserta["no_bpjs"]),
        "status_kepesertaan": peserta.get("status_kepesertaan"),
        "kelas_rawat": peserta.get("kelas_rawat"),
        "jenis_peserta": peserta.get("jenis_peserta"),
        "tunggakan_bulan": peserta.get("tunggakan_bulan", 0),
        "faskes_tingkat1": (peserta.get("faskes_tingkat1") or {}).get("nama"),
        "biometric_enrolled": bool(peserta.get("biometric_enrolled")),
        "biometric_enrolled_at": peserta.get("biometric_enrolled_at"),
        # Tingkat jaminan ditampilkan supaya pengguna tahu pendaftarannya
        # lemah (mandiri) atau kuat (terverifikasi Dukcapil / berbantuan).
        "assurance": (template or {}).get("assurance"),
    }
