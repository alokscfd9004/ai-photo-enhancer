"""Static files storage that never breaks the build on a missing manifest entry.

``CompressedManifestStaticFilesStorage`` is strict by default and raises
``ValueError: Missing staticfiles manifest entry`` when a file was not collected.
Because Vercel runs no ``collectstatic`` at build time (``staticfiles/`` is
committed), we resolve that class of failure silently instead of 500ing.
"""
from whitenoise.storage import CompressedManifestStaticFilesStorage


class ForgivingCompressedManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content=content, filename=filename)
        except ValueError:
            return name

    def stored_name(self, name, hashed_name=None, content=None):
        try:
            return super().stored_name(name, hashed_name=hashed_name, content=content)
        except ValueError:
            return name
