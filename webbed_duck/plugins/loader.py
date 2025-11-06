from __future__ import annotations

import hashlib
import os
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Callable

from importlib.util import module_from_spec, spec_from_file_location

__all__ = [
    "PluginLoader",
    "PluginLoadError",
    "normalize_callable_name",
    "normalize_plugin_path",
]


_PLUGIN_PATH_PATTERN = re.compile(r"^[A-Za-z0-9_./-]+$")
_CALLABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PluginLoadError(RuntimeError):
    """Raised when a plugin cannot be resolved from the configured directory."""


def _default_plugins_dir() -> Path:
    raw = os.environ.get("WEBBED_DUCK_PLUGINS_DIR", "plugins")
    return Path(raw)


def normalize_plugin_path(raw: object) -> str:
    """Return a normalised, POSIX-style plugin path relative to the plugins root."""

    text = str(raw).strip()
    if not text:
        raise PluginLoadError("'callable_path' must not be empty")
    if "\\" in text:
        raise PluginLoadError("'callable_path' must use forward slashes (/) only")
    if text.endswith("/"):
        raise PluginLoadError("'callable_path' must reference a .py file, not a directory")

    candidate = PurePosixPath(text)
    if candidate.is_absolute():
        raise PluginLoadError("'callable_path' must be relative to the plugins directory")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise PluginLoadError("'callable_path' may not contain '.' or '..' segments")

    if candidate.suffix and candidate.suffix != ".py":
        raise PluginLoadError("'callable_path' must reference a .py file")
    if not candidate.suffix:
        candidate = candidate.with_suffix(".py")

    normalized = candidate.as_posix()
    if not _PLUGIN_PATH_PATTERN.fullmatch(normalized):
        raise PluginLoadError(
            "'callable_path' contains invalid characters; only letters, numbers, '_', '-', and '/' are allowed"
        )
    return normalized


def normalize_callable_name(raw: object) -> str:
    """Validate and normalise a callable name."""

    text = str(raw).strip()
    if not text:
        raise PluginLoadError("'callable_name' must not be empty")
    if not _CALLABLE_NAME_PATTERN.fullmatch(text):
        raise PluginLoadError(
            "'callable_name' must be a valid Python identifier (letters, numbers, and underscores only)"
        )
    return text


@dataclass(frozen=True)
class _ModuleEntry:
    module: ModuleType
    module_name: str
    mtime_ns: int
    size: int


@dataclass(frozen=True)
class _CallableEntry:
    function: Callable[..., object]
    mtime_ns: int
    size: int


