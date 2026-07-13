"""Modal ``Dict`` adapter for IntelliqX state store.

Uses ``modal.Dict`` — an in-memory, per-app key/value store that
Modal persists across invocations. Important caveats:

* **No native TTL support.** :meth:`expire` is a no-op. Use a
  separate cleanup job if you need eviction.
* **Ephemeral by design.** When the Modal app is stopped, the dict
  contents are discarded.
* **Cross-function visibility.** All Modal functions in the same app
  can read and write the same dict.

Error handling pattern (``_try_init`` / ``_available``):

* ``_try_init`` catches ``Exception`` broadly (rather than just
  ``(ImportError, OSError)``) because ``modal.Dict.from_name`` can
  raise modal-specific exceptions beyond standard import/os errors,
  such as authentication failures or API rate limits.
* When ``_try_init`` returns ``False``, the ``_require`` guard
  raises ``RuntimeError`` on every data-access method. There is no
  silent fallback because Modal Dict is ephemeral and an in-memory
  substitute would not replicate across Modal functions.
* When ``_try_init`` returns ``True`` but the Modal API is
  unreachable at call time, errors propagate loudly so the caller
  can fail fast rather than silently dropping state.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from intelliqx_state.store import StateStore


class ModalDictStateStore(StateStore):
    """modal.Dict-backed ephemeral state store.

    Args:
        name: The Modal ``Dict`` name. Defaults to ``"intelliqx-state"``.
    """

    def __init__(self, name: str = "intelliqx-state") -> None:
        self.name = name
        self.__dict: Any = None
        self.__available = self._try_init()

    def _try_init(self) -> bool:
        """Try to look up (or implicitly create) the Modal Dict."""
        try:
            import modal  # type: ignore[import-not-found]

            # ``from_name`` returns a handle; the dict is provisioned
            # on first read/write.
            self.__dict = modal.Dict.from_name(self.name, create_if_missing=True)
            return True
        except Exception:
            return False

    def _require(self) -> None:
        """Raise a clear error when the adapter cannot reach Modal."""
        if not self.__available:
            raise RuntimeError("ModalDict requires modal SDK + token")

    async def get(self, key: str):
        """Fetch the value for ``key`` from the Modal Dict.

        Args:
            key: Storage key.

        Returns:
            The stored value, or ``None`` if the key does not exist.

        Raises:
            RuntimeError: If the Modal SDK is not installed or the
                token is missing.
        """
        self._require()
        return self.__dict.get(key)

    async def set(self, key: str, value, *, ttl_seconds: int | None = None) -> None:
        """Store ``value`` at ``key`` in the Modal Dict.

        ``ttl_seconds`` is accepted for interface compatibility but
        **ignored** — ``modal.Dict`` has no native TTL support. Use a
        separate cleanup job if eviction is needed.

        Args:
            key: Storage key.
            value: The value to store (must be serialisable by Modal).
            ttl_seconds: Ignored. Present for interface compatibility.

        Raises:
            RuntimeError: If the Modal SDK is not installed or the
                token is missing.
        """
        self._require()
        self.__dict[key] = value

    async def delete(self, key: str) -> None:
        """Remove ``key`` from the Modal Dict.

        This is idempotent: deleting a missing key is a no-op.

        Args:
            key: Storage key to remove.

        Raises:
            RuntimeError: If the Modal SDK is not installed or the
                token is missing.
        """
        self._require()
        with suppress(KeyError):
            del self.__dict[key]

    async def incr(self, key: str, amount: int = 1) -> int:
        """Atomically increment an integer counter at ``key``.

        Reads the current value (defaulting to 0), adds ``amount``,
        and writes it back. The read-modify-write is not atomic at
        the Redis level but is safe within a single Modal function.

        Args:
            key: Counter key.
            amount: Increment size (default 1). May be negative.

        Returns:
            The new value after the increment.

        Raises:
            RuntimeError: If the Modal SDK is not installed or the
                token is missing.
        """
        self._require()
        cur = int(self.__dict.get(key, 0))
        cur += amount
        self.__dict[key] = cur
        return cur

    async def expire(self, key: str, ttl_seconds: int) -> None:
        """No-op: ``modal.Dict`` has no native TTL support.

        This is documented in the module docstring. Use a separate
        cleanup job if eviction is needed.
        """
        pass

    async def keys(self, prefix: str):
        """Yield every key that starts with ``prefix``.

        Note: snapshots ``dict.keys()`` before iterating to avoid
        concurrent-modification issues.

        Args:
            prefix: Key prefix to match.

        Yields:
            Matching key strings.
        """
        self._require()
        for k in list(self.__dict.keys()):
            if k.startswith(prefix):
                yield k

    async def hset(self, key: str, field: str, value: str) -> None:
        """Set a single hash field under ``key``.

        The hash is stored as a regular ``dict`` under ``key`` in
        the Modal Dict because ``modal.Dict`` does not natively
        support Redis-style hash fields.

        Args:
            key: The hash key.
            field: The field name within the hash.
            value: The string value to store.
        """
        self._require()
        h = self.__dict.get(key, {})
        h[field] = value
        self.__dict[key] = h

    async def hgetall(self, key: str) -> dict:
        """Return all hash fields and values under ``key``.

        Returns:
            A ``dict[str, str]``; empty if the key has no hash fields.
        """
        self._require()
        return dict(self.__dict.get(key, {}))

    async def lpush(self, key: str, value: str) -> int:
        """Push ``value`` to the head of the list at ``key``.

        Returns:
            The new list length.
        """
        self._require()
        lst = list(self.__dict.get(key, []))
        lst.insert(0, value)
        self.__dict[key] = lst
        return len(lst)

    async def rpop(self, key: str):
        """Pop and return the tail element of the list at ``key``.

        Returns:
            The popped value, or ``None`` if the list is empty.
        """
        self._require()
        lst = list(self.__dict.get(key, []))
        if not lst:
            return None
        v = lst.pop()
        self.__dict[key] = lst
        return v
