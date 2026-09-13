from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

from app.config import get_settings

DEFAULT_NIK = "3174050412010001"
DEFAULT_BPJS = "0001234567890"
DEFAULT_FASKES = "0110P001"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def collect_from_folder(folder: Path) -> list[tuple[str, bytes]]:
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not files:
        raise SystemExit(f"[!] No .jpg/.png files found in {folder}")
    print(f"[*] Using {len(files)} image(s) from {folder}")
    for f in files:
        print(f"      {f.name}  ({f.stat().st_size // 1024} KB)")
    return [(f.name, f.read_bytes()) for f in files]


def collect_from_webcam(count: int = 3) -> list[tuple[str, bytes]]:
    """Capture frames interactively. Needs a GUI-capable OpenCV build."""
    import cv2

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise SystemExit(
            "[!] Could not open the webcam.\n"
            "    opencv-python-headless has no GUI support, so --webcam cannot show a\n"
            "    preview window. Either take photos with your phone and use --images,\n"
            "    or install the full package:  pip install opencv-python"
        )

    print(f"[*] Webcam open. Press SPACE to capture ({count} needed), Q to abort.")
    print("    Vary your angle and expression slightly between shots.")
    shots: list[tuple[str, bytes]] = []
    try:
        while len(shots) < count:
            ok, frame = cap.read()
            if not ok:
                raise SystemExit("[!] Failed to read from the webcam.")

            preview = frame.copy()
            cv2.putText(
                preview,
                f"SPACE = capture ({len(shots)}/{count})   Q = abort",
                (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )
            cv2.imshow("IdentiCare - enrolment", preview)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                raise SystemExit("[!] Aborted.")
            if key == ord(" "):
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
                if ok:
                    shots.append((f"webcam_{len(shots)}.jpg", buf.tobytes()))
                    print(f"    captured {len(shots)}/{count}")
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return shots


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrol a real face for the demo.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--images", type=Path, help="Folder of photos of one person")
    source.add_argument("--webcam", action="store_true", help="Capture from the webcam")
    parser.add_argument("--verify", type=Path, help="Check an existing enrolment against a photo")

    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--nama", default="Peserta Demo")
    parser.add_argument("--nik", default=DEFAULT_NIK)
    parser.add_argument("--no-bpjs", default=DEFAULT_BPJS)
    parser.add_argument("--kode-faskes", default=DEFAULT_FASKES)
    parser.add_argument("--tanggal-lahir", default="2001-12-04")
    parser.add_argument("--jenis-kelamin", default="L", choices=["L", "P"])
    parser.add_argument(
        "--firebase-uid",
        help="Link to the Firebase account you sign into the app with. "
        "Without it, the app cannot find this participant's history.",
    )
    parser.add_argument("--operator-key", default=None)
    args = parser.parse_args()

    settings = get_settings()
    operator_key = args.operator_key or settings.operator_api_key
    api = f"{args.url.rstrip('/')}/api/v1"
    operator = {"X-Api-Key": operator_key}
    http = httpx.Client(timeout=120.0)

    try:
        health = http.get(f"{api}/health").json()
    except httpx.HTTPError as exc:
        raise SystemExit(
            f"[!] Cannot reach the API at {args.url}: {exc}\n"
            "    Start it with:  uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend"
        ) from exc

    if health["checks"]["face_models"] != "loaded":
        raise SystemExit(
            "[!] Face models are not loaded on the server.\n"
            f"    {health['checks'].get('face_models_error')}\n"
            "    See backend/README.md for the download instructions."
        )
    print(f"[+] API healthy, face models loaded (dim={health['checks']['embedding_dim']})")

    if args.verify:
        return verify(http, api, operator, args)

    if not args.images and not args.webcam:
        parser.error("give --images FOLDER, --webcam, or --verify PHOTO")

    images = collect_from_webcam() if args.webcam else collect_from_folder(args.images)
    if len(images) < 2:
        print("[!] Only one image. Two or three give a much more robust template.")

    print(f"\n[*] Upserting peserta {args.no_bpjs} ({args.nama})")
    response = http.post(
        f"{api}/enrollment/peserta",
        headers=operator,
        json={
            "nik": args.nik,
            "no_bpjs": args.no_bpjs,
            "nama_lengkap": args.nama,
            "tanggal_lahir": args.tanggal_lahir,
            "jenis_kelamin": args.jenis_kelamin,
            "kelas_rawat": 1,
            "jenis_peserta": "PPU",
            "kode_faskes_tingkat1": args.kode_faskes,
            "status_kepesertaan": "AKTIF",
            "firebase_uid": args.firebase_uid,
        },
    )
    if response.status_code != 200:
        raise SystemExit(f"[!] peserta upsert failed: {response.status_code} {response.text[:300]}")
    print(f"[+] peserta_id={response.json()['peserta_id']}")

    if not args.firebase_uid:
        print("[!] No --firebase-uid given. The app will not be able to load this")
        print("    participant's verification history until the account is linked.")
        print("    Sign up in the app with this BPJS number, or re-run with --firebase-uid.")

    print("\n[*] Enrolling face...")
    response = http.post(
        f"{api}/enrollment/face",
        headers=operator,
        data={"no_bpjs": args.no_bpjs, "replace": "true"},
        files=[("frames", (name, blob, "image/jpeg")) for name, blob in images],
    )
    if response.status_code != 200:
        is_json = response.headers.get("content-type", "").startswith("application/json")
        body = response.json() if is_json else {}
        code = body.get("error_code", "")
        print(f"[!] Enrolment failed: {response.status_code} {code}")
        print(f"    {body.get('message', response.text[:300])}")
        print(explain(code, body))
        return 1

    result = response.json()
    quality = result.get("quality", {})
    print(f"[+] Enrolled. frames_used={result['frames_used']}/{len(images)}")
    if quality:
        print(
            f"    detection {quality.get('det_score')}  face {quality.get('face_px')}px  "
            f"blur {quality.get('blur_var')}  brightness {quality.get('brightness')}"
        )

    print("\n[*] Done. Now run the app:")
    print(f"    flutter run --dart-define=API_BASE_URL={args.url}")
    print(f"    Sign in, and use BPJS number {args.no_bpjs}.")
    print("\n[*] To check the enrolment against a NEW photo of yourself:")
    print("    python scripts/enroll_me.py --verify path/to/photo.jpg")
    return 0


def verify(http: httpx.Client, api: str, operator: dict, args) -> int:
    """Score a fresh photo against the stored template, without a session."""
    photo = args.verify
    if not photo.exists():
        raise SystemExit(f"[!] Not found: {photo}")

    print(f"\n[*] Verifying {photo.name} against enrolled templates")
    response = http.post(
        f"{api}/enrollment/face/probe",
        headers=operator,
        files=[("frames", (photo.name, photo.read_bytes(), "image/jpeg"))],
    )
    if response.status_code == 404:
        print("[!] This server build has no /enrollment/face/probe endpoint.")
        print("    Use the app itself, or scripts/check_face_models.py --images DIR")
        print("    to compare two photos directly.")
        return 1
    if response.status_code != 200:
        print(f"[!] {response.status_code} {response.text[:300]}")
        return 1

    body = response.json()
    matches = body.get("matches", [])
    if not matches:
        print("[-] No enrolled participant matched this photo.")
        return 1

    settings = get_settings()
    for match in matches:
        verdict = "MATCH" if match["score"] >= settings.face_match_accept else "below threshold"
        print(f"    {match['score']:.4f}  {match.get('nama', match['peserta_id'])}  [{verdict}]")
    print(f"\n    accept >= {settings.face_match_accept}, reject < {settings.face_match_review}")
    return 0


def explain(code: str, body: dict) -> str:
    if code == "NO_FACE_DETECTED":
        return (
            "    No face was found. Check that the face is well lit, roughly front-on,\n"
            "    and large in the frame (at least ~112 px across)."
        )
    if code == "ENROLL_FRAMES_INCONSISTENT":
        worst = body.get("details", {}).get("min_pairwise_cosine")
        return (
            f"    The photos do not agree with each other (worst pair {worst}).\n"
            "    They are probably of different people, or one is badly blurred.\n"
            "    This check is what stops two people being merged into one identity."
        )
    if code == "ALREADY_ENROLLED":
        return "    Pass --replace is already set, so this should not happen; check the peserta id."
    return ""


if __name__ == "__main__":
    sys.exit(main())
