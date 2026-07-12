"""AQIP agent SDK for third-party developers.

The SDK has two parts:

* :class:`AgentManifest` — a JSON-Schema-friendly description of a
  marketplace agent. Loaded from / written to disk by the loaders
  in :mod:`aqip_sdk.manifest`.
* :class:`Sandbox` — a small ``rlimit``-based sandbox for safely
  running third-party code. Production deployments should add a
  heavier sandbox (nsjail, firecracker, gVisor) on top of this.

Marketplace agents are loaded with :func:`aqip_sdk.manifest.load_manifest`
and executed in a :class:`Sandbox` enforced by the compute runtime.
"""

from aqip_sdk.manifest import AgentManifest, dump_manifest, load_manifest
from aqip_sdk.sandbox import Sandbox, SandboxViolation

__all__ = [
    "AgentManifest",
    "Sandbox",
    "SandboxViolation",
    "dump_manifest",
    "load_manifest",
]
