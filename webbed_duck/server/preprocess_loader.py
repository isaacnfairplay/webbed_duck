from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec, module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Literal, Mapping
import sys


@dataclass(frozen=True)
class CallableReference:
    """Normalized reference to a preprocess callable."""

    kind: Literal["module", "path"]
    location: str
    display: str
    callable_name: str

    @property
    def cache_key(self) -> str:
        return f"{self.kind}:{self.location}:{self.callable_name}"

    def describe(self) -> str:
        if self.kind == "module":
            return f"{self.location}:{self.callable_name}"
        return f"{self.display}::{self.callable_name}"


def normalize_callable_reference(step: Mapping[str, object]) -> CallableReference:
    """Extract a :class:`CallableReference` from ``step``.

    Supports both the new ``callable_*`` keys and legacy ``callable`` strings.
    """

    module_value = _coerce_optional_string(step.get("callable_module"))
    path_value = _coerce_optional_string(step.get("callable_path"))
    name_value = _coerce_optional_string(step.get("callable_name"))
    legacy_value = _coerce_optional_string(step.get("callable"))

    if not name_value and legacy_value:
        module_or_path, attr = _split_legacy_reference(legacy_value)
        name_value = attr
        if _looks_like_path(module_or_path):
            path_value = module_or_path
            module_value = None
        else:
            module_value = module_or_path
            path_value = None

    if not name_value:
        raise ValueError("Preprocess steps must define 'callable_name' or legacy 'callable'.")

    if module_value and path_value:
        raise ValueError(
            "Preprocess steps may specify only one of 'callable_module' or 'callable_path'."
        )

    if not module_value and not path_value:
        if not legacy_value:
            raise ValueError(
                "Preprocess steps must define either 'callable_module' or 'callable_path'."
            )
        module_or_path, _ = _split_legacy_reference(legacy_value)
        if _looks_like_path(module_or_path):
            path_value = module_or_path
        else:
            module_value = module_or_path

    if path_value:
        normalized_path = str(Path(path_value).expanduser().resolve(strict=False))
        return CallableReference("path", normalized_path, path_value, name_value)

    if module_value:
        return CallableReference("module", module_value, module_value, name_value)

    raise ValueError(
        "Preprocess steps must define either 'callable_module' or 'callable_path'."
    )


def validate_callable_reference(reference: CallableReference) -> None:
    """Ensure ``reference`` can be imported and resolves to a callable."""

    load_callable(reference)


def load_callable(reference: CallableReference):
    module = _load_module(reference)
    try:
        target = getattr(module, reference.callable_name)
    except AttributeError as error:
        target = _load_attribute_from_package(module, reference.callable_name)
        if target is None:
            raise AttributeError(
                f"Callable '{reference.callable_name}' not found in {reference.describe()}"
            ) from error
    if not callable(target):
        raise TypeError(f"Preprocessor '{reference.describe()}' is not callable")
    return target


def _load_module(reference: CallableReference) -> ModuleType:
    if reference.kind == "path":
        return _load_module_from_path(reference.location, reference.display)
    return _load_module_from_module_name(reference.location, reference.display)


def _load_module_from_path(location: str, display: str) -> ModuleType:
    file_path = Path(location)
    if not file_path.exists():
        raise ModuleNotFoundError(f"Preprocessor module '{display}' was not found")

    is_directory = file_path.is_dir()
    if is_directory:
        init_file = file_path / "__init__.py"
        if not init_file.exists():
            raise ModuleNotFoundError(
                f"Preprocessor module reference '{display}' points to a directory without an __init__.py"
            )
        load_target = init_file
    else:
        load_target = file_path

    if load_target.suffix != ".py":
        raise ModuleNotFoundError(
            f"Preprocessor module reference '{display}' must point to a Python file"
        )

    cache_key = f"webbed_duck.preprocess.path::{location}"
    if cache_key in sys.modules:
        return sys.modules[cache_key]

    search_locations = [str(file_path)] if is_directory else None
    spec = spec_from_file_location(
        cache_key,
        str(load_target),
        submodule_search_locations=search_locations,
    )
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"Could not load preprocessor module from '{display}'")
    module = module_from_spec(spec)
    sys.modules[cache_key] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _load_module_from_module_name(module_name: str, display: str) -> ModuleType:
    spec = find_spec(module_name)
    if spec is None:
        raise ModuleNotFoundError(f"Preprocessor module '{display}' could not be resolved")

    search_locations = None
    if spec.origin and spec.origin != "built-in":
        load_target = Path(spec.origin)
        if spec.submodule_search_locations:
            search_locations = list(spec.submodule_search_locations)
    elif spec.submodule_search_locations:
        locations = list(spec.submodule_search_locations)
        if not locations:
            raise ModuleNotFoundError(
                f"Preprocessor module '{display}' did not resolve to a file location"
            )
        load_target = Path(locations[0]) / "__init__.py"
        search_locations = locations
    else:
        raise ModuleNotFoundError(
            f"Preprocessor module '{display}' did not resolve to a file location"
        )

    if load_target.suffix != ".py":
        raise ModuleNotFoundError(
            f"Preprocessor module '{display}' must resolve to a Python file"
        )

    cache_key = f"webbed_duck.preprocess.module::{module_name}"
    if cache_key in sys.modules:
        return sys.modules[cache_key]

    spec = spec_from_file_location(
        cache_key,
        str(load_target),
        submodule_search_locations=search_locations,
    )
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"Could not load preprocessor module from '{display}'")
    module = module_from_spec(spec)
    sys.modules[cache_key] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _load_attribute_from_package(module: ModuleType, attr: str):
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
            submodule = _load_module_from_path(str(candidate), str(candidate))
        except ModuleNotFoundError:
            continue
        try:
            target = getattr(submodule, attr)
        except AttributeError:
            continue
        if callable(target):
            return target
    return None


def _coerce_optional_string(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _split_legacy_reference(reference: str) -> tuple[str, str]:
    module_part, sep, attr = reference.rpartition(":")
    if sep:
        module_part = module_part.strip()
        attr = attr.strip()
        if not module_part or not attr:
            raise ValueError(
                "Preprocess callable references must include a module and attribute separated by ':' or '.'."
            )
        return module_part, attr

    if "." in reference:
        module_part, attr = reference.rsplit(".", 1)
        module_part = module_part.strip()
        attr = attr.strip()
        if not module_part or not attr:
            raise ValueError(
                "Preprocess callable references must include a module and attribute separated by ':' or '.'."
            )
        return module_part, attr

    raise ValueError(
        "Preprocess callable references must include a module and attribute separated by ':' or '.'."
    )


def _looks_like_path(value: str) -> bool:
    path = Path(value)
    return (
        path.suffix == ".py"
        or path.is_absolute()
        or any(sep in value for sep in ("/", "\\"))
    )


__all__ = [
    "CallableReference",
    "load_callable",
    "normalize_callable_reference",
    "validate_callable_reference",
]
