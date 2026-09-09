"""Face detection (SCRFD) and recognition (ArcFace) via onnxruntime.

No face-recognition Python package is installed. We run InsightFace's published
ONNX graphs directly, which is what avoids the MSVC/Cython build wall that
`pip install insightface` hits on Python 3.12 + Windows. Same models, same
accuracy, none of the toolchain pain.

Models (download manually into backend/models/, see README):
  det_500m.onnx   SCRFD-500MF   ~2.5 MB   boxes + 5 keypoints
  w600k_r50.onnx  ArcFace R50   ~166 MB   512-d embedding

Both sessions are created once at startup and reused. ONNX Runtime sessions are
thread-safe for concurrent `run()`, so the FastAPI layer can call these from a
worker thread without extra locking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

log = logging.getLogger(__name__)

# The canonical ArcFace 5-point reference, in 112x112 space. Every ArcFace model
# ever published expects faces warped onto exactly these coordinates; changing
# them silently degrades every embedding.
ARCFACE_REF = np.array(
    [
        [38.2946, 51.6963],  # left eye
        [73.5318, 51.5014],  # right eye
        [56.0252, 71.7366],  # nose tip
        [41.5493, 92.3655],  # left mouth corner
        [70.7299, 92.2041],  # right mouth corner
    ],
    dtype=np.float32,
)

DET_SIZE = 640
REC_SIZE = 112


@dataclass
class Face:
    bbox: np.ndarray  # [x1, y1, x2, y2]
    kps: np.ndarray  # (5, 2)
    det_score: float
    sharpness: float = 0.0
    embedding: np.ndarray | None = None

    @property
    def width(self) -> float:
        return float(self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> float:
        return float(self.bbox[3] - self.bbox[1])

    @property
    def short_side(self) -> float:
        return min(self.width, self.height)

    @property
    def area(self) -> float:
        return self.width * self.height

    def yaw_proxy(self) -> float:
        """Cheap left/right head-turn estimate from the 5 keypoints.

        Horizontal offset of the nose from the eye midpoint, normalised by the
        inter-ocular distance. Not a calibrated angle - it only has to be
        monotonic in head yaw and stable in scale.

        An earlier version compared eye-to-nose *distances* normalised by face
        width. That was far too insensitive: a large nose displacement moved it
        by only ~0.03, because Euclidean distance to each eye changes
        sub-linearly with horizontal shift and face width is roughly twice the
        inter-ocular distance. The offset form below responds roughly 25x more
        strongly to the same movement.
        """
        left_eye, right_eye, nose = self.kps[0], self.kps[1], self.kps[2]
        eye_mid_x = (float(left_eye[0]) + float(right_eye[0])) / 2.0
        interocular = abs(float(right_eye[0]) - float(left_eye[0]))
        if interocular < 1.0:
            return 0.0
        return (float(nose[0]) - eye_mid_x) / interocular


@dataclass
class FrameAnalysis:
    """Everything one submitted frame yielded, including why it was rejected."""

    index: int
    ok: bool
    error_code: str | None = None
    face: Face | None = None
    blur_var: float = 0.0
    brightness: float = 0.0
    shape: tuple[int, int] = (0, 0)
    extras: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# SCRFD decode helpers
# --------------------------------------------------------------------------- #
def _distance2bbox(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


def _distance2kps(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    preds = []
    for i in range(0, distance.shape[1], 2):
        preds.append(points[:, 0] + distance[:, i])
        preds.append(points[:, 1] + distance[:, i + 1])
    return np.stack(preds, axis=-1)


def _nms(dets: np.ndarray, thresh: float = 0.4) -> list[int]:
    x1, y1, x2, y2, scores = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3], dets[:, 4]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]

    keep: list[int] = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1 + 1) * np.maximum(0.0, yy2 - yy1 + 1)
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[np.where(iou <= thresh)[0] + 1]
    return keep


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
class FaceEngine:
    def __init__(
        self,
        det_model: Path,
        rec_model: Path,
        det_thresh: float = 0.5,
        nms_thresh: float = 0.4,
        intra_op_threads: int = 4,
    ) -> None:
        self.det_thresh = det_thresh
        self.nms_thresh = nms_thresh

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = intra_op_threads
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        providers = ["CPUExecutionProvider"]

        log.info("Loading detector %s", det_model)
        self.det = ort.InferenceSession(str(det_model), opts, providers=providers)
        log.info("Loading recogniser %s", rec_model)
        self.rec = ort.InferenceSession(str(rec_model), opts, providers=providers)

        self.det_input = self.det.get_inputs()[0].name
        self.det_outputs = [o.name for o in self.det.get_outputs()]
        self.rec_input = self.rec.get_inputs()[0].name
        self.rec_output = self.rec.get_outputs()[0].name

        # SCRFD variants differ in output count. 9 outputs = with keypoints,
        # 6 = boxes only (unusable here, we need the keypoints for alignment).
        n_out = len(self.det_outputs)
        self.fmc = 3
        self.feat_strides = [8, 16, 32]
        self.use_kps = n_out >= 9
        self.num_anchors = 2
        if n_out in (6, 9):
            self.fmc, self.feat_strides, self.num_anchors = 3, [8, 16, 32], 2
        elif n_out in (10, 15):
            self.fmc, self.feat_strides, self.num_anchors = 5, [8, 16, 32, 64, 128], 1
            self.use_kps = n_out == 15
        if not self.use_kps:
            raise RuntimeError(
                f"Detector {det_model.name} has {n_out} outputs and emits no keypoints. "
                "Face alignment needs the 5-point landmarks - use det_500m.onnx "
                "(buffalo_s) or det_10g.onnx (buffalo_l)."
            )

        self.embedding_dim = int(self.rec.get_outputs()[0].shape[-1])
        log.info(
            "FaceEngine ready: %d det outputs, kps=%s, embedding_dim=%d",
            n_out,
            self.use_kps,
            self.embedding_dim,
        )

    # ----------------------------------------------------------------- #
    # Detection
    # ----------------------------------------------------------------- #
    def detect(self, img_bgr: np.ndarray) -> list[Face]:
        """Detect faces. Letterboxes into DET_SIZE and maps results back."""
        h, w = img_bgr.shape[:2]
        scale = min(DET_SIZE / h, DET_SIZE / w)
        resized = cv2.resize(img_bgr, (int(w * scale), int(h * scale)))

        canvas = np.zeros((DET_SIZE, DET_SIZE, 3), dtype=np.uint8)
        canvas[: resized.shape[0], : resized.shape[1]] = resized

        blob = cv2.dnn.blobFromImage(
            canvas, 1.0 / 128.0, (DET_SIZE, DET_SIZE), (127.5, 127.5, 127.5), swapRB=True
        )
        outputs = self.det.run(self.det_outputs, {self.det_input: blob})

        scores_all, bboxes_all, kpss_all = [], [], []
        for idx, stride in enumerate(self.feat_strides):
            scores = outputs[idx].reshape(-1)
            bbox_preds = outputs[idx + self.fmc].reshape(-1, 4) * stride
            kps_preds = outputs[idx + self.fmc * 2].reshape(-1, 10) * stride

            side = DET_SIZE // stride
            centers = np.stack(np.mgrid[:side, :side][::-1], axis=-1).astype(np.float32)
            centers = (centers * stride).reshape(-1, 2)
            if self.num_anchors > 1:
                centers = np.stack([centers] * self.num_anchors, axis=1).reshape(-1, 2)

            keep = np.where(scores >= self.det_thresh)[0]
            if keep.size == 0:
                continue
            scores_all.append(scores[keep])
            bboxes_all.append(_distance2bbox(centers, bbox_preds)[keep])
            kpss_all.append(_distance2kps(centers, kps_preds)[keep].reshape(-1, 5, 2))

        if not scores_all:
            return []

        scores = np.concatenate(scores_all)
        bboxes = np.concatenate(bboxes_all) / scale
        kpss = np.concatenate(kpss_all) / scale

        pre = np.hstack([bboxes, scores[:, None]]).astype(np.float32)
        keep = _nms(pre, self.nms_thresh)

        faces = [
            Face(bbox=bboxes[i], kps=kpss[i], det_score=float(scores[i])) for i in keep
        ]
        faces.sort(key=lambda f: f.area, reverse=True)
        return faces

    # ----------------------------------------------------------------- #
    # Recognition
    # ----------------------------------------------------------------- #
    def align(self, img_bgr: np.ndarray, kps: np.ndarray) -> np.ndarray:
        matrix, _ = cv2.estimateAffinePartial2D(
            kps.astype(np.float32), ARCFACE_REF, method=cv2.LMEDS
        )
        if matrix is None:
            raise ValueError("could not estimate alignment transform")
        return cv2.warpAffine(img_bgr, matrix, (REC_SIZE, REC_SIZE), borderValue=0)

    def embed(self, img_bgr: np.ndarray, kps: np.ndarray) -> np.ndarray:
        """Aligned crop -> 512-d L2-normalised embedding."""
        aligned = self.align(img_bgr, kps)
        blob = cv2.dnn.blobFromImage(
            aligned, 1.0 / 127.5, (REC_SIZE, REC_SIZE), (127.5, 127.5, 127.5), swapRB=True
        )
        vec = self.rec.run([self.rec_output], {self.rec_input: blob})[0].reshape(-1)
        norm = float(np.linalg.norm(vec))
        return (vec / norm).astype(np.float32) if norm else vec.astype(np.float32)


# --------------------------------------------------------------------------- #
# Process-wide singleton
# --------------------------------------------------------------------------- #
_engine: FaceEngine | None = None
_load_error: str | None = None


def load_engine(det_model: Path, rec_model: Path, intra_op_threads: int = 4) -> FaceEngine | None:
    """Load once. Returns None (and records why) if the models are absent, so the
    rest of the API still boots - only the face endpoints degrade."""
    global _engine, _load_error
    if _engine is not None:
        return _engine

    missing = [p for p in (det_model, rec_model) if not Path(p).exists()]
    if missing:
        _load_error = "Model files missing: " + ", ".join(str(p) for p in missing)
        log.warning("%s - face endpoints will return MODEL_UNAVAILABLE", _load_error)
        return None

    try:
        _engine = FaceEngine(Path(det_model), Path(rec_model), intra_op_threads=intra_op_threads)
        _load_error = None
    except Exception as exc:  # noqa: BLE001 - surfaced through /health
        _load_error = f"{type(exc).__name__}: {exc}"
        log.exception("Failed to load face models")
        return None
    return _engine


def get_engine() -> FaceEngine | None:
    return _engine


def load_error() -> str | None:
    return _load_error


def reset_engine() -> None:
    """Test hook."""
    global _engine, _load_error
    _engine, _load_error = None, None
