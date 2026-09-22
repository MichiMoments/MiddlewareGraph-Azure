import os
import time
from pathlib import Path
from typing import Any, Protocol


class TokenLock(Protocol):
    def __enter__(self) -> "TokenLock": ...
    def __exit__(self, *exc: object) -> None: ...


class FileTokenLock:
    """Single-machine mutex using an atomically-created lock file.

    Suitable when only one process ever refreshes the token cache. Not
    safe across machines -- use RedisTokenLock for multi-process/host
    deployments.
    """

    def __init__(
        self,
        lock_path: str | Path,
        timeout: float = 30,
        blocking_timeout: float = 15,
    ) -> None:
        self._path = Path(lock_path)
        self._timeout = timeout
        self._blocking_timeout = blocking_timeout
        self._fd: int | None = None

    def _is_stale(self) -> bool:
        try:
            age = time.time() - self._path.stat().st_mtime
        except OSError:
            return False
        return age > self._timeout

    def __enter__(self) -> "FileTokenLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self._blocking_timeout
        while True:
            try:
                self._fd = os.open(str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if self._is_stale():
                    try:
                        self._path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire file lock {self._path} "
                        f"within {self._blocking_timeout}s"
                    ) from None
                time.sleep(0.2)

    def __exit__(self, *exc: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass


class RedisTokenLock:
    """Distributed mutex backed by Redis. Required for multi-process or
    multi-host deployments sharing the same token cache."""

    def __init__(
        self,
        redis_url: str,
        name: str = "teams:token:refresh",
        timeout: int = 30,
        blocking_timeout: int = 15,
    ) -> None:
        try:
            import redis
        except ImportError:
            raise ImportError(
                "redis package is required when TEAMS_TOKEN_LOCK_URL is set. "
                "Install it with: pip install teams-core[redis]"
            ) from None

        self._redis = redis.Redis.from_url(redis_url)
        self._name = name
        self._timeout = timeout
        self._blocking_timeout = blocking_timeout
        self._lock: Any = None

    def __enter__(self) -> "RedisTokenLock":
        lock = self._redis.lock(
            self._name, timeout=self._timeout, blocking_timeout=self._blocking_timeout
        )
        lock.__enter__()
        self._lock = lock
        return self

    def __exit__(self, *exc: object) -> None:
        if self._lock is not None:
            self._lock.__exit__(*exc)
            self._lock = None


def create_lock(redis_url: str | None, lock_file_path: str | Path) -> TokenLock:
    if redis_url:
        return RedisTokenLock(redis_url)
    return FileTokenLock(lock_file_path)
