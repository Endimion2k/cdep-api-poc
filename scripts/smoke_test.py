"""Smoke test — validează că mediul local funcționează end-to-end.

Rulează-l ca prim pas după `pip install -r requirements-dev.txt`:

    python scripts/smoke_test.py

Ce verifică:
1. Import-urile funcționează (pydantic, requests, parsel).
2. Conectivitatea HTTP către cdep.ro (+ throttling/User-Agent din _http.py).
3. Parsarea HTML cu parsel (titlul paginii principale).
4. Serializarea Pydantic (Meta + round-trip JSON).

Dacă toate PASS → environment-ul e gata, putem trece la Ziua 2 (sitemap cdep.ro).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Permite rulare din orice director — adaugă root-ul proiectului la sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "✓" if ok else "✗"
    color_start = "\033[32m" if ok else "\033[31m"
    color_end = "\033[0m"
    suffix = f" — {detail}" if detail else ""
    print(f"  {color_start}{mark}{color_end} {label}{suffix}")
    return ok


def test_imports() -> bool:
    print("[1/4] Import-uri")
    try:
        import parsel  # noqa: F401
        import pydantic  # noqa: F401
        import requests  # noqa: F401

        return check("pydantic, requests, parsel se importă", True)
    except ImportError as e:
        return check("import dependințe", False, str(e))


def test_http() -> bool:
    print("[2/4] HTTP către cdep.ro (cu throttling)")
    try:
        from scrapers._http import get

        response = get("https://www.cdep.ro/")
        ok_status = response.status_code == 200
        check(
            f"GET https://www.cdep.ro/ → {response.status_code}",
            ok_status,
            f"{len(response.content)} bytes",
        )
        return ok_status
    except Exception as e:
        return check("cerere HTTP", False, f"{type(e).__name__}: {e}")


def test_parsing() -> bool:
    print("[3/4] Parsare HTML (parsel)")
    try:
        from parsel import Selector

        from scrapers._http import get

        response = get("https://www.cdep.ro/")
        sel = Selector(text=response.text)
        title = sel.css("title::text").get()
        ok = title is not None and len(title.strip()) > 0
        return check(
            "extrag <title> din pagina principală",
            ok,
            f"title={title!r}" if title else "title gol",
        )
    except Exception as e:
        return check("parsing HTML", False, f"{type(e).__name__}: {e}")


def test_pydantic() -> bool:
    print("[4/4] Pydantic round-trip")
    try:
        from schemas.common import Meta

        meta = Meta(
            generated_at=datetime.now(timezone.utc),
            source_url="https://www.cdep.ro/",
            scraper_version="0.1.0",
            count=0,
        )
        serialized = meta.model_dump_json()
        restored = Meta.model_validate_json(serialized)
        ok = restored.source_url == meta.source_url
        parsed = json.loads(serialized)
        return check(
            "Meta → JSON → Meta",
            ok,
            f"keys={list(parsed.keys())}",
        )
    except Exception as e:
        return check("pydantic", False, f"{type(e).__name__}: {e}")


def main() -> int:
    print("=" * 60)
    print("CDEP API — Smoke Test")
    print("=" * 60)

    results = [
        test_imports(),
        test_http(),
        test_parsing(),
        test_pydantic(),
    ]

    print("=" * 60)
    passed = sum(results)
    total = len(results)
    if passed == total:
        print(f"\033[32m✓ All {total} checks passed — environment gata.\033[0m")
        return 0
    else:
        print(f"\033[31m✗ {total - passed} / {total} checks failed.\033[0m")
        return 1


if __name__ == "__main__":
    sys.exit(main())
