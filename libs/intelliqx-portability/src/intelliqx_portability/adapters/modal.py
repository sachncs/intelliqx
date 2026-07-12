"""Modal cloud adapter.

The adapter itself does not import the ``modal`` SDK; cloud access
lives in feature-specific libs (``intelliqx-events.modal``,
``intelliqx-storage.modal``, …). The adapter exposes the resolved config
and a typed handle for Modal-specific helpers.
"""

from intelliqx_portability.adapter import CloudAdapter


class ModalAdapter(CloudAdapter):
    """Modal adapter.

    Modal's "regions" are managed by Modal itself (it picks the closest
    one to the caller), so :class:`~intelliqx_portability.config.CloudConfig`'s
    ``region`` field is informational only. The Modal SDK uses an auth
    token read from the environment (``MODAL_TOKEN_ID``/``MODAL_TOKEN_SECRET``)
    at first use.
    """
