"""Cross-process, fail-closed lock for a single Video IR publication.

An orphaned lock is deliberately NOT auto-removed: recovery must investigate
whether the remote YouTube upload completed before clearing the lock.
"""
from __future__ import annotations
from contextlib import contextmanager
import os
from pathlib import Path
import secrets


@contextmanager
def publication_lock(ir_path: str | Path):
    path = Path(ir_path)
    lock = path.with_name(path.name + ".publish.lock")
    token = secrets.token_hex(16)
    try:
        fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise RuntimeError("publication locked; inspect in-flight upload before retry") from error
    with os.fdopen(fd, "w", encoding="ascii") as stream:
        stream.write(token)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        yield
    finally:
        # Never remove another worker's lock after manual takeover.
        try:
            if lock.read_text(encoding="ascii") == token:
                lock.unlink()
        except FileNotFoundError:
            pass


def serialized_publication(fn):
    """Wrap an existing publisher without creating a new dispatch/control plane."""
    def wrapped(ir_path, *args, **kwargs):
        with publication_lock(ir_path):
            return fn(ir_path, *args, **kwargs)
    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped
