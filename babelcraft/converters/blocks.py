"""Fase blocks: bloques custom de Java -> bloques Bedrock 1.21.

Entradas:
  - ``assets/<ns>/blockstates/<name>.json`` (hasta 1.21.1) y
    ``assets/<ns>/blocks/<name>.json`` (1.21.2+, misma forma):
    variantes -> modelos.
  - claves de lang ``block.<ns>.<name>`` y bytecode (segunda prueba).

Conversión del modelo:
  - cubo completo (elemento 0..16 sin rotación, parents cube*): sin
    geometría custom — Bedrock ya dibuja el cubo por defecto con
    ``material_instances``. Ahorra un fichero por bloque.
  - otro modelo: geometría custom ``geometry.<ns>_<name>`` +
    ``minecraft:geometry`` + ``minecraft:collision_box`` derivada de los
    bounds REALES de la geometría.
  - multipart (vallas): todos los elementos en una geometría.
  - variantes con estado (facing=north...): Bedrock los soporta con
    permutations/estados, pero el mapeo manual es trabajo de v2: se usa
    la primera variante y se anota. Nada se rompe en silencio.

Componentes de comportamiento (dureza, resistencia): Java los define en
código, no en JSON. Defaults razonables + ``--overrides`` para afinar.
"""

from __future__ import annotations

from .. import versions
from ..entitykit import geometry_bounds
from ..model import Kind, Status, slug
from ..mappings import namespace_of
from .models import (
    geometry_from_model,
    iter_model_texture_refs,
    material_name,
    resolve_model,
)
from .textures import shortname_for

_STATE_DIRS = ("assets/{}/blockstates", "assets/{}/blocks")


def convert(ctx) -> None:
    mod, writer, result = ctx.mod, ctx.writer, ctx.result
    ns = ctx.ns

    for fmt in _STATE_DIRS:
        prefix = fmt.format(ns)
        for path in mod.source.glob(prefix + "/"):
            if not path.endswith(".json"):
                continue
            data = mod.source.read_json_or(path)
            if isinstance(data, dict):
                _convert_block(ctx, path, data)

    # Bloques con loot table pero sin blockstates: son bloques válidos
    # (algunos mods solo definen datapack); cubo por defecto + nota.
    for loot_id in list(ctx.loot_paths):
        if not loot_id.startswith(f"{ns}:blocks/"):
            continue
        name = loot_id.split("/")[1]
        ident = f"{ns}:{name}"
        if ident in ctx.block_ids:
            continue
        if f"block.{ns}.{name}" not in (ctx.lang_tables.get("en_us") or {}):
            continue  # sin segunda prueba: no es un bloque, es ruido
        _emit_block(ctx, path=f"loot:{loot_id}", name=name, models=[], notes=[
            "bloque solo definido en datapack (sin blockstates/modelo): cubo con textura placeholder"
        ], loot_ref=loot_id)


def _convert_block(ctx, path: str, data: dict) -> None:
    mod = ctx.mod
    ns = ctx.ns
    name = path.rsplit("/", 1)[-1][:-5]
    ident = f"{ns}:{name}"
    ctx.block_ids.add(ident)

    notes: list[str] = []
    models: list[str] = []  # rutas de modelos aplicados

    variants = data.get("variants")
    if isinstance(variants, dict):
        if not variants:
            notes.append("blockstates vacío")
        keys = sorted(variants.keys())
        if keys != [""]:
            notes.append(
                f"variantes con estado ({', '.join(keys[:4])}...): Bedrock soporta estados via "
                "permutations; conversion manual. Se usa la primera variante"
            )
        chosen = variants.get("") or variants.get(sorted(keys)[0]) if variants else None
        for entry in _as_list(chosen):
            if isinstance(entry, dict) and isinstance(entry.get("model"), str):
                models.append(entry["model"])
    multipart = data.get("multipart")
    if isinstance(multipart, list):
        for part in multipart:
            if not isinstance(part, dict):
                continue
            if part.get("when") is not None:
                notes.append("multipart condicional (when): se aplican TODAS las partes como si la condición fuese cierta")
            for entry in _as_list(part.get("apply")):
                if isinstance(entry, dict) and isinstance(entry.get("model"), str):
                    models.append(entry["model"])

    _emit_block(ctx, path=path, name=name, models=models, notes=notes, loot_ref=f"{ns}:blocks/{name}")


