# -*- coding: utf-8 -*-
"""Pruebas de regresión del radar. Se ejecutan sin red: las fuentes se
sustituyen por muestras reales guardadas en tests/fixtures/ (anonimizadas:
sin teléfonos, correos ni nombres de personas).

Desde licitaciones_marketing/:
    python -m pytest
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Los scrapers se importan como módulos sueltos (igual que los ejecuta el
# workflow), no como paquete.
for ruta in (RAIZ, RAIZ / "scrapers"):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))
