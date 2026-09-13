from __future__ import annotations

import cv2
import numpy as np

MAX_BYTES = 5 * 1024 * 1024
MAX_DIMENSION = 4096

MIN_BLUR_VAR = 8.0
MIN_FACE_SHARPNESS = 20.0
MIN_BRIGHTNESS = 60.0
MAX_BRIGHTNESS = 200.0


def decode(raw: bytes) -> np.ndarray:
    if len(raw) > MAX_BYTES:
        raise ValueError("IMAGE_TOO_LARGE")
    img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("DECODE_FAILED")
    h, w = img.shape[:2]
    if max(h, w) > MAX_DIMENSION:
        scale = MAX_DIMENSION / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    return img


def blur_variance(img_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def brightness(img_bgr: np.ndarray) -> float:
    return float(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).mean())


def quality_gate(img_bgr: np.ndarray) -> tuple[str | None, float, float]:
    """Returns (error_code | None, blur_var, brightness)."""
    blur = blur_variance(img_bgr)
    bright = brightness(img_bgr)
    if blur < MIN_BLUR_VAR:
        return "LOW_QUALITY_BLUR", blur, bright
    if bright < MIN_BRIGHTNESS or bright > MAX_BRIGHTNESS:
        return "LOW_QUALITY_LIGHT", blur, bright
    return None, blur, bright


def region_sharpness(img_bgr: np.ndarray, bbox: np.ndarray) -> float:
    x1, y1, x2, y2 = (int(max(0, v)) for v in bbox)
    crop = img_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return 0.0
    return blur_variance(crop)


def high_frequency_energy(img_bgr: np.ndarray) -> float:
    """Ratio of high-frequency energy in the FFT magnitude spectrum."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    if min(gray.shape) < 32:
        return 0.0
    spectrum = np.fft.fftshift(np.abs(np.fft.fft2(gray)))
    h, w = spectrum.shape
    cy, cx = h // 2, w // 2
    r = min(cy, cx) // 4
    low = spectrum[cy - r : cy + r, cx - r : cx + r].sum()
    total = spectrum.sum()
    if total <= 0:
        return 0.0
    return float((total - low) / total)


def saturation_stats(img_bgr: np.ndarray) -> tuple[float, float]:
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(np.float32)
    return float(sat.mean()), float(sat.std())
