"""Parameter form rendering for server-side routes."""
from __future__ import annotations

import html
from typing import Iterable, Mapping, Sequence

import pyarrow as pa

from ....core.routes import ParameterSpec, ParameterType
from ....server.cache import InvariantFilterSetting
from ..invariants import (
    coerce_page_set,
    coerce_invariant_index,
    extract_invariant_settings,
    pages_for_other_invariants,
    token_to_option_label,
    token_to_option_value,
)
from .multi_select import render_multi_select

_UNIQUE_VALUES_SENTINEL = "...unique_values..."


def _default_ui_label(name: str) -> str:
    # Preserve the long-standing behavior of turning snake_case into
    # space-separated words so default labels still resemble the column
    # headers that inspired them.
    spaced = name.replace("_", " ")
    if any(char.isupper() for char in name):
        return spaced
    return spaced.title()


def render_params_form(
    view_meta: Mapping[str, object] | None,
    params: Sequence[ParameterSpec] | None,
    param_values: Mapping[str, object] | None,
    *,
    format_hint: str | None = None,
    pagination: Mapping[str, object] | None = None,
    route_metadata: Mapping[str, object] | None = None,
    cache_meta: Mapping[str, object] | None = None,
    current_table: pa.Table | None = None,
) -> str:
    params_list = list(params or [])
    invariant_settings = extract_invariant_settings(route_metadata, cache_meta)
    if invariant_settings:
        existing = {spec.name for spec in params_list}
        for setting in invariant_settings.values():
            if setting.param in existing:
                continue
            params_list.append(_parameter_from_invariant(setting))
            existing.add(setting.param)
    if not params_list:
        return ""

    show: list[str] = []
    if view_meta:
        raw = view_meta.get("show_params")
        if isinstance(raw, str):
            show = [item.strip() for item in raw.split(",") if item.strip()]
        elif isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)):
            show = [str(name) for name in raw]
    if not show:
        return ""

    param_map = {spec.name: spec for spec in params_list}
    selected_specs = [param_map[name] for name in show if name in param_map]
    if not selected_specs:
        return ""

    values = dict(param_values or {})
    show_set = {spec.name for spec in selected_specs}
    hidden_inputs = []
    format_value = values.get("format") or format_hint
    if format_value:
        hidden_inputs.append(
            "<input type='hidden' name='format' value='"
            + html.escape(_stringify_param_value(format_value))
            + "'/>"
        )
        values.pop("format", None)
    for name, value in values.items():
        if name in show_set:
            continue
        if value in {None, ""}:
            continue
        hidden_inputs.append(
            "<input type='hidden' name='"
            + html.escape(name)
            + "' value='"
            + html.escape(_stringify_param_value(value))
            + "'/>"
        )
    if pagination:
        for key in ("limit", "offset"):
            value = pagination.get(key)
            if value in {None, ""}:
                continue
            hidden_inputs.append(
                "<input type='hidden' name='"
                + html.escape(str(key))
                + "' value='"
                + html.escape(_stringify_param_value(value))
                + "'/>"
            )

    fields: list[str] = []
    for spec in selected_specs:
        control = str(spec.extra.get("ui_control", "")).lower()
        if control not in {"input", "select"}:
            continue
        label = str(spec.extra.get("ui_label") or _default_ui_label(spec.name))
        value = values.get(spec.name, spec.default)
        selected_values = _normalize_selected_values(value)
        value_str = _stringify_param_value(value)
        field_html = ["<div class='param-field'>"]
        label_target = f"param-{spec.name}"
        if control == "select":
            label_target += "-toggle"
        field_html.append(
            "<label for='"
            + html.escape(label_target)
            + "'>"
            + html.escape(label)
            + "</label>"
        )
        if control == "input":
            input_type, extra_attr = _input_attrs_for_spec(spec)
            placeholder = spec.extra.get("ui_placeholder")
            placeholder_attr = (
                " placeholder='" + html.escape(str(placeholder)) + "'"
                if placeholder
                else ""
            )
            field_html.append(
                "<input type='"
                + input_type
                + "' id='"
                + html.escape(f"param-{spec.name}")
                + "' name='"
                + html.escape(spec.name)
                + "' value='"
                + html.escape(value_str)
                + "'"
                + placeholder_attr
                + extra_attr
                + "/>"
            )
        elif control == "select":
            raw_options = spec.extra.get("options")
            options = _resolve_select_options(
                spec,
                values,
                raw_options,
                invariant_settings,
                cache_meta,
                current_table,
            )
            placeholder_text = str(spec.extra.get("ui_placeholder") or "All values")
            field_html.append(
                render_multi_select(
                    spec.name,
                    options,
                    selected_values,
                    placeholder_text,
                )
            )
        help_text = (
            spec.extra.get("ui_help")
            or spec.extra.get("ui_hint")
            or spec.description
        )
        if help_text:
            field_html.append(
                "<p class='param-help'>" + html.escape(str(help_text)) + "</p>"
            )
        field_html.append("</div>")
        fields.append("".join(field_html))

    if not fields:
        return ""

    form_html = [
        "<div class='params-bar'><form method='get' action='?' class='params-form' data-wd-widget='params'>"
    ]
    form_html.extend(hidden_inputs)
    form_html.extend(fields)
    form_html.append(
        "<div class='param-actions'><button type='submit'>Apply</button><a class='reset-link' href='?'>Reset</a></div>"
    )
    form_html.append("</form></div>")
    return "".join(form_html)


