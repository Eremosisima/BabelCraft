"""Fase loot: loot tables de Java -> loot tables de Bedrock (BP).

Los loot tables de Bedrock son casi los de Java: pools/entries/
conditions/functions, SIN format_version. Las diferencias que hay que
cuidar (el resto del fichero pasa tal cual, que es lo fiel):

  - top-level ``type``/``random_sequence``: Java-only, se quitan.
  - funciones top-level: Bedrock no las soporta fuera de un entry; se
    descuentan con nota si traen algo real.
  - ``minecraft:explosion_decay``: en Bedrock es la CONDITION
    ``minecraft:survives_explosion`` del pool, no una función.
  - funciones avanzadas de Java sin equivalente (apply_bonus con
    fortuna, set_nbt, enchantments, copy_state...): se quitan con nota.
    El resto del pool sigue funcionando.
  - entries de tipo ``loot_table``: la referencia ``ns:blocks/x`` se
    reescribe a la ruta del BP convertido.

Salida:
  - ``loot_tables/<ns>/blocks/<name>.json``  (bloques)
  - ``loot_tables/<ns>/entities/<name>.json`` (entidades)
  - el resto de tablas (cofres...) se convierte igual: se pueden usar
    desde la Script API o eventos custom, y el informe lo recuerda.

Registra cada ruta en ``ctx.loot_paths`` para que bloques y entidades
cuelguen su ``minecraft:loot`` del fichero correcto.
"""

from __future__ import annotations

from ..model import Kind, Status
from ..mappings import normalize_item, namespace_of

# Funciones que Bedrock lee tal cual (nombres Java compatibles).
_KEPT_FUNCTIONS = {
    "minecraft:set_count",
    "minecraft:set_data",
    "minecraft:set_damage",
    "minecraft:set_name",
    "minecraft:furnace_set_smelt",
}

_KEPT_CONDITIONS = {
    "minecraft:random_chance",
    "minecraft:random_chance_with_enchant",
    "minecraft:killed_by_player",
    "minecraft:killed_by_mob",
    "minecraft:survives_explosion",
}

_DIRS = ("data/{}/loot_tables", "data/{}/loot_table")


def convert(ctx) -> None:
    mod, writer, result = ctx.mod, ctx.writer, ctx.result
    ns = ctx.ns

    for fmt in _DIRS:
        prefix = fmt.format(ns)
        for path in mod.source.glob(prefix + "/"):
            if not path.endswith(".json"):
                continue
            data = mod.source.read_json_or(path)
            if not isinstance(data, dict):
                result.residue(path, Kind.LOOT_TABLE, "JSON de loot table ilegible")
                continue
            _convert_table(ctx, path, data)


def _convert_table(ctx, path: str, data: dict) -> None:
    mod, writer, result = ctx.mod, ctx.writer, ctx.result
    ns = ctx.ns
    notes: list[str] = []

    out = _convert_node(ctx, data, notes, top=True)

    # Ruta de salida: data/<ns>/loot_tables/<resto>.json -> loot_tables/<ns>/<resto>.json
    rel = _after_loot_dir(path)
    dest = f"loot_tables/{ns}/{rel}"
    writer.bp_json(dest, out)

    # Registro para que bloques/entidades enganchen su componente loot.
    if rel.startswith("blocks/"):
        ctx.loot_paths[f"{ns}:{rel[:-5]}"] = dest
    elif rel.startswith("entities/"):
        ctx.loot_paths[f"{ns}:{rel[:-5]}"] = dest

    e = result.entry(path, Kind.LOOT_TABLE)
    e.status = Status.CONVERTED if not notes else Status.ADAPTED
    for n in notes:
        e.note(n)


def _after_loot_dir(path: str) -> str:
    """`data/ns/loot_tables/blocks/x.json` -> `blocks/x.json`."""
    for marker in ("/loot_tables/", "/loot_table/"):
        if marker in path:
            return path.split(marker, 1)[1]
    return path.rsplit("/", 1)[-1]


