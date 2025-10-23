from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from importlib import import_module
from typing import Callable, Iterable, MutableSequence, Sequence

import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.parquet as pa_parquet

from ..config import ShareConfig

EmailSendFn = Callable[[Sequence[str], str, str, str | None, Sequence[tuple[str, bytes]] | None], None]


@dataclass(slots=True)
class PreparedShareEmail:
    """Normalized payload for a share email."""

    recipients: Sequence[str]
    subject: str
    html_body: str
    text_body: str | None
    attachments: Sequence[tuple[str, bytes]]
    share_url: str


def load_email_adapter(spec: str | None) -> EmailSendFn | None:
    """Resolve an email adapter from ``spec``.

    ``spec`` may be ``None`` (disabled), a dotted path (``pkg.mod.func``), or a
    ``module:callable`` reference. The callable must accept the
    ``EmailSendFn`` signature.
    """

    if not spec:
        return None
    target = spec
    if spec.startswith("custom:"):
        target = spec.split("custom:", 1)[1]
    module_name: str
    attribute: str
    if ":" in target:
        module_name, attribute = target.split(":", 1)
    else:
        module_name, attribute = target.rsplit(".", 1)
    module = import_module(module_name)
    candidate = getattr(module, attribute)
    if callable(candidate):
        return candidate  # type: ignore[return-value]
    raise TypeError(f"Email adapter {spec!r} is not callable")


def normalize_recipients(values: object) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if isinstance(values, Sequence):
        recipients = [str(item).strip() for item in values if str(item).strip()]
        return recipients
    raise TypeError("email recipients must be a string or list of strings")


def build_share_attachments(
    table: pa.Table,
    *,
    route_id: str,
    formats: Iterable[str],
    config: ShareConfig,
    watermark_text: str | None = None,
    zip_passphrase: str | None = None,
) -> list[tuple[str, bytes]]:
    """Construct attachments for a share email respecting ``config``."""

    normalized = {fmt.lower() for fmt in formats if fmt}
    if not normalized:
        normalized = {"csv"}

    raw_attachments: MutableSequence[tuple[str, bytes]] = []
    if "csv" in normalized:
        raw_attachments.append((f"{route_id}.csv", _table_to_csv(table)))
    if "parquet" in normalized:
        raw_attachments.append((f"{route_id}.parquet", _table_to_parquet(table)))

    limit_bytes = max(1, int(config.max_total_size_mb)) * 1024 * 1024
    total_bytes = sum(len(content) for _, content in raw_attachments)
    if total_bytes > limit_bytes:
        raise ValueError("Share attachments exceed configured size limit")

    attachments: list[tuple[str, bytes]] = []
    if config.zip_attachments:
        if config.zip_passphrase_required:
            raise ValueError("Zip passphrases are currently not supported for email shares")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in raw_attachments:
                archive.writestr(name, content)
            metadata: dict[str, object] = {"route_id": route_id, "attachments": [name for name, _ in raw_attachments]}
            if watermark_text and config.watermark:
                archive.writestr("WATERMARK.txt", watermark_text)
                metadata["watermark"] = watermark_text
            archive.writestr("metadata.json", json.dumps(metadata, indent=2))
        attachments.append((f"{route_id}_share.zip", buffer.getvalue()))
    else:
        attachments.extend(raw_attachments)
        if watermark_text and config.watermark:
            attachments.append(("WATERMARK.txt", watermark_text.encode("utf-8")))
    return attachments


def _table_to_csv(table: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    pa_csv.write_csv(table, sink)
    return sink.getvalue().to_pybytes()


def _table_to_parquet(table: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    pa_parquet.write_table(table, sink)
    return sink.getvalue().to_pybytes()


__all__ = [
    "PreparedShareEmail",
    "build_share_attachments",
    "load_email_adapter",
    "normalize_recipients",
]
