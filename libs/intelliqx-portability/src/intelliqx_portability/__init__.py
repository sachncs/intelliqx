"""Cloud portability for IntelliqX.

This package is the bridge between cloud-agnostic agent code and the
three supported deployment targets: AWS, GCP, and Modal. It exposes a
single :func:`get_adapter` factory that returns a :class:`CloudAdapter`
for the provider selected via the ``INTELLIQX_CLOUD`` env var.

Why the indirection:

* Agent code never imports ``boto3``, ``google-cloud-*``, or ``modal``.
  That keeps the same code base deployable on any cloud.
* The adapter itself is a tiny, well-typed handle to the resolved
  configuration. Cloud SDK access lives in feature-specific libs
  (``intelliqx-storage.aws``, ``intelliqx-events.gcp`` …) so each layer can be
  swapped independently.
* The factory is ``lru_cache``d to keep cold-start latency low; tests
  call :func:`reset_adapter_cache` between cases.
"""

from intelliqx_portability.adapter import CloudAdapter, get_adapter
from intelliqx_portability.config import CloudConfig

__all__ = ["CloudAdapter", "CloudConfig", "get_adapter"]
