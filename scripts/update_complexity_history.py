#!/usr/bin/env python3
"""Update the auto-generated complexity history artifacts.

This script runs Radon via ``uvx`` to capture cyclomatic complexity metrics
for the ``webbed_duck`` package, stores a machine-readable history payload
inside ``docs/complexity_history.md``, and regenerates the rendered markdown
for humans.  The rendered markdown embeds a Matplotlib chart and references a
CSV export, replacing the previous Mermaid-based visualisation that failed to
render reliably in downstream tooling.
"""
from __future__ import annotations

import argparse
import csv
from datetime import UTC, datetime
import json
import math
import pathlib
import re
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

MODULES_OF_INTEREST: Sequence[str] = (
    "webbed_duck/server/ui/widgets/multi_select.py",
    "webbed_duck/server/ui/widgets/params.py",
)

DATA_MARKER_START = "<!--complexity-history:data"
DATA_MARKER_END = "complexity-history:data-->"
GRADE_ORDER = ("A", "B", "C", "D", "E", "F")


@dataclass
class Block:
    path: str
    name: str
    rank: str
    complexity: float
    lineno: int
    endline: int
    kind: str
    classname: str | None

    @property
    def qualified_name(self) -> str:
        if self.classname:
            return f"{self.classname}.{self.name}"
        return self.name

    @property
    def key(self) -> str:
        return f"{self.path}:{self.qualified_name}:{self.kind}"


@dataclass
class Entry:
    version: str
    timestamp: str
    average: float
    average_grade: str
    blocks_analyzed: int
    grade_counts: Mapping[str, int]
    top_blocks: Sequence[Block]
    modules: Mapping[str, Sequence[Block]]

    def to_json(self) -> Mapping[str, object]:
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "average": self.average,
            "average_grade": self.average_grade,
            "blocks_analyzed": self.blocks_analyzed,
            "grade_counts": dict(self.grade_counts),
            "top_blocks": [block.__dict__ for block in self.top_blocks],
            "modules": {
                module: [block.__dict__ for block in blocks]
                for module, blocks in self.modules.items()
            },
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, object]) -> "Entry":
        def parse_block(raw: Mapping[str, object]) -> Block:
            return Block(
                path=str(raw["path"]),
                name=str(raw["name"]),
                rank=str(raw["rank"]),
                complexity=float(raw["complexity"]),
                lineno=int(raw["lineno"]),
                endline=int(raw["endline"]),
                kind=str(raw["kind"]),
                classname=(str(raw["classname"]) if raw.get("classname") else None),
            )

        modules: Dict[str, List[Block]] = {}
        raw_modules = payload.get("modules", {})
        if isinstance(raw_modules, Mapping):
            for module, blocks in raw_modules.items():
                modules[str(module)] = [parse_block(block) for block in blocks]  # type: ignore[arg-type]

        return cls(
            version=str(payload["version"]),
            timestamp=str(payload["timestamp"]),
            average=float(payload["average"]),
            average_grade=str(payload["average_grade"]),
            blocks_analyzed=int(payload["blocks_analyzed"]),
            grade_counts={str(k): int(v) for k, v in dict(payload["grade_counts"]).items()},
            top_blocks=[parse_block(block) for block in payload.get("top_blocks", [])],
            modules=modules,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        required=True,
        help="The semantic version to associate with the captured metrics.",
    )
    parser.add_argument(
        "--output",
        default="docs/complexity_history.md",
        help="Path to the markdown file that stores the rendered history.",
    )
    parser.add_argument(
        "--radon-target",
        default="webbed_duck",
        help="Path (file or directory) to analyse with radon.",
    )
    parser.add_argument(
        "--chart-format",
        action="append",
        dest="chart_formats",
        choices=("svg", "png"),
        help=(
            "Image format to generate for the rendered chart. "
            "May be provided multiple times to emit several variants."
        ),
    )
    return parser.parse_args()


