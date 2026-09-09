"""Liveness detection: active challenge-response.

Why not a passive CNN. The standard open anti-spoof model (MiniFASNet, from the
Silent-Face-Anti-Spoofing project) ships as a PyTorch .pth with no official ONNX
export. Community conversions exist but are unvetted binaries, and putting an
unverifiable third-party artefact on the critical path of a fraud-prevention
demo is a worse risk than the one it mitigates.

What we have instead is already enough for a defensible check: SCRFD gives 5
keypoints per frame, and the client submits a 3-frame burst. The server issues a
RANDOM, single-use challenge before capture, so a pre-recorded video cannot
satisfy a direction chosen after the recording was made. That property - not the
texture heuristics - is what actually defeats replay.

Structured behind LivenessBackend so a passive model can be dropped in later
without touching the router.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from app.services.face_engine import Face
from app.utils import images

CHALLENGES = ("turn_left", "turn_right", "move_closer")

CHALLENGE_TEXT = {
    "turn_left": "Palingkan wajah ke kiri",
    "turn_right": "Palingkan wajah ke kanan",
    "move_closer": "Dekatkan wajah ke kamera",
}

# Weights sum to 1.0. Challenge compliance dominates because it is the only
# signal an attacker cannot satisfy ahead of time.
W_CHALLENGE = 0.35
W_MOTION = 0.20
W_TEXTURE = 0.15
W_MOIRE = 0.15
W_COLOR = 0.15

# Calibrated against measured captures, not guessed. With the offset-based yaw
# proxy a deliberate head turn shifts this by well over 0.10, while a static
# image shifts it by exactly 0.0.
YAW_SHIFT_REQUIRED = 0.10
AREA_GROWTH_REQUIRED = 0.25

# Keypoint displacement between frames ~340 ms apart. A hand-held phone measures
# 2-8 px; a photo taped to a stand measures 0. An earlier curve peaked at ~20 px,
# which scored real hand-held captures at 0.15 and would have failed genuine
# users - the threshold has to match how still a real hand actually is.
MOTION_DEAD_PX = 0.5     # below this: nothing moved at all -> printed photo
MOTION_GOOD_LO = 2.0     # full credit from here...
MOTION_GOOD_HI = 25.0    # ...to here
MOTION_MAX_PX = 40.0     # above this: a cut or a swapped image, not a head


def new_challenge() -> str:
    return secrets.choice(CHALLENGES)


@dataclass
class LivenessResult:
    passed: bool
    score: float
    method: str
    signals: dict[str, float]
    reason: str | None = None


class LivenessBackend(Protocol):
    name: str

    def evaluate(
        self, frames: list[np.ndarray], faces: list[Face], challenge: str | None, threshold: float
    ) -> LivenessResult: ...


class ActiveChallengeV1:
    name = "active_challenge_v1"

    def evaluate(
        self,
        frames: list[np.ndarray],
        faces: list[Face],
        challenge: str | None,
        threshold: float,
    ) -> LivenessResult:
        signals: dict[str, float] = {}

        if len(faces) < 2:
            # One usable frame cannot show motion at all. Fail closed rather than
            # awarding the motion and challenge points by default.
            return LivenessResult(
                passed=False,
                score=0.0,
                method=self.name,
                signals={"frames": float(len(faces))},
                reason="butuh minimal 2 frame wajah",
            )

        signals["challenge"] = self._challenge_score(faces, challenge)
        signals["motion"] = self._motion_score(faces)
        signals["texture"] = self._texture_score(frames, faces)
        signals["moire"] = self._moire_score(frames, faces)
        signals["color"] = self._color_score(frames, faces)

        score = (
            W_CHALLENGE * signals["challenge"]
            + W_MOTION * signals["motion"]
            + W_TEXTURE * signals["texture"]
            + W_MOIRE * signals["moire"]
            + W_COLOR * signals["color"]
        )
        passed = score >= threshold
        reason = None
        if not passed:
            weakest = min(signals, key=signals.get)
            reason = f"sinyal terlemah: {weakest} ({signals[weakest]:.2f})"
        return LivenessResult(passed, round(float(score), 4), self.name, signals, reason)

    # ------------------------------------------------------------------ #
    def _challenge_score(self, faces: list[Face], challenge: str | None) -> float:
        if not challenge:
            # No challenge was issued, so there is nothing to comply with. Award a
            # neutral score rather than a free pass.
            return 0.5

        first, last = faces[0], faces[-1]
        if challenge == "move_closer":
            growth = (last.area - first.area) / max(first.area, 1.0)
            return float(np.clip(growth / AREA_GROWTH_REQUIRED, 0.0, 1.0))

        shift = last.yaw_proxy() - first.yaw_proxy()
        if challenge == "turn_right":
            shift = -shift
        return float(np.clip(shift / YAW_SHIFT_REQUIRED, 0.0, 1.0))

    def _motion_score(self, faces: list[Face]) -> float:
        """A printed photo held still gives ~0 displacement; a swiped video jumps.

        Plateau rather than a peak: everything from a steady hand to a lively one
        is equally alive, so the score is flat across that whole band and only
        falls off at the two implausible extremes.
        """
        deltas = [
            float(np.abs(faces[i].kps - faces[i - 1].kps).mean()) for i in range(1, len(faces))
        ]
        motion = float(np.mean(deltas)) if deltas else 0.0

        if motion < MOTION_DEAD_PX or motion > MOTION_MAX_PX:
            return 0.0
        if motion < MOTION_GOOD_LO:
            return float((motion - MOTION_DEAD_PX) / (MOTION_GOOD_LO - MOTION_DEAD_PX))
        if motion <= MOTION_GOOD_HI:
            return 1.0
        return float(1.0 - (motion - MOTION_GOOD_HI) / (MOTION_MAX_PX - MOTION_GOOD_HI))

    def _texture_score(self, frames: list[np.ndarray], faces: list[Face]) -> float:
        """Screen replays are uniformly sharp; a real scene has depth of field, so
        the face is sharper than the background."""
        scores = []
        for frame, face in zip(frames, faces, strict=False):
            face_sharp = images.region_sharpness(frame, face.bbox)
            whole = images.blur_variance(frame)
            if whole <= 0:
                continue
            scores.append(np.clip(face_sharp / whole / 1.5, 0.0, 1.0))
        return float(np.mean(scores)) if scores else 0.5

    def _moire_score(self, frames: list[np.ndarray], faces: list[Face]) -> float:
        scores = []
        for frame, face in zip(frames, faces, strict=False):
            x1, y1, x2, y2 = (int(max(0, v)) for v in face.bbox)
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            hf = images.high_frequency_energy(crop)
            # Live skin sits in a moderate band; a screen pushes energy higher.
            scores.append(np.clip(1.0 - abs(hf - 0.55) / 0.45, 0.0, 1.0))
        return float(np.mean(scores)) if scores else 0.5

    def _color_score(self, frames: list[np.ndarray], faces: list[Face]) -> float:
        """Printed paper and screens skew the saturation histogram away from skin."""
        scores = []
        for frame, face in zip(frames, faces, strict=False):
            x1, y1, x2, y2 = (int(max(0, v)) for v in face.bbox)
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            mean_sat, std_sat = images.saturation_stats(crop)
            sat_ok = np.clip(1.0 - abs(mean_sat - 90.0) / 90.0, 0.0, 1.0)
            var_ok = np.clip(std_sat / 45.0, 0.0, 1.0)
            scores.append(0.6 * sat_ok + 0.4 * var_ok)
        return float(np.mean(scores)) if scores else 0.5


_backend: LivenessBackend = ActiveChallengeV1()


def get_backend() -> LivenessBackend:
    return _backend
