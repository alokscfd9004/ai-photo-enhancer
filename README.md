# AI Photo Enhancer

Production-ready Django web application that upscales low-resolution photos to
**HD / 4K** using the open-source **Real-ESRGAN (NCNN Vulkan)** engine.

Everything runs locally on your machine — images are never sent to third-party
APIs.

---

## Features

- Drag & drop upload (JPG / PNG / WebP) with live preview
- Three Real-ESRGAN models: general photo, anime, and fast anime-video
- **2× HD** and **3× / 4× 4K-ready** upscaling
- **Sharpness / clarity boost** and chroma-only JPEG cleanup
- Per-upload output format: JPEG / PNG / WebP
- Interactive **before / after comparison slider** + **100% pixel loupe**
- Asynchronous processing with live status + progress UI
- Job history with search / status filters, downloads and deletion
- JSON API + `/health/` endpoint
- Hardened production settings (WhiteNoise, HSTS, SSL redirect, gunicorn)
- Dockerfile + docker-compose
- Automated test suite

---

## Quick start (macOS / Linux)

> **Requires Python 3.10+ (3.12 recommended).** Django 5 will not install on
> Python 3.9 — check with `python3 --version` first.

### One command

```bash
cd "/Users/alok.kumar/Proj-PT/My Projects/AI-Photo-Enhancer"
./start.sh
```

`start.sh` creates `.venv` (Python 3.12), installs requirements, downloads the
Real-ESRGAN engine, migrates the DB and starts the server. Open
<http://127.0.0.1:8000/>.

### Manual (step by step)

```bash
cd "AI-Photo-Enhancer"

# 1. Virtual environment + dependencies  (MUST be Python 3.10+)
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
python --version        # confirm 3.10+ BEFORE installing
pip install -r requirements.txt

# 2. Install the Real-ESRGAN NCNN Vulkan engine + models (~30 MB)
python scripts/setup_realesrgan.py

# 3. Configure environment
cp .env.example .env
#   → set SECRET_KEY to a long random string

# 4. Database
python manage.py migrate
python manage.py createsuperuser   # optional, for /django-admin/

# 5. Run
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and drop in a photo.

> **Windows:** use `py -3.12 -m venv .venv` and `.venv\Scripts\activate`.
> The setup script installs `realesrgan-ncnn-vulkan.exe` automatically.

---

## Project layout

```
AI-Photo-Enhancer/
├── manage.py
├── requirements.txt
├── .env.example              # copy to .env
├── gunicorn.conf.py
├── Dockerfile / docker-compose.yml
├── Makefile
├── ai_photo_enhancer/        # Django project (settings, urls, wsgi/asgi)
├── enhancer/                 # main application
│   ├── models.py             # EnhancementJob
│   ├── services.py           # Real-ESRGAN NCNN Vulkan wrapper
│   ├── tasks.py              # background thread-pool worker
│   ├── views.py              # pages + JSON API
│   ├── forms.py / utils.py   # upload + image validation
│   ├── templates/            # UI templates
│   └── static/               # CSS / JS (comparison slider, polling)
├── scripts/
│   └── setup_realesrgan.py   # downloads engine + models from GitHub releases
├── bin/                      # engine binary + models (created by setup)
└── media/                    # originals/ + enhanced/ images
```

---

## API

| Method | Path                       | Description                          |
|--------|----------------------------|--------------------------------------|
| POST   | `/api/upload/`             | multipart upload → `202` + job JSON  |
| GET    | `/api/jobs/`               | list recent jobs                     |
| GET    | `/api/jobs/<uuid>/`        | poll a job (status, sizes, URLs)     |
| GET    | `/health/`                 | engine + service health (`200/503`)  |
| GET    | `/job/<uuid>/download/`    | download the enhanced image          |
| GET    | `/job/<uuid>/download/original/` | download the source image      |

Extra form fields for `/api/upload/`: `output_format` (`jpg|png|webp`),
`sharpness` (0–1), `denoise_strength` (0–1).

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/upload/ \
  -H "X-Requested-With: fetch" \
  -H "X-CSRFToken: <token from cookie>" \
  -F "original_image=@photo.jpg" \
  -F "model_name=realesrgan-x4plus" \
  -F "scale=4"
```

