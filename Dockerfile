# ---- build stage ----------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Real-ESRGAN NCNN Vulkan needs Vulkan ICD + libgomp at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        libvulkan1 \
        mesa-vulkan-drivers \
        curl \
        ca-certificates \
        unzip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Download the Linux engine + models at build time
RUN python scripts/setup_realesrgan.py

RUN python manage.py collectstatic --noinput \
    && python manage.py migrate --noinput

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health/ || exit 1

CMD ["gunicorn", "ai_photo_enhancer.wsgi:application", "--config", "gunicorn.conf.py"]
