"""Utilidades de análisis estático para el conversor.

Incluye validación/sintaxis de Molang y helpers de clasificación basados
en análisis estructural de contenido.
"""

from .molang import analyze_molang, is_valid_molang, sanitize_molang

__all__ = ["analyze_molang", "is_valid_molang", "sanitize_molang"]
