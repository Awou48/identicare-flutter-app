"""Rule engine. Runs server-side at commit; a client-supplied score is never trusted.

Weights sum into a 0-100 risk score:
    0-39   LOW     -> APPROVED
    40-69  MEDIUM  -> REVIEW
    >=70   HIGH    -> REJECTED
Any `critical` signal forces REJECTED regardless of the arithmetic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.utils.geo import haversine_km, implied_speed_kmh

SIMULTANEOUS_WINDOW_HOURS = 4
IMPOSSIBLE_TRAVEL_KMH = 120.0
HIGH_FREQUENCY_DAYS = 30
HIGH_FREQUENCY_LIMIT = 8
SHARED_DEVICE_DAYS = 7
SHARED_DEVICE_LIMIT = 3
FAILED_ATTEMPT_HOURS = 24
FAILED_ATTEMPT_LIMIT = 5
OFF_HOURS_WIB = (0, 5)
EMERGENCY_POLI = {"IGD", "Gawat Darurat", "Emergency"}
WIB_OFFSET_HOURS = 7


@dataclass
class Signal:
    rule_id: str
    severity: str
    weight: int
    title: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def band_for(score: int, signals: list[Signal]) -> tuple[str, str]:
    """(band, decision). A critical signal overrides the score entirely."""
    if any(s.severity == "critical" for s in signals):
        return "HIGH", "REJECTED"
    if score >= 70:
        return "HIGH", "REJECTED"
    if score >= 40:
        return "MEDIUM", "REVIEW"
    return "LOW", "APPROVED"


async def evaluate(
    db: AsyncDatabase,
    session: dict,
    *,
    peserta: dict,
    face_collisions: list[dict] | None = None,
) -> tuple[int, str, str, list[Signal]]:
    """Returns (score, band, decision, signals)."""
    signals: list[Signal] = []
    now = datetime.now(UTC)
    peserta_id = peserta["_id"]
    ctx = session.get("context", {})

    signals += await _simultaneous_claim(db, session, peserta_id, now)
    signals += await _impossible_travel(db, session, peserta_id, now, ctx)
    signals += await _high_frequency(db, peserta_id, now)
    signals += await _shared_device(db, ctx, peserta_id, now)
    signals += _face_collision(face_collisions or [])
    signals += await _repeated_failures(db, peserta_id, now)
    signals += _low_match_margin(session)
    signals += _software_key_only(session)
    signals += _off_hours(session, now)
    signals += _menunggak(peserta)

    score = min(100, sum(s.weight for s in signals))
    band, decision = band_for(score, signals)
    return score, band, decision, signals


# --------------------------------------------------------------------------- #
async def _simultaneous_claim(db, session, peserta_id, now) -> list[Signal]:
    """Same peserta, different faskes, inside 4 hours. The headline fraud case:
    one person claiming at two hospitals at once."""
    since = now - timedelta(hours=SIMULTANEOUS_WINDOW_HOURS)
    other = await db.verification_sessions.find_one(
        {
            "_id": {"$ne": session["_id"]},
            "peserta_id": peserta_id,
            "status": {"$in": ["committed", "face_passed", "fingerprint_passed", "reviewed"]},
            "created_at": {"$gte": since},
            "context.faskes_id": {"$ne": session.get("context", {}).get("faskes_id")},
        },
        sort=[("created_at", -1)],
    )
    if not other:
        return []

    other_created = other["created_at"]
    if other_created.tzinfo is None:
        other_created = other_created.replace(tzinfo=UTC)
    delta_min = abs((now - other_created).total_seconds()) / 60.0

    distance_km = 0.0
    try:
        a = session["context"]["location"]["geo"]["coordinates"]
        b = other["context"]["location"]["geo"]["coordinates"]
        distance_km = haversine_km(a, b)
    except (KeyError, TypeError):
        pass

    return [
        Signal(
            "SIMULTANEOUS_CLAIM",
            "critical",
            40,
            "Klaim ganda terdeteksi di dua faskes",
            {
                "other_session_id": str(other["_id"]),
                "other_faskes": other.get("context", {}).get("kode_faskes"),
                "delta_minutes": round(delta_min, 1),
                "distance_km": round(distance_km, 1),
            },
        )
    ]


async def _impossible_travel(db, session, peserta_id, now, ctx) -> list[Signal]:
    previous = await db.verification_sessions.find_one(
        {
            "_id": {"$ne": session["_id"]},
            "peserta_id": peserta_id,
            "status": "committed",
        },
        sort=[("created_at", -1)],
    )
    if not previous:
        return []
    try:
        here = ctx["location"]["geo"]["coordinates"]
        there = previous["context"]["location"]["geo"]["coordinates"]
    except (KeyError, TypeError):
        return []

    prev_at = previous.get("result", {}).get("decided_at") or previous["created_at"]
    if prev_at.tzinfo is None:
        prev_at = prev_at.replace(tzinfo=UTC)

    distance_km = haversine_km(here, there)
    minutes = (now - prev_at).total_seconds() / 60.0
    speed = implied_speed_kmh(distance_km, minutes)
    if speed <= IMPOSSIBLE_TRAVEL_KMH or distance_km < 1.0:
        return []

    return [
        Signal(
            "IMPOSSIBLE_TRAVEL",
            "high",
            30,
            "Perpindahan lokasi tidak masuk akal",
            {
                "distance_km": round(distance_km, 1),
                "elapsed_minutes": round(minutes, 1),
                "implied_kmh": round(speed, 1) if speed != float("inf") else "tak terhingga",
                "previous_faskes": previous.get("context", {}).get("kode_faskes"),
            },
        )
    ]


async def _high_frequency(db, peserta_id, now) -> list[Signal]:
    since = now - timedelta(days=HIGH_FREQUENCY_DAYS)
    count = await db.verification_sessions.count_documents(
        {"peserta_id": peserta_id, "result.decision": "APPROVED", "created_at": {"$gte": since}}
    )
    if count <= HIGH_FREQUENCY_LIMIT:
        return []
    return [
        Signal(
            "HIGH_FREQUENCY_CLAIM",
            "high",
            25,
            "Frekuensi klaim tidak wajar",
            {"approved_count": count, "window_days": HIGH_FREQUENCY_DAYS},
        )
    ]


async def _shared_device(db, ctx, peserta_id, now) -> list[Signal]:
    device_uid = ctx.get("device_uid")
    if not device_uid:
        return []
    since = now - timedelta(days=SHARED_DEVICE_DAYS)
    others = await db.verification_sessions.distinct(
        "peserta_id", {"context.device_uid": device_uid, "created_at": {"$gte": since}}
    )
    distinct = {str(p) for p in others} | {str(peserta_id)}
    if len(distinct) < SHARED_DEVICE_LIMIT:
        return []
    return [
        Signal(
            "SHARED_DEVICE",
            "medium",
            20,
            "Satu perangkat dipakai banyak peserta",
            {"peserta_count": len(distinct), "window_days": SHARED_DEVICE_DAYS},
        )
    ]


def _face_collision(collisions: list[dict]) -> list[Signal]:
    """The 1:N sweep found this face enrolled under a different no_bpjs."""
    if not collisions:
        return []
    top = collisions[0]
    return [
        Signal(
            "FACE_COLLISION",
            "critical",
            35,
            "Wajah cocok dengan peserta lain",
            {
                "other_peserta_id": str(top["peserta_id"]),
                "score": top["score"],
                "total_matches": len(collisions),
            },
        )
    ]


async def _repeated_failures(db, peserta_id, now) -> list[Signal]:
    since = now - timedelta(hours=FAILED_ATTEMPT_HOURS)
    count = await db.verification_events.count_documents(
        {"peserta_id": peserta_id, "step": "face", "outcome": "failed", "at": {"$gte": since}}
    )
    if count < FAILED_ATTEMPT_LIMIT:
        return []
    return [
        Signal(
            "REPEATED_FAILED_ATTEMPTS",
            "medium",
            15,
            "Percobaan verifikasi wajah gagal berulang",
            {"failed_count": count, "window_hours": FAILED_ATTEMPT_HOURS},
        )
    ]


def _low_match_margin(session) -> list[Signal]:
    face = session.get("steps", {}).get("face", {})
    score = face.get("match_score")
    threshold = face.get("threshold")
    review_floor = face.get("review_threshold")
    if score is None or threshold is None or review_floor is None:
        return []
    if not (review_floor <= score < threshold):
        return []
    return [
        Signal(
            "LOW_MATCH_MARGIN",
            "low",
            10,
            "Skor kecocokan wajah berada di ambang tinjau",
            {"match_score": score, "accept_threshold": threshold},
        )
    ]


def _software_key_only(session) -> list[Signal]:
    fp = session.get("steps", {}).get("fingerprint", {})
    if fp.get("security_level") != "SOFTWARE":
        return []
    return [
        Signal(
            "SOFTWARE_KEY_ONLY",
            "low",
            10,
            "Sidik jari diverifikasi tanpa pengikatan perangkat keras",
            {"method": fp.get("method")},
        )
    ]


def _off_hours(session, now) -> list[Signal]:
    poli = (session.get("claim") or {}).get("poli", "")
    if poli in EMERGENCY_POLI:
        return []
    wib_hour = (now + timedelta(hours=WIB_OFFSET_HOURS)).hour
    lo, hi = OFF_HOURS_WIB
    if not (lo <= wib_hour < hi):
        return []
    return [
        Signal(
            "OFF_HOURS",
            "info",
            5,
            "Klaim di luar jam layanan pada poli non-darurat",
            {"jam_wib": wib_hour, "poli": poli},
        )
    ]


def _menunggak(peserta) -> list[Signal]:
    months = peserta.get("tunggakan_bulan", 0) or 0
    if months <= 0:
        return []
    return [
        Signal(
            "PESERTA_MENUNGGAK",
            "medium",
            15,
            "Peserta memiliki tunggakan iuran",
            {"tunggakan_bulan": months, "status": peserta.get("status_kepesertaan")},
        )
    ]


async def persist(
    db: AsyncDatabase, signals: list[Signal], *, peserta_id: ObjectId, session_id: ObjectId
) -> None:
    if not signals:
        return
    now = datetime.now(UTC)
    await db.fraud_signals.insert_many(
        [
            {
                "peserta_id": peserta_id,
                "session_id": session_id,
                "rule_id": s.rule_id,
                "severity": s.severity,
                "weight": s.weight,
                "title": s.title,
                "detail": s.detail,
                "status": "open",
                "detected_at": now,
                "resolved_at": None,
                "resolved_by": None,
            }
            for s in signals
        ]
    )
