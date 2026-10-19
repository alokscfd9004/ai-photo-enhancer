#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ai_photo_enhancer.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Did you install the requirements and "
            "activate the virtual environment (.venv)?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
