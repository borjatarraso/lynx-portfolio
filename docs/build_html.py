#!/usr/bin/env python3
"""
Build styled HTML documentation from Markdown sources.

Usage:  python docs/build_html.py
"""

import os
import re
import sys

import markdown

DOCS_DIR = os.path.dirname(os.path.abspath(__file__))

# Pages to build: (md_filename, nav_title)
PAGES = [
    ("README.md",        "Overview"),
    ("user-guide.md",    "User Guide"),
    ("api-reference.md", "API Reference"),
    ("architecture.md",  "Architecture"),
]

# ---------------------------------------------------------------------------
# Extract headings from HTML to build sidebar TOC
# ---------------------------------------------------------------------------

def _extract_headings(html: str):
    """Return list of (level, id, text) from <h2>/<h3> tags."""
    headings = []
    for m in re.finditer(r'<h([23])\s*(?:id="([^"]*)")?>(.*?)</h\1>', html, re.DOTALL):
        level = int(m.group(1))
        raw_text = re.sub(r'<[^>]+>', '', m.group(3)).strip()
        slug = m.group(2) or re.sub(r'[^a-z0-9]+', '-', raw_text.lower()).strip('-')
        headings.append((level, slug, raw_text))
    return headings


def _inject_heading_ids(html: str, headings):
    """Add id= attributes to h2/h3 tags that don't have them."""
    idx = 0
    def _replacer(m):
        nonlocal idx
        if idx >= len(headings):
            return m.group(0)
        level, slug, _ = headings[idx]
        tag_level = int(m.group(1))
        if tag_level != level:
            return m.group(0)
        idx += 1
        if m.group(2):
            return m.group(0)  # already has id
        return f'<h{tag_level} id="{slug}">{m.group(3)}</h{tag_level}>'
    return re.sub(r'<h([23])\s*(?:id="([^"]*)")?>(.*?)</h\1>', _replacer, html, flags=re.DOTALL)


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Lynx Portfolio</title>
<style>
/* ── Reset & base ──────────────────────────────────────────────── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  --bg:          #0d1117;
  --bg-sidebar:  #0a0e14;
  --bg-card:     #131920;
  --bg-code:     #1a2230;
  --border:      #1e2a38;
  --fg:          #c9d1d9;
  --fg-dim:      #7a8595;
  --fg-heading:  #e6edf3;
  --accent:      #58a6ff;
  --accent-dim:  #2d6cb4;
  --green:       #3fb950;
  --yellow:      #d29922;
  --red:         #f85149;
  --purple:      #bc8cff;
  --sidebar-w:   260px;
}}

html {{ scroll-behavior: smooth; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.65;
  font-size: 15px;
}}

/* ── Top bar ───────────────────────────────────────────────────── */
.topbar {{
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 52px;
  background: var(--bg-sidebar);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 24px;
  z-index: 100;
}}
.topbar .logo {{
  font-size: 18px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: 1px;
}}
.topbar .logo span {{
  color: var(--fg-dim);
  font-weight: 400;
  font-size: 13px;
  margin-left: 10px;
}}

/* ── Sidebar ───────────────────────────────────────────────────── */
.sidebar {{
  position: fixed;
  top: 52px;
  left: 0;
  bottom: 0;
  width: var(--sidebar-w);
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  padding: 20px 0;
  z-index: 90;
}}
.sidebar::-webkit-scrollbar {{ width: 4px; }}
.sidebar::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 4px; }}

.sidebar .nav-section {{
  padding: 0 16px;
  margin-bottom: 18px;
}}
.sidebar .nav-section-title {{
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--fg-dim);
  margin-bottom: 8px;
  padding-left: 8px;
}}
.sidebar a {{
  display: block;
  padding: 5px 8px 5px 12px;
  color: var(--fg);
  text-decoration: none;
  font-size: 13px;
  border-radius: 5px;
  transition: background 0.15s, color 0.15s;
}}
.sidebar a:hover {{
  background: rgba(88, 166, 255, 0.08);
  color: var(--accent);
}}
.sidebar a.active {{
  background: rgba(88, 166, 255, 0.12);
  color: var(--accent);
  font-weight: 600;
}}
.sidebar a.toc-h3 {{
  padding-left: 28px;
  font-size: 12px;
  color: var(--fg-dim);
}}
.sidebar a.toc-h3:hover {{
  color: var(--accent);
}}

/* ── Main content ──────────────────────────────────────────────── */
.content {{
  margin-left: var(--sidebar-w);
  margin-top: 52px;
  padding: 36px 48px 80px;
  max-width: 900px;
}}

/* ── Typography ────────────────────────────────────────────────── */
h1 {{
  font-size: 32px;
  font-weight: 700;
  color: var(--fg-heading);
  margin-bottom: 8px;
  padding-bottom: 10px;
  border-bottom: 2px solid var(--accent-dim);
}}
h2 {{
  font-size: 22px;
  font-weight: 600;
  color: var(--accent);
  margin-top: 48px;
  margin-bottom: 14px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}}
