"""Helpers for resolving and loading callable references."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.util import find_spec, module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Callable, Literal
import sys


class CallableResolutionError(RuntimeError):
    """Raised when a callable reference cannot be resolved."""


@dataclass(frozen=True, slots=True)
class CallableDescriptor:
    """Normalised description of a callable target."""

    name: str
    source_type: Literal["module", "path"]
    source_value: str
    resolved_path: Path
    module_name: str | None = None

    def cache_key(self) -> str:
        return f"{self.source_type}:{self.resolved_path}::{self.name}"


def resolve_descriptor(
    *,
    callable_name: str,
    callable_module: str | None,
    callable_path: str | None,
    base_dir: Path | None,
) -> CallableDescriptor:
    """Resolve callable metadata into a :class:`CallableDescriptor`."""

    name = callable_name.strip()
    if not name:
        raise CallableResolutionError("callable_name must be a non-empty string")

    module_ref = callable_module.strip() if callable_module else None
    path_ref = callable_path.strip() if callable_path else None

    if module_ref and path_ref:
        raise CallableResolutionError(
            "Provide either callable_module or callable_path, not both"
        )
    if not module_ref and not path_ref:
        raise CallableResolutionError(
            "Either callable_module or callable_path must be supplied"
        )

    if module_ref:
        resolved_path = _module_reference_to_path(module_ref)
        return CallableDescriptor(
            name=name,
            source_type="module",
            source_value=module_ref,
            resolved_path=resolved_path,
            module_name=module_ref,
        )

    assert path_ref is not None
    resolved_path = _resolve_path_reference(path_ref, base_dir)
    return CallableDescriptor(
        name=name,
        source_type="path",
        source_value=path_ref,
        resolved_path=resolved_path,
        module_name=None,
    )


def load_callable(descriptor: CallableDescriptor) -> Callable[..., object]:
    """Load the callable described by ``descriptor``."""

    if descriptor.source_type == "module":
        assert descriptor.module_name is not None
        try:
            module = import_module(descriptor.module_name)
        except ModuleNotFoundError as error:
            raise CallableResolutionError(
                f"Module '{descriptor.module_name}' could not be imported"
            ) from error
    else:
        module = _load_module_from_path(descriptor.resolved_path)
    try:
        target = getattr(module, descriptor.name)
    except AttributeError as error:
        target = _load_attribute_from_package(module, descriptor.name)
        if target is None:
            raise AttributeError(
                f"Callable '{descriptor.name}' not found in '{descriptor.source_value}'"
            ) from error
    if not callable(target):
        raise TypeError(
            f"Resolved object '{descriptor.name}' from '{descriptor.source_value}' is not callable"
        )
    return target


def _module_reference_to_path(module_reference: str) -> Path:
    spec = find_spec(module_reference)
    if spec is None:
        try:
            module = import_module(module_reference)
        except ModuleNotFoundError as error:  # pragma: no cover - defensive
            raise CallableResolutionError(
                f"Module '{module_reference}' could not be imported"
            ) from error
        module_file = getattr(module, "__file__", None)
        if not module_file:
            raise CallableResolutionError(
                f"Module '{module_reference}' does not expose a filesystem path"
            )
        return _normalise_module_path(Path(module_file))

    if spec.origin and spec.origin != "built-in":
        return _normalise_module_path(Path(spec.origin))

    if spec.submodule_search_locations:
        # namespace package – no __init__.py. Require explicit file path.
        location = next(iter(spec.submodule_search_locations), None)
        if location is None:
            raise CallableResolutionError(
                f"Module '{module_reference}' does not resolve to a loadable path"
            )
        candidate = Path(location)
        if not (candidate / "__init__.py").exists():
            raise CallableResolutionError(
                f"Module '{module_reference}' is a namespace package; provide callable_path instead"
            )
        return candidate

    raise CallableResolutionError(
        f"Module '{module_reference}' does not resolve to a loadable path"
    )


def _normalise_module_path(path: Path) -> Path:
    if path.name == "__init__.py":
        return path.parent
    return path


def _resolve_path_reference(path_reference: str, base_dir: Path | None) -> Path:
    path = Path(path_reference)
    if not path.is_absolute():
        if base_dir is None:
            path = (Path.cwd() / path).resolve()
        else:
            path = (base_dir / path).resolve()
    else:
        path = path.resolve()

    if not path.exists():
        raise CallableResolutionError(
            f"Callable path '{path_reference}' does not exist"
        )

    if path.is_dir():
        if not (path / "__init__.py").exists():
            raise CallableResolutionError(
                f"Callable path '{path_reference}' points to a directory without __init__.py"
            )
        return path

    if path.suffix != ".py":
        raise CallableResolutionError(
            f"Callable path '{path_reference}' must reference a Python file"
        )

    return path


def descriptor_from_legacy_reference(
    reference: str, *, base_dir: Path | None
) -> CallableDescriptor:
    module_name, sep, attr = reference.rpartition(":")
    if sep:
        attr = attr.strip()
        if not attr:
            raise CallableResolutionError(
                f"Preprocessor '{reference}' is missing a callable attribute"
            )
        module_name = module_name.strip()
        if _looks_like_path(module_name):
            return resolve_descriptor(
                callable_name=attr,
                callable_module=None,
                callable_path=module_name,
                base_dir=base_dir,
            )
        return resolve_descriptor(
            callable_name=attr,
            callable_module=module_name,
            callable_path=None,
            base_dir=base_dir,
        )
    if "." in reference:
        module_name, attr = reference.rsplit(".", 1)
        attr = attr.strip()
        if not attr:
            raise CallableResolutionError(
                f"Preprocessor '{reference}' is missing a callable attribute"
            )
        return resolve_descriptor(
            callable_name=attr,
            callable_module=module_name,
            callable_path=None,
            base_dir=base_dir,
        )
    raise CallableResolutionError(
        "Preprocess callable references must include a module and attribute separated by ':' or '.'"
    )


def _looks_like_path(reference: str) -> bool:
    return reference.endswith(".py") or any(sep in reference for sep in ("/", "\\"))


def _load_module_from_path(reference: Path) -> ModuleType:
    file_path = reference
    is_directory = reference.is_dir()
    if is_directory:
        load_target = reference / "__init__.py"
    else:
        load_target = reference

    if not load_target.exists():
        raise ModuleNotFoundError(
            f"Preprocessor module '{reference}' was not found"
        )

    if load_target.suffix != ".py":
        raise ModuleNotFoundError(
            f"Preprocessor module reference '{reference}' must point to a Python file"
        )

    cache_key = f"webbed_duck.preprocess.path::{reference}"
    if cache_key in sys.modules:
        return sys.modules[cache_key]

    search_locations = [str(reference)] if is_directory else None
    spec = spec_from_file_location(
        cache_key,
        str(load_target),
        submodule_search_locations=search_locations,
    )
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(
            f"Could not load preprocessor module from '{reference}'"
        )

    module = module_from_spec(spec)
    sys.modules[cache_key] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _load_attribute_from_package(
    module: ModuleType, attr: str
) -> Callable[..., object] | None:
    spec = getattr(module, "__spec__", None)
    search_locations: list[str] = []
    if spec is not None and spec.submodule_search_locations:
        search_locations.extend(spec.submodule_search_locations)
    else:
        module_file = getattr(module, "__file__", None)
        if module_file:
            search_locations.append(str(Path(module_file).parent))

    for location in search_locations:
        candidate = Path(location) / f"{attr}.py"
        if not candidate.exists():
            continue
        try:
            submodule = _load_module_from_path(candidate)
        except ModuleNotFoundError:
            continue
        target = getattr(submodule, attr, None)
        if callable(target):
            return target
    return None


__all__ = [
    "CallableDescriptor",
    "CallableResolutionError",
    "descriptor_from_legacy_reference",
    "load_callable",
    "resolve_descriptor",
]
