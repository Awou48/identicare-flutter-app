FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/user \
    IDENTICARE_ENV=prod \
    FACE_DET_MODEL=/app/models/det_500m.onnx \
    FACE_REC_MODEL=/app/models/w600k_r50.onnx \
    KEK_PATH=/app/keys/kek.bin \
    ROTATION_PATH=/app/keys/rotation_v1.npy

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl unzip libgomp1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 user

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

RUN mkdir -p /app/models /tmp/insightface \
 && curl -fsSL --retry 8 --retry-all-errors --retry-delay 5 -C - -o /tmp/insightface/buffalo_s.zip https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip \
 && curl -fsSL --retry 8 --retry-all-errors --retry-delay 5 -C - -o /tmp/insightface/buffalo_l.zip https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip \
 && unzip -j -o /tmp/insightface/buffalo_s.zip det_500m.onnx -d /app/models \
 && unzip -j -o /tmp/insightface/buffalo_l.zip w600k_r50.onnx -d /app/models \
 && rm -rf /tmp/insightface

COPY backend/app /app/app
COPY backend/scripts /app/scripts
COPY backend/ruff.toml /app/ruff.toml

RUN mkdir -p /app/keys && chown -R user:user /app
USER user

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD curl -fsS http://127.0.0.1:7860/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
