"""Filesystem helpers shared across tests."""

from __future__ import annotations

import contextlib
import shutil
from pathlib import Path
from typing import Iterator


@contextlib.contextmanager
def temporary_storage(tmp_path_factory, *, prefix: str = "storage") -> Iterator[Path]:
    """Yield a scratch directory suitable for use as a storage root."""

    root = Path(tmp_path_factory.mktemp(prefix))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)
