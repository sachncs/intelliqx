"""Cloud adapter package — lazy imports of the four profile adapters.

The actual adapter classes live in ``aws.py``, ``gcp.py``, ``modal.py``,
and ``local.py``. They are imported lazily by
:func:`aqip_portability.adapter.get_adapter` to keep import latency low
when the platform is running on a single cloud.
"""

from aqip_portability.adapters.aws import AWSAdapter
from aqip_portability.adapters.gcp import GCPAdapter
from aqip_portability.adapters.local import LocalAdapter
from aqip_portability.adapters.modal import ModalAdapter

__all__ = ["AWSAdapter", "GCPAdapter", "LocalAdapter", "ModalAdapter"]
