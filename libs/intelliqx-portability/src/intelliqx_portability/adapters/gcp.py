"""GCP cloud adapter.

The adapter itself does not import any ``google-cloud-*`` SDK; cloud
access lives in feature-specific libs (``intelliqx-storage.gcp``,
``intelliqx-events.gcp`` …). The adapter exposes the resolved config and
exposes ``config.project_id`` for code that needs it.
"""

from intelliqx_portability.adapter import CloudAdapter


class GCPAdapter(CloudAdapter):
    """GCP adapter.

    GCP requires a project id for almost every API call; it is captured
    in :class:`~intelliqx_portability.config.CloudConfig` and accessible
    via ``self.config.project_id``. The adapter itself does not validate
    the value — feature libs raise :class:`CloudConfigError` lazily when
    the project id is required and missing.
    """
