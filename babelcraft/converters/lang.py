"""Fase lang: archivos de idioma de Java -> textos de Bedrock.

Java:   assets/<ns>/lang/en_us.json    {"item.minimod.ruby": "Ruby"}
Bedrock: RP/texts/en_US.lang           "item.minimod:ruby=Ruby"

Las claves se transforman por contenido (item./block./entity.) con
`lang_key_java_to_bedrock`; las que no encajan (subtítulos de sonidos,
claves de GUI propias del mod, traducciones de poemas del End...) se
dejan pasar tal cual: Bedrock ignora las claves que no reconoce y no
rompe nada.

Los NOMBRES (valores) se reutilizan después en items, bloques y
entidades: es la única fuente fiable de cómo se llama cada cosa.
"""

from __future__ import annotations

from ..model import Kind, Status
from ..mappings import lang_key_java_to_bedrock


def convert(ctx) -> None:
    mod, writer, result = ctx.mod, ctx.writer, ctx.result
    ns = ctx.ns

    for path in mod.source.glob(f"assets/{ns}/lang/"):
        if not path.endswith(".json"):
            continue
        lang_file = path.rsplit("/", 1)[-1][:-5]  # en_us
        # Bedrock usa mayúsculas y guiones: en_US, es_ES, pt_BR...
        bedrock_lang = _bedrock_lang_name(lang_file)
        data = mod.source.read_json_or(path)
        if not isinstance(data, dict):
            continue
        e = result.converted(path, Kind.LANG)

        table = ctx.lang_tables.setdefault(lang_file, data)
        count = 0
        for key, value in data.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            mapped = lang_key_java_to_bedrock(key, value)
            if mapped:
                writer.add_lang(bedrock_lang, mapped[0], mapped[1])
                count += 1
            else:
                writer.add_lang(bedrock_lang, key, value)
                e.note(f"clave sin equivalente directo: {key}")
        ctx.lang_files.append(path)
        if count == 0:
            e.status = Status.ADAPTED
            e.note("sin claves mapeables (item./block./entity.)")


def _bedrock_lang_name(java_lang: str) -> str:
    """en_us -> en_US, es -> es_ES, pt_br -> pt_BR."""
    parts = java_lang.replace("-", "_").split("_")
    lang = parts[0][:2].lower()
    region = parts[1].upper() if len(parts) > 1 and parts[1] else lang.upper()
    return f"{lang}_{region}"
