import os
import threading
import time
from pathlib import Path

import pytest

from teams_core.auth.lock import FileTokenLock, RedisTokenLock, create_lock


def test_file_lock_acquire_release(tmp_path: Path) -> None:
    lock_path = tmp_path / "token.lock"
    lock = FileTokenLock(lock_path)

    with lock:
        assert lock_path.exists()

    assert not lock_path.exists()


def test_file_lock_blocks_concurrent(tmp_path: Path) -> None:
    lock_path = tmp_path / "token.lock"
    lock_a = FileTokenLock(lock_path, blocking_timeout=5)
    lock_b = FileTokenLock(lock_path, blocking_timeout=5)

    acquired_b_at: list[float] = []

    def hold_a() -> None:
        with lock_a:
            time.sleep(0.5)

    def acquire_b() -> None:
        with lock_b:
            acquired_b_at.append(time.monotonic())

    t_a = threading.Thread(target=hold_a)
    start = time.monotonic()
    t_a.start()
    time.sleep(0.1)  # ensure A acquires first

    t_b = threading.Thread(target=acquire_b)
    t_b.start()
    t_a.join()
    t_b.join()

    assert acquired_b_at[0] - start >= 0.4


def test_file_lock_timeout(tmp_path: Path) -> None:
    lock_path = tmp_path / "token.lock"
    # Simulate a live holder by pre-creating the lock file.
    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)

    lock = FileTokenLock(lock_path, timeout=30, blocking_timeout=0.3)
    with pytest.raises(TimeoutError):
        with lock:
            pass


def test_file_lock_stale_recovery(tmp_path: Path) -> None:
    lock_path = tmp_path / "token.lock"
    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)

    # Backdate the lock file so it looks abandoned.
    old_time = time.time() - 60
    os.utime(lock_path, (old_time, old_time))

    lock = FileTokenLock(lock_path, timeout=30, blocking_timeout=5)
    with lock:
        assert lock_path.exists()


def test_file_lock_creates_parent_dirs(tmp_path: Path) -> None:
    lock_path = tmp_path / "nested" / "dir" / "token.lock"
    lock = FileTokenLock(lock_path)

    with lock:
        assert lock_path.exists()


def test_create_lock_returns_file_when_no_url(tmp_path: Path) -> None:
    lock = create_lock(None, tmp_path / "token.lock")
    assert isinstance(lock, FileTokenLock)


def test_create_lock_returns_file_when_empty_url(tmp_path: Path) -> None:
    lock = create_lock("", tmp_path / "token.lock")
    assert isinstance(lock, FileTokenLock)


def test_create_lock_returns_redis_when_url_set(tmp_path: Path) -> None:
    pytest.importorskip("redis")
    lock = create_lock("redis://localhost:6379/0", tmp_path / "token.lock")
    assert isinstance(lock, RedisTokenLock)