def _emit_block(ctx, path: str, name: str, models: list[str], notes: list[str], loot_ref: str | None) -> None:
    mod, writer, result = ctx.mod, ctx.writer, ctx.result
    ns = ctx.ns
    ident = f"{ns}:{name}"
    ctx.block_ids.add(ident)

    # Resolver modelos y juntar elementos.
    resolved_list: list[dict] = []
    tex_ids: list[str] = []
    for model_ref in models:
        mns, _, mref = model_ref.partition(":")
        mpath = f"assets/{mns or ns}/models/{mref}.json"
        if not mod.source.exists(mpath):
            notes.append(f"modelo no encontrado: {model_ref}")
            continue
        resolved = resolve_model(ctx, mpath)
        if resolved:
            resolved_list.append(resolved)
            # Marcar el modelo como convertido.
            model_entry = result.entry(mpath, Kind.MODEL)
            model_entry.status = Status.CONVERTED
            for t in sorted(iter_model_texture_refs(resolved)):
                if t not in tex_ids:
                    tex_ids.append(t)

    ov = ctx.overrides.block(ident)

    # Geometría: cubo completo vs custom.
    geometry_id = None
    geo_doc: dict | None = None
    geo_refs: list[str] = []
    collision: bool | dict = True
    if _is_full_cube(resolved_list):
        # Cubo por defecto del motor; sin fichero de geometría.
        pass
    elif resolved_list:
        geometry_id = f"geometry.{ns}_{slug(name)}"
        merged = _merge_models(resolved_list)
        geo_doc, geo_notes, geo_refs = geometry_from_model(ctx, merged, geometry_id, attachable=False)
        notes.extend(geo_notes)
        if geo_doc is None:
            geometry_id = None
            notes.append("el modelo no produce geometría: se usa el cubo por defecto")
        else:
            writer.rp_json(f"models/entity/{ns}_{slug(name)}.geo.json", geo_doc)
            bounds = geometry_bounds(geo_doc["minecraft:geometry"][0])
            if bounds:
                x0, y0, z0, x1, y1, z1 = bounds
                w = max(0.0, (x1 - x0) / 16)
                h = max(0.0, (y1 - y0) / 16)
                # La caja se centra en el bloque: si el modelo está descentrado
                # es una aproximación (anotada).
                off_x = (x0 + x1) / 32
                off_z = (z0 + z1) / 32
                if abs(off_x) > 0.15 or abs(off_z) > 0.15:
                    notes.append("modelo descentrado del bloque: la caja de colisión se centra (aproximación)")
                collision = {
                    "width": round(min(max(w, 0.0625), 1.0), 3),
                    "height": round(min(max(h, 0.0625), 1.0), 3),
                }
    elif models:
        notes.append("sin modelos legibles")

    # Materiales: "*" para el cubo por defecto y una instancia por cada
    # textura que usan las caras de la geometría custom. Si una cara apunta a
    # un material no definido, Bedrock no la dibuja: se cae a "*" y se anota.
    primary = _primary_texture(ctx, resolved_list, tex_ids)
    materials: dict[str, dict] = {}
    tex_override = ov.get("texture")
    if isinstance(tex_override, str) and tex_override:
        # Shortname literal: permite reutilizar texturas vanilla o de otro
        # addon cuyo shortname Bedrock no se deriva del id Java (p.ej. "stone").
        materials["*"] = {
            "texture": tex_override,
            "render_method": str(ov.get("render_method", "opaque")),
        }
        if geo_doc:
            _drop_material_instances(geo_doc)
        notes.append(f"textura forzada por override: {tex_override}")
    else:
        if primary and primary in ctx.tex_rpaths:
            materials["*"] = _material_for(ctx, writer, primary, ov)
        for ref in geo_refs:
            instance = material_name(ref)
            if instance in materials:
                continue
            if ref in ctx.tex_rpaths:
                materials[instance] = _material_for(ctx, writer, ref, ov)
            else:
                notes.append(
                    f"textura {ref} no disponible: sus caras usan el material principal"
                )
        if geo_doc:
            _drop_undefined_materials(geo_doc, materials)
        if not materials:
            notes.append("sin textura resuelta: material sin textura (bloque rosa de Bedrock)")

    # Loot.
    loot_path = ctx.loot_paths.get(loot_ref or "")

    components: dict = {}
    if geometry_id:
        components["minecraft:geometry"] = {"identifier": geometry_id}
    if materials:
        components["minecraft:material_instances"] = materials
    components["minecraft:destructible_by_mining"] = {"seconds_to_destroy": ov.get("seconds_to_destroy", 1.5)}
    components["minecraft:destructible_by_explosion"] = {"explosion_resistance": ov.get("explosion_resistance", 3)}
    components["minecraft:collision_box"] = collision
    components["minecraft:selection_box"] = collision
    if primary and primary in ctx.tex_rpaths:
        components["minecraft:map_color"] = ctx.stats_for(primary)["hex"]
    if loot_path:
        components["minecraft:loot"] = loot_path
    for key, value in ov.items():
        if key not in ("seconds_to_destroy", "explosion_resistance") and key.startswith("minecraft:"):
            components[key] = value
    light = ov.get("light_emission")
    if isinstance(light, int) and light:
        components["minecraft:light_emission"] = light

    doc = {
        "format_version": versions.BLOCK,
        "minecraft:block": {
            "description": {
                "identifier": ident,
                "menu_category": {"category": ctx.overrides.menu.get(ident, "construction")},
            },
            "components": components,
        },
    }
    writer.bp_json(f"blocks/{ns}_{slug(name)}.json", doc)

    # blocks.json (RP): sonido y textura SOLO para cubos por defecto.
    # Bloques con geometría custom no deben estar en blocks.json.
    if not geometry_id:
        visual = materials.get("*")
        if visual:
            writer.add_block_visual(ident, ov.get("sound", "stone"), {"texture": visual["texture"]})

    display = ctx.name_for("block", ident)
    if display:
        writer.add_lang(ctx.opts.lang_out, f"tile.{ns}:{name}.name", display)

    e = result.entry(path, Kind.BLOCK)
    e.status = Status.CONVERTED if not notes else Status.ADAPTED
    for n in notes:
        e.note(n)


