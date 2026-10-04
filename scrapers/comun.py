# -*- coding: utf-8 -*-
"""Guardado de crudos y de errores, igual para todos los scrapers.

Cada pasada deja en data/raw/ un JSON con lo descargado
(<prefijo>_<AAAAMMDDTHHMMSSZ>.json) o, si la fuente falla, uno de error
(..._error.json) que clasificar.py ignora: sin crudo nuevo, reutiliza lo
último bueno de esa fuente.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def _ruta(prefijo: str, ahora: datetime, sufijo: str = "") -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DIR / f"{prefijo}_{ahora.strftime('%Y%m%dT%H%M%SZ')}{sufijo}.json"


def guardar_crudo(fuente: str, prefijo: str, items: list[dict]) -> Path:
    ahora = datetime.now(timezone.utc)
    ruta = _ruta(prefijo, ahora)
    payload = {"fuente": fuente, "timestamp": ahora.isoformat(), "num_resultados": len(items), "resultados": items}
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def guardar_error(fuente: str, prefijo: str, exc: Exception) -> Path:
    ahora = datetime.now(timezone.utc)
    ruta = _ruta(prefijo, ahora, "_error")
    ruta.write_text(json.dumps({"fuente": fuente, "timestamp": ahora.isoformat(), "error": str(exc)},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta
