from __future__ import annotations

import sys
import re
import textwrap
from pathlib import Path

SQL_BLOCK_PATTERN = re.compile(r"```sql\s*(?P<sql>.*?)```", re.DOTALL | re.IGNORECASE)


def write_sidecar_route(base: Path, name: str, content: str) -> None:
    """Materialise a TOML/SQL sidecar route from legacy markdown-style text."""

    text = textwrap.dedent(content).strip()
    if not text.startswith("+++"):
        raise ValueError("Route definitions must start with TOML frontmatter")

    first = text.find("+++")
    second = text.find("+++", first + 3)
    if second == -1:
        raise ValueError("Route definitions must contain closing frontmatter delimiter")

    frontmatter = text[first + 3 : second].strip()
    body = text[second + 3 :].strip()

    match = SQL_BLOCK_PATTERN.search(body)
    if not match:
        raise ValueError("Route definitions must contain a ```sql``` block")

    sql = match.group("sql").strip()
    doc = (body[: match.start()] + body[match.end() :]).strip()

    (base / f"{name}.toml").write_text(frontmatter + "\n", encoding="utf-8")
    (base / f"{name}.sql").write_text(sql + "\n", encoding="utf-8")
    if doc:
        (base / f"{name}.md").write_text(doc + "\n", encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
