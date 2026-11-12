"""Fase recipes: recetas de crafteo de Java -> recetas Bedrock.

Mapeo verificado contra el validador estructural de portkit (corpus de
mods reales) y la documentación de Bedrock:

  Java                          Bedrock
  ----------------------------  ----------------------------------------
  minecraft:crafting_shaped     minecraft:recipe_shaped   tags [crafting_table]
  minecraft:crafting_shapeless  minecraft:recipe_shapeless tags [crafting_table]
  minecraft:stonecutting        minecraft:recipe_shapeless tags [stonecutter]
  minecraft:smelting            minecraft:recipe_furnace   tags [furnace]
  minecraft:blasting            minecraft:recipe_furnace   tags [blast_furnace]
  minecraft:smoking             minecraft:recipe_furnace   tags [smoker]
  minecraft:campfire_cooking    minecraft:recipe_furnace   tags [campfire, soul_campfire]

Detalles que rompen silenciosamente si no se cuidan:
  - ``unlock`` es OBLIGATORIO con format_version >= 1.20.10: se deriva
    de los ingredientes si Java no lo declara.
  - el input/output del furnace es un id STRING suelto (no objeto), y
    una receta con tag de entrada no tiene sitio ahí: se reporta.
  - cookingtime y xp no tienen equivalente en la receta Bedrock: se
    anotan, no se inventan.
  - los ingredientes custom de OTROS mods (dependencias) se dejan tal
    cual con nota: solo funcionan si ese addon está instalado.
"""

from __future__ import annotations

from .. import versions
from ..model import Kind, Status, slug
from ..mappings import normalize_item

# (tipo Java) -> (tipo Bedrock, tags)
_COOKING = {
    "minecraft:smelting": ("minecraft:recipe_furnace", ["furnace"]),
    "minecraft:blasting": ("minecraft:recipe_furnace", ["blast_furnace"]),
    "minecraft:smoking": ("minecraft:recipe_furnace", ["smoker"]),
    "minecraft:campfire_cooking": ("minecraft:recipe_furnace", ["campfire", "soul_campfire"]),
}

_DIRS = ("data/{}/recipe", "data/{}/recipes")


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
                result.residue(path, Kind.RECIPE, "JSON de receta ilegible")
                continue
            _convert_one(ctx, path, data)


def _convert_one(ctx, path: str, data: dict) -> None:
    mod, result = ctx.mod, ctx.result
    java_type = str(data.get("type", ""))
    name = path.rsplit("/", 1)[-1][:-5]

    if java_type in _COOKING:
        bedrock_type, tags = _COOKING[java_type]
        entry = _furnace(ctx, path, data, bedrock_type, tags, name)
    elif java_type == "minecraft:crafting_shaped":
        entry = _shaped(ctx, path, data, name)
    elif java_type == "minecraft:crafting_shapeless":
        entry = _shapeless(ctx, path, data, name)
    elif java_type == "minecraft:stonecutting":
        entry = _stonecutter(ctx, path, data, name)
    else:
        result.residue(
            path,
            Kind.RECIPE,
            f"tipo de receta sin equivalente Bedrock: {java_type or '(sin tipo)'}"
            + (" (smithing/cervecería/desbloqueo vanilla)" if java_type.startswith(("minecraft:smithing", "minecraft:crafting_special")) else ""),
        )
        return

    if entry is None:
        return
    ctx.writer.bp_json(f"recipes/{ctx.ns}_{slug(name)}.json", entry)


# ---------------------------------------------------------------------------


