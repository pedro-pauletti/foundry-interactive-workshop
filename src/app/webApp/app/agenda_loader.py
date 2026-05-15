"""Parse `agenda.md` into an ordered list of AgendaItem objects.

The web app's left-nav menu and the auto-discovered section sub-apps are
both derived from this file at runtime. Editing `agenda.md` (and restarting
or hot-reloading the app) is enough to update the menu — never hard-code
agenda items elsewhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Bullet format expected:  - <Title>: <Description>
# Greedy title, colonless description — supports titles that themselves contain ':'.
_BULLET_RE = re.compile(r"^\s*[-*]\s*(?P<title>.+):\s+(?P<desc>[^:]+?)\s*$")


@dataclass(frozen=True)
class AgendaItem:
    title: str
    description: str
    slug: str


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return s or "section"


def normalize_for_match(text: str) -> str:
    """Lowercase + strip non-alphanumerics for fuzzy title matching."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _find_agenda_file() -> Optional[Path]:
    """Locate agenda.md.

    1. Same folder as this module (Docker image: copied next to app.py).
    2. Walk up the parent chain (local dev: project root).
    """
    here = Path(__file__).resolve().parent
    candidates = [here / "agenda.md"]
    for parent in here.parents:
        candidates.append(parent / "agenda.md")
    for p in candidates:
        if p.exists():
            return p
    return None


def load_agenda(path: Optional[Path] = None) -> List[AgendaItem]:
    """Parse the bullet list under the SKILL data heading."""
    if path is None:
        path = _find_agenda_file()
    if path is None or not path.exists():
        return []

    items: List[AgendaItem] = []
    in_block = False

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        # Activate parsing when we hit the data heading
        if stripped.startswith("###") and "Workshop App" in stripped:
            in_block = True
            continue
        # Deactivate on the next heading of equal or higher level
        if in_block and stripped.startswith("#"):
            break
        if not in_block:
            continue

        m = _BULLET_RE.match(line)
        if not m:
            continue

        title = m.group("title").strip()
        desc = m.group("desc").strip()
        items.append(AgendaItem(title=title, description=desc, slug=_slugify(title)))

    return items