# ---------------------------------------------------------------------------


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _material_for(ctx, writer, tex_id: str, ov: dict) -> dict:
    """Instancia de material para una textura, con render_method derivado del arte."""
    stats = ctx.stats_for(tex_id)
    render = ov.get("render_method")
    if not isinstance(render, str) or not render:
        render = "blend" if stats["semi"] else (
            "alpha_test" if _has_alpha(ctx, tex_id, stats) else "opaque"
        )
    short = shortname_for(tex_id)
    writer.add_terrain_texture(short, ctx.tex_rpaths[tex_id])
    return {"texture": short, "render_method": render}


def _cubes(geo_doc: dict):
    geo = geo_doc.get("minecraft:geometry")
    if not isinstance(geo, list) or not geo:
        return
    for bone in geo[0].get("bones") or []:
        for cube in bone.get("cubes") or []:
            if isinstance(cube, dict):
                yield cube


def _drop_material_instances(geo_doc: dict) -> None:
    """Quita `material_instance` de las caras (se usa el material "*")."""
    for cube in _cubes(geo_doc):
        for face in (cube.get("uv") or {}).values():
            if isinstance(face, dict):
                face.pop("material_instance", None)


def _drop_undefined_materials(geo_doc: dict, defined: dict) -> None:
    """Quita las referencias a instancias de material que no existen."""
    for cube in _cubes(geo_doc):
        for face in (cube.get("uv") or {}).values():
            if isinstance(face, dict):
                instance = face.get("material_instance")
                if isinstance(instance, str) and instance not in defined:
                    face.pop("material_instance", None)


def _primary_texture(ctx, resolved_list: list[dict], tex_ids: list[str]) -> str | None:
    for resolved in resolved_list:
        tex = resolved.get("textures") or {}
        for pref in ("all", "particle", "side", "top", "bottom", "north", "end", "cross"):
            v = tex.get(pref)
            if isinstance(v, str) and v and not v.startswith("#"):
                return v
        for v in tex.values():
            if isinstance(v, str) and v and not v.startswith("#"):
                return v
    return tex_ids[0] if tex_ids else None


def _has_alpha(ctx, tex_id: str, stats: dict) -> bool:
    """¿La textura tiene píxeles transparentes? (decide alpha_test)."""
    rpath = ctx.tex_rpaths.get(tex_id)
    if not rpath:
        return False
    from ..pngcodec import decode_png

    png = decode_png(ctx.writer.rp.get(rpath + ".png", b""))
    if png is None:
        return False
    return any(png.pixels[i + 3] == 0 for i in range(0, len(png.pixels), 4))


def _is_full_cube(resolved_list: list[dict]) -> bool:
    """Cubo 0..16 sin rotación en el primer modelo aplicado."""
    if not resolved_list:
        return False
    r = resolved_list[0]
    elements = r.get("elements")
    if not isinstance(elements, list) or len(elements) != 1:
        return False
    el = elements[0]
    if not isinstance(el, dict):
        return False
    fr, to = el.get("from"), el.get("to")
    if fr != [0, 0, 0] or to != [16, 16, 16]:
        return False
    if el.get("rotation"):
        return False
    return True


def _merge_models(resolved_list: list[dict]) -> dict:
    """Varios modelos aplicados (multipart) -> un modelo con todo."""
    merged = {"elements": [], "textures": {}, "display": {}, "flat": False}
    for r in resolved_list:
        merged["elements"].extend(r.get("elements") or [])
        merged["textures"].update(r.get("textures") or {})
    return merged
