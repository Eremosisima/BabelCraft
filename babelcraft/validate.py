"""Validador estructural del addon generado.

No pregunta a un modelo si el resultado "parece bien": comprueba las
reglas que Bedrock exige de verdad y que rompen el pack cuando fallan:

  - JSON válido en todos los documentos.
  - manifests con UUIDs válidos, módulos y dependencia BP -> RP.
  - toda textura de ``item_texture.json`` / ``terrain_texture.json``
    existe como PNG en el RP.
  - todo ``material_instances`` de bloque apunta a un shortname
    registrado (o avisa si es de otro pack).
  - toda geometría/animación/render controller referenciada existe.
  - todo ``minecraft:loot`` apunta a un loot table emitido.
  - recetas: identificador, unlock obligatorio (1.20.10+), resultado e
    ingredientes con formato correcto.
  - límites de Bedrock: texture handles (recomendado 800, duro 4000).

Los hallazgos van a ``result.findings`` con severidad error/warn/info y
código estable (``ref.texture_missing``...). Un error significa que el
addon está roto; un aviso, que funciona pero con pérdidas documentadas.
"""

from __future__ import annotations

import json
import re

from .model import ConversionResult

_ID_RE = re.compile(r"^[a-z0-9_.:-]+$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_VANILLA_TEXTURE_PATHS = {"textures/misc/enchanted_item_glint"}


def validate(writer, result: ConversionResult) -> ConversionResult:
    """Ejecuta todas las comprobaciones y devuelve el mismo resultado."""
    parsed = {"bp": {}, "rp": {}}
    _parse_all(writer, parsed, result)

    textures = _rp_textures(writer)
    geometries = _geometry_ids(parsed)
    animations = _animation_ids(parsed)
    controllers = _render_controller_ids(parsed)
    anim_controllers = _animation_controller_ids(parsed)
    loot_paths = {p for p in writer.bp if p.startswith("loot_tables/") and p.endswith(".json")}

    _check_manifests(parsed, result)
    _check_texture_indexes(parsed, textures, result)
    _check_blocks_json(parsed, result)
    _check_items(parsed, result)
    _check_blocks(parsed, textures, geometries, loot_paths, result)
    _check_attachables(parsed, textures, geometries, animations, controllers, anim_controllers, result)
    _check_entities(parsed, textures, geometries, animations, controllers, anim_controllers, loot_paths, result)
    _check_animation_docs(parsed, result)
    _check_recipes(parsed, result)
    _check_loot(parsed, result)
    _check_limits(writer, textures, result)
    return result


# ---------------------------------------------------------------------------
#  Índices
# ---------------------------------------------------------------------------


def _parse_all(writer, parsed: dict, result: ConversionResult) -> None:
    for side, tree in (("bp", writer.bp), ("rp", writer.rp)):
        for rel, data in tree.items():
            if not rel.endswith(".json"):
                continue
            if data[:3] == b"\xef\xbb\xbf":
                result.error("json.bom", f"{side}/{rel}", "el documento lleva BOM; Bedrock no lo acepta")
            try:
                parsed[side][rel] = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                result.error("json.invalid", f"{side}/{rel}", f"JSON inválido: {exc}")


def _rp_textures(writer) -> set[str]:
    return {
        rel[:-4]
        for rel in writer.rp
        if rel.endswith(".png")
    }


def _geometry_ids(parsed: dict) -> set[str]:
    out: set[str] = set()
    for rel, doc in parsed["rp"].items():
        if not rel.endswith(".geo.json") or not isinstance(doc, dict):
            continue
        geo = doc.get("minecraft:geometry")
        for item in geo if isinstance(geo, list) else [geo]:
            if isinstance(item, dict):
                ident = (item.get("description") or {}).get("identifier")
                if isinstance(ident, str):
                    out.add(ident)
    return out


def _animation_ids(parsed: dict) -> set[str]:
    out: set[str] = set()
    for rel, doc in parsed["rp"].items():
        if not rel.endswith(".animation.json") or not isinstance(doc, dict):
            continue
        anims = doc.get("animations")
        if isinstance(anims, dict):
            out |= set(anims.keys())
    return out


def _render_controller_ids(parsed: dict) -> set[str]:
    out: set[str] = set()
    for rel, doc in parsed["rp"].items():
        if not rel.startswith("render_controllers/") or not isinstance(doc, dict):
            continue
        rcs = doc.get("render_controllers")
        if isinstance(rcs, dict):
            out |= set(rcs.keys())
    return out


def _animation_controller_ids(parsed: dict) -> set[str]:
    """Ids definidos en los documentos `animation_controllers/` del RP."""
    out: set[str] = set()
    for rel, doc in parsed["rp"].items():
        if not rel.startswith("animation_controllers/") or not isinstance(doc, dict):
            continue
        ctrls = doc.get("animation_controllers")
        if isinstance(ctrls, dict):
            out |= set(ctrls.keys())
    return out


def _index_shortnames(parsed: dict, side_file: str) -> dict[str, object]:
    doc = parsed["rp"].get(side_file)
    if not isinstance(doc, dict):
        return {}
    data = doc.get("texture_data")
    return data if isinstance(data, dict) else {}


def _texture_path_of(value) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        path = value.get("path")
        if isinstance(path, str):
            return path
    return None


# ---------------------------------------------------------------------------
#  Comprobaciones
# ---------------------------------------------------------------------------


def _check_manifests(parsed: dict, result: ConversionResult) -> None:
    uuids: dict[str, str] = {}
    for side in ("bp", "rp"):
        doc = parsed[side].get("manifest.json")
        if not isinstance(doc, dict):
            result.error("manifest.missing", f"{side}/manifest.json", "falta el manifest")
            continue
        header = doc.get("header") or {}
        uid = header.get("uuid")
        if not isinstance(uid, str) or not _UUID_RE.match(uid):
            result.error("manifest.uuid", f"{side}/manifest.json", "UUID de cabecera inválido")
        else:
            uuids[side] = uid
        version = header.get("version")
        if not isinstance(version, list) or len(version) != 3:
            result.error("manifest.version", f"{side}/manifest.json", "versión de pack inválida")
        engine = header.get("min_engine_version")
        if not isinstance(engine, list) or len(engine) != 3:
            result.error("manifest.min_engine", f"{side}/manifest.json", "min_engine_version inválida")
        modules = doc.get("modules")
        if not isinstance(modules, list) or not modules:
            result.error("manifest.modules", f"{side}/manifest.json", "sin módulos")
        else:
            for mod in modules:
                uuid_m = (mod or {}).get("uuid") if isinstance(mod, dict) else None
                if not isinstance(uuid_m, str) or not _UUID_RE.match(uuid_m):
                    result.error("manifest.module_uuid", f"{side}/manifest.json", "UUID de módulo inválido")
    bp = parsed["bp"].get("manifest.json") or {}
    deps = bp.get("dependencies") if isinstance(bp, dict) else None
    rp_uuid = uuids.get("rp")
    if rp_uuid and (not isinstance(deps, list) or not any(
        isinstance(d, dict) and d.get("uuid") == rp_uuid for d in deps
    )):
        result.warn(
            "manifest.dependency",
            "bp/manifest.json",
            "el BP no declara dependencia del RP: en algunos dispositivos el RP no se activa solo",
        )


def _check_texture_indexes(parsed: dict, textures: set[str], result: ConversionResult) -> None:
    for side_file, label in (
        ("textures/item_texture.json", "item_texture"),
        ("textures/terrain_texture.json", "terrain_texture"),
    ):
        for shortname, value in _index_shortnames(parsed, side_file).items():
            path = _texture_path_of(value)
            if path is None:
                result.warn(
                    "index.bad_entry",
                    f"rp/{side_file}",
                    f"entrada '{shortname}' sin ruta de textura legible",
                )
                continue
            if path not in textures:
                result.error(
                    "ref.texture_missing",
                    f"rp/{side_file}",
                    f"'{shortname}' apunta a {path}.png, que no existe en el RP",
                )


def _check_blocks_json(parsed: dict, result: ConversionResult) -> None:
    doc = parsed["rp"].get("blocks.json")
    if not isinstance(doc, dict):
        return
    terrain = set(_index_shortnames(parsed, "textures/terrain_texture.json"))
    for ident, entry in doc.items():
        if ident == "format_version" or not isinstance(entry, dict):
            continue
        if not _ID_RE.match(ident):
            result.warn("ident.invalid", "rp/blocks.json", f"identificador inválido: {ident}")
        tex = entry.get("textures")
        values = tex.values() if isinstance(tex, dict) else [tex]
        for v in values:
            if isinstance(v, str) and v not in terrain:
                result.warn(
                    "ref.shortname_unknown",
                    "rp/blocks.json",
                    f"{ident}: shortname '{v}' no está en terrain_texture.json (¿textura vanilla u otro pack?)",
                )


def _check_items(parsed: dict, result: ConversionResult) -> None:
    index = set(_index_shortnames(parsed, "textures/item_texture.json"))
    for rel, doc in parsed["bp"].items():
        if not rel.startswith("items/") or not isinstance(doc, dict):
            continue
        item = doc.get("minecraft:item")
        if not isinstance(item, dict):
            result.error("item.structure", f"bp/{rel}", "sin 'minecraft:item'")
            continue
        desc = item.get("description") or {}
        ident = desc.get("identifier")
        if not isinstance(ident, str) or not _ID_RE.match(ident):
            result.error("ident.invalid", f"bp/{rel}", f"identificador de ítem inválido: {ident!r}")
        category = (desc.get("menu_category") or {}).get("category")
        if category is not None and category not in ("construction", "nature", "equipment", "items", "none"):
            result.warn("item.menu", f"bp/{rel}", f"categoría de menú desconocida: {category!r}")
        components = item.get("components") or {}
        icon = components.get("minecraft:icon")
        if isinstance(icon, str):
            if index and icon not in index:
                result.error(
                    "ref.item_icon",
                    f"bp/{rel}",
                    f"el icono '{icon}' no está registrado en item_texture.json",
                )
        elif isinstance(icon, dict):
            for key, value in (icon.get("textures") or {}).items():
                if isinstance(value, str) and index and value not in index:
                    result.error(
                        "ref.item_icon",
                        f"bp/{rel}",
                        f"el icono '{key}'='{value}' no está registrado en item_texture.json",
                    )
        else:
            result.warn("item.icon", f"bp/{rel}", "ítem sin minecraft:icon legible")
        stack = components.get("minecraft:max_stack_size", 64)
        if not isinstance(stack, int) or not (1 <= stack <= 99):
            result.warn("item.stack", f"bp/{rel}", f"max_stack_size fuera de rango: {stack!r}")


def _check_blocks(
    parsed: dict,
    textures: set[str],
    geometries: set[str],
    loot_paths: set[str],
    result: ConversionResult,
) -> None:
    terrain = set(_index_shortnames(parsed, "textures/terrain_texture.json"))
    items = set(_index_shortnames(parsed, "textures/item_texture.json"))
    for rel, doc in parsed["bp"].items():
        if not rel.startswith("blocks/") or not isinstance(doc, dict):
            continue
        block = doc.get("minecraft:block")
        if not isinstance(block, dict):
            result.error("block.structure", f"bp/{rel}", "sin 'minecraft:block'")
            continue
        desc = block.get("description") or {}
        ident = desc.get("identifier")
        if not isinstance(ident, str) or not _ID_RE.match(ident):
            result.error("ident.invalid", f"bp/{rel}", f"identificador de bloque inválido: {ident!r}")
        components = block.get("components") or {}

        geo = components.get("minecraft:geometry")
        if isinstance(geo, str) and geo not in geometries and geo != "minecraft:geometry.full_block":
            result.error("ref.geometry", f"bp/{rel}", f"geometría '{geo}' no existe en el RP")
        elif isinstance(geo, dict):
            ref = geo.get("identifier")
            if isinstance(ref, str) and ref not in geometries:
                result.error("ref.geometry", f"bp/{rel}", f"geometría '{ref}' no existe en el RP")

        mats = components.get("minecraft:material_instances")
        if isinstance(mats, dict):
            for name, mat in mats.items():
                tex = (mat or {}).get("texture") if isinstance(mat, dict) else None
                if not isinstance(tex, str):
                    result.warn("block.material", f"bp/{rel}", f"material '{name}' sin textura")
                elif tex not in terrain and tex not in items:
                    result.warn(
                        "ref.shortname_unknown",
                        f"bp/{rel}",
                        f"material '{name}': shortname '{tex}' no registrado (¿vanilla u otro pack?)",
                    )
        else:
            result.warn("block.material", f"bp/{rel}", "bloque sin minecraft:material_instances")

        loot = components.get("minecraft:loot")
        if isinstance(loot, str) and loot not in loot_paths:
            result.error("ref.loot", f"bp/{rel}", f"loot table '{loot}' no existe en el BP")

        for key in ("minecraft:collision_box", "minecraft:selection_box"):
            box = components.get(key)
            if isinstance(box, dict):
                w, h = box.get("width", 1), box.get("height", 1)
                if not isinstance(w, (int, float)) or not isinstance(h, (int, float)) or w <= 0 or h <= 0:
                    result.error("block.box", f"bp/{rel}", f"{key} con dimensiones no válidas")


def _check_attachables(
    parsed: dict,
    textures: set[str],
    geometries: set[str],
    animations: set[str],
    controllers: set[str],
    anim_controllers: set[str],
    result: ConversionResult,
) -> None:
    for rel, doc in parsed["rp"].items():
        if not rel.startswith("attachables/") or not isinstance(doc, dict):
            continue
        att = doc.get("minecraft:attachable")
        if not isinstance(att, dict):
            result.error("attachable.structure", f"rp/{rel}", "sin 'minecraft:attachable'")
            continue
        desc = att.get("description") or {}
        ident = desc.get("identifier")
        if not isinstance(ident, str) or not _ID_RE.match(ident):
            result.error("ident.invalid", f"rp/{rel}", f"identificador inválido: {ident!r}")

        tex = (desc.get("textures") or {}).get("default")
        if isinstance(tex, str) and tex not in _VANILLA_TEXTURE_PATHS and tex not in textures:
            result.error("ref.texture_missing", f"rp/{rel}", f"textura '{tex}.png' no existe en el RP")

        geo = (desc.get("geometry") or {}).get("default")
        if isinstance(geo, str) and geo not in geometries:
            result.error("ref.geometry", f"rp/{rel}", f"geometría '{geo}' no existe en el RP")

        _check_animation_refs(desc, animations, anim_controllers, f"rp/{rel}", result)

        for rc in desc.get("render_controllers") or []:
            rc_id = rc.get("controller") if isinstance(rc, dict) else rc
            if isinstance(rc_id, str) and rc_id not in controllers:
                result.error("ref.render_controller", f"rp/{rel}", f"render controller '{rc_id}' no existe")


def _check_entities(
    parsed: dict,
    textures: set[str],
    geometries: set[str],
    animations: set[str],
    controllers: set[str],
    anim_controllers: set[str],
    loot_paths: set[str],
    result: ConversionResult,
) -> None:
    for rel, doc in parsed["rp"].items():
        if not rel.startswith("entity/") or not isinstance(doc, dict):
            continue
        client = doc.get("minecraft:client_entity")
        if not isinstance(client, dict):
            continue
        desc = client.get("description") or {}
        ident = desc.get("identifier")
        if not isinstance(ident, str) or not _ID_RE.match(ident):
            result.error("ident.invalid", f"rp/{rel}", f"identificador inválido: {ident!r}")

        tex = (desc.get("textures") or {}).get("default")
        if isinstance(tex, str) and tex not in _VANILLA_TEXTURE_PATHS and tex not in textures:
            result.error("ref.texture_missing", f"rp/{rel}", f"textura '{tex}.png' no existe en el RP")

        geo = (desc.get("geometry") or {}).get("default")
        if isinstance(geo, str) and geo not in geometries:
            result.error("ref.geometry", f"rp/{rel}", f"geometría '{geo}' no existe en el RP")

        _check_animation_refs(desc, animations, anim_controllers, f"rp/{rel}", result)

        for rc in desc.get("render_controllers") or []:
            rc_id = rc.get("controller") if isinstance(rc, dict) else rc
            if isinstance(rc_id, str) and rc_id not in controllers:
                result.error("ref.render_controller", f"rp/{rel}", f"render controller '{rc_id}' no existe")

        egg = desc.get("spawn_egg")
        if isinstance(egg, dict):
            for key in ("base_color", "overlay_color"):
                val = egg.get(key)
                if not isinstance(val, str) or not re.match(r"^#[0-9A-Fa-f]{6}$", val):
                    result.warn("entity.spawn_egg", f"rp/{rel}", f"{key} no es un color #RRGGBB: {val!r}")

    for rel, doc in parsed["bp"].items():
        if not rel.startswith("entities/") or not isinstance(doc, dict):
            continue
        entity = doc.get("minecraft:entity")
        if not isinstance(entity, dict):
            continue
        components = entity.get("components") or {}
        loot = components.get("minecraft:loot")
        if isinstance(loot, str) and loot not in loot_paths:
            result.error("ref.loot", f"bp/{rel}", f"loot table '{loot}' no existe en el BP")
        box = components.get("minecraft:collision_box")
        if isinstance(box, dict):
            w, h = box.get("width"), box.get("height")
            if not isinstance(w, (int, float)) or not isinstance(h, (int, float)) or w <= 0 or h <= 0:
                result.error("entity.box", f"bp/{rel}", "collision_box con dimensiones no válidas")
        health = components.get("minecraft:health")
        if isinstance(health, dict):
            val, mx = health.get("value"), health.get("max")
            if isinstance(val, (int, float)) and isinstance(mx, (int, float)) and val > mx:
                result.warn("entity.health", f"bp/{rel}", "health.value > health.max")


def _check_animation_refs(desc: dict, animations: set[str], anim_controllers: set[str], path: str, result: ConversionResult) -> None:
    """Comprueba el mapa de animaciones y los alias de `scripts.animate`.

    El mapa de animaciones del client entity mezcla dos cosas: alias ->
    animación y alias -> controlador de animación. Se resuelve contra los
    documentos que existen de verdad en el RP (no contra los render
    controllers, que son otra familia).
    """
    anim_map = desc.get("animations")
    if not isinstance(anim_map, dict):
        anim_map = {}
    for key, value in anim_map.items():
        if not isinstance(value, str):
            continue
        if value in anim_controllers or value in animations:
            continue
        if value.startswith("controller."):
            result.error(
                "ref.animation_controller",
                path,
                f"el controlador de animación '{value}' no existe en el RP",
            )
        else:
            result.error("ref.animation", path, f"la animación '{value}' no existe en el RP")

    scripts = desc.get("scripts")
    if not isinstance(scripts, dict):
        return
    for item in scripts.get("animate") or []:
        if isinstance(item, str):
            if item not in anim_map:
                result.warn(
                    "ref.animation_alias",
                    path,
                    f"'{item}' no está en el mapa de animaciones del client entity",
                )
        elif isinstance(item, dict):
            for alias in item:
                if isinstance(alias, str) and alias not in anim_map:
                    result.warn(
                        "ref.animation_alias",
                        path,
                        f"'{alias}' no está en el mapa de animaciones del client entity",
                    )


def _check_animation_docs(parsed: dict, result: ConversionResult) -> None:
    for rel, doc in parsed["rp"].items():
        if rel.startswith("animations/") and rel.endswith(".animation.json"):
            _check_animation_doc(rel, doc, result)
        elif rel.startswith("animation_controllers/") and rel.endswith(".animation_controllers.json"):
            _check_controller_doc(rel, doc, result)


def _check_animation_doc(rel: str, doc, result: ConversionResult) -> None:
    if not isinstance(doc, dict):
        return
    if not isinstance(doc.get("format_version"), str):
        result.warn("anim.format", f"rp/{rel}", "sin format_version: Bedrock puede ignorar el documento")
    anims = doc.get("animations")
    if not isinstance(anims, dict) or not anims:
        result.error("anim.structure", f"rp/{rel}", "sin bloque 'animations' utilizable")
        return
    for name, anim in anims.items():
        if not isinstance(anim, dict):
            result.error("anim.structure", f"rp/{rel}", f"la animación '{name}' no es un objeto")
            continue
        bones = anim.get("bones")
        effects = any(
            isinstance(anim.get(k), dict) and anim.get(k)
            for k in ("particle_effects", "sound_effects")
        )
        # Un hueso vacío es tan inútil como no tenerlos: la animación no
        # mueve nada.
        if not (isinstance(bones, dict) and bones) and not effects:
            result.error("anim.bones", f"rp/{rel}", f"la animación '{name}' no tiene huesos ni efectos")
            continue
        loop = anim.get("loop")
        if loop is not None and not isinstance(loop, bool) and loop != "hold_on_last_frame":
            result.warn("anim.loop", f"rp/{rel}", f"la animación '{name}' tiene loop={loop!r} no válido")
        length = anim.get("animation_length")
        if length is not None and (
            isinstance(length, bool) or not isinstance(length, (int, float)) or length <= 0
        ):
            result.warn("anim.length", f"rp/{rel}", f"la animación '{name}' tiene animation_length={length!r} no válido")
            continue
        if isinstance(length, (int, float)) and not isinstance(length, bool):
            last = _last_keyframe(anim)
            if last > length + 0.01:
                result.warn(
                    "anim.length",
                    f"rp/{rel}",
                    f"la animación '{name}' tiene un keyframe en {last:g}s y animation_length {length:g}s: se recorta",
                )


def _last_keyframe(anim: dict) -> float:
    mx = 0.0
    bones = anim.get("bones")
    if not isinstance(bones, dict):
        return mx
    for bone in bones.values():
        if not isinstance(bone, dict):
            continue
        for ch in ("rotation", "position", "scale"):
            channel = bone.get(ch)
            if not isinstance(channel, dict):
                continue
            for t in channel:
                try:
                    value = float(t)
                except (TypeError, ValueError):
                    continue
                if value > mx:
                    mx = value
    return mx


def _check_controller_doc(rel: str, doc, result: ConversionResult) -> None:
    if not isinstance(doc, dict):
        return
    if not isinstance(doc.get("format_version"), str):
        result.warn("anim.format", f"rp/{rel}", "sin format_version: Bedrock puede ignorar el documento")
    ctrls = doc.get("animation_controllers")
    if not isinstance(ctrls, dict) or not ctrls:
        result.error("anim.controller_structure", f"rp/{rel}", "sin bloque 'animation_controllers' utilizable")
        return
    for ctrl_id, ctrl in ctrls.items():
        if not isinstance(ctrl, dict):
            result.error("anim.controller_structure", f"rp/{rel}", f"el controlador '{ctrl_id}' no es un objeto")
            continue
        states = ctrl.get("states")
        if not isinstance(states, dict) or not states:
            result.error("anim.controller_states", f"rp/{rel}", f"el controlador '{ctrl_id}' no tiene estados")
            continue
        initial = ctrl.get("initial_state")
        if isinstance(initial, str) and initial not in states:
            result.warn(
                "anim.controller_initial",
                f"rp/{rel}",
                f"el controlador '{ctrl_id}' declara initial_state '{initial}', que no existe",
            )
        for state_name, state in states.items():
            if not isinstance(state, dict):
                result.error(
                    "anim.controller_state",
                    f"rp/{rel}",
                    f"{ctrl_id}.{state_name}: el estado no es un objeto",
                )
                continue
            anims = state.get("animations")
            if anims is not None and not isinstance(anims, list):
                result.warn(
                    "anim.controller_animations",
                    f"rp/{rel}",
                    f"{ctrl_id}.{state_name}: 'animations' debe ser una lista",
                )
            transitions = state.get("transitions")
            if transitions is not None and not isinstance(transitions, list):
                result.warn(
                    "anim.controller_transitions",
                    f"rp/{rel}",
                    f"{ctrl_id}.{state_name}: 'transitions' debe ser una lista",
                )


def _check_recipes(parsed: dict, result: ConversionResult) -> None:
    emitted = set()
    for rel, doc in parsed["bp"].items():
        if rel.startswith("items/") and isinstance(doc, dict):
            ident = ((doc.get("minecraft:item") or {}).get("description") or {}).get("identifier")
            if isinstance(ident, str):
                emitted.add(ident)
        if rel.startswith("blocks/") and isinstance(doc, dict):
            ident = ((doc.get("minecraft:block") or {}).get("description") or {}).get("identifier")
            if isinstance(ident, str):
                emitted.add(ident)

    for rel, doc in parsed["bp"].items():
        if not rel.startswith("recipes/") or not isinstance(doc, dict):
            continue
        kinds = [k for k in doc if k.startswith("minecraft:recipe_")]
        if len(kinds) != 1:
            result.error("recipe.structure", f"bp/{rel}", "el documento no tiene exactamente una receta")
            continue
        recipe = doc[kinds[0]]
        if not isinstance(recipe, dict):
            result.error("recipe.structure", f"bp/{rel}", "cuerpo de receta inválido")
            continue
        ident = (recipe.get("description") or {}).get("identifier")
        if not isinstance(ident, str) or not _ID_RE.match(ident):
            result.error("ident.invalid", f"bp/{rel}", f"identificador de receta inválido: {ident!r}")
        unlock = recipe.get("unlock")
        if unlock is not None and (not isinstance(unlock, list) or not unlock):
            result.error("recipe.unlock", f"bp/{rel}", "unlock vacío: la receta no aparecerá en el libro")
        res = recipe.get("result")
        if isinstance(res, dict):
            item = res.get("item")
            if isinstance(item, str):
                ns = item.split(":", 1)[0]
                if ns != "minecraft" and item not in emitted:
                    result.warn("recipe.result_unknown", f"bp/{rel}", f"resultado '{item}' no fue emitido por el conversor")
        elif kinds[0] == "minecraft:recipe_furnace":
            out = recipe.get("output")
            if isinstance(out, str) and out.split(":", 1)[0] != "minecraft" and out not in emitted:
                result.warn("recipe.result_unknown", f"bp/{rel}", f"salida '{out}' no fue emitida por el conversor")
        else:
            result.error("recipe.result", f"bp/{rel}", "receta sin resultado legible")
        if kinds[0] == "minecraft:recipe_shaped":
            pattern = recipe.get("pattern")
            key = recipe.get("key")
            if not isinstance(pattern, list) or not pattern:
                result.error("recipe.pattern", f"bp/{rel}", "pattern vacío")
            elif isinstance(key, dict):
                symbols = {sym for row in pattern if isinstance(row, str) for sym in row}
                missing = {s for s in symbols if s != " " and s not in key}
                if missing:
                    result.error("recipe.key", f"bp/{rel}", f"el pattern usa símbolos sin definir: {sorted(missing)}")


def _check_loot(parsed: dict, result: ConversionResult) -> None:
    for rel, doc in parsed["bp"].items():
        if not rel.startswith("loot_tables/") or not isinstance(doc, dict):
            continue
        pools = doc.get("pools")
        if pools is not None and not isinstance(pools, list):
            result.error("loot.pools", f"bp/{rel}", "pools debe ser una lista")
            continue
        for pool in pools or []:
            if not isinstance(pool, dict):
                result.error("loot.pool", f"bp/{rel}", "pool inválido")
                continue
            entries = pool.get("entries")
            if entries is not None and not isinstance(entries, list):
                result.error("loot.entries", f"bp/{rel}", "entries debe ser una lista")


def _check_limits(writer, textures: set[str], result: ConversionResult) -> None:
    handles = len([t for t in textures if t.startswith("textures/")])
    if handles > 4000:
        result.error(
            "limits.texture_handles",
            "rp",
            f"{handles} texturas: Bedrock tiene un límite duro de 4000 texture handles",
        )
    elif handles > 800:
        result.warn(
            "limits.texture_handles",
            "rp",
            f"{handles} texturas: por encima de 800 el motor recomienda atlas (usa --atlas)",
        )
    result.info(
        "limits.files",
        "addon",
        f"BP: {len(writer.bp)} ficheros · RP: {len(writer.rp)} ficheros · texturas: {handles}",
    )
