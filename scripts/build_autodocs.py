"""Generate a static documentation site from Markdown files.

This script scans the repository for Markdown files, converts them to HTML,
and builds a hierarchical navigation structure suitable for publishing via
GitHub Pages.
"""

from __future__ import annotations

import argparse
import html
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Tuple

import markdown


EXCLUDED_DIR_PARTS = {
    ".git",
    "node_modules",
    "__pycache__",
    "site",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    "storage",
}

STYLESHEET_CONTENT = """
:root {
  color-scheme: light dark;
  --bg: #f9fafb;
  --bg-alt: #ffffff;
  --fg: #111827;
  --fg-muted: #4b5563;
  --accent: #2563eb;
  --border: #e5e7eb;
  font-family: "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  display: grid;
  grid-template-columns: minmax(18rem, 22rem) 1fr;
  min-height: 100vh;
}

nav {
  background: var(--bg-alt);
  border-right: 1px solid var(--border);
  padding: 1.5rem;
  overflow-y: auto;
}

nav h1 {
  font-size: 1.1rem;
  margin-top: 0;
  margin-bottom: 1rem;
}

.nav-tree {
  list-style: none;
  padding-left: 0;
}

.nav-tree details {
  margin-bottom: 0.35rem;
}

.nav-tree summary {
  cursor: pointer;
  font-weight: 600;
}

.nav-tree a {
  color: var(--accent);
  text-decoration: none;
}

.nav-tree a:hover {
  text-decoration: underline;
}

.nav-tree .file a {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.nav-tree .file-name {
  font-weight: 600;
}

.nav-tree .file-path {
  font-size: 0.75rem;
  color: var(--fg-muted);
}

.nav-tree .active > a {
  font-weight: 700;
}

main {
  padding: 2rem;
}

main article {
  max-width: 65ch;
  line-height: 1.6;
}

.back-links {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.back-links a {
  display: inline-block;
  padding: 0.35rem 0.75rem;
  border-radius: 0.5rem;
  background: var(--accent);
  color: white;
  font-size: 0.9rem;
}

.back-links a:hover {
  opacity: 0.9;
}

.doc-list {
  list-style: none;
  margin: 0.75rem 0 0.75rem 0;
  padding-left: 1.2rem;
}

.doc-list li {
  margin: 0.3rem 0;
}

.doc-list .folder-name {
  font-weight: 600;
  display: inline-block;
  margin-bottom: 0.25rem;
}

.doc-list a {
  color: var(--accent);
  text-decoration: none;
}

.doc-list a:hover {
  text-decoration: underline;
}

code, pre {
  font-family: "JetBrains Mono", "Fira Code", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  background: rgba(37, 99, 235, 0.08);
  border-radius: 0.35rem;
}

pre {
  padding: 1rem;
  overflow-x: auto;
}

blockquote {
  border-left: 4px solid var(--accent);
  margin: 0;
  padding-left: 1rem;
  color: var(--fg-muted);
}

@media (max-width: 960px) {
  body {
    grid-template-columns: 1fr;
  }

  nav {
    position: sticky;
    top: 0;
    max-height: 50vh;
  }
}
"""


@dataclass
class NavNode:
    """Represents a folder in the Markdown navigation tree."""

    name: str
    parent: "NavNode | None" = None
    children: dict[str, "NavNode"] = field(default_factory=dict)
    files: List[Path] = field(default_factory=list)

    @property
    def path_parts(self) -> Tuple[str, ...]:
        if self.parent is None or not self.name:
            return tuple()
        return (*self.parent.path_parts, self.name)

    @property
    def anchor_id(self) -> str:
        parts = self.path_parts
        if not parts:
            return "nav-root"
        return "nav-" + "-".join(parts)

    def add_child(self, name: str) -> "NavNode":
        if name not in self.children:
            self.children[name] = NavNode(name=name, parent=self)
        return self.children[name]

    def add_file(self, rel_path: Path) -> None:
        self.files.append(rel_path)


@dataclass
class Page:
    source: Path
    relative_path: Path
    output_path: Path


def should_skip(path: Path, source_dir: Path) -> bool:
    parts = path.relative_to(source_dir).parts
    return any(part in EXCLUDED_DIR_PARTS for part in parts[:-1])


def collect_markdown_files(source_dir: Path, output_dir: Path) -> List[Page]:
    pages: List[Page] = []
    for md_file in sorted(source_dir.rglob("*.md")):
        if md_file.is_dir():
            continue
        if should_skip(md_file, source_dir):
            continue
        rel_path = md_file.relative_to(source_dir)
        output_path = output_dir / rel_path.with_suffix(".html")
        pages.append(Page(source=md_file, relative_path=rel_path, output_path=output_path))
    return pages


def build_nav_tree(pages: Iterable[Page]) -> NavNode:
    root = NavNode(name="")
    for page in pages:
        parts = list(page.relative_path.parts)
        current = root
        for folder in parts[:-1]:
            current = current.add_child(folder)
        current.add_file(page.relative_path)
    return root


def ensure_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_stylesheet(output_dir: Path) -> None:
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "styles.css").write_text(STYLESHEET_CONTENT, encoding="utf-8")


def rel_href(from_path: Path, to_path: Path) -> str:
    href = os.path.relpath(to_path, start=from_path.parent)
    return href.replace(os.sep, "/")