def _parameter_from_invariant(setting: InvariantFilterSetting) -> ParameterSpec:
    extra_mapping = setting.extra if isinstance(setting.extra, Mapping) else {}
    extra: dict[str, object] = dict(extra_mapping)
    raw_type = extra.pop("type", None)
    param_type = ParameterType.STRING
    if isinstance(raw_type, str):
        try:
            param_type = ParameterType.from_string(raw_type)
        except ValueError:
            param_type = ParameterType.STRING
    required = bool(extra.pop("required", False))
    default = extra.pop("default", None)
    description_raw = extra.pop("description", None)
    if "ui_control" not in extra:
        extra["ui_control"] = "select"
    if "options" not in extra:
        extra["options"] = _UNIQUE_VALUES_SENTINEL
    if "ui_label" not in extra:
        extra["ui_label"] = _default_ui_label(setting.param)
    if "ui_allow_blank" not in extra:
        extra["ui_allow_blank"] = True
    description = str(description_raw) if description_raw is not None else None
    return ParameterSpec(
        name=setting.param,
        type=param_type,
        required=required,
        default=default,
        description=description,
        extra=extra,
    )


def _input_attrs_for_spec(spec: ParameterSpec) -> tuple[str, str]:
    if spec.type is ParameterType.INTEGER:
        return "number", ""
    if spec.type is ParameterType.FLOAT:
        return "number", " step='any'"
    if spec.type is ParameterType.BOOLEAN:
        return "text", ""
    return "text", ""


def _resolve_select_options(
    spec: ParameterSpec,
    current_values: Mapping[str, object],
    raw_options: object,
    invariant_settings: Mapping[str, InvariantFilterSetting],
    cache_meta: Mapping[str, object] | None,
    current_table: pa.Table | None,
) -> list[tuple[str, str]]:
    static_prefill: list[tuple[str, str]] = []
    wants_dynamic = False
    if isinstance(raw_options, Sequence) and not isinstance(raw_options, (str, bytes, bytearray)):
        filtered_items: list[object] = []
        for item in raw_options:
            if isinstance(item, str) and item.strip().lower() == _UNIQUE_VALUES_SENTINEL:
                wants_dynamic = True
                continue
            filtered_items.append(item)
        if wants_dynamic:
            static_prefill = _normalize_options(filtered_items)
    elif isinstance(raw_options, str):
        if raw_options.strip().lower() == _UNIQUE_VALUES_SENTINEL:
            wants_dynamic = True
    elif raw_options is None:
        wants_dynamic = True

    if wants_dynamic:
        dynamic = _unique_invariant_options(
            spec,
            invariant_settings,
            cache_meta,
            current_values,
            current_table,
        )
        if not dynamic:
            dynamic = _unique_options_from_table(
                spec,
                current_table,
                current_values,
            )
        combined = _merge_option_lists(dynamic or [("", "")], static_prefill)
        return combined or [("", "")]

    return _normalize_options(raw_options)


