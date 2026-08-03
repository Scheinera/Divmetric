"""Divmetric collector stub — official/API first, then consolidated export.

Do not scrape vendor UIs aggressively. Prefer BCB + market APIs, then
authorized exports from consolidated dividend sources (e.g. Status Invest).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"


def write_json(name: str, payload: dict) -> Path:
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_meta() -> Path:
    return write_json(
        "meta.json",
        {
            "product": "Divmetric",
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "disclaimer": "Conteúdo educacional. Não é recomendação de investimento.",
            "layers": {
                "official": "BCB SGS",
                "market": "BRAPI/Yahoo/B3 provider",
                "dividends": "consolidated copy (Status Invest or authorized feed)",
                "editorial": "Suno / InfoMoney (links only)",
            },
        },
    )


def main() -> None:
    path = export_meta()
    print(f"exported {path}")


if __name__ == "__main__":
    main()
