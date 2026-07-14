"""
Shared: eta

Cálculo de tiempo estimado restante para trabajos en progreso (hoy: el
Smart Auto-Seed), a partir de cuánto se lleva hecho y cuánto tiempo pasó.

Nace de un problema real reportado: durante una corrida larga, el
usuario veía "Sync en curso" sin ninguna noción de cuánto faltaba, y
llegó a pensar que estaba roto (no traía datos) cuando en realidad
solo era lento -- después de esperar, empezó a llenarse normalmente.
Un ETA visible resuelve la ambigüedad "¿está colgado o solo tarda?"
sin que el usuario tenga que adivinar.

Función pura, sin dependencias de framework -- se puede testear sin
FastAPI/Streamlit/NiceGUI instalados, y la usa el lado de la API para
que TODAS las UIs (Streamlit, NiceGUI, futuras) muestren el mismo
cálculo sin duplicarlo cada una.
"""

from datetime import datetime, timezone
from typing import Optional


def estimate_seconds_remaining(
    total: Optional[int], done: Optional[int], started_at: Optional[str],
    now: Optional[datetime] = None,
) -> Optional[float]:
    """
    Estima segundos restantes extrapolando el ritmo observado hasta
    ahora (done / tiempo transcurrido) hacia lo que falta (total - done).

    Devuelve None cuando no hay suficiente evidencia para estimar algo
    razonable -- nunca inventa un número (mismo principio que el resto
    del proyecto: sin evidencia, sin dato, no un placeholder disfrazado
    de estimación real):
    - Sin `total`/`done`/`started_at` -- no hay con qué calcular.
    - `done <= 0` -- ritmo indefinido (recién arrancó, 0 progreso).
    - `done >= total` -- ya terminó, no hay "resto".
    - Timestamp de arranque en el futuro o mal formado -- dato inconsistente.
    """
    if total is None or done is None or started_at is None:
        return None
    if done <= 0 or total <= 0 or done >= total:
        return None

    try:
        start = datetime.fromisoformat(started_at)
    except ValueError:
        return None

    reference_now = now or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=timezone.utc)

    elapsed_seconds = (reference_now - start).total_seconds()
    if elapsed_seconds <= 0:
        return None

    rate_per_second = done / elapsed_seconds
    if rate_per_second <= 0:
        return None

    remaining = total - done
    return remaining / rate_per_second


def format_duration_hours(hours: Optional[float]) -> Optional[str]:
    """
    Texto legible en español para una duración expresada en horas --
    hoy usado para el tiempo estimado de venta (`ExitTimeEngine`), que
    se calculaba pero se descartaba después de convertirse en score,
    sin llegar nunca como número crudo a la UI.
    """
    if hours is None:
        return None
    if hours < 1:
        return f"~{int(round(hours * 60))} min"
    if hours < 24:
        return f"~{hours:.1f}h"
    days = hours / 24
    return f"~{days:.1f} días"


def format_eta(seconds: Optional[float]) -> Optional[str]:
    """
    Texto legible en español para mostrar en UI. None si `seconds` es
    None (el caller decide qué mostrar en ese caso -- típicamente nada,
    nunca "calculando..." indefinido).
    """
    if seconds is None:
        return None
    if seconds < 60:
        return f"~{int(seconds)}s"
    if seconds < 3600:
        return f"~{int(round(seconds / 60))} min"
    hours = seconds / 3600
    return f"~{hours:.1f}h"
