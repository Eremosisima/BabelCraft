"""Conversión de ítems de Cobblemon con heurísticas de mecánicas básicas.

Objetivo: mejorar fidelidad visual y utilidad en Bedrock (iconos/texturas correctas,
categorías, consumibles, pokeballs lanzables como aproximación), sin fingir
mecánicas complejas no portables (captura/batalla real, IA, etc.).
"""

from __future__ import annotations

import json
import re
from typing import Any


# Nombres que suelen ser variantes internas de modelo/casting, no ítems de gameplay.
_MODEL_VARIANT_SUFFIXES = ("_model", "_cast")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "_", name.lower())


def _safe_read_json(source, path: str) -> dict | None:
    try:
        data = source.read_json(path)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _resolve_item_texture_path(mod, item_name: str, model_data: dict | None) -> str | None:
    """Resuelve ruta de textura dentro del jar para un item de Cobblemon."""
    # 1) Desde model layer0: "cobblemon:item/poke_balls/poke_ball"
    if model_data:
        textures = model_data.get("textures")
        if isinstance(textures, dict):
            for key in ("layer0", "texture", "particle"):
                ref = textures.get(key)
                if not isinstance(ref, str) or not ref:
                    continue
                ref = ref.strip()
                # soportar "cobblemon:item/..." o "item/..."
                if ":" in ref:
                    ns, rest = ref.split(":", 1)
                else:
                    ns, rest = mod.namespace, ref
                if not rest.startswith("textures/"):
                    rest = "textures/" + rest
                if not rest.endswith(".png"):
                    rest = rest + ".png"
                path = f"assets/{ns}/{rest}"
                if mod.source.exists(path):
                    return path

    # 2) Ruta plana textures/item/<name>.png
    candidates = [
        f"assets/{mod.namespace}/textures/item/{item_name}.png",
        f"assets/{mod.namespace}/textures/items/{item_name}.png",
    ]
    # 3) Pokeballs en subcarpeta
    candidates.extend([
        f"assets/{mod.namespace}/textures/item/poke_balls/{item_name}.png",
        f"assets/{mod.namespace}/textures/item/pokeballs/{item_name}.png",
    ])
    # 4) Alternativas por sufijo de modelo
    for suf in _MODEL_VARIANT_SUFFIXES:
        if item_name.endswith(suf):
            base = item_name[: -len(suf)]
            candidates.extend([
                f"assets/{mod.namespace}/textures/item/{base}.png",
                f"assets/{mod.namespace}/textures/item/poke_balls/{base}.png",
                f"assets/{mod.namespace}/textures/item/pokeballs/{base}.png",
            ])
            break
    for p in candidates:
        if mod.source.exists(p):
            return p

    # 5) Búsqueda por nombre de archivo (último recurso)
    needle = f"/{item_name}.png"
    for p in mod.source.glob(f"assets/{mod.namespace}/textures/item/"):
        if p.endswith(needle):
            return p
    # también fuera de textures/item (algunas variantes)
    for p in mod.source.glob(f"assets/{mod.namespace}/textures/"):
        if p.endswith(needle) and "/item/" in p:
            return p
    return None


