"""Lightweight sandbox for third-party agent code.

The :class:`Sandbox` uses POSIX ``setrlimit`` to bound CPU time,
address space, and open file descriptors around a block of code.
It is **not** a full sandbox — there is no syscall filter, no
filesystem namespace, no network policy. It is a safety net that
catches runaway loops and accidental memory bombs.

Production deployments should layer a heavier sandbox (nsjail,
firecracker, gVisor) on top of this. The :class:`SandboxViolation`
exception is the single error type the sandbox emits; higher layers
can map it to their own policy violations.

Security / trust boundary:

* The sandbox enforces **resource limits only** — it is not a
  security boundary. A malicious agent can still open files, make
  network requests, and execute arbitrary system calls. Do **not**
  use :class:`Sandbox` as the sole defence against untrusted code.
* ``setrlimit`` applies to the **entire process**, not just the
  code block. Nested sandboxes share the same process, so the
  innermost limit wins. On macOS, ``RLIMIT_AS`` is advisory and
  may not be enforced by the kernel.
* The ``enforce()`` context manager **restores** the original
  limits on exit, even on exception. If the restore itself fails
  (e.g. the process is already inside a tighter sandbox), the
  failure is silently ignored — the block is exiting anyway and
  crashing on cleanup is worse than leaving stale limits.
* ``SandboxViolation`` is raised when ``setrlimit`` fails (e.g.
  on macOS where raising the FD limit past the system ceiling is
  rejected). Higher layers should catch it and return a policy
  error (HTTP 403 or equivalent).
"""

from __future__ import annotations

import resource
from contextlib import contextmanager


class SandboxViolation(Exception):
    """Raised when the sandbox cannot enforce a limit.

    Raised either by :meth:`Sandbox.enforce` if ``setrlimit`` fails
    (typically because the platform doesn't allow raising limits,
    e.g. macOS sandboxing) or by ``OSError`` / ``ValueError``
    bubbling up from inside the protected block.
    """


class Sandbox:
    """Set CPU, memory, and FD limits around a code block.

    Args:
        cpu_time_seconds: Maximum CPU time (seconds) before SIGXCPU.
            Linux signals the process; the runtime is expected to
            translate that into a clean :class:`SandboxViolation`.
        memory_mb: Maximum address space in megabytes. Applies to
            the whole process (text + data + stack).
        max_file_descriptors: Cap on simultaneously open files.

    Example:
        >>> with Sandbox(cpu_time_seconds=5, memory_mb=256).enforce():
        ...     do_untrusted_work()
    """

    def __init__(
        self, *, cpu_time_seconds: int = 60, memory_mb: int = 512, max_file_descriptors: int = 64
    ) -> None:
        self.cpu_time_seconds = cpu_time_seconds
        self.memory_mb = memory_mb
        self.max_file_descriptors = max_file_descriptors

    @contextmanager
    def enforce(self):
        """Apply the sandbox limits for the duration of the block.

        The limits are restored to their previous values on exit,
        even when the wrapped code raises.

        Raises:
            SandboxViolation: If ``setrlimit`` itself fails (e.g.
                when the process isn't allowed to lower its own
                limits). On macOS in particular, raising the FD
                limit past the system ceiling fails.
        """
        old_limits = (
            resource.getrlimit(resource.RLIMIT_CPU),
            resource.getrlimit(resource.RLIMIT_AS),
            resource.getrlimit(resource.RLIMIT_NOFILE),
        )
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (self.cpu_time_seconds, self.cpu_time_seconds))
            resource.setrlimit(
                resource.RLIMIT_AS, (self.memory_mb * 1024 * 1024, self.memory_mb * 1024 * 1024)
            )
            resource.setrlimit(
                resource.RLIMIT_NOFILE, (self.max_file_descriptors, self.max_file_descriptors)
            )
            yield self
        except (OSError, ValueError) as e:
            raise SandboxViolation(str(e)) from e
        finally:
            try:
                resource.setrlimit(resource.RLIMIT_CPU, old_limits[0])
                resource.setrlimit(resource.RLIMIT_AS, old_limits[1])
                resource.setrlimit(resource.RLIMIT_NOFILE, old_limits[2])
            except (OSError, ValueError):
                # Restoring limits may fail in tightly sandboxed
                # processes; the block is exiting anyway.
                pass
