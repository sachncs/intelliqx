"""Modal ``Dict`` adapter for AQIP state store.

Uses ``modal.Dict`` — an in-memory, per-app key/value store that
Modal persists across invocations. Important caveats:

* **No native TTL support.** :meth:`expire` is a no-op. Use a
  separate cleanup job if you need eviction.
* **Ephemeral by design.** When the Modal app is stopped, the dict
  contents are discarded.
* **Cross-function visibility.** All Modal functions in the same app
  can read and write the same dict.
"""

from __future__ import annotations

from contextlib import suppress

from aqip_state.store import StateStore


class ModalDictStateStore(StateStore):
    """modal.Dict-backed ephemeral state store.

    Args:
        name: The Modal ``Dict`` name. Defaults to ``"aqip-state"``.
    """

    def __init__(self, name: str = "aqip-state") -> None:
        self.name = name
        self._dict = None
        self._available = self._try_init()

    def _try_init(self) -> bool:
        """Try to look up (or implicitly create) the Modal Dict."""
        try:
            import modal  # type: ignore

            # ``from_name`` returns a handle; the dict is provisioned
            # on first read/write.
            self._dict = modal.Dict.from_name(self.name, create_if_missing=True)
            return True
        except Exception:
            return False

    def _require(self) -> None:
        """Raise a clear error when the adapter cannot reach Modal."""
        if not self._available:
            raise RuntimeError("ModalDict requires modal SDK + token")

    async def get(self, key: str):
        self._require()
        return self._dict.get(key)

    async def set(self, key: str, value, *, ttl_seconds: int | None = None) -> None:
        self._require()
        # modal.Dict doesn't natively support TTL; ttl_seconds is
        # accepted for interface compatibility but ignored.
        self._dict[key] = value

    async def delete(self, key: str) -> None:
        self._require()
        with suppress(KeyError):
            del self._dict[key]

    async def incr(self, key: str, amount: int = 1) -> int:
        self._require()
        cur = int(self._dict.get(key, 0))
        cur += amount
        self._dict[key] = cur
        return cur

    async def expire(self, key: str, ttl_seconds: int) -> None:
        # No native support; intentionally a no-op.
        pass

    async def keys(self, prefix: str):
        self._require()
        for k in list(self._dict.keys()):
            if k.startswith(prefix):
                yield k

    async def hset(self, key: str, field: str, value: str) -> None:
        self._require()
        # modal.Dict values must be serialisable; we store the hash
        # as a regular Python dict under the same key.
        h = self._dict.get(key, {})
        h[field] = value
        self._dict[key] = h

    async def hgetall(self, key: str) -> dict:
        self._require()
        return dict(self._dict.get(key, {}))

    async def lpush(self, key: str, value: str) -> int:
        self._require()
        lst = list(self._dict.get(key, []))
        lst.insert(0, value)
        self._dict[key] = lst
        return len(lst)

    async def rpop(self, key: str):
        self._require()
        lst = list(self._dict.get(key, []))
        if not lst:
            return None
        v = lst.pop()
        self._dict[key] = lst
        return v
