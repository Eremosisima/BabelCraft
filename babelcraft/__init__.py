"""BabelCraft — conversor de mods de Minecraft Java a addons de Bedrock.

La API pública es una sola función, :func:`convert`, y devuelve un objeto
:class:`Conversion` con el addon, el informe y el libro de cuentas::

    import babelcraft

    conv = babelcraft.convert("MiMod.jar", "salida")
    print(conv.addon_path, conv.report_path)
    if conv.errors:
        ...

Principio de diseño: **nunca fingir**. Cada fichero de entrada acaba como
`converted` (fiel), `adapted` (con pérdidas documentadas) o `residue` (sin
equivalente, con la razón y qué hacer a mano). El validador estructural
comprueba la salida contra las reglas que Bedrock exige de verdad.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import ConversionResult, Overrides, SourceMod
from .pack import AddonWriter

__version__ = "0.1.0"

__all__ = ["Conversion", "convert", "__version__"]


@dataclass
class Conversion:
    """Resultado completo de una conversión."""

    mod: SourceMod
    writer: AddonWriter
    result: ConversionResult
    addon_path: str = ""
    report_path: str = ""

    @property
    def errors(self) -> list:
        return [f for f in self.result.findings if f.severity == "error"]

    @property
    def warnings(self) -> list:
        return [f for f in self.result.findings if f.severity == "warn"]

    def summary(self) -> dict:
        """Cifras listas para imprimir o registrar."""
        coverage = self.result.coverage()
        counts = {
            status: sum(row[status] for row in coverage.values())
            for status in ("converted", "adapted", "residue", "total")
        }
        return {
            "namespace": self.mod.namespace,
            "name": self.mod.name,
            "loader": self.mod.loader,
            "java_version": self.mod.java_version,
            "bp_files": len(self.writer.bp),
            "rp_files": len(self.writer.rp),
            "addon": self.addon_path,
            "report": self.report_path,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            **counts,
        }


def convert(
    source,
    out_dir: str,
    *,
    variant: str = "",
    atlas: bool | None = None,
    atlas_cell: int = 0,
    max_texture: int = 0,
    placeholders: bool = False,
    thin: bool = True,
    prune_bones: bool = True,
    overrides=None,
    lang_out: str = "en_US",
    despawn_distance: int = 0,
    minify: bool = True,
    report: str | None = None,
) -> Conversion:
    """Convierte un mod/datapack de Java en un `.mcaddon` de Bedrock.

    `source` puede ser una carpeta, un `.jar` o un `.zip`; también acepta un
    :class:`~babelcraft.source.Source` ya abierto. `overrides` es una ruta a
    un JSON o un :class:`~babelcraft.model.Overrides`.
    """
    from .converters import Options, run
    from .report import write_report
    from .source import load_mod
    from .validate import validate

    mod = load_mod(source)
    ov = overrides if isinstance(overrides, Overrides) else (
        Overrides.load(str(overrides)) if overrides else Overrides()
    )
    opts = Options(
        max_texture=max_texture,
        atlas=bool(atlas),
        atlas_cell=atlas_cell,
        variant=variant or "",
        minify=minify,
        placeholders=placeholders,
        thin=thin,
        prune_bones=prune_bones,
        despawn_distance=despawn_distance,
        lang_out=lang_out,
    )

    writer, result = run(mod, out_dir, opts, ov)
    validate(writer, result)
    report_path = write_report(
        mod, writer, result, getattr(writer, "addon_path", ""), out_dir, path=report
    )
    return Conversion(
        mod=mod,
        writer=writer,
        result=result,
        addon_path=getattr(writer, "addon_path", ""),
        report_path=report_path,
    )
