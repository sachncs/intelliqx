"""Cloud configuration value object.

A frozen Pydantic model that captures everything the platform needs to
know about the current cloud profile. The provider checks
(``is_aws``/``is_gcp``/``is_modal``/``is_local``) are exposed as
properties so call sites can branch on the active profile without
parsing strings.
"""

from __future__ import annotations

from aqip_core.models import CloudProvider
from pydantic import BaseModel, ConfigDict, Field


class CloudConfig(BaseModel):
    """Resolved cloud configuration.

    The object is frozen; mutating an active config is not supported.
    If you need different config, build a new ``CloudAdapter`` instance.

    Attributes:
        provider: One of :class:`aqip_core.models.CloudProvider`.
        region: Default region for all cloud operations. AWS and GCP
            honour it; Modal ignores it (Modal picks the closest region).
        project_id: GCP project id. ``None`` for non-GCP profiles.
        environment: Free-form environment name (``"dev"``,
            ``"staging"``, ``"prod"`` …) used for tagging and log
            routing. Never used for control-flow decisions.
        extra: Open-ended bag for adapter-specific overrides
            (e.g. AWS endpoint URL for LocalStack).
    """

    model_config = ConfigDict(frozen=True)

    provider: CloudProvider
    region: str = "us-east-1"
    project_id: str | None = None  # GCP
    environment: str = "dev"
    extra: dict[str, str] = Field(default_factory=dict)

    @property
    def is_local(self) -> bool:
        """Return ``True`` if the profile is the in-process local one."""
        return self.provider == CloudProvider.LOCAL

    @property
    def is_aws(self) -> bool:
        """Return ``True`` if the profile is AWS."""
        return self.provider == CloudProvider.AWS

    @property
    def is_gcp(self) -> bool:
        """Return ``True`` if the profile is GCP."""
        return self.provider == CloudProvider.GCP

    @property
    def is_modal(self) -> bool:
        """Return ``True`` if the profile is Modal."""
        return self.provider == CloudProvider.MODAL
