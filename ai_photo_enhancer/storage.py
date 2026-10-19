"""Static files storage that never breaks the build on a missing manifest entry.

``CompressedManifestStaticFilesStorage`` is strict by default and raises
``ValueError: Missing staticfiles manifest entry`` when a file was not collected.
Because Vercel runs no ``collectstatic`` at build time (``staticfiles/`` is
committed), we resolve that class of failure silently instead of 500ing.

``stored_name`` is overridden with a catch-all ``*args, **kwargs`` signature on
purpose: its exact signature differs across Django releases and WhiteNoise calls
it during startup. A hardcoded signature raised
``TypeError: unexpected keyword argument 'hashed_name'`` and killed the worker.
"""
from whitenoise.storage import CompressedManifestStaticFilesStorage


class ForgivingCompressedManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    manifest_strict = False

    def stored_name(self, *args, **kwargs):
        try:
            return super().stored_name(*args, **kwargs)
        except ValueError:
            return args[0] if args else kwargs.get("name", "")
