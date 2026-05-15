"""Build a static snapshot of the webApp for GitHub Pages.

Usage:
    python infra/scripts/build_static_site.py [--out dist] [--base-url /repo-name]

What it does:
  1. Sets ``DISABLE_REAL_MODE=1`` and ``DEMO_MODE_DEFAULT=mock`` so the public
     build can never hit Azure.
  2. Imports the FastAPI app from ``src/app/webApp/app/app.py`` and uses
     ``TestClient`` to render ``/``, ``/sections/<slug>`` and the static API
     stubs (``/api/demo-mode``, ``/api/industry``, ``/api/language``).
  3. Copies the ``static/`` tree into ``dist/static/``.
  4. Rewrites absolute paths (``href="/...``, ``src="/...``, ``action="/...``,
     ``fetch("/...``) so the site works when served from a subpath
     (e.g. ``username.github.io/repo-name``).
  5. Emits ``.nojekyll`` and a ``404.html`` (clone of index) so unknown routes
     still show the demo entry point.

Interactive widgets that POST to per-section APIs will not work on the static
build — that is by design. The static deployment is for browsing the demo
content only. Real interactions require running the project locally.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WEBAPP_APP_DIR = REPO_ROOT / "src" / "app" / "webApp" / "app"


def _prepare_env() -> None:
    os.environ["DISABLE_REAL_MODE"] = "1"
    os.environ["DEMO_MODE_DEFAULT"] = "mock"
    os.environ.setdefault("LANG_DEFAULT", "pt")
    # Avoid touching Azure on import:
    os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "")
    os.environ.setdefault("AZURE_SEARCH_ENDPOINT", "")
    sys.path.insert(0, str(WEBAPP_APP_DIR))


def _load_client():
    from fastapi.testclient import TestClient  # type: ignore
    import app as webapp_module  # type: ignore

    return TestClient(webapp_module.app), webapp_module


def _rewrite_html(html: str, base_url: str) -> str:
    if not base_url:
        return html
    base = base_url.rstrip("/")
    # href="/...", src="/...", action="/..."  (but skip "//" protocol-relative)
    html = re.sub(r'(href|src|action)="/(?!/)', rf'\1="{base}/', html)
    # Inline JS fetch("/...") and fetch('/...')
    html = re.sub(r"""fetch\((["'])/(?!/)""", rf"fetch(\1{base}/", html)
    return html


def _rewrite_js(js: str, base_url: str) -> str:
    if not base_url:
        return js
    base = base_url.rstrip("/")
    js = re.sub(r"""fetch\((["'])/(?!/)""", rf"fetch(\1{base}/", js)
    # window.location.href = "/sections/..."
    js = re.sub(r"""(location(?:\.href)?\s*=\s*["'])/(?!/)""", rf"\1{base}/", js)
    return js


def _write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dist", help="output directory")
    parser.add_argument(
        "--base-url",
        default=os.getenv("PAGES_BASE_URL", ""),
        help='URL prefix when served from a subpath (e.g. "/repo-name")',
    )
    args = parser.parse_args()

    out_dir = (REPO_ROOT / args.out).resolve()
    base_url = args.base_url.rstrip("/")

    print(f"[build] output: {out_dir}")
    print(f"[build] base-url: {base_url or '(root)'}")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    _prepare_env()
    client, webapp_module = _load_client()

    # 1. Copy static/ tree, rewriting JS.
    src_static = WEBAPP_APP_DIR / "static"
    dst_static = out_dir / "static"
    for src_path in src_static.rglob("*"):
        if src_path.is_dir():
            continue
        rel = src_path.relative_to(src_static)
        dst = dst_static / rel
        if src_path.suffix.lower() == ".js":
            _write(dst, _rewrite_js(src_path.read_text(encoding="utf-8"), base_url))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst)
    print(f"[build] copied static assets ({sum(1 for _ in src_static.rglob('*') if _.is_file())} files)")

    # 2. Render HTML routes.
    routes: list[tuple[str, Path]] = [("/", out_dir / "index.html")]
    for slug, _router, _title, _icon in webapp_module.SECTIONS:
        routes.append((f"/sections/{slug}", out_dir / "sections" / slug / "index.html"))

    rendered = 0
    for url, dst in routes:
        resp = client.get(url, follow_redirects=True)
        if resp.status_code != 200:
            print(f"[build] WARN {url} -> HTTP {resp.status_code}", file=sys.stderr)
            continue
        html = _rewrite_html(resp.text, base_url)
        _write(dst, html)
        rendered += 1
    print(f"[build] rendered {rendered} HTML pages")

    # 3. Static API stubs (so the JS gets coherent responses instead of 404s).
    api_stubs = {
        "api/demo-mode": {"mode": "mock", "default": "mock", "real_disabled": True},
        "api/industry": client.get("/api/industry").json(),
        "api/language": client.get("/api/language").json(),
        # Per-section API stubs — kept up to date when the section ships an
        # internal listing endpoint that the JS calls on page load.
        "sections/ato1_hosted_agents/api/agents":
            client.get("/sections/ato1_hosted_agents/api/agents").json(),
    }
    for rel, payload in api_stubs.items():
        # Write as a plain file (no extension) so the existing JS calls to
        # ``/api/demo-mode`` etc. get a coherent response. ``fetch().json()``
        # parses regardless of Content-Type.
        _write(out_dir / rel, json.dumps(payload, ensure_ascii=False, indent=2))

    # 4. Pages housekeeping.
    _write(out_dir / ".nojekyll", "")
    # 404 falls back to the home page so SPA-ish navigation still lands somewhere.
    shutil.copy2(out_dir / "index.html", out_dir / "404.html")

    print(f"[build] done -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