def _merge_option_lists(
    dynamic: list[tuple[str, str]],
    static: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    seen = {value for value, _ in dynamic}
    merged = list(dynamic)
    for value, label in static:
        if value in seen:
            continue
        merged.append((value, label))
        seen.add(value)
    return merged


def _normalize_options(options: object) -> list[tuple[str, str]]:
    normalized: list[tuple[str, str]] = []
    if isinstance(options, Mapping):
        for value, label in options.items():
            normalized.append((
                _stringify_param_value(value),
                str(label) if label is not None else "",
            ))
    elif isinstance(options, Iterable) and not isinstance(options, (str, bytes)):
        for item in options:
            if isinstance(item, Mapping):
                value = item.get("value")
                label = item.get("label", value)
                normalized.append((
                    _stringify_param_value(value),
                    str(label) if label is not None else "",
                ))
            else:
                normalized.append((
                    _stringify_param_value(item),
                    _stringify_param_value(item),
                ))
    return normalized


def _unique_invariant_options(
    spec: ParameterSpec,
    invariant_settings: Mapping[str, InvariantFilterSetting],
    cache_meta: Mapping[str, object] | None,
    current_values: Mapping[str, object],
    current_table: pa.Table | None,
) -> list[tuple[str, str]]:
    param_name = spec.name
    setting = invariant_settings.get(param_name)
    if setting is None:
        return []
    index = coerce_invariant_index(cache_meta)
    if not index:
        return []
    param_index = index.get(param_name)
    if not isinstance(param_index, Mapping):
        return []

    allowed_pages, _ = pages_for_other_invariants(
        param_name,
        invariant_settings,
        index,
        current_values,
    )
    if allowed_pages is not None and len(allowed_pages) == 0:
        return [("", "")]

    options: list[tuple[str, str]] = []
    seen: set[str] = set()
    for token, entry in param_index.items():
        if not isinstance(entry, Mapping):
            continue
        entry_pages = coerce_page_set(entry.get("pages"))
        if allowed_pages is not None and entry_pages is not None:
            if not entry_pages & allowed_pages:
                continue
        value = token_to_option_value(token, entry)
        if value in seen:
            continue
        label = token_to_option_label(token, entry)
        options.append((value, label))
        seen.add(value)
    options = _filter_options_by_table_values(spec, options, current_table)
    options.sort(key=lambda item: item[1].lower())
    if not any(value == "" for value, _ in options):
        options.insert(0, ("", ""))

    existing_values = {value for value, _ in options}
    for current_value in _normalize_selected_values(current_values.get(param_name)):
        if current_value and current_value not in existing_values:
            options.append((current_value, current_value))
            existing_values.add(current_value)

    return options


def _unique_options_from_table(
    spec: ParameterSpec,
    table: pa.Table | None,
    current_values: Mapping[str, object],
) -> list[tuple[str, str]]:
    if table is None:
        return []
    column_name = _resolve_option_column_name(spec, table)
    if column_name is None:
        return []
    column = table.column(column_name)
    seen: set[str] = set()
    options: list[tuple[str, str]] = []
    for value in column.to_pylist():
        option_value = _stringify_param_value(value)
        if option_value in seen:
            continue
        label = "" if option_value == "" else str(value)
        options.append((option_value, label))
        seen.add(option_value)
    options.sort(key=lambda item: item[1].lower())
    if "" not in seen:
        options.insert(0, ("", ""))
        seen.add("")
    for current_value in _normalize_selected_values(current_values.get(spec.name)):
        if current_value and current_value not in seen:
            options.append((current_value, current_value))
            seen.add(current_value)
    return options


def _filter_options_by_table_values(
    spec: ParameterSpec,
    options: list[tuple[str, str]],
    table: pa.Table | None,
) -> list[tuple[str, str]]:
    if table is None:
        return options
    column_name = _resolve_option_column_name(spec, table)
    if column_name is None:
        return options
    column = table.column(column_name)
    table_values = {
        _stringify_param_value(value)
        for value in column.to_pylist()
    }
    if not table_values:
        return [item for item in options if item[0] == ""]
    return [item for item in options if item[0] in table_values or item[0] == ""]


def _resolve_option_column_name(
    spec: ParameterSpec,
    table: pa.Table,
) -> str | None:
    extra = spec.extra if isinstance(spec.extra, Mapping) else {}
    candidates: list[str] = []
    for key in ("options_column", "column", "value_column"):
        raw = extra.get(key)
        if isinstance(raw, str) and raw:
            candidates.append(raw)
    if spec.name not in candidates:
        candidates.append(spec.name)
    return next((name for name in candidates if name in table.column_names), None)


def _normalize_selected_values(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        return []
    if isinstance(raw, (str, bytes, bytearray)):
        return [_stringify_param_value(raw)]
    if isinstance(raw, Iterable):
        values: list[str] = []
        for item in raw:
            value = _stringify_param_value(item)
            if value not in values:
                values.append(value)
        return values
    return [_stringify_param_value(raw)]


def _stringify_param_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


__all__ = ["render_params_form"]
