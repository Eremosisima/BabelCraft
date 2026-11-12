"""Informe de conversión en Markdown (en español, junto al addon).

Principio: el usuario tiene que poder decidir qué revisar sin abrir
50 ficheros. El informe dice, por tipo de contenido, qué se convirtió
fiel, qué con pérdidas y qué quedó fuera, con la razón exacta. También
incluye los hallazgos del validador y los límites de Bedrock medidos en
el pack generado.
"""

from __future__ import annotations

import os
from datetime import date

from .model import ConversionResult, SourceMod, Status

_STATUS_LABEL = {
    Status.CONVERTED.value: "convertido",
    Status.ADAPTED.value: "adaptado",
    Status.RESIDUE.value: "residuo",
}

_KIND_LABEL = {
    "item": "Ítems",
    "block": "Bloques",
    "entity": "Entidades",
    "recipe": "Recetas",
    "loot_table": "Loot tables",
    "lang": "Idiomas",
    "texture": "Texturas",
    "model": "Modelos",
    "sound": "Sonidos",
    "tag": "Tags",
    "animation": "Animaciones",
    "geometry": "Geometrías",
    "advancement": "Progresos",
    "worldgen": "Generación de mundo",
    "structure": "Estructuras",
    "function": "Funciones",
    "metadata": "Metadatos",
    "bytecode": "Bytecode",
    "other": "Otros",
}


def build_report(
    mod: SourceMod,
    writer,
    result: ConversionResult,
    addon_path: str,
) -> str:
    coverage = result.coverage()
    errors = [f for f in result.findings if f.severity == "error"]
    warns = [f for f in result.findings if f.severity == "warn"]
    infos = [f for f in result.findings if f.severity == "info"]

    lines: list[str] = []
    lines.append(f"# Informe de conversión — {mod.name}")
    lines.append("")
    lines.append(f"Generado por **BabelCraft** el {date.today().isoformat()}.")
    lines.append("")
    lines.append("| Dato | Valor |")
    lines.append("|---|---|")
    lines.append(f"| Namespace | `{mod.namespace}` |")
    lines.append(f"| Loader detectado | {mod.loader} |")
    lines.append(f"| Versión del mod | {mod.version} |")
    if mod.java_version:
        lines.append(f"| Versión de bytecode | Java {mod.java_version - 44} (major {mod.java_version}) |")
    lines.append(f"| Ficheros en el BP | {len(writer.bp)} |")
    lines.append(f"| Ficheros en el RP | {len(writer.rp)} |")
    if addon_path:
        lines.append(f"| Addon | `{os.path.basename(addon_path)}` |")
    lines.append("")

    # --- Veredicto.
    lines.append("## Veredicto")
    lines.append("")
    if errors:
        lines.append(f"**{len(errors)} error(es) del validador**: el addon NO cargará bien hasta corregirlos.")
    elif warns:
        lines.append(f"Sin errores. {len(warns)} aviso(s): el addon funciona, con las pérdidas que se detallan.")
    else:
        lines.append("Sin errores ni avisos del validador.")
    lines.append("")

    # --- Cobertura.
    lines.append("## Cobertura por tipo de contenido")
    lines.append("")
    if coverage:
        lines.append("| Tipo | Convertido | Adaptado | Residuo | Total |")
        lines.append("|---|---:|---:|---:|---:|")
        for kind in sorted(coverage):
            row = coverage[kind]
            label = _KIND_LABEL.get(kind, kind)
            lines.append(
                f"| {label} | {row['converted']} | {row['adapted']} | {row['residue']} | {row['total']} |"
            )
        total = {
            "converted": sum(r["converted"] for r in coverage.values()),
            "adapted": sum(r["adapted"] for r in coverage.values()),
            "residue": sum(r["residue"] for r in coverage.values()),
            "total": sum(r["total"] for r in coverage.values()),
        }
        lines.append(
            f"| **Total** | **{total['converted']}** | **{total['adapted']}** | **{total['residue']}** | **{total['total']}** |"
        )
    else:
        lines.append("No se reconoció contenido convertible.")
    lines.append("")

    # --- Residuo explicado.
    residue = [e for e in result.entries if e.status is Status.RESIDUE]
    if residue:
        lines.append("## Lo que quedó fuera (y por qué)")
        lines.append("")
        for e in sorted(residue, key=lambda x: (x.kind.value, x.path)):
            reason = "; ".join(e.notes) if e.notes else "sin motivo registrado"
            lines.append(f"- `{e.path}` ({_KIND_LABEL.get(e.kind.value, e.kind.value)}): {reason}")
        lines.append("")

    # --- Adaptados (pérdidas documentadas).
    adapted = [e for e in result.entries if e.status is Status.ADAPTED]
    if adapted:
        lines.append("## Convertido con pérdidas")
        lines.append("")
        for e in sorted(adapted, key=lambda x: (x.kind.value, x.path)):
            lines.append(f"- `{e.path}`: " + "; ".join(e.notes))
        lines.append("")

    # --- Validador.
    if result.findings:
        lines.append("## Hallazgos del validador")
        lines.append("")
        for severity, items, title in (
            ("error", errors, "Errores"),
            ("warn", warns, "Avisos"),
            ("info", infos, "Información"),
        ):
            if not items:
                continue
            lines.append(f"### {title} ({len(items)})")
            lines.append("")
            for f in items:
                lines.append(f"- `{f.code}` en `{f.path}`: {f.message}")
            lines.append("")

    # --- Contexto del mod.
    lines.append("## Contexto detectado")
    lines.append("")
    if mod.mentions_geckolib:
        lines.append("- El mod usa **GeckoLib**: sus modelos/animaciones ya están en formato Bedrock.")
    if mod.class_strings:
        lines.append(f"- Se leyeron {len(mod.class_strings)} cadenas del bytecode como evidencia de registros.")
    if mod.foreign_namespaces:
        ns_list = ", ".join(sorted(mod.foreign_namespaces))
        lines.append(f"- Namespaces de dependencias referenciados: `{ns_list}` (no se convierten).")
    if mod.loaders:
        lines.append(f"- Loaders presentes: {', '.join(mod.loaders)}.")
    lines.append("")

    # --- Siguientes pasos.
    lines.append("## Siguientes pasos manuales")
    lines.append("")
    steps = _next_steps(mod, result, errors, warns)
    for step in steps:
        lines.append(f"1. {step}")
    lines.append("")
    lines.append(
        "> Bedrock no puede replicar la lógica Java (IA, hechizos, metas, eventos): "
        "eso requiere la Script API. BabelCraft convierte el contenido declarativo y "
        "marca el resto, nunca lo inventa."
    )
    lines.append("")
    return "\n".join(lines)


