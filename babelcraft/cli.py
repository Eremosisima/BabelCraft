"""Interfaz de línea de comandos de BabelCraft.

Uso::

    babelcraft convert MiMod.jar -o salida
    babelcraft convert MiMod.jar -o salida --variant mobile --placeholders
    python -m babelcraft convert MiMod.jar -o salida

Códigos de salida:
  0  addon generado sin errores del validador (puede haber avisos)
  1  errores del validador, fuente inválida o fallo inesperado
  2  uso incorrecto de la línea de comandos (lo gestiona argparse)
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__, convert


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="babelcraft",
        description="Convierte mods de Minecraft Java Edition a addons de Bedrock (.mcaddon).",
    )
    parser.add_argument("--version", action="version", version=f"BabelCraft {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("convert", help="convertir un mod, datapack o resourcepack")
    p.add_argument("source", help="carpeta, .jar o .zip del mod de Java")
    p.add_argument(
        "-o", "--out", default="babelcraft_out",
        help="carpeta de salida (por defecto: babelcraft_out)",
    )
    p.add_argument(
        "--variant", choices=("", "mobile", "desktop"), default="",
        help="perfil de rendimiento: mobile activa atlas y despawn agresivo; "
             "desktop activa atlas con celdas mayores",
    )
    p.add_argument(
        "--max-texture", type=int, default=0, metavar="PX",
        help="reducir toda textura para que su lado mayor no pase de PX (0 = no reducir)",
    )
    p.add_argument(
        "--atlas", dest="atlas", action="store_true", default=None,
        help="unir las texturas de entidades en un atlas (1 texture handle)",
    )
    p.add_argument(
        "--no-atlas", dest="atlas", action="store_false",
        help="no usar atlas de entidades",
    )
    p.add_argument(
        "--atlas-cell", type=int, default=0, metavar="PX",
        help="lado de cada celda del atlas en píxeles (0 = automático)",
    )
    p.add_argument(
        "--placeholders", action="store_true",
        help="generar iconos/texturas placeholder cuando falte arte "
             "(por defecto esos ítems/entidades quedan como residuo)",
    )
    p.add_argument(
        "--no-thin", dest="thin", action="store_false", default=True,
        help="no adelgazar animaciones",
    )
    p.add_argument(
        "--no-prune", dest="prune_bones", action="store_false", default=True,
        help="no podar huesos vacíos de las geometrías",
    )
    p.add_argument(
        "--no-minify", dest="minify", action="store_false", default=True,
        help="escribir los JSON con indentación (más pesados en RAM al cargar)",
    )
    p.add_argument(
        "--overrides", metavar="JSON",
        help="JSON con valores que el bytecode no puede dar (comida, dureza, vida...)",
    )
    p.add_argument(
        "--lang", dest="lang_out", default="en_US", metavar="IDIOMA",
        help="idioma principal de salida (por defecto en_US)",
    )
    p.add_argument(
        "--report", metavar="RUTA",
        help="ruta del informe Markdown (por defecto <salida>/REPORT.md)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "convert":
        parser.print_help()
        return 2

    try:
        conv = convert(
            args.source,
            args.out,
            variant=args.variant,
            atlas=args.atlas,
            atlas_cell=args.atlas_cell,
            max_texture=args.max_texture,
            placeholders=args.placeholders,
            thin=args.thin,
            prune_bones=args.prune_bones,
            overrides=args.overrides,
            lang_out=args.lang_out,
            minify=args.minify,
            report=args.report,
        )
    except (ValueError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - la CLI nunca debe escupir un traceback
        print(f"error inesperado: {exc!r}", file=sys.stderr)
        return 1

    _print_summary(conv)
    return 1 if conv.errors else 0


def _print_summary(conv) -> None:
    s = conv.summary()
    java = ""
    if s["java_version"]:
        java = f" · Java {s['java_version'] - 44} (major {s['java_version']})"
    print("")
    print(f"BabelCraft {__version__}")
    print(f"  Mod:      {s['name']} ({s['namespace']})")
    print(f"  Loader:   {s['loader']}{java}")
    print(f"  Salida:   BP {s['bp_files']} ficheros · RP {s['rp_files']} ficheros")
    print(
        f"  Contenido: {s['converted']} convertidos · "
        f"{s['adapted']} adaptados · {s['residue']} residuos"
    )
    if s["addon"]:
        print(f"  Addon:    {s['addon']}")
    if s["report"]:
        print(f"  Informe:  {s['report']}")
    print(f"  Validador: {s['errors']} error(es) · {s['warnings']} aviso(s)")

    errors = conv.errors
    if errors:
        print("")
        print("Errores del validador (el addon no cargará bien hasta corregirlos):")
        for f in errors[:20]:
            print(f"  - [{f.code}] {f.path}: {f.message}")
        if len(errors) > 20:
            print(f"  ... y {len(errors) - 20} más; ver el informe.")
        print("")
        print("Revisa el informe para el detalle y los siguientes pasos.")
    else:
        print("")
        print("Listo. Instala el .mcaddon en Minecraft Bedrock (doble clic o importar).")
        if conv.warnings:
            print(f"Hay {len(conv.warnings)} aviso(s) con pérdidas documentadas: ver el informe.")
    print("")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