h3 {{
  font-size: 17px;
  font-weight: 600;
  color: var(--purple);
  margin-top: 32px;
  margin-bottom: 10px;
}}
h4 {{
  font-size: 15px;
  font-weight: 600;
  color: var(--yellow);
  margin-top: 24px;
  margin-bottom: 8px;
}}

p {{ margin-bottom: 14px; }}

a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

strong {{ color: var(--fg-heading); }}

/* ── Lists ─────────────────────────────────────────────────────── */
ul, ol {{
  margin: 0 0 16px 24px;
}}
li {{
  margin-bottom: 4px;
}}
li > ul, li > ol {{
  margin-top: 4px;
  margin-bottom: 4px;
}}

/* ── Code ──────────────────────────────────────────────────────── */
code {{
  font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", Consolas, monospace;
  font-size: 13px;
  background: var(--bg-code);
  color: var(--green);
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid var(--border);
}}

pre {{
  background: var(--bg-code);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 20px;
  overflow-x: auto;
  margin: 16px 0;
  line-height: 1.5;
}}
pre code {{
  background: none;
  border: none;
  padding: 0;
  color: var(--fg);
  font-size: 13px;
}}

/* ── Tables ────────────────────────────────────────────────────── */
table {{
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0;
  font-size: 14px;
}}
thead {{
  background: var(--bg-card);
}}
th {{
  text-align: left;
  padding: 10px 14px;
  font-weight: 600;
  color: var(--accent);
  border-bottom: 2px solid var(--border);
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}}
td {{
  padding: 9px 14px;
  border-bottom: 1px solid var(--border);
}}
tr:hover {{
  background: rgba(88, 166, 255, 0.04);
}}

/* ── Blockquote ────────────────────────────────────────────────── */
blockquote {{
  border-left: 3px solid var(--accent-dim);
  margin: 16px 0;
  padding: 12px 20px;
  background: var(--bg-card);
  border-radius: 0 8px 8px 0;
  color: var(--fg-dim);
}}

/* ── Horizontal rule ───────────────────────────────────────────── */
hr {{
  border: none;
  border-top: 1px solid var(--border);
  margin: 32px 0;
}}

/* ── Responsive ────────────────────────────────────────────────── */
@media (max-width: 800px) {{
  .sidebar {{ display: none; }}
  .content {{ margin-left: 0; padding: 24px 20px 60px; }}
}}
</style>
</head>
<body>

<div class="topbar">
  <div class="logo">LYNX <span>Portfolio Documentation</span></div>
</div>

<nav class="sidebar">
  <div class="nav-section">
    <div class="nav-section-title">Documentation</div>
    {nav_links}
  </div>
  <div class="nav-section">
    <div class="nav-section-title">On this page</div>
    {toc_links}
  </div>
</nav>

<main class="content">
{body}
</main>

<script>
// Highlight active sidebar link on scroll
(function() {{
  const headings = document.querySelectorAll('h2[id], h3[id]');
  const tocLinks = document.querySelectorAll('.sidebar a[href^="#"]');
  if (!headings.length || !tocLinks.length) return;

  function update() {{
    let current = '';
    for (const h of headings) {{
      if (h.getBoundingClientRect().top <= 100) current = h.id;
    }}
    tocLinks.forEach(a => {{
      a.classList.toggle('active', a.getAttribute('href') === '#' + current);
    }});
  }}
  window.addEventListener('scroll', update, {{ passive: true }});
  update();
}})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_page(md_file: str, nav_title: str, all_pages) -> str:
    """Convert a Markdown file to styled HTML."""
    with open(os.path.join(DOCS_DIR, md_file)) as f:
        md_src = f.read()

    html_body = markdown.markdown(
        md_src,
        extensions=["tables", "fenced_code", "toc", "attr_list"],
        extension_configs={"toc": {"permalink": False}},
    )

    headings = _extract_headings(html_body)
    html_body = _inject_heading_ids(html_body, headings)

    # Build nav links (cross-page)
    nav_parts = []
    for fname, title in all_pages:
        html_name = fname.replace(".md", ".html")
        cls = ' class="active"' if fname == md_file else ""
        nav_parts.append(f'    <a href="{html_name}"{cls}>{title}</a>')
    nav_links = "\n".join(nav_parts)

    # Build TOC links (this page)
    toc_parts = []
    for level, slug, text in headings:
        cls = "toc-h3" if level == 3 else ""
        toc_parts.append(f'    <a href="#{slug}" class="{cls}">{text}</a>')
    toc_links = "\n".join(toc_parts)

    return TEMPLATE.format(
        title=nav_title,
        nav_links=nav_links,
        toc_links=toc_links,
        body=html_body,
    )


def main():
    for md_file, nav_title in PAGES:
        md_path = os.path.join(DOCS_DIR, md_file)
        if not os.path.isfile(md_path):
            print(f"  skip {md_file} (not found)")
            continue
        html = build_page(md_file, nav_title, PAGES)
        out_path = os.path.join(DOCS_DIR, md_file.replace(".md", ".html"))
        with open(out_path, "w") as f:
            f.write(html)
        print(f"  built {out_path}")
    print("Done.")


if __name__ == "__main__":
    main()
