"""Local (in-process) cloud adapter for development and tests.

This adapter does not touch any cloud SDK. It exists so the rest of the
platform has a uniform ``CloudAdapter`` instance even when running
fully offline, and so unit tests can construct an adapter without
needing AWS/GCP/Modal credentials.
"""

from aqip_portability.adapter import CloudAdapter


class LocalAdapter(CloudAdapter):
    """No-op adapter for local dev / tests.

    The adapter itself exposes no additional behaviour; the in-process
    implementations used under this profile live in the corresponding
    ``*InMemory*`` / ``LocalFileSystem*`` classes throughout the
    platform (e.g. ``aqip_storage.store.InMemoryObjectStore``).
    """
