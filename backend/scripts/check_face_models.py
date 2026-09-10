"""Prove the ONNX face pipeline works before any router depends on it.

    python scripts/check_face_models.py                 # mechanical checks only
    python scripts/check_face_models.py --images DIR    # real photos, full pipeline

This is the riskiest single step in the backend: insightface has no cp312 wheel,
so if running the graphs directly did not work, the whole face design would need
rethinking. Run it first, before trusting any endpoint.

With --images, point at a folder of JPEGs named <person>_<n>.jpg (e.g.
marcel_1.jpg, marcel_2.jpg, budi_1.jpg). Same-person pairs should score well
above the accept threshold and different-person pairs well below it.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

import _bootstrap_path  # noqa: F401  (side effect: sys.path)
from app.config import get_settings
from app.security import rotation
from app.services import face_engine
from app.utils import images


def mechanical_checks(engine: face_engine.FaceEngine) -> bool:
    """Verify the graphs execute and produce well-formed output, with no photos."""
    ok = True
    print("\n[*] Mechanical checks (no real faces needed)")

    noise = np.random.default_rng(0).integers(0, 255, (480, 640, 3), dtype=np.uint8)
    t0 = time.perf_counter()
    faces = engine.detect(noise)
    dt = (time.perf_counter() - t0) * 1000
    print(f"  [+] detector ran on random noise in {dt:6.1f} ms -> {len(faces)} faces (0 expected)")

    # Embed an arbitrary crop by feeding the reference landmarks, which makes the
    # alignment transform the identity. This exercises ArcFace without needing a
    # detectable face.
    crop = np.random.default_rng(1).integers(0, 255, (112, 112, 3), dtype=np.uint8)
    t0 = time.perf_counter()
    vec = engine.embed(crop, face_engine.ARCFACE_REF.copy())
    dt = (time.perf_counter() - t0) * 1000
    print(f"  [+] recogniser ran in {dt:6.1f} ms -> shape {vec.shape}, dtype {vec.dtype}")

    if vec.shape != (engine.embedding_dim,):
        print(f"  [!] expected shape ({engine.embedding_dim},)")
        ok = False

    norm = float(np.linalg.norm(vec))
    print(f"  [+] L2 norm = {norm:.6f} (1.0 expected)")
    if abs(norm - 1.0) > 1e-4:
        print("  [!] embedding is not L2-normalised")
        ok = False

    self_cos = rotation.cosine(vec, vec)
    print(f"  [+] self-cosine = {self_cos:.6f} (1.0 expected)")
    if abs(self_cos - 1.0) > 1e-5:
        ok = False

    vec2 = engine.embed(crop, face_engine.ARCFACE_REF.copy())
    if not np.allclose(vec, vec2, atol=1e-5):
        print("  [!] same input gave different embeddings - inference is not deterministic")
        ok = False
    else:
        print("  [+] deterministic: same input -> identical embedding")

    other = engine.embed(
        np.random.default_rng(2).integers(0, 255, (112, 112, 3), dtype=np.uint8),
        face_engine.ARCFACE_REF.copy(),
    )
    print(f"  [+] cosine against a different crop = {rotation.cosine(vec, other):+.4f}")

    print("\n[*] Latency over 10 runs")
    for label, fn in (
        ("detect  640x480", lambda: engine.detect(noise)),
        ("embed   112x112", lambda: engine.embed(crop, face_engine.ARCFACE_REF.copy())),
    ):
        times = []
        for _ in range(10):
            t0 = time.perf_counter()
            fn()
            times.append((time.perf_counter() - t0) * 1000)
        print(f"  {label}: mean {np.mean(times):6.1f} ms   p90 {np.percentile(times, 90):6.1f} ms")

    return ok


def real_images(engine: face_engine.FaceEngine, folder: Path, settings) -> bool:
    print(f"\n[*] Real-image pipeline over {folder}")
    files = sorted(
        p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    if not files:
        print(f"  [!] no images found in {folder}")
        return False

    by_person: dict[str, list[tuple[str, np.ndarray]]] = defaultdict(list)
    for path in files:
        img = images.decode(path.read_bytes())
        code, blur, bright = images.quality_gate(img)
        faces = engine.detect(img)
        if not faces:
            print(f"  [-] {path.name:<28} NO FACE (blur {blur:.0f}, light {bright:.0f})")
            continue
        face = faces[0]
        note = f"gate={code}" if code else "gate=ok"
        print(
            f"  [+] {path.name:<28} det {face.det_score:.3f}  {int(face.short_side):>4}px  "
            f"blur {blur:6.0f}  {note}"
        )
        by_person[path.stem.split("_")[0]].append((path.name, engine.embed(img, face.kps)))

    if not by_person:
        return False

    print("\n[*] Same-person pairs (should be >= accept threshold "
          f"{settings.face_match_accept})")
    same_scores = []
    for person, items in by_person.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                score = rotation.cosine(items[i][1], items[j][1])
                same_scores.append(score)
                verdict = "PASS" if score >= settings.face_match_accept else "FAIL"
                print(f"  [{verdict}] {person:<12} {items[i][0]} vs {items[j][0]}: {score:.4f}")

    print(f"\n[*] Different-person pairs (should be < reject threshold "
          f"{settings.face_match_review})")
    diff_scores = []
    names = list(by_person)
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            score = rotation.cosine(by_person[names[a]][0][1], by_person[names[b]][0][1])
            diff_scores.append(score)
            verdict = "PASS" if score < settings.face_match_review else "FAIL"
            print(f"  [{verdict}] {names[a]} vs {names[b]}: {score:.4f}")

    if same_scores and diff_scores:
        margin = min(same_scores) - max(diff_scores)
        print(f"\n[*] Separation margin: {margin:+.4f}")
        print(f"    worst same-person {min(same_scores):.4f} | best different-person {max(diff_scores):.4f}")
        if margin <= 0:
            print("    [!] Classes overlap. Do NOT trust the thresholds - recalibrate.")
            return False
        mid = (min(same_scores) + max(diff_scores)) / 2
        print(f"    Suggested FACE_MATCH_ACCEPT around {mid:.2f} for this data.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the ONNX face pipeline.")
    parser.add_argument("--images", type=Path, help="Folder of <person>_<n>.jpg photos")
    parser.add_argument("--rec-model", type=Path, help="Override the recognition model")
    args = parser.parse_args()

    settings = get_settings()
    det = settings.face_det_model
    rec = args.rec_model or settings.face_rec_model

    print(f"[*] Python {sys.version.split()[0]}")
    import onnxruntime as ort

    print(f"[*] onnxruntime {ort.__version__} providers={ort.get_available_providers()}")
    print(f"[*] detector   {det}")
    print(f"[*] recogniser {rec}")

    for path in (det, rec):
        if not Path(path).exists():
            print(f"\n[!] Missing model: {path}")
            print("    See backend/README.md for the download instructions.")
            return 1

    t0 = time.perf_counter()
    engine = face_engine.FaceEngine(
        Path(det), Path(rec), intra_op_threads=settings.ort_intra_op_threads
    )
    print(f"[+] Both models loaded in {time.perf_counter() - t0:.1f}s, dim={engine.embedding_dim}")

    ok = mechanical_checks(engine)
    if args.images:
        ok = real_images(engine, args.images, settings) and ok
    else:
        print("\n[*] No --images given, so real-face matching was NOT verified.")
        print("    The graphs execute correctly, but accuracy and thresholds are unproven.")
        print("    Run: python scripts/check_face_models.py --images path/to/photos")

    print("\n" + ("[+] PASS" if ok else "[!] FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
