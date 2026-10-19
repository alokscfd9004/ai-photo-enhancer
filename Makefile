.PHONY: venv install engine migrate run test lint prod

PY := .venv/bin/python
PIP := .venv/bin/pip

venv:
	python3.12 -m venv .venv

install:
	$(PIP) install -r requirements.txt

engine:
	$(PY) scripts/setup_realesrgan.py

migrate:
	$(PY) manage.py migrate

run:
	$(PY) manage.py runserver

test:
	$(PY) manage.py test

collectstatic:
	$(PY) manage.py collectstatic --noinput

prod:
	gunicorn ai_photo_enhancer.wsgi:application --config gunicorn.conf.py

setup: install engine migrate
	@echo "Ready. Run: make run"
