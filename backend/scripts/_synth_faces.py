"""Synthetic faces for driving the pipeline without real photographs.

READ THIS BEFORE TRUSTING ANY NUMBER THESE PRODUCE.

SCRFD does detect these drawings (det_score ~0.75), and ArcFace does return
consistent 512-d embeddings for them, which is enough to exercise every stage of
the API end to end: enrolment, session state machine, matching, fraud rules.

But ArcFace was never trained on cartoons, so it collapses them into one tight
region of the embedding space. Measured on three synthetic identities:

    same "person"      0.951 - 0.975
    different "person" 0.654 - 0.887      <-- still far above the 0.42 threshold

Real photographs separate roughly 0.5-0.8 versus 0.0-0.2. So these fixtures:

    CAN   verify that the plumbing works and that same > different
    CANNOT validate FACE_MATCH_ACCEPT, FRR/FAR, or liveness robustness

They also CANNOT simulate head yaw. Both moving the drawn nose and applying a
perspective warp were tried; SCRFD's landmark regressor anchors to the drawing's
symmetric structure and the measured yaw proxy shifts by only ~0.02, far under
the 0.10 a real head turn produces. So `turn_left`/`turn_right` cannot be
exercised with these fixtures - only `move_closer` (area growth, which warps
faithfully) and the negative cases.

The right response to that is NOT to lower YAW_SHIFT_REQUIRED until a cartoon
passes - that would tune a security threshold to fit a bad fixture. The turn
challenges need validating on a real device with a real camera.

Threshold calibration needs real photographs of real people. Run
`scripts/check_face_models.py --images DIR` against those before any demo.
"""

from __future__ import annotations

import cv2
import numpy as np

PEOPLE: dict[str, dict] = {
    "andi": dict(skin=(190, 200, 215), hair=(40, 40, 60), eye=(60, 45, 35),
                 ew=24, gap=45, fw=110, fh=150),
    "budi": dict(skin=(140, 158, 188), hair=(20, 20, 25), eye=(30, 25, 20),
                 ew=19, gap=54, fw=125, fh=138),
    "citra": dict(skin=(212, 216, 226), hair=(90, 110, 150), eye=(120, 90, 55),
                  ew=28, gap=39, fw=98, fh=160),
}

WIDTH, HEIGHT = 480, 640


def render(
    person: str,
    *,
    seed: int = 0,
    nose_shift: int = 0,
    scale: float = 1.0,
    jitter: bool = True,
) -> np.ndarray:
    """Draw one frame.

    nose_shift moves the nose horizontally relative to the eyes, which is what
    the liveness yaw proxy measures - positive simulates turning left.
    scale grows the face, simulating "move closer".
    """
    p = PEOPLE[person]
    rng = np.random.default_rng(seed)
    w, h = WIDTH, HEIGHT
    dx, dy = (rng.integers(-6, 7, 2) if jitter else (0, 0))

    img = np.full((h, w, 3), (160, 165, 170), np.uint8)
    cx, cy = w // 2 + int(dx), h // 2 + int(dy)
    fw, fh = int(p["fw"] * scale), int(p["fh"] * scale)
    gap, ew = int(p["gap"] * scale), int(p["ew"] * scale)

    cv2.ellipse(img, (cx, cy), (fw, fh), 0, 0, 360, p["skin"], -1)
    cv2.ellipse(img, (cx, cy - fh + 20), (fw + 10, int(90 * scale)), 0, 0, 360, p["hair"], -1)

    for sgn in (-1, 1):
        ex, ey = cx + sgn * gap, cy - int(40 * scale)
        cv2.ellipse(img, (ex, ey), (ew, int(12 * scale)), 0, 0, 360, (255, 255, 255), -1)
        cv2.circle(img, (ex, ey), int(9 * scale), p["eye"], -1)
        cv2.circle(img, (ex, ey), int(4 * scale), (10, 10, 10), -1)
        cv2.ellipse(img, (ex, ey - int(16 * scale)), (ew + 2, int(10 * scale)), 0, 180, 360,
                    p["hair"], 3)

    nose_x = cx + nose_shift
    cv2.ellipse(img, (nose_x, cy + int(15 * scale)), (int(16 * scale), int(30 * scale)),
                0, 0, 360, tuple(int(c * 0.88) for c in p["skin"]), -1)
    cv2.ellipse(img, (cx, cy + int(80 * scale)), (int(38 * scale), int(18 * scale)),
                0, 0, 180, (120, 110, 140), -1)

    img = cv2.GaussianBlur(img, (5, 5), 0)
    return cv2.add(img, rng.integers(0, 18, (h, w, 3), dtype=np.uint8))


def _yaw_warp(img: np.ndarray, amount: float) -> np.ndarray:
    """Perspective-warp the frame to simulate a head turn.

    Moving the drawn nose alone does not work: SCRFD regresses the nose KEYPOINT
    from overall face structure, so it barely follows a repositioned ellipse. A
    perspective warp moves eyes, nose and mouth together, which is what a real
    yaw does and what the landmark model actually responds to.
    """
    if abs(amount) < 1e-6:
        return img
    h, w = img.shape[:2]
    dx = amount * w * 0.18
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[dx, 0], [w + dx * 0.25, 0], [w + dx * 0.25, h], [dx, h]])
    if amount > 0:
        dst = np.float32([[0, 0], [w - dx, dx * 0.35], [w - dx, h - dx * 0.35], [0, h]])
    else:
        d = -dx
        dst = np.float32([[d, d * 0.35], [w, 0], [w, h], [d, h - d * 0.35]])
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, matrix, (w, h), borderValue=(160, 165, 170))


def burst(person: str, challenge: str | None = "turn_left", seed: int = 0) -> list[bytes]:
    """Three JPEG frames that satisfy the given liveness challenge."""
    frames = []
    for i in range(3):
        t = i / 2.0
        if challenge == "turn_left":
            img = _yaw_warp(render(person, seed=seed + i), amount=0.9 * t)
        elif challenge == "turn_right":
            img = _yaw_warp(render(person, seed=seed + i), amount=-0.9 * t)
        elif challenge == "move_closer":
            img = render(person, seed=seed + i, scale=1.0 + 0.22 * t)
        else:
            img = render(person, seed=seed + i)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not ok:
            raise RuntimeError("JPEG encode failed")
        frames.append(buf.tobytes())
    return frames


def still(person: str, seed: int = 0) -> list[bytes]:
    """Three IDENTICAL frames - simulates holding a printed photo to the camera.

    Micro-motion is zero and the challenge is never satisfied, so this is what a
    working liveness check must reject.
    """
    img = render(person, seed=seed, jitter=False)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return [buf.tobytes()] * 3
