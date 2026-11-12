"""Módulos de mecánicas específicas por mod.

Extiende BabelCraft con conversores especializados (p.ej. Cobblemon)
sin mezclar lógica específica en el pipeline base.
"""

from .base import MechanicsConverter, MechanicsContext, detect_mechanics
from .cobblemon import CobblemonMechanicsConverter

__all__ = [
    "MechanicsConverter",
    "MechanicsContext",
    "detect_mechanics",
    "CobblemonMechanicsConverter",
]