def render_nav_html(node: NavNode, output_dir: Path, from_page: Path, active_page: Path | None = None) -> str:
    def render_node(current: NavNode) -> str:
        items: List[str] = ["<ul class=\"nav-tree\">"] if current is node else ["<ul>"]
        for rel_file in sorted(current.files, key=lambda p: p.as_posix()):
            target = output_dir / rel_file.with_suffix(".html")
            href = rel_href(from_page, target)
            classes = ["file"]
            if active_page is not None and rel_file == active_page:
                classes.append("active")
            class_attr = " ".join(classes)
            file_name = html.escape(rel_file.name)
            file_path = html.escape(rel_file.as_posix())
            items.append(
                """
<li class=\"{class_attr}\">
  <a href=\"{href}\">
    <span class=\"file-name\">{file_name}</span>
    <span class=\"file-path\">{file_path}</span>
  </a>
</li>
""".format(class_attr=class_attr, href=href, file_name=file_name, file_path=file_path)
            )
        for child_name in sorted(current.children):
            child = current.children[child_name]
            summary_id = child.anchor_id
            child_html = render_node(child)
            items.append(
                "<li class=\"folder\">"
                f"<details open><summary id=\"{summary_id}\">{child_name}</summary>{child_html}</details>"
                "</li>"
            )
        items.append("</ul>")
        return "".join(items)

    return render_node(node)


def render_directory_listing(node: NavNode, output_dir: Path, from_page: Path) -> str:
    def render_children(current: NavNode) -> str:
        items: List[str] = []
        for child_name in sorted(current.children):
            child = current.children[child_name]
            anchor = f"#{child.anchor_id}"
            label = html.escape(child_name)
            nested = render_children(child)
            items.append(
                """
<li class=\"folder\">
  <span class=\"folder-name\"><a href=\"{anchor}\">{label}</a></span>
  {nested}
</li>
""".format(anchor=anchor, label=label, nested=nested)
            )
        for rel_file in sorted(current.files, key=lambda p: p.as_posix()):
            target = output_dir / rel_file.with_suffix(".html")
            href = rel_href(from_page, target)
            label = html.escape(rel_file.as_posix())
            items.append(f"<li class=\"file\"><a href=\"{href}\">{label}</a></li>")
        if not items:
            return ""
        return "<ul class=\"doc-list\">" + "".join(items) + "</ul>"

    listing = render_children(node)
    if not listing:
        return "<p>No Markdown files were found.</p>"
    return listing


def convert_markdown_to_html(markdown_text: str) -> str:
    return markdown.markdown(
        markdown_text,
        extensions=[
            "extra",
            "codehilite",
            "toc",
            "tables",
            "fenced_code",
        ],
        output_format="html5",
    )


def build_page_html(
    content_html: str,
    nav_html: str,
    css_href: str,
    title: str,
    back_links: List[tuple[str, str]],
) -> str:
    links_markup = "".join(
        f"<a href=\"{href}\">{label}</a>" for label, href in back_links
    )
    back_markup = f"<div class=\"back-links\">{links_markup}</div>" if back_links else ""
    return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{title}</title>
  <link rel=\"stylesheet\" href=\"{css_href}\" />
</head>
<body>
  <nav>
    <h1>Repository Docs</h1>
    {nav_html}
  </nav>
  <main>
    {back_markup}
    <article>
      {content_html}
    </article>
  </main>
</body>
</html>
"""


def create_back_links(page: Page, output_dir: Path) -> List[tuple[str, str]]:
    links: List[tuple[str, str]] = []
    index_path = output_dir / "index.html"
    index_href = rel_href(page.output_path, index_path)
    links.append(("Back to index", index_href))

    if len(page.relative_path.parts) > 1:
        parent_parts = page.relative_path.parts[:-1]
        anchor = "-".join(parent_parts)
        parent_href = f"{index_href}#nav-{anchor}" if anchor else index_href
        links.append(("Back to parent", parent_href))
    return links


def generate_pages(pages: List[Page], output_dir: Path, nav_root: NavNode) -> None:
    for page in pages:
        ensure_directory(page.output_path)
        markdown_text = page.source.read_text(encoding="utf-8")
        html_content = convert_markdown_to_html(markdown_text)
        nav_html = render_nav_html(
            nav_root,
            output_dir=output_dir,
            from_page=page.output_path,
            active_page=page.relative_path,
        )
        css_href = rel_href(page.output_path, output_dir / "assets" / "styles.css")
        back_links = create_back_links(page, output_dir)
        title = f"{page.relative_path.name} – Repository Docs"
        full_html = build_page_html(html_content, nav_html, css_href, title, back_links)
        page.output_path.write_text(full_html, encoding="utf-8")


def build_index_page(output_dir: Path, nav_root: NavNode, pages: List[Page]) -> None:
    index_path = output_dir / "index.html"
    ensure_directory(index_path)
    nav_html = render_nav_html(nav_root, output_dir=output_dir, from_page=index_path)
    css_href = rel_href(index_path, output_dir / "assets" / "styles.css")
    listing_html = render_directory_listing(nav_root, output_dir, index_path)
    content = f"""
<h1>Repository Documentation Index</h1>
<p>Select a document below to jump directly to it. The entries mirror the directory structure
of Markdown files within the repository.</p>
{listing_html}
"""
    back_links: List[tuple[str, str]] = []
    index_html = build_page_html(content, nav_html, css_href, "Repository Docs", back_links)
    index_path.write_text(index_html, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a static docs site from Markdown files.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path.cwd(),
        help="Root directory to scan for Markdown files (defaults to current directory).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("site"),
        help="Directory where the static site should be written (defaults to ./site).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove the output directory before building the documentation site.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_dir = args.source.resolve()
    output_dir = args.output.resolve()

    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    pages = collect_markdown_files(source_dir, output_dir)
    if not pages:
        raise SystemExit("No Markdown files found to document.")

    nav_root = build_nav_tree(pages)

    write_stylesheet(output_dir)
    generate_pages(pages, output_dir, nav_root)
    build_index_page(output_dir, nav_root, pages)


if __name__ == "__main__":
    main()