def _shaped(ctx, path: str, data: dict, name: str):
    mod, result = ctx.mod, ctx.result
    ns = ctx.ns
    pattern = data.get("pattern")
    key = data.get("key")
    res = _result(data)
    if not isinstance(pattern, list) or not isinstance(key, dict) or res is None:
        result.residue(path, Kind.RECIPE, "receta shaped incompleta (pattern/key/result)")
        return None

    notes: list[str] = []
    bkey: dict[str, dict] = {}
    unlock: list[dict] = []
    for sym, spec in key.items():
        if not isinstance(sym, str) or sym in (" ",):
            continue
        ing = _ingredient(ctx, spec, notes)
        if ing is None:
            return None
        bkey[sym] = ing
        if "item" in ing:
            unlock.append({"item": ing["item"]})

    # Java 1.20.5+: unlock explícito; si no, se deriva de los ingredientes.
    unlock = _unlock(ctx, data, notes) or unlock

    body = {
        "format_version": versions.RECIPE,
        "minecraft:recipe_shaped": {
            "description": {"identifier": f"{ns}:{name}"},
            "tags": ["crafting_table"],
            "pattern": pattern,
            "key": bkey,
            "unlock": unlock or [{"item": "minecraft:stick"}],
            "result": res,
        },
    }
    _claim(ctx, path, notes)
    return body


def _shapeless(ctx, path: str, data: dict, name: str):
    mod, result = ctx.mod, ctx.result
    ns = ctx.ns
    ingredients = data.get("ingredients")
    res = _result(data)
    if not isinstance(ingredients, list) or res is None:
        result.residue(path, Kind.RECIPE, "receta shapeless incompleta (ingredients/result)")
        return None

    notes: list[str] = []
    bing: list[dict] = []
    unlock: list[dict] = []
    for spec in ingredients:
        ing = _ingredient(ctx, spec, notes)
        if ing is None:
            return None
        bing.append(ing)
        if "item" in ing:
            unlock.append({"item": ing["item"]})

    unlock = _unlock(ctx, data, notes) or unlock
    body = {
        "format_version": versions.RECIPE,
        "minecraft:recipe_shapeless": {
            "description": {"identifier": f"{ns}:{name}"},
            "tags": ["crafting_table"],
            "ingredients": bing,
            "unlock": unlock or [{"item": "minecraft:stick"}],
            "result": res,
        },
    }
    _claim(ctx, path, notes)
    return body


def _stonecutter(ctx, path: str, data: dict, name: str):
    mod, result = ctx.mod, ctx.result
    ns = ctx.ns
    res = _result(data)
    ingredient = data.get("ingredient")
    if res is None or ingredient is None:
        result.residue(path, Kind.RECIPE, "receta de cortapiedras incompleta")
        return None
    notes: list[str] = []
    ing = _ingredient(ctx, ingredient, notes)
    if ing is None:
        return None
    unlock = [{"item": ing["item"]}] if "item" in ing else []
    body = {
        "format_version": versions.RECIPE,
        "minecraft:recipe_shapeless": {
            "description": {"identifier": f"{ns}:{name}"},
            "tags": ["stonecutter"],
            "ingredients": [ing],
            "unlock": unlock or [{"item": "minecraft:stick"}],
            "result": res,
        },
    }
    _claim(ctx, path, notes)
    return body


def _furnace(ctx, path: str, data: dict, bedrock_type: str, tags: list[str], name: str):
    mod, result = ctx.mod, ctx.result
    ns = ctx.ns
    ingredient = data.get("ingredient")
    res_id = _result_id(data)
    notes: list[str] = []

    if isinstance(ingredient, dict) and "tag" in ingredient:
        result.residue(
            path,
            Kind.RECIPE,
            f"entrada de horno con tag {ingredient['tag']!r}: Bedrock solo admite un ítem en la entrada",
        )
        return None
    if res_id is None:
        result.residue(path, Kind.RECIPE, "receta de horno sin resultado legible")
        return None

    inp_id = ingredient.get("item") if isinstance(ingredient, dict) else ingredient
    if not isinstance(inp_id, str):
        result.residue(path, Kind.RECIPE, "entrada de horno ilegible")
        return None

    inp_id, n1 = _norm(ctx, inp_id, notes)
    out_id, n2 = _norm(ctx, res_id, notes)

    # Validar que los ítems existan (si son del mod, deben estar convertidos).
    inp_ns = inp_id.split(":")[0] if ":" in inp_id else ns
    out_ns = out_id.split(":")[0] if ":" in out_id else ns
    if inp_ns == ns and inp_id not in ctx.item_ids:
        result.residue(path, Kind.RECIPE, f"receta de horno con ítem de entrada inexistente: {inp_id}")
        return None
    if out_ns == ns and out_id not in ctx.item_ids:
        result.residue(path, Kind.RECIPE, f"receta de horno con resultado inexistente: {out_id}")
        return None

    ct = data.get("cookingtime")
    if isinstance(ct, (int, float)) and abs(ct - 200) > 1:
        notes.append(f"cookingtime de {ct} ticks: Bedrock usa el tiempo fijo del horno ({int(ct / 20 * 1000)} ms aprox.), no se transfiere")
    if data.get("experience") not in (None, 0):
        notes.append("experience no tiene equivalente en la receta Bedrock")

    body = {
        "format_version": versions.RECIPE,
        bedrock_type: {
            "description": {"identifier": f"{ns}:{name}"},
            "tags": tags,
            "input": inp_id,
            "output": out_id,
        },
    }
    _claim(ctx, path, notes)
    return body


