from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_header_scroll_hides_offset() -> None:
    """The sticky table header should reset when the top bar hides itself."""

    repo_root = Path(__file__).resolve().parents[1]
    header_js = Path("webbed_duck/static/assets/wd/header.js")

    script = f"""
const styleMap = new Map();
const listeners = Object.create(null);

const root = {{
  style: {{
    setProperty(name, value) {{
      styleMap.set(name, value);
    }},
    getPropertyValue(name) {{
      return styleMap.get(name) ?? '';
    }},
  }},
}};

const topButton = {{
  dataset: {{}},
  textContent: '',
  setAttribute() {{}},
  addEventListener(_type, cb) {{
    this._handler = cb;
  }},
}};

const header = {{
  _attrs: new Map([
    ['data-hidden', 'false'],
    ['data-collapsed', 'false'],
  ]),
  dataset: {{}},
  querySelector(selector) {{
    if (selector === '[data-wd-top-toggle]') return topButton;
    return null;
  }},
  setAttribute(name, value) {{
    this._attrs.set(name, value);
  }},
  getAttribute(name) {{
    return this._attrs.get(name) ?? 'false';
  }},
  addEventListener() {{}},
  getBoundingClientRect() {{
    return {{ height: 120 }};
  }},
}};

globalThis.document = {{
  readyState: 'complete',
  documentElement: root,
  querySelector(selector) {{
    if (selector === '[data-wd-top]') return header;
    return null;
  }},
  addEventListener() {{}},
}};

globalThis.window = {{
  scrollY: 0,
  addEventListener(type, handler) {{
    if (!listeners[type]) {{
      listeners[type] = [];
    }}
    listeners[type].push(handler);
  }},
  requestAnimationFrame(cb) {{
    cb();
  }},
}};

globalThis.requestAnimationFrame = globalThis.window.requestAnimationFrame;

const mod = await import('./{header_js.as_posix()}');

mod.initHeader(header);

const initial = root.style.getPropertyValue('--wd-top-offset');

window.scrollY = 300;
if (listeners['scroll']) {{
  for (const handler of listeners['scroll']) {{
    handler();
  }}
}}

const afterHide = root.style.getPropertyValue('--wd-top-offset');

console.log(JSON.stringify({{ initial, afterHide }}));
"""

    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js runtime is required to exercise header interactions.")

    completed = subprocess.run(
        [node, "--input-type=module", "-"],
        input=script.encode("utf-8"),
        capture_output=True,
        check=True,
        cwd=repo_root,
    )

    payload = json.loads(completed.stdout.decode("utf-8").strip())

    assert payload["initial"] == "120px"
    assert payload["afterHide"] == "0px"
