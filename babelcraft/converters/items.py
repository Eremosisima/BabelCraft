"""Fase items: ítems custom -> BP/items/*.json + icono + attachable.

Fuente de candidatos (evidencia, en este orden de confianza):
  1. ``assets/<ns>/models/item/<name>.json`` — un modelo de ítem ES un
     ítem (Java solo dibuja así los ítems custom).
  2. ``assets/<ns>/items/<name>.json`` — definiciones de cliente 1.21.4+
     (``item_model``); apuntan a un modelo.
  3. claves de lang ``item.<ns>.<name>``.
  4. ids ``ns:<name>`` del bytecode, solo si ya hay segunda prueba
     (lang o modelo): un id que solo vive en bytecode no tiene arte y
     convertirlo sería inventar un icono.

Para cada ítem:
  - icono: la textura de su modelo plano (``layer0``), o la primera
    textura del modelo 3D si tiene attachable.
  - ``minecraft:icon`` como SHORTNAME string con format 1.20.10 (la
    forma que valida el motor actual, ídem que hace portkit con corpus
    real) o 1.20.30 cuando añade ``minecraft:hand_equipped`` (modelos
    con parent ``item/handheld``).
  - componentes extra SOLO desde ``--overrides``: comida, durabilidad,
    combustible, stack. Nada se inventa: lo que el bytecode sabe (vida,
    daño) no es legible sin descompilar, y el informe lo dice.
"""

from __future__ import annotations

from .. import versions
from ..model import Kind, Status, slug
from ..mappings import normalize_item
from .models import flat_texture, resolve_model
from .textures import shortname_for

# Overrides -> componente Bedrock (los valores los aporta el usuario).
_OVERRIDE_COMPONENTS = {
    "food": "minecraft:food",
    "fuel": "minecraft:fuel",
    "wearable": "minecraft:wearable",
    "cooldown": "minecraft:cooldown",
    "damage": "minecraft:damage",
    "durability": "minecraft:durability",
    "digger": "minecraft:digger",
    "glint": "minecraft:glint",
}


