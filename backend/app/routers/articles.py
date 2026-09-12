"""Artikel kesehatan.

Sebelumnya satu artikel di-hardcode di home_page.dart bersama URL gambar
Unsplash, sehingga mengubah isinya berarti merilis ulang aplikasi. Sekarang
isinya ada di MongoDB dan dikelola lewat API.

Membaca artikel tidak memerlukan autentikasi - ini materi edukasi publik, dan
mewajibkan token hanya akan menghalangi kampanye kesehatan yang justru ingin
dijangkau seluas mungkin. Menulis tetap memerlukan kunci operator.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Query

from app.deps import DbDep, OperatorDep
from app.utils.errors import ApiError

router = APIRouter(prefix="/articles", tags=["articles"])

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    return _SLUG_STRIP.sub("-", text.lower()).strip("-")[:80]


def _public(doc: dict, *, full: bool = False) -> dict:
    out = {
        "slug": doc["slug"],
        "judul": doc["judul"],
        "ringkasan": doc.get("ringkasan", ""),
        "kategori": doc.get("kategori", ""),
        "image_url": doc.get("image_url"),
        "penulis": doc.get("penulis"),
        "published_at": doc.get("published_at"),
        "reading_minutes": doc.get("reading_minutes"),
        "featured": doc.get("featured", False),
    }
    if full:
        out["konten"] = doc.get("konten", "")
        out["sumber"] = doc.get("sumber")
    return out


@router.get("")
async def list_articles(
    db: DbDep,
    limit: int = Query(default=20, ge=1, le=50),
    skip: int = Query(default=0, ge=0),
    kategori: str | None = None,
    featured_only: bool = False,
    q: str | None = None,
) -> dict:
    query: dict = {"published": True}
    if kategori:
        query["kategori"] = kategori
    if featured_only:
        query["featured"] = True
    if q:
        # Pencarian sederhana pada judul dan ringkasan. Cukup untuk katalog
        # sebesar ini; kalau tumbuh, naikkan ke text index.
        query["$or"] = [
            {"judul": {"$regex": re.escape(q), "$options": "i"}},
            {"ringkasan": {"$regex": re.escape(q), "$options": "i"}},
        ]

    total = await db.articles.count_documents(query)
    docs = (
        await db.articles.find(query)
        .sort([("featured", -1), ("published_at", -1)])
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )
    return {
        "status": "ok",
        "items": [_public(d) for d in docs],
        "total": total,
        "has_more": skip + len(docs) < total,
    }


@router.get("/categories")
async def list_categories(db: DbDep) -> dict:
    categories = await db.articles.distinct("kategori", {"published": True})
    return {"status": "ok", "kategori": sorted(c for c in categories if c)}


@router.get("/{slug}")
async def get_article(slug: str, db: DbDep) -> dict:
    doc = await db.articles.find_one({"slug": slug, "published": True})
    if not doc:
        raise ApiError("ARTICLE_NOT_FOUND", 404, message="Artikel tidak ditemukan.")

    # Penghitung baca. Tidak fatal kalau gagal - artikelnya tetap dikirim.
    await db.articles.update_one({"_id": doc["_id"]}, {"$inc": {"views": 1}})
    return {"status": "ok", "article": _public(doc, full=True)}


@router.post("")
async def upsert_article(payload: dict, db: DbDep, _: OperatorDep) -> dict:
    judul = (payload.get("judul") or "").strip()
    if not judul:
        raise ApiError("VALIDATION_ERROR", 422, details={"field": "judul"})

    slug = (payload.get("slug") or slugify(judul)).strip()
    now = datetime.now(UTC)
    konten = payload.get("konten", "")

    doc = {
        "slug": slug,
        "judul": judul,
        "ringkasan": (payload.get("ringkasan") or "").strip(),
        "konten": konten,
        "kategori": (payload.get("kategori") or "Umum").strip(),
        "image_url": payload.get("image_url"),
        "penulis": payload.get("penulis"),
        "sumber": payload.get("sumber"),
        "featured": bool(payload.get("featured", False)),
        "published": bool(payload.get("published", True)),
        # ~200 kata per menit, minimum 1 - supaya tidak pernah tampil "0 menit".
        "reading_minutes": max(1, round(len(konten.split()) / 200)),
        "updated_at": now,
    }

    existing = await db.articles.find_one({"slug": slug}, {"_id": 1})
    if existing:
        await db.articles.update_one({"_id": existing["_id"]}, {"$set": doc})
        return {"status": "ok", "slug": slug, "created": False}

    doc["published_at"] = payload.get("published_at") or now
    doc["views"] = 0
    await db.articles.insert_one(doc)
    return {"status": "ok", "slug": slug, "created": True}


@router.delete("/{slug}")
async def delete_article(slug: str, db: DbDep, _: OperatorDep) -> dict:
    result = await db.articles.delete_one({"slug": slug})
    if result.deleted_count == 0:
        raise ApiError("ARTICLE_NOT_FOUND", 404, message="Artikel tidak ditemukan.")
    return {"status": "ok", "slug": slug}
