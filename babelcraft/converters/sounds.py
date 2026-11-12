"""Fase sounds: sounds.json + .ogg de Java -> sound_definitions de Bedrock.

Java:   assets/<ns>/sounds.json
        {"entity.gob.hurt": {"subtitle": ..., "sounds": [{"name": "gob/hurt1"}]}}
        assets/<ns>/sounds/gob/hurt1.ogg

Bedrock: RP/sounds/sound_definitions.json
        {"format_version": "1.14.0",
         "sound_definitions": {"ns.entity.gob.hurt": {
             "category": "neutral",
             "sounds": [{"name": "sounds/ns/gob/hurt1", "volume": 1, "pitch": 1}]}}}
        RP/sounds/ns/gob/hurt1.ogg

Detalles:
  - Las referencias SIN namespace en sounds.json son del propio mod
    (Java resuelve contra el pack que declara el fichero): el fichero
    está en assets/<ns>/sounds/<ruta>.ogg.
  - Las referencias a OTRO namespace son dependencias: no se copian y
    se anotan.
  - ``subtitle`` no existe en Bedrock: se descarta con nota.
  - Los sonidos de una criatura (hurt/death/ambient) se disparan desde
    EVENTOS del entity JSON, que se escriben a mano en v2: aquí quedan
    definidos y listos, y el informe lo recuerda.
"""

from __future__ import annotations

from .. import versions
from ..model import Kind, Status

_ENTITY_CATEGORIES = ("hurt", "death", "attack", "step", "ambient", "idle", "eat")
_CATEGORY_BY_KIND = {
    "hostile": "hostile",
    "ambient": "ambient",
    "block": "block",
    "ui": "ui",
    "music": "music",
    "weather": "weather",
    "record": "record",
    "player": "player",
}


def convert(ctx) -> None:
    mod, writer, result = ctx.mod, ctx.writer, ctx.result
    ns = ctx.ns
    path = f"assets/{ns}/sounds.json"
    if not mod.source.exists(path):
        return
    data = mod.source.read_json_or(path)
    if not isinstance(data, dict):
        result.residue(path, Kind.SOUND, "sounds.json ilegible")
        return

    e = result.entry(path, Kind.SOUND)
    converted = 0
    for event, spec in data.items():
        if not isinstance(spec, dict):
            continue
        entries = spec.get("sounds")
        if not isinstance(entries, list):
            continue
        sound_name = f"{ns}.{event}"
        out_entries: list[dict] = []
        for entry in entries:
            if isinstance(entry, str):
                entry = {"name": entry}
            if not isinstance(entry, dict):
                continue
            ref = entry.get("name")
            if not isinstance(ref, str) or not ref:
                continue
            rns, _, rel = ref.partition(":")
            if not rel:  # sin namespace: es de este mod
                rns, rel = ns, ref
            if rns != ns:
                e.note(f"sonido de otra namespace (dependencia): {ref}")
                continue
            src = f"assets/{rns}/sounds/{rel}.ogg"
            if not mod.source.exists(src):
                e.note(f"fichero de sonido ausente: {src}")
                continue
            dest = f"sounds/{rns}/{rel}.ogg"
            writer.rp_blob(dest, mod.source.read_bytes(src))
            # Marcar el archivo de sonido como convertido.
            snd_entry = result.entry(src, Kind.SOUND)
            snd_entry.status = Status.CONVERTED
            snd: dict = {"name": dest[:-4]}
            if isinstance(entry.get("volume"), (int, float)):
                snd["volume"] = entry["volume"]
            if isinstance(entry.get("pitch"), (int, float)):
                snd["pitch"] = entry["pitch"]
            if entry.get("stream"):
                snd["stream"] = True
            out_entries.append(snd)

        if out_entries:
            writer.add_sound(sound_name, {
                "category": _category(event),
                "sounds": out_entries,
            })
            converted += 1
            e.note("definido; conéctalo a eventos de entidad/ítem a mano (v2)")

    if spec_has_subtitle(data):
        e.note("subtitles no existen en Bedrock: descartados")

    if converted == 0:
        e.status = Status.RESIDUE
        e.note("sin sonidos convertibles")
    else:
        e.status = Status.CONVERTED if not e.notes else Status.ADAPTED


def _category(event: str) -> str:
    low = event.lower()
    for cat in _CATEGORY_BY_KIND:
        if low.startswith(cat + ".") or f".{cat}." in f".{low}.":
            return _CATEGORY_BY_KIND[cat]
    if low.startswith("entity."):
        for marker in _ENTITY_CATEGORIES:
            if f".{marker}" in low:
                return "hostile" if marker in ("hurt", "death", "attack") else "neutral"
        return "neutral"
    return "master"


def spec_has_subtitle(data: dict) -> bool:
    return any(isinstance(v, dict) and "subtitle" in v for v in data.values())