def _classify_item(item_name: str) -> dict[str, Any]:
    n = item_name.lower()
    info: dict[str, Any] = {
        "kind": "generic",
        "category": "items",
        "max_stack_size": 64,
        "hand_equipped": False,
        "throwable": False,
        "consumable": False,
        "food": None,
        "use_animation": None,
        "use_duration": None,
        "cooldown": None,
        "allow_off_hand": True,
    }

    # Poké Balls y variantes
    if "ball" in n or "pokeball" in n:
        info["kind"] = "pokeball"
        info["category"] = "equipment"
        info["hand_equipped"] = True
        info["throwable"] = True
        info["cooldown"] = {"category": "cobblemon_pokeball", "duration": 1.0}
        info["use_animation"] = "bow"
        info["max_stack_size"] = 16 if any(x in n for x in ("master", "origin", "cherish", "beast")) else 64
        return info

    # Bayas y comida
    if "berry" in n or n in {"leftovers", "lava_cookie", "old_gateau", "casteliacone", "big_malasada", "lumiose_galette", "rage_candy_bar"}:
        info["kind"] = "food"
        info["category"] = "nature" if "berry" in n else "equipment"
        info["consumable"] = True
        info["food"] = {"nutrition": 2, "saturation_modifier": "low", "can_always_eat": True}
        info["use_animation"] = "eat"
        info["use_duration"] = 1.6
        return info

    # Curación/medicina
    if any(x in n for x in ("potion", "heal", "revive", "antidote", "burn_heal", "ice_heal", "paralyze_heal", "awakening", "full_restore", "ether", "elixir", "fresh_water", "soda_pop", "lemonade", "moomoo_milk")):
        info["kind"] = "medicine"
        info["category"] = "equipment"
        info["consumable"] = True
        info["use_animation"] = "drink" if any(x in n for x in ("potion", "water", "soda", "lemonade", "milk", "ether", "elixir")) else "eat"
        info["use_duration"] = 1.6
        return info

    # Caramelos/experiencia/mejoras
    if any(x in n for x in ("candy", "rare_candy", "exp_", "vitamin", "protein", "iron", "calcium", "zinc", "carbos", "hp_up", "pp_", "feather")):
        info["kind"] = "enhancement"
        info["category"] = "equipment"
        info["consumable"] = True
        info["use_animation"] = "eat"
        info["use_duration"] = 1.6
        return info

    # Piedras evolutivas / objetos clave de evolución
    if any(x in n for x in ("stone", "evo", "link_cable", "upgrade", "dubious_disc", "protector", "electirizer", "magmarizer", "prism_scale", "reaper_cloth", "sachet", "whipped_dream", "sweet", "apple", "galarica", "scroll", "fossil")):
        info["kind"] = "evolution"
        info["category"] = "items"
        info["hand_equipped"] = "sword" in n or "shield" in n
        return info

    # MTs/HMs y aprendizaje
    if n.startswith("tm_") or n.startswith("hm_") or n.startswith("tr_") or "move_tutor" in n:
        info["kind"] = "move"
        info["category"] = "items"
        info["max_stack_size"] = 1
        return info

    # Herramientas utilitarias
    if any(x in n for x in ("rod", "pokedex", "healer", "pc", "pasture", "candy_jar", "campfire_pot", "bottle_cap", "mint")):
        info["kind"] = "utility"
        info["category"] = "equipment"
        info["hand_equipped"] = True
        info["max_stack_size"] = 1 if any(x in n for x in ("pokedex", "rod")) else 64
        return info

    return info


def _build_item_components(item_name: str, icon_shortname: str, classification: dict[str, Any]) -> dict[str, Any]:
    components: dict[str, Any] = {
        "minecraft:icon": {"textures": {"default": icon_shortname}},
        "minecraft:display_name": {"value": f"item.cobblemon.{item_name}.name"},
        "minecraft:max_stack_size": classification["max_stack_size"],
    }

    if classification.get("hand_equipped"):
        components["minecraft:hand_equipped"] = True

    if classification.get("allow_off_hand"):
        components["minecraft:allow_off_hand"] = True

    # Consumibles/comida
    if classification.get("food"):
        components["minecraft:food"] = classification["food"]
        components["minecraft:use_modifiers"] = {
            "use_duration": classification.get("use_duration", 1.6),
            "movement_modifier": 0.35,
        }
        components["minecraft:use_animation"] = classification.get("use_animation", "eat")

    # Poké Balls: mecánica básica de lanzamiento (aproximación Bedrock)
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

    return components


def convert_items(mod, writer) -> int:
    """Convierte ítems de Cobblemon con mejor resolución de texturas y componentes."""
    item_count = 0
    seen: set[str] = set()

    for model_path in mod.source.glob(f"assets/{mod.namespace}/models/item/"):
        if not model_path.endswith(".json"):
            continue
        item_name = model_path.rsplit("/", 1)[-1][:-5]
        if not item_name or item_name in seen:
            continue
        seen.add(item_name)

        model_data = _safe_read_json(mod.source, model_path) or {}
        tex_path = _resolve_item_texture_path(mod, item_name, model_data)
        if not tex_path:
            continue

        try:
            tex_data = mod.source.read_bytes(tex_path)
        except Exception:
            continue

        # Registrar textura del ítem (RP)
        rp_tex_path = f"textures/items/cobblemon/{item_name}"
        writer.rp_blob(rp_tex_path + ".png", tex_data)
        icon_shortname = f"cobblemon_{item_name}"
        try:
            writer.add_item_texture(icon_shortname, rp_tex_path)
        except Exception:
            # Fallback: algunos writers esperan sin prefijos repetidos
            writer.add_item_texture(icon_shortname, f"textures/items/cobblemon/{item_name}")

        classification = _classify_item(item_name)
        components = _build_item_components(item_name, icon_shortname, classification)

        item_def = {
            "format_version": "1.20.50",
            "minecraft:item": {
                "description": {
                    "identifier": f"cobblemon:{item_name}",
                    "menu_category": {"category": classification["category"]},
                },
                "components": components,
            },
        }

        writer.bp_json(f"items/cobblemon_{_slug(item_name)}.json", item_def)

        # Nombre legible básico (si no hay lang ya gestionado para este item)
        display = item_name.replace("_", " ").strip().title()
        try:
            writer.add_lang("en_US", f"item.cobblemon.{item_name}.name", display)
        except Exception:
            pass

        item_count += 1

    print(f"  [OK] Items convertidos (mejorados): {item_count}")
    return item_count