def _next_steps(mod: SourceMod, result: ConversionResult, errors, warns) -> list[str]:
    steps: list[str] = []
    if errors:
        steps.append("Corrige primero los **errores** del validador (arriba): sin eso el pack no carga.")
    has_entities = any(e.kind.value == "entity" and e.status is not Status.RESIDUE for e in result.entries)
    if has_entities:
        steps.append(
            "Ajusta el comportamiento de cada criatura (IA, metas, spawn natural) con componentes "
            "de entidad; el conversor solo deja la base física."
        )
        steps.append("Conecta los sonidos de criatura a eventos (`minecraft:entity` > `events`) si los hay.")
    if any(e.kind.value == "block" and e.status is Status.ADAPTED for e in result.entries):
        steps.append(
            "Revisa los bloques marcados como adaptados: variantes con estado y texturas vanilla "
            "necesitan mapping manual (usa `--overrides`)."
        )
    if result.entries and any(e.kind.value == "item" and e.status is Status.ADAPTED for e in result.entries):
        steps.append(
            "Añade a `--overrides` la comida, durabilidad o combustible de los ítems cuyo "
            "comportamiento vive en el código Java."
        )
    steps.append("Prueba el addon en un mundo de Bedrock con los experimentos mínimos que pida tu versión.")
    steps.append("Si publicas el addon, revisa la licencia del mod original y da crédito a sus autores.")
    return steps


def write_report(
    mod: SourceMod,
    writer,
    result: ConversionResult,
    addon_path: str,
    out_dir: str,
    path: str | None = None,
) -> str:
    """Escribe el informe (por defecto `<out_dir>/REPORT.md`) y devuelve su ruta."""
    text = build_report(mod, writer, result, addon_path)
    target = path or os.path.join(out_dir, "REPORT.md")
    parent = os.path.dirname(os.path.abspath(target))
    os.makedirs(parent, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(text)
    return target
