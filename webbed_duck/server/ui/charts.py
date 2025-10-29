"""Chart configuration helpers."""
from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Mapping, Sequence

import pyarrow as pa

from .utils import json_friendly


def build_chartjs_configs(
    table: pa.Table,
    specs: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    configs: list[dict[str, object]] = []
    if not specs:
        return configs

    for index, raw in enumerate(specs):
        if not isinstance(raw, Mapping):
            continue
        chart_type = str(raw.get("type") or "line").strip() or "line"
        chart_id = str(raw.get("id") or f"chart_{index}")
        x_column = str(raw.get("x") or "").strip()

        y_spec = raw.get("y")
        if isinstance(y_spec, Sequence) and not isinstance(y_spec, (str, bytes)):
            y_columns = [str(item) for item in y_spec if str(item)]
        elif isinstance(y_spec, str):
            y_columns = [y_spec]
        else:
            inferred = [name for name in table.column_names if name != x_column]
            y_columns = inferred[:1]

        if not y_columns:
            continue

        labels = _chartjs_labels(table, x_column)
        datasets = _chartjs_datasets(table, y_columns, raw)
        if not datasets:
            continue

        options = {}
        raw_options = raw.get("options")
        if isinstance(raw_options, Mapping):
            options = dict(raw_options)

        title = raw.get("title") or raw.get("label")
        heading = raw.get("heading") or title
        if heading is None:
            heading = chart_id.replace("_", " ").title()

        base_options = {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "legend": {"display": True},
            },
        }
        if title:
            base_options["plugins"]["title"] = {
                "display": True,
                "text": str(title),
            }
        merged_options = _merge_chart_options(base_options, options)

        config = {
            "type": chart_type,
            "data": {
                "labels": labels,
                "datasets": datasets,
            },
            "options": merged_options,
        }
        configs.append({"id": chart_id, "heading": heading, "config": config})

    return configs


def chart_config_json(config: Mapping[str, object]) -> str:
    try:
        payload = json.dumps(
            config,
            default=json_friendly,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        payload = "{}"
    return payload.replace("</", "<\\/")


def _chartjs_labels(table: pa.Table, column: str) -> list[object]:
    if column and column in table.column_names:
        values = table.column(column).to_pylist()
        return [json_friendly(value) for value in values]
    return list(range(1, table.num_rows + 1))


def _chartjs_datasets(
    table: pa.Table,
    columns: Sequence[str],
    spec: Mapping[str, object],
) -> list[dict[str, object]]:
    datasets: list[dict[str, object]] = []
    if not columns:
        return datasets

    palette = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#6366f1", "#14b8a6"]
    label_overrides = spec.get("dataset_labels")
    color_overrides = spec.get("colors")
    dataset_overrides = spec.get("dataset_options")

    for idx, column in enumerate(columns):
        if column not in table.column_names:
            continue
        values = table.column(column).to_pylist()
        converted = [_coerce_numeric(value) for value in values]
        if not any(item is not None for item in converted):
            continue

        if len(converted) > table.num_rows:
            converted = converted[: table.num_rows]
        elif len(converted) < table.num_rows:
            converted.extend([None] * (table.num_rows - len(converted)))

        if isinstance(label_overrides, Sequence) and not isinstance(
            label_overrides, (str, bytes)
        ) and idx < len(label_overrides):
            label = str(label_overrides[idx])
        else:
            label = spec.get("label") if len(columns) == 1 else column
            label = str(label)

        if isinstance(color_overrides, Sequence) and not isinstance(
            color_overrides, (str, bytes)
        ) and idx < len(color_overrides):
            color = str(color_overrides[idx])
        else:
            color = palette[idx % len(palette)]

        dataset = {
            "label": label,
            "data": converted,
            "borderColor": color,
            "backgroundColor": color,
        }
        if str(spec.get("type") or "line").strip().lower() in {"line", "radar"}:
            dataset["fill"] = False
            dataset["tension"] = 0.25

        if isinstance(dataset_overrides, Mapping):
            dataset.update(dataset_overrides)
        elif isinstance(dataset_overrides, Sequence) and not isinstance(
            dataset_overrides, (str, bytes)
        ) and idx < len(dataset_overrides):
            override = dataset_overrides[idx]
            if isinstance(override, Mapping):
                dataset.update(override)

        datasets.append(dataset)

    return datasets


def _merge_chart_options(
    base: Mapping[str, object],
    overrides: Mapping[str, object] | None,
) -> dict[str, object]:
    merged = dict(base)
    if not overrides:
        return merged
    for key, value in overrides.items():
        if (
            key in merged
            and isinstance(merged[key], Mapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = _merge_chart_options(merged[key], value)
        else:
            merged[key] = value
    return merged


def _coerce_numeric(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dt.datetime):
        return value.timestamp()
    if isinstance(value, dt.date):
        return float(dt.datetime.combine(value, dt.time.min).timestamp())
    try:
        text = str(value)
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


__all__ = ["build_chartjs_configs", "chart_config_json"]
