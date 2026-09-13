from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import OkResponse


class Alamat(BaseModel):
    jalan: str = ""
    kelurahan: str = ""
    kecamatan: str = ""
    kota: str = ""
    provinsi: str = ""
    kode_pos: str = ""


class PesertaCreate(BaseModel):
    nik: str = Field(pattern=r"^[0-9]{16}$")
    no_bpjs: str = Field(pattern=r"^[0-9]{13}$")
    nama_lengkap: str = Field(min_length=1, max_length=200)
    tanggal_lahir: date
    jenis_kelamin: Literal["L", "P"]
    alamat: Alamat = Field(default_factory=Alamat)
    no_hp: str | None = None
    kelas_rawat: int = Field(ge=1, le=3)
    jenis_peserta: Literal["PBI", "PPU", "PBPU", "BP"]
    kode_faskes_tingkat1: str
    status_kepesertaan: Literal["AKTIF", "NONAKTIF", "MENUNGGAK"] = "AKTIF"
    tunggakan_bulan: int = Field(default=0, ge=0)
    firebase_uid: str | None = None


class PesertaPreview(BaseModel):
    """Masked view returned at session start."""

    nama_masked: str
    no_bpjs_masked: str
    biometric_enrolled: bool


class PesertaFull(BaseModel):
    nama_lengkap: str
    no_bpjs: str
    nik_masked: str
    tanggal_lahir: date | None = None
    jenis_kelamin: str | None = None
    kelas_rawat: int | None = None
    jenis_peserta: str | None = None
    status_kepesertaan: str
    tunggakan_bulan: int = 0
    faskes_tingkat1: str | None = None


class PesertaCreated(OkResponse):
    peserta_id: str
    no_bpjs: str
    created: bool
