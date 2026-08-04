"""COPOM — decisões históricas (Selic BCB) + calendário publicado."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
CALENDAR = ROOT / "config" / "copom_calendar.yaml"


def _load_upcoming() -> list[dict[str, Any]]:
    if not CALENDAR.exists() or yaml is None:
        return []
    raw = yaml.safe_load(CALENDAR.read_text(encoding="utf-8")) or {}
    return list(raw.get("upcoming_meetings") or [])


def decisions_from_selic_series(points: list[dict[str, Any]], start_date: str = "2015-01-01") -> list[dict[str, Any]]:
    """Quando a meta Selic muda, marcar como decisão COPOM (aproximação oficial via SGS 432)."""
    rows = [p for p in points if p.get("date") and p["date"] >= start_date]
    if not rows:
        return []
    out = []
    prev = None
    for p in rows:
        val = float(p["value"])
        if prev is None:
            prev = val
            continue
        if abs(val - prev) >= 0.01:
            delta = round(val - prev, 2)
            out.append(
                {
                    "date": p["date"],
                    "selic_pct": val,
                    "change_pp": delta,
                    "action": "hike" if delta > 0 else "cut" if delta < 0 else "hold",
                    "source": "BCB SGS 432 (mudança de meta)",
                }
            )
            prev = val
    return out[-40:]


def build_copom_bundle(
    selic_points: list[dict[str, Any]] | None,
    selic_latest: float | None,
    start_date: str = "2015-01-01",
) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date().isoformat()
    upcoming = []
    for m in _load_upcoming():
        end = m.get("decision_date") or (m.get("dates") or [None])[-1]
        if not end:
            continue
        status = "upcoming" if end >= today else "past"
        upcoming.append({**m, "status": status})

    decisions = decisions_from_selic_series(selic_points or [], start_date=start_date)
    next_meeting = next((m for m in upcoming if m.get("status") == "upcoming"), None)

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "as_of": today,
        "analysis_start": start_date,
        "selic_latest_pct": selic_latest,
        "next_meeting": next_meeting,
        "upcoming_meetings": [m for m in upcoming if m.get("status") == "upcoming"],
        "recent_decisions": list(reversed(decisions[-12:])),
        "decisions_since_start": decisions,
        "notes": [
            "Calendário futuro: comunicado BCB (embed em config/copom_calendar.yaml).",
            "Histórico de decisões: mudanças da Selic meta (SGS 432).",
            "Ata: tipicamente terça seguinte à decisão, 8h (Brasília).",
        ],
        "source": "BCB (calendário publicado + SGS 432)",
        "status": "live",
    }