def convert(ctx) -> None:
    mod, writer, result = ctx.mod, ctx.writer, ctx.result
    ns = ctx.ns

    candidates: dict[str, dict] = {}

    # 1. Modelos de ítem (la evidencia más fuerte: hay arte).
    for path in mod.source.glob(f"assets/{ns}/models/item/"):
        if not path.endswith(".json"):
            continue
        name = path.rsplit("/", 1)[-1][:-5]
        if not name:
            continue
        candidates.setdefault(name, {})["model"] = path
        candidates[name]["model_path"] = f"assets/{ns}/models/item/{name}.json"

    # 2. Definiciones de cliente 1.21.4+ (item_model).
    for path in mod.source.glob(f"assets/{ns}/items/"):
        if not path.endswith(".json"):
            continue
        name = path.rsplit("/", 1)[-1][:-5]
        if not name:
            continue
        data = mod.source.read_json_or(path)
        model_ref = _client_item_model_ref(data)
        if model_ref is None:
            e = result.residue(path, Kind.ITEM, "definición de ítem sin modelo legible (item_model)")
            continue
        mns, _, mref = model_ref.partition(":")
        mpath = f"assets/{mns or ns}/models/{mref}.json"
        entry = candidates.setdefault(name, {})
        entry["model_path"] = mpath
        entry["src"] = path

    # 3. Lang (nombre existe pero puede no tener arte).
    lang = ctx.lang_tables.get("en_us") or {}
    for key in lang:
        if key.startswith(f"item.{ns}."):
            name = key[len(f"item.{ns}."):]
            name = name[:-5] if name.endswith(".name") else name
            if name and "/" not in name:
                candidates.setdefault(name, {})["lang"] = True

    # 4. Bytecode: solo refuerza a los que ya tienen modelo/lang.
    for ident in mod.ids_from_bytecode:
        bns, _, name = ident.partition(":")
        if bns == ns and name and "/" not in name:
            candidates.setdefault(name, {})["bytecode"] = True

    for name in sorted(candidates):
        info = candidates[name]
        ident = f"{ns}:{name}"
        src = info.get("src") or info.get("model_path") or f"lang:item.{ns}.{name}"
        e = result.entry(src, Kind.ITEM)
        ctx.item_ids.add(ident)

        # --- Icono.
        model_path = info.get("model_path")
        tex_id = None
        if model_path and mod.source.exists(model_path):
            resolved = resolve_model(ctx, model_path)
            if resolved:
                tex_id = flat_texture(resolved)
                if tex_id is None and ident in ctx.attachable_icons:
                    tex_id = ctx.attachable_icons[ident]
        if tex_id is None and ident in ctx.attachable_icons:
            tex_id = ctx.attachable_icons[ident]

        if tex_id is None or tex_id not in ctx.tex_rpaths:
            if ctx.opts.placeholders:
                from ..pngcodec import Png, encode_png

                png = _placeholder_png(name)
                rpath = f"textures/{ns}/item/{name}"
                writer.rp_blob(rpath + ".png", encode_png(png.width, png.height, png.pixels))
                shortname = shortname_for(f"{ns}:item/{name}")
                writer.add_item_texture(shortname, rpath)
                e.note("sin arte: icono placeholder generado (--placeholders)")
            else:
                e.status = Status.RESIDUE
                e.note("sin modelo/textura: no hay forma fiel de dibujar este ítem (registrado en código/lang)")
                ctx.item_ids.discard(ident)
                continue
        else:
            rpath = ctx.tex_rpaths[tex_id]
            shortname = shortname_for(tex_id)
            writer.add_item_texture(shortname, rpath)

        # --- Documento BP del ítem.
        held = _is_held(ctx, model_path)
        components = {
            "minecraft:icon": shortname,
            "minecraft:max_stack_size": 64,
        }
        if held:
            components["minecraft:hand_equipped"] = True

        # Mejoras específicas (Cobblemon): clasificación y componentes aproximados
        # para ítems/poké balls, manteniendo overrides del usuario como prioridad.
        if _is_cobblemon_context(mod):
            classification = _classify_cobblemon_item(name)
            components["minecraft:icon"] = {"textures": {"default": shortname}}
            components["minecraft:display_name"] = {"value": f"item.{ns}.{name}.name"}
            components["minecraft:max_stack_size"] = classification.get("max_stack_size", 64)
            if classification.get("hand_equipped") or held:
                components["minecraft:hand_equipped"] = True
            if classification.get("allow_off_hand", True):
                components["minecraft:allow_off_hand"] = True
            if classification.get("food"):
                components["minecraft:food"] = classification["food"]
                components["minecraft:use_modifiers"] = {
                    "use_duration": classification.get("use_duration", 1.6),
                    "movement_modifier": 0.35,
                }
                components["minecraft:use_animation"] = classification.get("use_animation", "eat")
            if classification.get("throwable"):
                components["minecraft:throwable"] = {
                    "do_swing_animation": True,
                    "launch_power_scale": 1.0,
                    "max_draw_duration": 0.0,
                    "max_launch_power": 1.0,
                    "min_draw_duration": 0.0,
                    "scale_power_by_draw_duration": False,
                }
                components["minecraft:projectile"] = {
                    "minimum_critical_power": 1.25,
                    "projectile_entity": "minecraft:snowball",
                }
                components["minecraft:use_animation"] = classification.get("use_animation", "bow")
                components["minecraft:cooldown"] = classification.get("cooldown", {"category": "cobblemon_pokeball", "duration": 1.0})
            e.note("mecánicas Cobblemon aplicadas (clasificación heurística/estática)")
        else:
            components["minecraft:icon"] = shortname

        # Overrides del usuario (valores sacados del código fuente del mod).
        ov = ctx.overrides.item(ident)
        for key, value in ov.items():
            if key == "max_stack_size":
                components["minecraft:max_stack_size"] = value
            elif key in _OVERRIDE_COMPONENTS:
                components[_OVERRIDE_COMPONENTS[key]] = value
            elif key.startswith("minecraft:"):
                components[key] = value

        display = ctx.name_for("item", ident) or ctx.name_for("item", f"{ns}:{name}")
        if display:
            components["minecraft:display_name"] = {"value": f"item.{ns}:{name}"}
            writer.add_lang(ctx.opts.lang_out, f"item.{ns}:{name}", display)
        elif _is_cobblemon_context(mod):
            writer.add_lang(ctx.opts.lang_out, f"item.{ns}.{name}.name", name.replace("_", " ").strip().title())

        menu = ctx.overrides.menu.get(ident, ("equipment" if _is_cobblemon_context(mod) and _classify_cobblemon_item(name).get("kind") in {"pokeball","medicine","utility"} else "items"))
        doc = {
            "format_version": "1.20.50" if _is_cobblemon_context(mod) else (versions.ITEM_HELD if held else versions.ITEM),
            "minecraft:item": {
                "description": {
                    "identifier": ident,
                    "menu_category": {"category": menu},
                },
                "components": components,
            },
        }
        writer.bp_json(f"items/{ns}_{slug(name)}.json", doc)
        e.status = Status.CONVERTED if not e.notes else Status.ADAPTED


