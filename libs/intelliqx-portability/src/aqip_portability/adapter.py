"""Cloud adapter abstraction and factory.

The :class:`CloudAdapter` is intentionally tiny: it carries the resolved
:class:`CloudConfig` and exposes a short name for log lines. All
cloud-SDK access lives in the per-feature adapter libs (``aqip-storage``,
``aqip-events``, …) so the platform can mix and match (e.g. run on AWS
Lambda with GCS for object storage).
"""

from __future__ import annotations

import os
from functools import lru_cache

from aqip_core.errors import CloudConfigError
from aqip_core.models import CloudProvider

from aqip_portability.config import CloudConfig


class CloudAdapter:
    """Base cloud adapter.

    Subclasses may attach cloud-specific helpers but are not required to
    do so. The adapter is *not* a service locator; it is a typed handle
    to the resolved configuration.

    Args:
        config: The frozen cloud configuration.
    """

    def __init__(self, config: CloudConfig) -> None:
        self.config = config

    @property
    def provider(self) -> CloudProvider:
        """Return the cloud provider enum value."""
        return self.config.provider

    def short_name(self) -> str:
        """Return the short provider name (``"aws"``, ``"gcp"``, …).

        Used in log lines and metric labels to keep tags compact.
        """
        return self.config.provider.value


@lru_cache(maxsize=1)
def get_adapter() -> CloudAdapter:
    """Return the process-wide :class:`CloudAdapter`.

    Resolution order:

    1. Read the ``AQIP_CLOUD`` env var (defaults to ``"local"``).
    2. Construct a :class:`CloudConfig` from ``AQIP_REGION``,
       ``AQIP_PROJECT_ID``, and ``AQIP_ENV``.
    3. Instantiate the matching adapter.

    The result is cached with ``lru_cache``; tests must call
    :func:`reset_adapter_cache` to force re-resolution.

    Raises:
        CloudConfigError: If ``AQIP_CLOUD`` is not one of the supported
            providers.
    """
    from aqip_portability.adapters.aws import AWSAdapter
    from aqip_portability.adapters.gcp import GCPAdapter
    from aqip_portability.adapters.local import LocalAdapter
    from aqip_portability.adapters.modal import ModalAdapter

    provider_str = os.environ.get("AQIP_CLOUD", "local").lower()
    try:
        provider = CloudProvider(provider_str)
    except ValueError as e:
        raise CloudConfigError(f"Unknown AQIP_CLOUD: {provider_str!r}") from e

    config = CloudConfig(
        provider=provider,
        region=os.environ.get("AQIP_REGION", "us-east-1"),
        project_id=os.environ.get("AQIP_PROJECT_ID"),
        environment=os.environ.get("AQIP_ENV", "dev"),
    )

    if provider == CloudProvider.AWS:
        return AWSAdapter(config)
    if provider == CloudProvider.GCP:
        return GCPAdapter(config)
    if provider == CloudProvider.MODAL:
        return ModalAdapter(config)
    return LocalAdapter(config)


def reset_adapter_cache() -> None:
    """Clear the ``lru_cache`` on :func:`get_adapter`.

    Tests call this to force a fresh adapter on the next call. Production
    code should not need to call this — the cache lives for the
    process lifetime and is cheap to populate once.
    """
    get_adapter.cache_clear()