---

## Models

| Key                        | Best for                    | Scales  |
|----------------------------|-----------------------------|---------|
| `realesrgan-x4plus`        | real photos (default)       | 4×      |
| `realesrgan-x4plus-anime`  | illustrations / line art    | 4×      |
| `realesr-animevideov3`     | quick drafts, video frames  | 2/3/4×  |

**Sharpness pipeline (v2):** EXIF orientation → JPEG deblock (when block
artefacts are detected) → chroma-only noise cleanup (luminance detail is kept)
→ Real-ESRGAN → **source-texture restoration** (adds micro-detail back that
ESRGAN smooths away) → Lanczos resample for 2×/3× → multi-scale unsharp
(fine detail + clarity) → encode.

- **Sharpness** slider (0–1, default 0.45) controls the post-detail boost.
- **Texture** slider (0–1, default 0.35) transfers fine grain/detail from the
  source back into the result — keeps skin & fabric from looking plastic.
- **Color cleanup** slider (0–1, default 0) blurs only the chroma channels —
  removes JPEG colour noise without the waxy look of full-image smoothing.
- **Output format** is chosen per upload: JPEG (q92 progressive, recommended),
  PNG (lossless, optimised) or WebP (q92).

**The comparison slider is fair by default:** the “before” side shows a naive
4× upscale of your photo (not the small original), so both sides share the same
pixel dimensions and are downscaled equally. Viewing a 600 px original at 1:1
next to a 2400 px AI image squeezed into the same box is misleading — the
browser’s heavy downscale of the big image makes it *look* softer. Use the
**Original** toggle if you want the raw file, and **Inspect at 100%** /
**Open full size** to judge real pixel detail.

> Note: the 4× models produce native 4× output. When you request 2× or 3× the
> result is produced at 4× and downsampled with Lanczos (then sharpened).

### Importing files already in `media/originals`

```bash
python manage.py import_originals            # queue jobs for orphan images
python manage.py import_originals --dry-run  # preview only
python manage.py import_originals --scale 2 --format png --sharpness 0.6

### Why can the original look “sharper” in the slider?

A small original (e.g. 600 px) is shown at almost 1:1, while the 4× AI result
(e.g. 2400 px) is squashed into the same box — the browser’s heavy downscale
softens it. That’s why the slider defaults to a **naive 4× upscale** of your
photo as “before”: both sides then have the same pixel grid and are filtered
identically. Judge real detail with **Inspect at 100%** or **Open full size**.
```

---

## Production

```bash
cp .env.example .env
# DEBUG=False
# SECRET_KEY=<random 50+ chars>
# ALLOWED_HOSTS=photos.example.com
# CSRF_TRUSTED_ORIGINS=https://photos.example.com

python manage.py migrate
python manage.py collectstatic --noinput
gunicorn ai_photo_enhancer.wsgi:application --config gunicorn.conf.py
```

Static files are served by **WhiteNoise**. Media files are served by Django in
development; in production put nginx (or any static server) in front of
`media/`, or mount it on a CDN.

### Docker

```bash
docker compose up --build
# → http://127.0.0.1:8000
```

---

## Tests

```bash
python manage.py test
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "Engine offline" in the header | `python scripts/setup_realesrgan.py` |
| `Enhancement failed … exit -6` on macOS | The 2022 macOS binary may need Rosetta on Apple Silicon: `softwareupdate --install-rosetta` |
| Out of memory on huge photos | Lower `MAX_IMAGE_PIXELS` in `.env`, or pre-downscale |
| Slow on CPU | The NCNN build uses Vulkan; install a Vulkan-capable GPU driver for big speedups (set `REALESRGAN_GPU_ID`) |
| `Permission denied` launching the engine | `chmod +x bin/realesrgan-ncnn-vulkan` |

---

## License notes

This project is MIT-licensed. **Real-ESRGAN** is licensed under BSD-3-Clause —
see [xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN).