def run_radon_json(target: str) -> Mapping[str, Sequence[Mapping[str, object]]]:
    """Run ``radon cc`` via ``uvx`` and return the parsed JSON payload."""
    result = subprocess.run(
        ["uvx", "radon", "cc", target, "--json"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.stderr:
        # Radon prints nothing noteworthy to stderr for successful runs, so we
        # surface the output early when anything leaks through.
        print(result.stderr)
    return json.loads(result.stdout)


def grade_for_complexity(value: float) -> str:
    thresholds = (
        (5, "A"),
        (10, "B"),
        (20, "C"),
        (30, "D"),
        (40, "E"),
    )
    for limit, grade in thresholds:
        if value < limit:
            return grade
    return "F"


def collect_blocks(raw: Mapping[str, Sequence[Mapping[str, object]]]) -> List[Block]:
    blocks: List[Block] = []
    for path, entries in raw.items():
        for entry in entries:
            blocks.append(
                Block(
                    path=str(path),
                    name=str(entry["name"]),
                    rank=str(entry["rank"]),
                    complexity=float(entry["complexity"]),
                    lineno=int(entry["lineno"]),
                    endline=int(entry["endline"]),
                    kind=str(entry["type"]),
                    classname=(str(entry["classname"]) if entry.get("classname") else None),
                )
            )
    return blocks


def load_existing_entries(path: pathlib.Path) -> List[Entry]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"{re.escape(DATA_MARKER_START)}\n(?P<payload>.*?)\n{DATA_MARKER_END}",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return []
    payload = json.loads(match.group("payload"))
    raw_entries = payload.get("entries", [])
    return [Entry.from_json(entry) for entry in raw_entries]


def serialise_entries(entries: Sequence[Entry]) -> str:
    payload = {
        "entries": [entry.to_json() for entry in entries],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def sort_key(version: str) -> tuple[int, ...]:
    parts: List[int] = []
    for token in version.split('.'):
        if token.isdigit():
            parts.append(int(token))
        else:
            # Support prereleases like "1.2.3b1" by splitting numeric prefix.
            numeric = ''.join(ch for ch in token if ch.isdigit())
            suffix = ''.join(ch for ch in token if not ch.isdigit())
            parts.append(int(numeric) if numeric else 0)
            if suffix:
                # Encode suffix via ordinal tuple to ensure deterministic ordering.
                parts.extend(ord(ch) for ch in suffix)
    return tuple(parts)


def build_entry(version: str, blocks: Sequence[Block]) -> Entry:
    average = sum(block.complexity for block in blocks) / len(blocks)
    grade_counts: Dict[str, int] = {grade: 0 for grade in GRADE_ORDER}
    for block in blocks:
        grade_counts[block.rank] = grade_counts.get(block.rank, 0) + 1
    # Ensure all grades are present for downstream formatting.
    for grade in GRADE_ORDER:
        grade_counts.setdefault(grade, 0)

    top_blocks = sorted(blocks, key=lambda block: block.complexity, reverse=True)[:10]

    modules: Dict[str, List[Block]] = {}
    for module in MODULES_OF_INTEREST:
        module_blocks = [block for block in blocks if block.path == module]
        modules[module] = sorted(
            module_blocks,
            key=lambda block: (block.complexity, block.qualified_name),
            reverse=True,
        )

    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return Entry(
        version=version,
        timestamp=timestamp,
        average=average,
        average_grade=grade_for_complexity(average),
        blocks_analyzed=len(blocks),
        grade_counts=grade_counts,
        top_blocks=top_blocks,
        modules=modules,
    )


def write_csv(entries: Sequence[Entry], path: pathlib.Path) -> None:
    """Persist the high-level metrics for each entry as CSV."""

    fieldnames = (
        "version",
        "timestamp",
        "average_complexity",
        "average_grade",
        "blocks_analyzed",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "version": entry.version,
                    "timestamp": entry.timestamp,
                    "average_complexity": f"{entry.average:.6f}",
                    "average_grade": entry.average_grade,
                    "blocks_analyzed": entry.blocks_analyzed,
                }
            )


def render_chart(entries: Sequence[Entry], path: pathlib.Path, fmt: str) -> None:
    """Render a Matplotlib chart that mirrors the historical averages."""

    if not entries:
        path.unlink(missing_ok=True)
        return

    versions = [f"v{entry.version}" for entry in entries]
    averages = [entry.average for entry in entries]

    figure, axis = plt.subplots(figsize=(9, 4.5))
    axis.plot(versions, averages, marker="o", linewidth=2)
    axis.set_title("Webbed Duck Cyclomatic Complexity")
    axis.set_xlabel("Version")
    axis.set_ylabel("Average Cyclomatic Complexity")
    axis.grid(True, which="major", linestyle="--", linewidth=0.5, alpha=0.6)
    axis.set_ylim(bottom=0)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)

    save_kwargs = {"format": fmt}
    if fmt == "png":
        save_kwargs["dpi"] = 200
    figure.savefig(path, **save_kwargs)
    plt.close(figure)


def format_grade_table(entry: Entry) -> str:
    header = "| Grade | Blocks | Share |\n| ----- | ------ | ----- |"
    rows = [header]
    for grade in GRADE_ORDER:
        count = entry.grade_counts.get(grade, 0)
        share = (count / entry.blocks_analyzed) * 100 if entry.blocks_analyzed else 0.0
        rows.append(f"| {grade} | {count} | {share:.1f}% |")
    return "\n".join(rows)


def describe_block(block: Block) -> str:
    target = block.qualified_name
    location = f"{block.path}:{block.lineno}"
    return f"`{target}` ({location})"


def format_top_blocks(entry: Entry) -> str:
    header = "| Rank | Block | Complexity |\n| ---- | ----- | ---------- |"
    rows = [header]
    for index, block in enumerate(entry.top_blocks, start=1):
        rows.append(
            "| {idx} | `{name}` ({path}:{lineno}) | {complexity:.0f} ({rank}) |".format(
                idx=index,
                name=block.qualified_name,
                path=block.path,
                lineno=block.lineno,
                complexity=block.complexity,
                rank=block.rank,
            )
        )
    return "\n".join(rows)


def format_module_breakdown(module: str, blocks: Sequence[Block]) -> str:
    if not blocks:
        return f"No blocks analysed for `{module}`."
    header = "| Block | Type | Line Range | Complexity | Grade |\n| ----- | ---- | ---------- | ---------- | ----- |"
    rows = [header]
    for block in blocks:
        line_range = f"{block.lineno}-{block.endline}" if block.endline != block.lineno else str(block.lineno)
        rows.append(
            "| `{name}` | {kind} | {lines} | {complexity:.0f} | {rank} |".format(
                name=block.qualified_name,
                kind=block.kind,
                lines=line_range,
                complexity=block.complexity,
                rank=block.rank,
            )
        )
    return "\n".join(rows)


def format_comparison(current: Entry, previous: Entry) -> str:
    lines = [
        f"- Average complexity changed by {current.average - previous.average:+.3f} (from {previous.average_grade} to {current.average_grade})."
    ]

    deltas = []
    for grade in GRADE_ORDER:
        delta = current.grade_counts.get(grade, 0) - previous.grade_counts.get(grade, 0)
        if delta:
            deltas.append(f"{grade} {delta:+d}")
    if deltas:
        lines.append(f"- Grade distribution shifts: {', '.join(deltas)}.")

    for module in MODULES_OF_INTEREST:
        prev_blocks = {block.key: block for block in previous.modules.get(module, [])}
        curr_blocks = {block.key: block for block in current.modules.get(module, [])}
        module_changes: List[str] = []
        for key in sorted(set(prev_blocks) | set(curr_blocks)):
            prev_block = prev_blocks.get(key)
            curr_block = curr_blocks.get(key)
            if prev_block and not curr_block:
                module_changes.append(f"{describe_block(prev_block)} was removed from the tracked blocks.")
            elif curr_block and not prev_block:
                module_changes.append(f"{describe_block(curr_block)} was added with complexity {curr_block.complexity:.0f} ({curr_block.rank}).")
            elif curr_block and prev_block:
                if not math.isclose(curr_block.complexity, prev_block.complexity) or curr_block.rank != prev_block.rank:
                    module_changes.append(
                        "{name} shifted from {prev_complexity:.0f} ({prev_rank}) to {curr_complexity:.0f} ({curr_rank}).".format(
                            name=describe_block(curr_block),
                            prev_complexity=prev_block.complexity,
                            prev_rank=prev_block.rank,
                            curr_complexity=curr_block.complexity,
                            curr_rank=curr_block.rank,
                        )
                    )
        if module_changes:
            lines.append(f"- `{module}` updates:")
            for change in module_changes:
                lines.append(f"  - {change}")

    if len(lines) == 1:
        lines.append("- No tracked complexity deltas for monitored blocks.")

    body = "\n".join(lines)
    return f"<details>\n<summary>Changes since v{previous.version}</summary>\n\n{body}\n\n</details>"


def render_entry(entry: Entry, previous: Entry | None) -> str:
    parts = [f"## Version v{entry.version} ({entry.timestamp})", "", "### Summary", "", f"- Blocks analysed: {entry.blocks_analyzed}", f"- Average cyclomatic complexity: {entry.average:.3f} ({entry.average_grade})", "", "### Grade distribution", "", format_grade_table(entry), "", "### Most complex blocks", "", format_top_blocks(entry)]

    for module in MODULES_OF_INTEREST:
        parts.extend([
            "",
            f"### `{module}`",
            "",
            format_module_breakdown(module, entry.modules.get(module, [])),
        ])

    if previous:
        parts.extend(["", format_comparison(entry, previous)])

    return "\n".join(parts)


def rebuild_markdown(entries: Sequence[Entry], chart_asset: str, csv_asset: str) -> str:
    header = (
        "# Cyclomatic Complexity History\n\n"
        "This file is auto-generated by `scripts/update_complexity_history.py`.\n"
        "Do not edit manually—changes will be overwritten during the automated\n"
        "version bump workflow.\n"
    )
    visualisation = (
        f"![Cyclomatic complexity history]({chart_asset})\n\n"
        f"The underlying metrics are available as [`{csv_asset}`]({csv_asset})."
    )
    data_comment = serialise_entries(entries)
    body_sections = []
    for index, entry in enumerate(entries):
        previous = entries[index - 1] if index > 0 else None
        body_sections.append(render_entry(entry, previous))
    data_block = f"{DATA_MARKER_START}\n{data_comment}\n{DATA_MARKER_END}"
    return "\n\n".join([header, visualisation, data_block, *body_sections]) + "\n"


def main() -> None:
    args = parse_args()
    output_path = pathlib.Path(args.output)
    existing_entries = load_existing_entries(output_path)
    raw = run_radon_json(args.radon_target)
    blocks = collect_blocks(raw)
    entry = build_entry(args.version, blocks)

    entries: Dict[str, Entry] = {item.version: item for item in existing_entries}
    entries[entry.version] = entry
    ordered = [entries[version] for version in sorted(entries, key=sort_key)]

    csv_path = output_path.with_suffix(".csv")

    raw_chart_formats = args.chart_formats or ["svg"]
    chart_formats: List[str] = []
    for fmt in raw_chart_formats:
        if fmt not in chart_formats:
            chart_formats.append(fmt)

    chart_paths = [output_path.with_suffix(f".{fmt}") for fmt in chart_formats]

    write_csv(ordered, csv_path)
    for fmt, path in zip(chart_formats, chart_paths):
        render_chart(ordered, path, fmt)

    markdown = rebuild_markdown(ordered, chart_paths[0].name, csv_path.name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")


if __name__ == "__main__":
    main()
