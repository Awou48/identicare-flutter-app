"""Legacy compatibility for the existing Flutter symptom checker.

lib/services/api_service.dart already POSTs {"gejala": [...]} to /analyze_symptoms
on a hardcoded LAN IP. That server no longer exists anywhere in the project, so
the feature is dead. Re-hosting the same contract here revives it for the cost of
one route, and moves the 42 hardcoded symptoms in symptom_checker_page.dart:19-28
onto the server where the model can change them without an app release.

Backed by Ollama if it is running locally; falls back to a transparent rule-based
response otherwise, clearly labelled as such rather than pretending to be AI.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter

from app.deps import SettingsDep

log = logging.getLogger(__name__)
router = APIRouter(tags=["symptoms"])

SYMPTOM_CATALOG = [
    "Sakit kepala", "Pusing", "Migrain", "Kehilangan keseimbangan", "Batuk", "Sesak Napas",
    "Pilek", "Nyeri dada saat bernapas", "Mual", "Muntah", "Diare", "Sakit perut", "Sembelit",
    "Nafsu makan menurun", "Detak jantung tidak teratur", "Nyeri dada", "Tekanan darah tinggi",
    "Mudah lelah", "Demam", "Menggigil", "Berkeringat berlebihan", "Tubuh terasa lemas",
    "Nyeri otot", "Sendi kaku", "Bengkak", "Sulit bergerak (sendi/otot)", "Mata merah",
    "Penglihatan kabur", "Bengkak (mata)", "Mata sulit fokus/bergerak normal",
    "Sakit tenggorokan", "Hidung tersumbat", "Gangguan pendengaran", "Sakit telinga", "Ruam",
    "Gatal-gatal", "Luka tidak sembuh", "Kulit kering", "Stres", "Cemas", "Sulit tidur",
    "Mudah marah",
]

PROMPT = (
    "Anda adalah asisten kesehatan. Berdasarkan gejala berikut, berikan analisis awal "
    "singkat dalam Bahasa Indonesia (maksimal 150 kata): kemungkinan kondisi, tingkat "
    "urgensi, dan saran tindakan. Selalu akhiri dengan pengingat untuk berkonsultasi "
    "dengan dokter.\n\nGejala: {gejala}"
)

DISCLAIMER = (
    "\n\nCatatan: analisis ini bersifat informasi awal dan bukan diagnosis medis. "
    "Silakan berkonsultasi dengan tenaga kesehatan."
)


@router.get("/api/v1/symptoms/catalog")
async def catalog() -> dict:
    """Serves the symptom list so the Flutter client stops hardcoding it."""
    return {"status": "ok", "gejala": SYMPTOM_CATALOG, "count": len(SYMPTOM_CATALOG)}


async def _analyse(gejala: list[str], settings) -> dict:
    if not gejala:
        return {"status": "error", "message": "Tidak ada gejala yang dipilih."}

    joined = ", ".join(gejala)
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": PROMPT.format(gejala=joined),
                    "stream": False,
                },
            )
            if response.status_code == 200:
                text = response.json().get("response", "").strip()
                if text:
                    return {"status": "ok", "result": text + DISCLAIMER, "engine": "ollama"}
            log.warning("Ollama returned %s", response.status_code)
    except (httpx.HTTPError, ValueError) as exc:
        log.info("Ollama unavailable (%s); using fallback", type(exc).__name__)

    return {
        "status": "ok",
        "result": _fallback(gejala) + DISCLAIMER,
        "engine": "rule_based_fallback",
    }


def _fallback(gejala: list[str]) -> str:
    """Honest fallback. Says plainly that no AI model was involved rather than
    dressing a keyword match up as analysis."""
    urgent = {"Nyeri dada", "Sesak Napas", "Detak jantung tidak teratur", "Nyeri dada saat bernapas"}
    hits = [g for g in gejala if g in urgent]
    lines = [f"Gejala yang dilaporkan: {', '.join(gejala)}."]
    if hits:
        lines.append(
            f"PERHATIAN: {', '.join(hits)} dapat menandakan kondisi serius. "
            "Segera kunjungi IGD atau hubungi layanan gawat darurat."
        )
    else:
        lines.append(
            "Tidak terdeteksi gejala kegawatdaruratan. Istirahat cukup, jaga hidrasi, "
            "dan pantau perkembangan gejala."
        )
    lines.append("(Model AI tidak tersedia - ini adalah respons berbasis aturan sederhana.)")
    return " ".join(lines)


@router.post("/analyze_symptoms")
async def analyze_symptoms_legacy(payload: dict, settings: SettingsDep) -> dict:
    """The exact path and body shape api_service.dart:10 already sends."""
    return await _analyse(payload.get("gejala", []), settings)


@router.post("/api/v1/symptoms/analyze")
async def analyze_symptoms(payload: dict, settings: SettingsDep) -> dict:
    return await _analyse(payload.get("gejala", []), settings)