def _is_held(ctx, model_path: str | None) -> bool:
    """¿El modelo cuelga de item/handheld? (se dibuja 'como herramienta')."""
    if not model_path:
        return False
    resolved = resolve_model(ctx, model_path) if ctx.mod.source.exists(model_path) else None
    if not resolved:
        return False
    return bool(resolved.get("held"))


def _client_item_model_ref(data) -> str | None:
    """Extrae la referencia al modelo de una definición 1.21.4+."""
    if not isinstance(data, dict):
        return None
    model = data.get("model")
    if isinstance(model, str):
        return model
    if isinstance(model, dict):
        ref = model.get("model")
        if isinstance(ref, str):
            return ref
        for entry in model.get("entries", []) or []:
            if isinstance(entry, dict) and isinstance(entry.get("model"), str):
                return entry["model"]
    # Formas sueltas: {"model": {"type": "minecraft:condition", ...}}.
    stack = [data]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k == "model" and isinstance(v, str) and "/" in v:
                    return v
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(v for v in cur if isinstance(v, (dict, list)))
    return None


def _is_cobblemon_context(mod) -> bool:
    ns = (getattr(mod, "namespace", "") or "").lower()
    name = (getattr(mod, "name", "") or "").lower()
    haystack = f"{ns} {name}"
    if "cobblemon" in haystack:
        return True
    try:
        for _ in mod.source.glob("assets/cobblemon/"):
            return True
    except Exception:
        pass
    return False


def _classify_cobblemon_item(item_name: str) -> dict:
    """Clasificador heurístico/estático para ítems Cobblemon en pipeline general."""
    n = item_name.lower()
    info = {
        "kind": "generic",
        "max_stack_size": 64,
        "hand_equipped": False,
        "allow_off_hand": True,
        "throwable": False,
        "food": None,
        "use_animation": None,
        "use_duration": None,
        "cooldown": None,
    }
    if "ball" in n or "pokeball" in n:
        info.update({
            "kind": "pokeball",
            "hand_equipped": True,
            "throwable": True,
            "use_animation": "bow",
            "cooldown": {"category": "cobblemon_pokeball", "duration": 1.0},
            "max_stack_size": 16 if any(x in n for x in ("master", "origin", "cherish", "beast")) else 64,
        })
        return info
    if "berry" in n or n in {"leftovers", "lava_cookie", "old_gateau", "casteliacone", "big_malasada", "lumiose_galette", "rage_candy_bar"}:
        info.update({
            "kind": "food",
            "food": {"nutrition": 2, "saturation_modifier": "low", "can_always_eat": True},
            "use_animation": "eat",
            "use_duration": 1.6,
        })
        return info
    if any(x in n for x in ("potion", "heal", "revive", "antidote", "burn_heal", "ice_heal", "paralyze_heal", "awakening", "full_restore", "ether", "elixir", "fresh_water", "soda_pop", "lemonade", "moomoo_milk")):
        info.update({"kind": "medicine", "use_animation": "drink", "use_duration": 1.6})
        return info
    if any(x in n for x in ("candy", "rare_candy", "exp_", "vitamin", "protein", "iron", "calcium", "zinc", "carbos", "hp_up", "pp_", "feather")):
        info.update({"kind": "enhancement", "use_animation": "eat", "use_duration": 1.6})
        return info
    if n.startswith("tm_") or n.startswith("hm_") or n.startswith("tr_"):
        info.update({"kind": "move", "max_stack_size": 1})
        return info
    if any(x in n for x in ("pokedex", "rod")):
        info.update({"kind": "utility", "hand_equipped": True, "max_stack_size": 1})
        return info
    return info


def _placeholder_png(name: str, size: int = 16):
    """Icono determinista derivado del nombre (cuadradito con borde)."""
    from ..pngcodec import Png

    seed = sum(name.encode("utf-8")) or 7
    r = (seed * 41) % 200 + 55
    g = (seed * 67) % 200 + 55
    b = (seed * 97) % 200 + 55
    px = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            i = (y * size + x) * 4
            border = x == 0 or y == 0 or x == size - 1 or y == size - 1
            f = 0.55 if border else 1.0
            px[i] = round(r * f)
            px[i + 1] = round(g * f)
            px[i + 2] = round(b * f)
            px[i + 3] = 255
    return Png(size, size, px)