class PluginLoader:
    """Load plugin callables from a dedicated plugins directory."""

    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(root) if root is not None else _default_plugins_dir()
        self._root = base.expanduser().resolve(strict=False)
        self._lock = threading.RLock()
        self._module_cache: dict[Path, _ModuleEntry] = {}
        self._callable_cache: dict[tuple[str, str], _CallableEntry] = {}
        self._validated_root = False

    @property
    def root(self) -> Path:
        return self._root

    def load_callable(self, relative_path: str, callable_name: str) -> Callable[..., object]:
        """Load ``callable_name`` from ``relative_path`` within :attr:`root`."""

        normalized_path = normalize_plugin_path(relative_path)
        normalized_name = normalize_callable_name(callable_name)

        with self._lock:
            module_entry = self._load_module(normalized_path)
            key = (normalized_path, normalized_name)
            cached = self._callable_cache.get(key)
            if cached and cached.mtime_ns == module_entry.mtime_ns and cached.size == module_entry.size:
                return cached.function

            try:
                target = getattr(module_entry.module, normalized_name)
            except AttributeError as exc:
                raise PluginLoadError(
                    f"File '{normalized_path}' does not define a callable named '{normalized_name}'"
                ) from exc

            if not callable(target):
                raise PluginLoadError(
                    f"Attribute '{normalized_name}' in '{normalized_path}' is not callable"
                )

            self._callable_cache[key] = _CallableEntry(
                function=target,
                mtime_ns=module_entry.mtime_ns,
                size=module_entry.size,
            )
            return target

    def invalidate(self, relative_path: str | None = None) -> None:
        """Invalidate cached modules or callables for ``relative_path``."""

        with self._lock:
            if relative_path is None:
                for entry in self._module_cache.values():
                    sys.modules.pop(entry.module_name, None)
                self._module_cache.clear()
                self._callable_cache.clear()
                self._validated_root = False
                return

            try:
                normalized = normalize_plugin_path(relative_path)
            except PluginLoadError:
                normalized = normalize_plugin_path(f"{relative_path}")
            file_path = (self._root / Path(normalized)).resolve(strict=False)
            entry = self._module_cache.pop(file_path, None)
            if entry is not None:
                sys.modules.pop(entry.module_name, None)
            for key in list(self._callable_cache):
                if key[0] == normalized:
                    self._callable_cache.pop(key, None)
            if Path(normalized).name == "__init__.py":
                self._validated_root = False

    def _load_module(self, normalized_path: str) -> _ModuleEntry:
        file_path = (self._root / Path(normalized_path)).resolve(strict=False)
        self._ensure_root_valid()
        self._ensure_within_root(file_path, normalized_path)
        if not file_path.exists():
            raise PluginLoadError(
                f"Preprocessor file '{normalized_path}' not found under '{self._root}'"
            )
        if file_path.is_dir():
            raise PluginLoadError(
                f"Preprocessor path '{normalized_path}' points to a directory; only .py files are supported"
            )
        if file_path.suffix != ".py":
            raise PluginLoadError(
                f"Preprocessor path '{normalized_path}' must reference a .py file"
            )
        self._ensure_no_init_in_parents(file_path)

        stat = file_path.stat()
        cached = self._module_cache.get(file_path)
        if cached and cached.mtime_ns == stat.st_mtime_ns and cached.size == stat.st_size:
            return cached

        if cached is not None:
            sys.modules.pop(cached.module_name, None)
            for key in list(self._callable_cache):
                if key[0] == normalized_path:
                    self._callable_cache.pop(key, None)

        module_name = self._build_module_name(file_path, normalized_path)
        spec = spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"Could not load plugin file '{normalized_path}'")

        module = module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        entry = _ModuleEntry(
            module=module,
            module_name=module_name,
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
        )
        self._module_cache[file_path] = entry
        return entry

    def _ensure_root_valid(self) -> None:
        if self._validated_root:
            return
        if not self._root.exists():
            self._root.mkdir(parents=True, exist_ok=True)
        if not self._root.is_dir():
            raise PluginLoadError(f"Plugins directory '{self._root}' is not a directory")
        forbidden = next(self._root.rglob("__init__.py"), None)
        if forbidden is not None:
            relative = forbidden.relative_to(self._root)
            raise PluginLoadError(
                f"Plugins directory '{self._root}' must not contain '__init__.py' files (found '{relative}')"
            )
        self._validated_root = True

    def _ensure_within_root(self, path: Path, normalized: str) -> None:
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise PluginLoadError(
                f"Preprocess path '{normalized}' escapes the plugins directory; only paths under '{self._root}' are allowed"
            ) from exc

    def _ensure_no_init_in_parents(self, path: Path) -> None:
        for parent in path.parents:
            if parent == self._root.parent:
                break
            if parent == self._root:
                break
            init_file = parent / "__init__.py"
            if init_file.exists():
                relative = init_file.relative_to(self._root)
                raise PluginLoadError(
                    f"Plugins directory must not contain '__init__.py'; remove '{relative}'"
                )

    def _build_module_name(self, path: Path, normalized: str) -> str:
        digest = hashlib.blake2s(path.read_bytes(), digest_size=16).hexdigest()
        slug = normalized.replace("/", "_").replace(".py", "")
        return f"webbed_duck.plugins._auto_{slug}_{digest}"