# ---------------------------------------------------------------------------


def _ingredient(ctx, spec, notes: list) -> dict | None:
    """Un ingrediente Java -> forma Bedrock ({"item": ...} | {"tag": ...})."""
    if isinstance(spec, str):
        spec = {"item": spec}
    if not isinstance(spec, dict):
        notes.append("ingrediente ilegible")
        return None
    if "tag" in spec:
        tag = spec["tag"]
        ns_tag = str(tag).split(":", 1)[0]
        if ns_tag not in ("minecraft", ctx.ns):
            notes.append(f"tag de dependencia: {tag}")
        else:
            notes.append(f"tag {tag}: Bedrock solo conoce los tags vanilla de ítems")
        return {"tag": tag}
    item = spec.get("item")
    if not isinstance(item, str):
        notes.append("ingrediente sin item legible")
        return None
    item, note = _norm(ctx, item, notes)
    out = {"item": item}
    if "data" in spec:
        out["data"] = spec["data"]
    return out


def _result(data: dict) -> dict | None:
    """Resultado Java -> {"item", "count"}.

    Formas que existen: objeto 1.20.5+ (`{"id": ..., "count": ...}`), objeto
    clásico (`{"item": ...}`) y cadena suelta (cortapiedras, horno antiguo).
    """
    r = data.get("result")
    if isinstance(r, str):
        return {"item": r, "count": data.get("count", 1)}
    if isinstance(r, dict):
        ident = r.get("id") or r.get("item")
        if isinstance(ident, str):
            return {"item": ident, "count": r.get("count", 1)}
    return None


def _result_id(data: dict) -> str | None:
    r = _result(data)
    return r["item"] if r else None


def _norm(ctx, item_id: str, notes: list) -> tuple[str, str | None]:
    """Normaliza un id de ítem y anota lo que toque."""
    out, note = normalize_item(item_id)
    if note:
        notes.append(note)
    ns = item_id.split(":", 1)[0] if ":" in item_id else ""
    if ns not in ("minecraft", ctx.ns):
        notes.append(f"referencia a dependencia: {item_id} (solo funciona con ese addon instalado)")
    if ns == ctx.ns and item_id not in ctx.item_ids and item_id not in ctx.block_ids:
        notes.append(f"resultado/ingrediente {item_id} no se convirtió: revisa su fase")
    return out, note


def _unlock(ctx, data: dict, notes: list) -> list[dict]:
    """Java 1.20.5+ declara unlock; si no, [] (el llamador deriva)."""
    unlock = data.get("unlock")
    if isinstance(unlock, list):
        out: list[dict] = []
        for spec in unlock:
            if isinstance(spec, dict) and isinstance(spec.get("item"), str):
                out.append({"item": normalize_item(spec["item"])[0]})
            elif isinstance(spec, str):
                out.append({"item": normalize_item(spec)[0]})
        return out
    return []


def _claim(ctx, path: str, notes: list) -> None:
    e = ctx.result.converted(path, Kind.RECIPE, notes)
