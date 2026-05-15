"""Validate parity across content/<lang>/ folders.

Exits 0 when:
  * Every workshop.yaml dotted-key in PT exists in EN and ES.
  * Every agenda item ``id`` in PT exists in EN and ES.

Exits 1 with a human-readable diff otherwise.

Usage:
    python scripts/validate_i18n.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print("FATAL: pyyaml is required. `pip install pyyaml`", file=sys.stderr)
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT = REPO_ROOT / "content"
LANGS = ("pt", "en", "es")
FALLBACK = "pt"


def _flat_keys(d: Any, prefix: str = "") -> Iterable[str]:
    if isinstance(d, dict):
        for k, v in d.items():
            new_prefix = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                yield from _flat_keys(v, new_prefix)
            else:
                yield new_prefix


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"FATAL: {path} top-level must be a mapping")
    return data


def _check_workshop() -> List[str]:
    errors: List[str] = []
    base = _read_yaml(CONTENT / FALLBACK / "workshop.yaml")
    base_keys = set(_flat_keys(base))
    for lang in LANGS:
        if lang == FALLBACK:
            continue
        loc = _read_yaml(CONTENT / lang / "workshop.yaml")
        loc_keys = set(_flat_keys(loc))
        missing = base_keys - loc_keys
        if missing:
            errors.append(
                f"workshop.yaml [{lang}] missing {len(missing)} key(s): "
                + ", ".join(sorted(missing)[:10])
                + ("…" if len(missing) > 10 else "")
            )
    return errors


def _check_agenda() -> List[str]:
    errors: List[str] = []
    base = _read_yaml(CONTENT / FALLBACK / "agenda.yaml")
    base_ids = [item.get("id") for item in (base.get("items") or []) if item.get("id")]
    base_set = set(base_ids)
    for lang in LANGS:
        if lang == FALLBACK:
            continue
        loc = _read_yaml(CONTENT / lang / "agenda.yaml")
        loc_ids = {item.get("id") for item in (loc.get("items") or []) if item.get("id")}
        missing = base_set - loc_ids
        if missing:
            errors.append(
                f"agenda.yaml [{lang}] missing {len(missing)} id(s): " + ", ".join(sorted(missing))
            )
        extra = loc_ids - base_set
        if extra:
            errors.append(
                f"agenda.yaml [{lang}] has {len(extra)} id(s) not in PT: " + ", ".join(sorted(extra))
            )
    return errors


def main() -> int:
    if not CONTENT.is_dir():
        print(f"FATAL: {CONTENT} not found", file=sys.stderr)
        return 2
    errors = _check_workshop() + _check_agenda()
    if errors:
        print("i18n parity check FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"i18n parity OK ({', '.join(LANGS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