def _convert_node(ctx, node, notes: list, top=False, item_name=False):
    """Convierte recursivamente pools/entries. Los dicts pasan saneados.

    `item_name` distingue el `name` de un entry de ítem (se normaliza como
    ítem) del `name` de un entry `minecraft:loot_table` (se reescribe como
    ruta de loot table del BP).
    """
    if isinstance(node, list):
        return [_convert_node(ctx, v, notes, item_name=item_name) for v in node]
    if not isinstance(node, dict):
        return node

    out: dict = {}
    for key, value in node.items():
        if top and key in ("type", "random_sequence"):
            continue  # Java-only
        if key == "functions" and top:
            # Bedrock no admite funciones a nivel de tabla: se avisa.
            real = [f for f in value if isinstance(f, dict) and f.get("function") not in _KEPT_FUNCTIONS]
            if real:
                notes.append("funciones a nivel de tabla (Java-only): se pierden")
            continue
        if key == "pools":
            out["pools"] = [
                _convert_pool(ctx, p, notes) if isinstance(p, dict) else p for p in value or []
            ]
            continue
        if key == "conditions":
            out["conditions"] = _convert_conditions(value, notes)
            continue
        if key == "functions":
            out["functions"] = _convert_functions(value, notes)
            continue
        if key == "entries":
            out["entries"] = [
                _convert_entry(ctx, e, notes) if isinstance(e, dict) else e for e in value or []
            ]
            continue
        if key == "name" and isinstance(value, str) and ":" in value:
            if item_name:
                out[key], note = normalize_item(value)
            else:
                out[key], note = _normalize_name(ctx, value)
            if note:
                notes.append(note)
            continue
        out[key] = (
            _convert_node(ctx, value, notes, item_name=item_name)
            if isinstance(value, (dict, list))
            else value
        )
    return out


def _convert_pool(ctx, pool: dict, notes: list) -> dict:
    return _convert_node(ctx, pool, notes)


def _convert_entry(ctx, entry: dict, notes: list) -> dict:
    t = entry.get("type", "")
    if t in ("minecraft:alternatives", "minecraft:group", "minecraft:sequence", "minecraft:dynamic"):
        notes.append(f"entry de tipo {t}: Bedrock no lo soporta; se aplana a su primer hijo si existe")
        children = entry.get("children")
        if isinstance(children, list) and children:
            child = _convert_entry(ctx, children[0] if isinstance(children[0], dict) else {}, notes)
            child.setdefault("weight", entry.get("weight", 1))
            return child
        return {"type": "empty", "weight": entry.get("weight", 1)}
    # Un entry `loot_table` referencia otra tabla; el resto lleva un ítem.
    return _convert_node(ctx, entry, notes, item_name=(t != "minecraft:loot_table"))


def _convert_conditions(conds, notes: list) -> list:
    out = []
    for c in _as_list(conds):
        if not isinstance(c, dict):
            continue
        name = str(c.get("condition", ""))
        if name == "minecraft:match_tool":
            if c.get("predicate") not in (None, {}):
                notes.append("match_tool con predicado avanzado: Bedrock lo ignora, la condición se simplifica")
            out.append({"condition": name})
        elif name in _KEPT_CONDITIONS:
            out.append(c)
        elif name == "minecraft:block_state_property":
            notes.append("condición block_state_property (Java-only): se quita")
        elif name:
            notes.append(f"condición sin equivalente Bedrock: {name}")
    return out


def _convert_functions(funcs, notes: list) -> list:
    out = []
    for f in _as_list(funcs):
        if not isinstance(f, dict):
            continue
        name = str(f.get("function", ""))
        if name == "minecraft:explosion_decay":
            # En Bedrock la explosión se filtra con la condición del pool.
            notes.append("explosion_decay: en Bedrock es la condición survives_explosion (no una función)")
            continue
        if name in _KEPT_FUNCTIONS:
            out.append(f)
        elif name:
            notes.append(f"función sin equivalente Bedrock: {name} (fortune/NBT/encantos)")
    return out


def _normalize_name(ctx, value: str) -> tuple[str, str | None]:
    """Referencia a otra loot table (`minecraft:loot_table` entry) -> ruta BP."""
    ns = namespace_of(value)
    ref = value.split(":", 1)[1] if ":" in value else value
    if not ref:
        return value, None
    if not ref.endswith(".json"):
        ref += ".json"
    if ns == "minecraft":
        return (
            f"loot_tables/minecraft/{ref}",
            "referencia a loot table vanilla: Bedrock no la expone como fichero del addon",
        )
    path = f"loot_tables/{ns}/{ref}"
    if ns != ctx.ns:
        return path, f"referencia a loot table de otro addon ({value}): solo funciona con ese addon"
    return path, None


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]
