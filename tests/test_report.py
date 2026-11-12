"""Tests del informe Markdown en español.

El informe es la cara honesta del conversor: cada entrada tiene que
aparecer con su estado y su razón. Aquí se comprueba la estructura del
documento generado y que nada quede sin contar.
"""

from __future__ import annotations

import os

from babelcraft.model import ConversionResult, Kind, SourceMod, Status
from babelcraft.report import build_report, write_report
from babelcraft.source import Source


def _mod(**kw) -> SourceMod:
    base = dict(
        source=Source({}),
        namespace="minimod",
        name="Mini Mod",
        version="1.2.3",
        loader="fabric",
        java_version=61,
    )
    base.update(kw)
    return SourceMod(**base)


def _writer():
    from babelcraft.pack import AddonWriter

    w = AddonWriter(".", "minimod", "Mini Mod", "1.2.3")
    w.bp = {"manifest.json": b"{}", "items/x.json": b"{}"}
    w.rp = {"manifest.json": b"{}", "textures/a.png": b"png"}
    return w


def test_report_header_and_summary_table():
    text = build_report(_mod(), _writer(), ConversionResult(), "out/mini_mod.mcaddon")
    assert text.startswith("# Informe de conversión — Mini Mod")
    assert "Namespace | `minimod`" in text
    assert "Loader detectado | fabric" in text
    assert "Versión del mod | 1.2.3" in text
    assert "Java 17 (major 61)" in text
    assert "Ficheros en el BP | 2" in text
    assert "Ficheros en el RP | 2" in text
    assert "`mini_mod.mcaddon`" in text
    assert "BabelCraft" in text


def test_report_verdict_by_severity():
    result = ConversionResult()
    text = build_report(_mod(), _writer(), result, "x.mcaddon")
    assert "Sin errores ni avisos del validador." in text

    result.warn("ref.shortname_unknown", "rp/blocks.json", "shortname ajeno")
    text = build_report(_mod(), _writer(), result, "x.mcaddon")
    assert "Sin errores. 1 aviso(s)" in text

    result.error("ref.texture_missing", "rp/x.json", "falta png")
    text = build_report(_mod(), _writer(), result, "x.mcaddon")
    assert "1 error(es) del validador" in text
    assert "Hallazgos del validador" in text
    assert "`ref.texture_missing` en `rp/x.json`: falta png" in text


def test_report_coverage_table_counts_all_states():
    result = ConversionResult()
    result.converted("assets/m/lang/en_us.json", Kind.LANG)
    result.adapted("assets/m/lang/es_es.json", Kind.LANG, "claves sin equivalente")
    result.residue("data/m/recipe/x.json", Kind.RECIPE, "tipo sin equivalente")
    text = build_report(_mod(), _writer(), result, "x.mcaddon")
    assert "| Idiomas | 1 | 1 | 0 | 2 |" in text
    assert "| Recetas | 0 | 0 | 1 | 1 |" in text
    assert "| **Total** | **1** | **1** | **1** | **3** |" in text


def test_report_residue_and_adapted_sections():
    result = ConversionResult()
    result.residue("data/m/worldgen/biome.json", Kind.WORLDGEN, "sin equivalente en Bedrock")
    result.adapted(
        "assets/m/models/item/x.json",
        Kind.MODEL,
        "recortado el primer fotograma de la textura animada",
    )
    text = build_report(_mod(), _writer(), result, "x.mcaddon")
    assert "## Lo que quedó fuera (y por qué)" in text
    assert "- `data/m/worldgen/biome.json` (Generación de mundo): sin equivalente en Bedrock" in text
    assert "## Convertido con pérdidas" in text
    assert "- `assets/m/models/item/x.json`: recortado el primer fotograma" in text


def test_report_residue_without_notes_says_so():
    result = ConversionResult()
    result.entry("data/x.json", Kind.OTHER).status = Status.RESIDUE
    text = build_report(_mod(), _writer(), result, "x.mcaddon")
    assert "sin motivo registrado" in text


def test_report_context_section():
    mod = _mod(
        mentions_geckolib=True,
        class_strings={"minimod:ruby", "othermod:gem"},
        foreign_namespaces={"othermod"},
        loaders=["fabric"],
    )
    text = build_report(mod, _writer(), ConversionResult(), "x.mcaddon")
    assert "usa **GeckoLib**" in text
    assert "Se leyeron 2 cadenas del bytecode" in text
    assert "`othermod` (no se convierten)" in text
    assert "Loaders presentes: fabric." in text


def test_report_next_steps_react_to_content():
    # Sin entidades ni adaptados: pasos genéricos.
    result = ConversionResult()
    text = build_report(_mod(), _writer(), result, "x.mcaddon")
    assert "Prueba el addon en un mundo de Bedrock" in text
    assert "revisa la licencia" in text

    # Con entidad convertida y bloque adaptado: pasos específicos.
    result2 = ConversionResult()
    result2.converted("assets/m/geo/gob.geo.json", Kind.ENTITY)
    result2.adapted("assets/m/blockstates/fence.json", Kind.BLOCK, "multipart")
    result2.adapted("assets/m/models/item/ruby.json", Kind.MODEL, "x")
    text2 = build_report(_mod(), _writer(), result2, "x.mcaddon")
    assert "Ajusta el comportamiento de cada criatura" in text2
    assert "Conecta los sonidos de criatura" in text2
    assert "Revisa los bloques marcados como adaptados" in text2
    assert "`--overrides`" in text2

    # Con errores: el primer paso es corregirlos.
    result3 = ConversionResult()
    result3.error("ref.loot", "bp/x.json", "falta")
    text3 = build_report(_mod(), _writer(), result3, "x.mcaddon")
    assert text3.index("Corrige primero los **errores**") < text3.index("Prueba el addon")


def test_report_empty_result_still_renders():
    text = build_report(_mod(), _writer(), ConversionResult(), "x.mcaddon")
    assert "No se reconoció contenido convertible." in text
    assert "## Siguientes pasos manuales" in text


def test_write_report_to_disk(tmp_path):
    result = ConversionResult()
    result.converted("a.json", Kind.LANG)
    out = write_report(_mod(), _writer(), result, "x.mcaddon", str(tmp_path))
    assert out == os.path.join(str(tmp_path), "REPORT.md")
    with open(out, encoding="utf-8") as f:
        text = f.read()
    assert text.startswith("# Informe de conversión — Mini Mod")

    # Ruta personalizada.
    custom = tmp_path / "sub" / "informe.md"
    out2 = write_report(_mod(), _writer(), result, "x.mcaddon", str(tmp_path), str(custom))
    assert out2 == str(custom)
    assert custom.is_file()
