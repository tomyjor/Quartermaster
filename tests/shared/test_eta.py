"""Tests para shared/eta.py -- cálculo de tiempo estimado restante."""

from datetime import datetime, timezone, timedelta

from shared.eta import estimate_seconds_remaining, format_eta


def test_estimates_reasonable_eta_from_observed_rate():
    """Caso real reportado: 893/19164 procesados tras 5 minutos."""
    started = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    eta = estimate_seconds_remaining(total=19164, done=893, started_at=started)

    assert eta is not None
    # Ritmo observado: 893 en 300s = ~2.977/s. Restan 18271 -> ~6138s (~1.7h).
    assert 6000 < eta < 6300


def test_returns_none_without_enough_evidence():
    started = datetime.now(timezone.utc).isoformat()
    assert estimate_seconds_remaining(None, 100, started) is None
    assert estimate_seconds_remaining(100, None, started) is None
    assert estimate_seconds_remaining(100, 50, None) is None


def test_returns_none_when_already_done_or_not_started():
    started = datetime.now(timezone.utc).isoformat()
    assert estimate_seconds_remaining(100, 100, started) is None, "done >= total no debería estimar"
    assert estimate_seconds_remaining(100, 150, started) is None, "done > total (dato inconsistente)"
    assert estimate_seconds_remaining(100, 0, started) is None, "sin progreso, ritmo indefinido"


def test_returns_none_for_malformed_timestamp():
    assert estimate_seconds_remaining(100, 50, "no-es-una-fecha") is None


def test_format_eta_seconds_minutes_hours():
    assert format_eta(30) == "~30s"
    assert format_eta(150) == "~2 min"
    assert format_eta(5400) == "~1.5h"
    assert format_eta(None) is None
