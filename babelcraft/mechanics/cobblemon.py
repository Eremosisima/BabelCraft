"""Conversor de mecánicas específicas de Cobblemon (scaffold)."""

from __future__ import annotations

from ..model import SourceMod
from .base import MechanicsContext, register


class CobblemonMechanicsConverter:
    id = "cobblemon"
    name = "Cobblemon Mechanics"

    def matches(self, mod: SourceMod) -> bool:
        ns = (getattr(mod, "namespace", "") or "").lower()
        name = (getattr(mod, "name", "") or "").lower()
        modid = (getattr(mod, "modid", "") or "").lower()
        haystack = " ".join([ns, name, modid])
        if "cobblemon" in haystack:
            return True
        # Heurística por assets conocidos
        try:
            for p in mod.source.glob("assets/cobblemon/"):
                if p:
                    return True
        except Exception:
            pass
        return False

    def convert(self, ctx: MechanicsContext) -> None:
        """Punto de extensión para mecánicas Cobblemon.

        Estado actual: scaffold. Próximos pasos:
        - Convertir ítems especiales (pokeballs/berries/healing) con componentes más ricos.
        - Mapear stats/species/spawn data declarativa a componentes/propiedades.
        - Generar plantillas para captura/batalla/PC como placeholders explícitos.
        - Integrar worldgen/estructuras/árboles cuando haya conversores compatibles.
        """
        ctx.note("Cobblemon detectado: aplicando conversor de mecánicas (scaffold, sin lógica de batalla/captura aún).")
        # Placeholder: integración futura con helpers reutilizables.
        # Ej.: self._convert_items(ctx)
        return


# Registro automático al importar.
register(CobblemonMechanicsConverter())
