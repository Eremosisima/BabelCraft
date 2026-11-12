"""Fase entities: entidades GeckoLib -> BP + RP de Bedrock.

Por qué GeckoLib: los mods modernos (1.16+) dibujan entidades con
GeckoLib, cuyo formato de modelo YA es el de Bedrock (``minecraft:geometry``
1.12.0) y cuyas animaciones también (``format_version`` 1.8.0). La
conversión honesta no es "traducir lógica Java": es reensamblar el
contenido declarativo (modelo + textura + animaciones) y darle el
comportamiento Bedrock mínimo que lo hace existir como criatura.

Qué se genera por entidad:
  - RP ``models/entity/<ns>_<name>.geo.json``     (geometría)
  - RP ``animations/<ns>_<name>.animation.json``  (animaciones, opcional)
  - RP ``textures/entity/<ns>/<name>.png``        (textura)
  - RP ``entity/<ns>_<name>.entity.json``         (client entity + huevo)
  - BP ``entity/<ns>_<name>.entity.json``         (criatura: física,
    caja de colisión medida del modelo, loot si su tabla se convirtió)

Optimización de RAM (opcional, ``--atlas`` o ``--variant mobile``),
portada de ``CobblemonBedrock/tools`` donde se midió sobre 1074
especies:
  - **atlas**: todas las texturas en UNA imagen; las UV de cada geometría
    pasan a ser locales a su celda y un render controller con ``uv_anim``
    aplica offset/escala por entidad. Un solo "texture handle" para todo
    el addon (el límite recomendado son 800, el duro 4000).
  - **poda de huesos** y **adelgazado de animaciones**: quitan lo que no
    se reproduce, sin cambiar el resultado visible.

Lo que NO se convierte (y el informe dice): el cerebro del mob (IA,
metas, hechizos), el spawn natural, los sonidos ligados a eventos y las
variantes de modelo por estado. Todo eso vive en código o en datos con
otra forma y se hace a mano.
"""

from __future__ import annotations

import json

from .. import versions
from ..animkit import (
    build_aliases,
    controller_alias,
    controller_refs,
    sanitize_animations,
    sanitize_controllers,
    select_slots,
    unique_alias,
)
from ..entitykit import (
    blit_into_atlas,
    geometry_bounds,
    normalize_geometry_to_cell,
    plan_grid,
    prune_bones,
    thin_animation,
)
from ..model import Kind, Status, slug
from ..pngcodec import decode_png, encode_png, texture_stats
from ..pngcodec import Png

_GEO_DIRS = ("assets/{}/geo", "assets/{}/models/entity", "assets/{}/geckolib/models")
_ANIM_DIRS = (
    "assets/{}/animations",
    "assets/{}/animations/entity",
    "assets/{}/geckolib/animations",
)
_CTRL_DIRS = (
    "assets/{}/animation_controllers",
    "assets/{}/geckolib/animation_controllers",
)
# Layout de Cobblemon: bedrock/<categoria>/models|animations/<dir>/<name>.<tipo>.json
_COBBLEMON_LAYOUT = "assets/{}/bedrock"

DEFAULT_MATERIAL = "entity_alphatest"
_ATLAS_TEXTURE = "textures/entity/atlas"


def convert(ctx) -> None:
    mod, writer, result = ctx.mod, ctx.writer, ctx.result
    ns = ctx.ns

    records: list[dict] = []
    seen: set[str] = set()

    # 1. Layouts estándar (geo/, models/entity/, geckolib/models/).
    for fmt in _GEO_DIRS:
        for path in mod.source.glob(fmt.format(ns) + "/"):
            if not path.endswith(".json"):
                continue
            name = _geo_name(path)
            if not name or name in seen:
                continue
            seen.add(name)
            rec = _build_entity(ctx, path, name)
            if rec:
                records.append(rec)

    # 2. Layout de Cobblemon: bedrock/<categoria>/models/<dir>/<name>.geo.json
    cobblemon_prefix = _COBBLEMON_LAYOUT.format(ns) + "/"
    for path in mod.source.glob(cobblemon_prefix):
        if not path.endswith(".geo.json") or "/models/" not in path:
            continue
        name = _geo_name(path)
        if not name or name in seen:
            continue
        seen.add(name)
        rec = _build_entity(ctx, path, name)
        if rec:
            records.append(rec)

    if records:
        if ctx.opts.atlas and len([r for r in records if r["png"] is not None]) >= 2:
            _build_atlas(ctx, records)
        else:
            _write_without_atlas(ctx, records)

    # Entidades declaradas solo en lang/bytecode: sin modelo no hay nada
    # que convertir de forma fiel; se reportan en vez de inventarlas.
    lang = ctx.lang_tables.get("en_us") or {}
    for key in lang:
        if not key.startswith(f"entity.{ns}."):
            continue
        name = key[len(f"entity.{ns}."):]
        name = name[:-5] if name.endswith(".name") else name
        if (
            name
            and name not in seen
            and name not in ctx.entity_ids
            and f"entity.{ns}.{name}" not in ctx.result.entries
        ):
            result.residue(
                f"lang:entity.{ns}.{name}",
                Kind.ENTITY,
                "entidad declarada en lang pero sin geometría GeckoLib: no hay modelo que "
                "convertir. Usa Blockbench/GeckoLib para su geo o deja el mob fuera del addon",
            )


# ---------------------------------------------------------------------------
#  Construcción de una entidad (sin escribir aún: el atlas puede cambiar UVs)
# ---------------------------------------------------------------------------


def _geo_name(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    for suffix in (".geo.json", ".json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _build_entity(ctx, path: str, name: str) -> dict | None:
    mod, result = ctx.mod, ctx.result
    ns = ctx.ns
    e = result.entry(path, Kind.ENTITY)

    data = mod.source.read_json_or(path)
    if not isinstance(data, dict):
        e.status = Status.RESIDUE
        e.note("geometría ilegible")
        return None

    geo_def = _first_geometry(data)
    if not isinstance(geo_def, dict):
        e.status = Status.RESIDUE
        e.note("fichero sin 'minecraft:geometry' legible")
        return None

    notes: list[str] = []
    ident = f"{ns}:{name}"
    geometry_id = f"geometry.{ns}_{slug(name)}"
    desc = geo_def.setdefault("description", {})
    declared = desc.get("identifier")
    declared_short = declared.rsplit(".", 1)[-1] if isinstance(declared, str) else name
    desc["identifier"] = geometry_id

    # Animaciones y controladores: se cargan por nombre de fichero Y por el
    # identificador declarado en la geometría (a veces no coinciden).
    anim_notes: list[str] = []
    ctrl_notes: list[str] = []
    (
        anims_doc,
        ctrls_doc,
        alias_map,
        by_name,
        anim_sources,
        ctrl_sources,
    ) = _load_animation_data(ctx, name, declared_short, anim_notes, ctrl_notes)
    if anim_notes:
        notes.extend(f"animaciones: {n}" for n in anim_notes)
    if ctrl_notes:
        notes.extend(f"controladores: {n}" for n in ctrl_notes)
    if len(anim_sources) > 1:
        notes.append(f"animaciones combinadas de {len(anim_sources)} ficheros")
    _mark_animation_entries(ctx, anim_sources, ctrl_sources, anim_notes, ctrl_notes)

    # Poda de huesos muertos (locators/vacíos) antes de medir nada. Se hace
    # con las animaciones YA saneadas: así no se poda un hueso que una
    # animación sí usa.
    if ctx.opts.prune_bones:
        removed = prune_bones(geo_def, _anim_list(anims_doc))
        if removed:
            notes.append(f"podados {removed} huesos sin cubos ni uso")
    if ctx.opts.thin and anims_doc:
        total = 0
        for anim in anims_doc.get("animations", {}).values():
            total += thin_animation(anim)
        if total:
            notes.append(f"animaciones adelgazadas: {total} keyframes redundantes eliminados")

    # --- Textura.
    tex_path = _find_texture(ctx, name, geo_def)
    png = None
    if tex_path:
        png = decode_png(mod.source.read_bytes(tex_path))
        if png is None:
            notes.append("PNG no legible por el códec: se copia sin analizar")
    if tex_path is None:
        if not ctx.opts.placeholders:
            e.status = Status.RESIDUE
            e.note(
                "sin textura: no se pudo asociar ningún PNG a la entidad "
                f"(buscado en textures/entity/**/{name}.png). Sin textura no se puede dibujar"
            )
            return None
        png = _placeholder_entity_png(name)
        tex_path = f"assets/{ns}/textures/entity/{name}.png"
        notes.append("sin textura: placeholder generado (--placeholders)")

    stats = texture_stats(png)
    bounds = geometry_bounds(geo_def)
    width, height = _collision_from_bounds(bounds, notes)

    ov = ctx.overrides.entity(ident)
    if isinstance(ov.get("width"), (int, float)):
        width = float(ov["width"])
    if isinstance(ov.get("height"), (int, float)):
        height = float(ov["height"])

    server = _server_doc(ctx, ident, width, height, ov)
    client = _client_desc(
        ctx, ident, name, geometry_id, anims_doc, ctrls_doc, alias_map, by_name, stats, notes
    )

    e.status = Status.CONVERTED if not notes else Status.ADAPTED
    for n in notes:
        e.note(n)
    ctx.entity_ids.add(ident)

    # Nombres y huevo.
    display = ctx.name_for("entity", ident) or _title(name)
    ctx.writer.add_lang(ctx.opts.lang_out, f"entity.{ident}.name", display)
    ctx.writer.add_lang(ctx.opts.lang_out, f"item.spawn_egg.entity.{ident}.name", f"Generar {display}")

    return {
        "path": path,
        "name": name,
        "ident": ident,
        "key": f"{ns}_{slug(name)}",
        "geometry_id": geometry_id,
        "geo_doc": {"format_version": data.get("format_version") or versions.GEOMETRY,
                    "minecraft:geometry": [geo_def]},
        "geo_def": geo_def,
        "anims_doc": anims_doc,
        "ctrls_doc": ctrls_doc,
        "png": png,
        "tex_path": tex_path,
        "stats": stats,
        "client": client,
        "server": server,
        "notes": notes,
    }


def _first_geometry(data: dict) -> dict | None:
    geo = data.get("minecraft:geometry")
    if isinstance(geo, list) and geo and isinstance(geo[0], dict):
        return geo[0]
    if isinstance(geo, dict):
        return geo
    # Formato 1.21: la geometría puede venir directamente arriba.
    if "bones" in data and isinstance(data.get("bones"), list):
        return data
    return None


def _load_animation_data(
    ctx,
    name: str,
    identifier_short: str,
    anim_notes: list[str],
    ctrl_notes: list[str],
):
    """Carga, mezcla y sanea animaciones + controladores de una entidad.

    Dos pasadas: primero los documentos dedicados (el fichero se llama
    como la entidad), después los compartidos cuyas claves mencionan la
    entidad o alguno de los nombres que usan los controladores. Así
    funciona con `gob.animation.json`, con `animations/entity/gob...` y
    con un `common.animation.json` lleno de animaciones de varios mobs.
    """
    names = {name, identifier_short}
    raw_anims, anim_paths = _collect_docs(
        ctx, _ANIM_DIRS, names, "animations", notes=anim_notes
    )
    raw_ctrls, ctrl_paths = _collect_docs(
        ctx, _CTRL_DIRS, names, "animation_controllers", notes=ctrl_notes
    )

    # Los controladores dicen qué animaciones necesitan aunque el fichero
    # compartido no mencione el nombre de la entidad.
    if raw_ctrls:
        refs = controller_refs(raw_ctrls)
        if refs:
            extra, extra_paths = _collect_docs(
                ctx, _ANIM_DIRS, names, "animations", wanted=refs, notes=anim_notes
            )
            if extra:
                raw_anims = _merge_docs(raw_anims, extra)
                for path in extra_paths:
                    if path not in anim_paths:
                        anim_paths.append(path)

    anims_doc = sanitize_animations(raw_anims, anim_notes) if raw_anims else None
    alias_map: dict[str, str] = {}
    by_name: dict[str, str] = {}
    ctrls_doc = None

    if anims_doc:
        alias_map, by_name = build_aliases(anims_doc)
        if raw_ctrls:
            ctrls_doc = sanitize_controllers(
                raw_ctrls,
                set(anims_doc.get("animations") or {}),
                by_name,
                ctrl_notes,
            )
    elif raw_ctrls:
        ctrl_notes.append(
            "hay controladores pero ninguna animación asociada: se omiten "
            "(un controlador sin animaciones no reproduce nada)"
        )

    return anims_doc, ctrls_doc, alias_map, by_name, anim_paths, ctrl_paths


def _collect_docs(ctx, dirs, names, block_name: str, wanted=None, notes=None):
    """Recolecta y mezcla bloques `animations` / `animation_controllers`.

    Un fichero corrupto o sin el bloque esperado NO se salta en silencio:
    queda en el libro de cuentas como residuo, y si era dedicado a esta
    entidad se explica además en sus notas.

    Además de los directorios estándar, busca en el layout de Cobblemon
    (bedrock/<cat>/animations/ y bedrock/<cat>/animation_controllers/).
    """
    merged: dict | None = None
    sources: list[str] = []
    seen: set[str] = set()
    stems = {str(n).lower() for n in names if n}

    # Caché de documentos parseados: evita leer el mismo JSON múltiples veces.
    doc_cache_key = f"_anim_doc_cache_{block_name}"
    if not hasattr(ctx, doc_cache_key):
        setattr(ctx, doc_cache_key, {})
    doc_cache = getattr(ctx, doc_cache_key)

    # Índice inverso: nombre de entidad -> archivos que la contienen.
    # Se construye una sola vez al inicio leyendo el contenido de los archivos.
    index_key = f"_anim_index_{block_name}"
    if not hasattr(ctx, index_key):
        # Construir índice: usar nombres de archivo Y nombres mencionados en animaciones.
        index = {}
        
        # Obtener archivos relevantes.
        files = []
        for fmt in dirs:
            prefix = fmt.format(ctx.ns) + "/"
            for path in ctx.mod.source.glob(prefix):
                if path.endswith(".json"):
                    files.append(path)
        block_dir = "animations" if block_name == "animations" else "animation_controllers"
        for path in ctx.mod.source.glob(f"assets/{ctx.ns}/bedrock/"):
            if path.endswith(".json") and f"/{block_dir}/" in path:
                files.append(path)
        
        # Para cada archivo, indexarlo bajo:
        # 1. El stem del nombre del archivo (ej: "bulbasaur.animation.json" -> "bulbasaur")
        # 2. Los nombres de entidades mencionados en las claves de animación
        for path in files:
            stem = _stem(path).lower()
            if stem not in index:
                index[stem] = []
            index[stem].append(path)
            
            # Leer el archivo para extraer nombres de entidades mencionadas.
            data = ctx.mod.source.read_json_or(path)
            if isinstance(data, dict):
                block = data.get(block_name)
                if isinstance(block, dict):
                    # Extraer nombres de entidades de las claves de animación.
                    # Ej: "animation.wisp.fly" -> "wisp"
                    for key in block.keys():
                        if isinstance(key, str) and key.startswith("animation."):
                            parts = key.split(".")
                            if len(parts) >= 2:
                                entity_name = parts[1].lower()
                                if entity_name not in index:
                                    index[entity_name] = []
                                if path not in index[entity_name]:
                                    index[entity_name].append(path)
        
        setattr(ctx, index_key, index)
    
    index = getattr(ctx, index_key)

    def consider(path: str) -> None:
        nonlocal merged
        if not path.endswith(".json") or path in seen:
            return
        
        # Usar caché de documentos parseados.
        if path not in doc_cache:
            data = ctx.mod.source.read_json_or(path)
            doc_cache[path] = data
        data = doc_cache[path]
        
        if data is None:
            ctx.result.residue(
                path, Kind.ANIMATION,
                "JSON ilegible: el documento no se puede leer y se descarta entero",
            )
            if _stem(path).lower() in stems and notes is not None:
                notes.append(f"{path.rsplit('/', 1)[-1]} ilegible: descartado")
            return
        if not isinstance(data, dict):
            return
        block = data.get(block_name)
        if not isinstance(block, dict) or not block:
            if _stem(path).lower() in stems:
                ctx.result.residue(
                    path, Kind.ANIMATION,
                    f"sin bloque '{block_name}' legible: el documento no aporta nada",
                )
                if notes is not None:
                    notes.append(f"{path.rsplit('/', 1)[-1]} sin '{block_name}'")
            return
        stem = _stem(path)
        dedicated = any(
            stem and stem.lower() == str(n).lower() for n in names if n
        )
        picked = (
            dict(block)
            if dedicated
            else {
                k: v
                for k, v in block.items()
                if isinstance(k, str) and _mentions_name(k, names, wanted)
            }
        )
        if not picked:
            return
        if merged is None:
            merged = {"format_version": data.get("format_version"), block_name: {}}
        merged[block_name].update(picked)
        sources.append(path)
        seen.add(path)

    # Usar índice inverso: solo iterar sobre archivos relevantes para esta entidad.
    candidate_files = set()
    for name in names:
        if name:
            name_lower = str(name).lower()
            if name_lower in index:
                candidate_files.update(index[name_lower])
    
    # También incluir archivos dedicados (stem coincide exactamente).
    for name in names:
        if name:
            name_lower = str(name).lower()
            for path, data in doc_cache.items():
                if _stem(path).lower() == name_lower:
                    candidate_files.add(path)
    
    for path in candidate_files:
        consider(path)

    return merged, sources


def _mentions_name(key: str, names, wanted=None) -> bool:
    low = key.lower()
    if any(str(n).lower() in low for n in names if n):
        return True
    if wanted:
        short = low.rsplit(".", 1)[-1]
        for ref in wanted:
            ref_low = str(ref).lower()
            if not ref_low:
                continue
            if (
                short == ref_low
                or low.endswith("." + ref_low)
                or f".{ref_low}." in f".{low}."
            ):
                return True
    return False


def _merge_docs(base: dict | None, extra: dict | None) -> dict | None:
    if not base:
        return extra
    if not extra:
        return base
    for block_name in ("animations", "animation_controllers"):
        a = base.get(block_name)
        b = extra.get(block_name)
        if isinstance(a, dict) and isinstance(b, dict):
            a.update(b)
    if not base.get("format_version"):
        base["format_version"] = extra.get("format_version")
    return base


def _stem(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    for suffix in (".animation_controllers.json", ".animation.json", ".json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _mark_animation_entries(ctx, anim_paths, ctrl_paths, anim_notes, ctrl_notes) -> None:
    """Registra en el libro de cuentas los ficheros de animación usados."""
    for path in anim_paths:
        entry = ctx.result.entry(path, Kind.ANIMATION)
        entry.status = Status.ADAPTED if anim_notes else Status.CONVERTED
        for note in anim_notes:
            entry.note(note)
    for path in ctrl_paths:
        entry = ctx.result.entry(path, Kind.ANIMATION)
        entry.status = Status.ADAPTED if ctrl_notes else Status.CONVERTED
        for note in ctrl_notes:
            entry.note(note)


def _anim_list(anims_doc: dict | None) -> list[dict]:
    if not isinstance(anims_doc, dict):
        return []
    return [v for v in (anims_doc.get("animations") or {}).values() if isinstance(v, dict)]


def _find_texture(ctx, name: str, geo_def: dict) -> str | None:
    mod = ctx.mod
    ns = ctx.ns
    desc = geo_def.get("description") or {}
    declared = desc.get("texture")

    # 1. Textura declarada explícitamente en la geometría.
    if isinstance(declared, str):
        dns, _, dpath = declared.partition(":")
        if dpath:
            cand = f"assets/{dns or ns}/textures/{dpath}.png"
            if mod.source.exists(cand):
                return cand

    # 2. Patrones estándar por nombre exacto (rutas fijas, O(1)).
    standard = [
        f"assets/{ns}/textures/entity/{name}.png",
        f"assets/{ns}/textures/entity/{name}/{name}.png",
        f"assets/{ns}/textures/models/entity/{name}.png",
        f"assets/{ns}/textures/entity/{name.lower()}.png",
    ]
    for c in standard:
        if mod.source.exists(c):
            return c

    # 3. Índice caché: stem -> [rutas]. O(1) por entidad tras el primer build.
    idx = ctx.get_texture_candidates()
    candidates = idx.get(name.lower(), [])

    # Regla de variantes: si name termina en _female/_male/... y no hay
    # textura propia, se usa la base (sin sufijo).
    if not candidates:
        for suffix in ("_female", "_male", "_shiny", "_hisuian", "_galar", "_alola",
                       "_paldea", "_antique", "_phony", "_crowned", "_eternamax",
                       "_starter", "_captain", "_detective"):
            if name.endswith(suffix):
                base = name[:-len(suffix)].lower()
                candidates = idx.get(base, [])
                if candidates:
                    break

    if not candidates:
        return None

    # Preferencia: misma carpeta que el modelo, luego textures/pokemon,
    # luego textures/entity, luego la primera.
    # Buscar la ruta del modelo padre para detectar "misma carpeta".
    geo_path = None
    for e in ctx.result.entries:
        if e.kind.value == "entity" and e.path.endswith(f"/{name}.geo.json"):
            geo_path = e.path
            break
    if not geo_path:
        # La entidad actual aún no está en entries; deducir por la ruta de
        # la geometría declarada en desc (si está).
        pass

    # Si hay una única candidata, úsala.
    if len(candidates) == 1:
        return candidates[0]

    # Preferencia por categoría de Cobblemon.
    def score(p: str) -> int:
        if "/textures/pokemon/" in p:
            return 0
        if "/textures/entity/" in p:
            return 1
        if "/textures/poke_balls/" in p:
            return 2
        if "/textures/npcs/" in p:
            return 3
        if "/textures/fossils/" in p:
            return 4
        return 5

    return sorted(candidates, key=score)[0]


def _collision_from_bounds(bounds, notes: list[str]) -> tuple[float, float]:
    if not bounds:
        notes.append("geometría sin cubos: caja de colisión por defecto 0.6x1.8")
        return 0.6, 1.8
    x0, y0, z0, x1, y1, z1 = bounds
    width = max(0.0625, (x1 - x0) / 16)
    height = max(0.0625, (y1 - y0) / 16)
    if width > 4 or height > 8:
        notes.append("caja de colisión enorme (modelo en otra escala): ajustada a 4x8 bloques")
        width, height = min(width, 4), min(height, 8)
    if y0 < -1:
        notes.append(f"el modelo baja {abs(y0):.1f}px por debajo de los pies: Bedrock lo enterraría")
    return round(width, 3), round(height, 3)


def _server_doc(ctx, ident: str, width: float, height: float, ov: dict) -> dict:
    ns = ctx.ns
    light = ctx.opts.variant == "mobile"
    behaviors = {
        "minecraft:behavior.float": {"priority": 0},
        "minecraft:behavior.panic": {"priority": 1, "speed_multiplier": 1.2},
        "minecraft:behavior.random_stroll": {"priority": 6, "speed_multiplier": 0.8},
        "minecraft:behavior.hurt_by_target": {"priority": 1},
    }
    if not light:
        behaviors["minecraft:behavior.look_at_player"] = {
            "priority": 7, "look_distance": 6, "probability": 0.02,
        }
        behaviors["minecraft:behavior.random_look_around"] = {"priority": 8}

    if ctx.opts.despawn_distance:
        despawn = {"despawn_from_distance": {
            "min_range": ctx.opts.despawn_distance,
            "max_range": ctx.opts.despawn_distance + 16,
        }}
    else:
        despawn = {"despawn_from_distance": {}}

    components = {
        "minecraft:type_family": {"family": [ns, "mob"]},
        "minecraft:health": {"value": ov.get("health", 20), "max": ov.get("health", 20)},
        "minecraft:physics": {},
        "minecraft:pushable": {"is_pushable": True, "is_pushable_by_piston": True},
        "minecraft:collision_box": {"width": width, "height": height},
        "minecraft:movement": {"value": ov.get("movement", 0.2)},
        "minecraft:navigation.walk": {
            "can_path_over_water": True, "avoid_water": False, "can_pass_doors": True,
        },
        "minecraft:movement.basic": {},
        "minecraft:jump.static": {},
        "minecraft:can_climb": {},
        "minecraft:breathable": {"total_supply": 15, "suffocate_time": 0},
        "minecraft:nameable": {},
        "minecraft:persistent": {},
        "minecraft:despawn": despawn,
        **behaviors,
    }
    loot = ctx.loot_paths.get(f"{ns}:entities/{_entity_name(ident)}")
    if loot:
        components["minecraft:loot"] = loot
    return {
        "format_version": versions.SERVER_ENTITY,
        "minecraft:entity": {
            "description": {
                "identifier": ident,
                "is_spawnable": True,
                "is_summonable": True,
                "is_experimental": False,
            },
            "components": components,
        },
    }


def _entity_name(ident: str) -> str:
    return ident.split(":", 1)[1]


def _client_desc(
    ctx,
    ident: str,
    name: str,
    geometry_id: str,
    anims_doc: dict | None,
    ctrls_doc: dict | None,
    alias_map: dict[str, str],
    by_name: dict[str, str],
    stats: dict,
    notes: list[str],
) -> dict:
    ns = ctx.ns
    # Todas las animaciones quedan disponibles por alias. No es ruido:
    # permite que un animation_controller o el usuario las invoque sin
    # editar el JSON generado.
    animations: dict[str, str] = dict(alias_map)
    animate: list = []

    if ctrls_doc:
        used = set(animations)
        for ctrl_id in (ctrls_doc.get("animation_controllers") or {}):
            alias = unique_alias(controller_alias(ctrl_id), used)
            used.add(alias)
            animations[alias] = ctrl_id
            animate.append(alias)
    else:
        slots = select_slots(anims_doc)
        idle_alias = by_name.get(slots["idle"]) if "idle" in slots else None
        walk_alias = by_name.get(slots["walk"]) if "walk" in slots else None
        if idle_alias and walk_alias and idle_alias != walk_alias:
            animate = [
                {walk_alias: "query.modified_move_speed > 0.05"},
                {idle_alias: "query.modified_move_speed <= 0.05"},
            ]
        elif idle_alias:
            animate = [idle_alias]
        elif walk_alias:
            animate = [walk_alias]
        if anims_doc and not animate:
            notes.append(
                "animaciones incluidas pero sin idle/walk reconocibles: no se "
                "reproducen automáticamente (añade un animation_controller)"
            )

    desc: dict = {
        "identifier": ident,
        "materials": {"default": DEFAULT_MATERIAL},
        "textures": {"default": ""},  # lo fija la fase de escritura (atlas o suelto)
        "geometry": {"default": geometry_id},
        "render_controllers": [f"controller.render.{ns}.default"],
        "spawn_egg": {
            "base_color": stats["hex"],
            "overlay_color": stats["overlay"],
        },
    }
    if animations:
        desc["animations"] = animations
    if animate:
        desc["scripts"] = {"animate": animate}
    return desc


def _pick_anims(anims_doc: dict | None) -> tuple[str | None, str | None]:
    """Compatibilidad: devuelve (idle, walk) usando la selección robusta."""
    slots = select_slots(anims_doc)
    return slots.get("idle"), slots.get("walk")


def _title(name: str) -> str:
    return " ".join(part.capitalize() for part in name.replace("_", " ").split()) or name


# ---------------------------------------------------------------------------
#  Escritura: sin atlas / con atlas
# ---------------------------------------------------------------------------


def _write_without_atlas(ctx, records: list[dict], write_rc: bool = True) -> None:
    writer = ctx.writer
    ns = ctx.ns
    wrote_rc = False
    for rec in records:
        # Textura.
        if rec["png"] is not None:
            dest = f"textures/entity/{ns}/{rec['name']}.png"
            writer.rp_blob(dest, encode_png(rec["png"].width, rec["png"].height, rec["png"].pixels))
            rec["client"]["textures"]["default"] = dest[:-4]
            # Marcar la textura de origen como convertida.
            tex_path = rec.get("tex_path")
            if tex_path:
                tex_entry = ctx.result.entry(tex_path, Kind.TEXTURE)
                tex_entry.status = Status.CONVERTED
        elif rec.get("tex_path") and ctx.mod.source.exists(rec["tex_path"]):
            # PNG que el códec no pudo decodificar: se copia en crudo. Es
            # mejor perder los stats del color que dejar la entidad sin
            # textura (una referencia vacía rompe el render).
            dest = f"textures/entity/{ns}/{rec['name']}.png"
            try:
                writer.rp_blob(dest, ctx.mod.source.read_bytes(rec["tex_path"]))
                rec["client"]["textures"]["default"] = dest[:-4]
            except (KeyError, OSError, ValueError):
                ctx.result.error(
                    "entity.texture",
                    f"rp/entity/{rec['key']}.entity.json",
                    f"no se pudo copiar la textura de {rec['name']}",
                )
        # Geometría + animaciones + controladores.
        writer.rp_json(f"models/entity/{rec['key']}.geo.json", rec["geo_doc"])
        if rec["anims_doc"]:
            writer.rp_json(f"animations/{rec['key']}.animation.json", rec["anims_doc"])
        if rec.get("ctrls_doc"):
            writer.rp_json(
                f"animation_controllers/{rec['key']}.animation_controllers.json",
                rec["ctrls_doc"],
            )
        # Entidades.
        writer.bp_json(f"entities/{rec['key']}.entity.json", rec["server"])
        writer.rp_json(
            f"entity/{rec['key']}.entity.json",
            {"format_version": versions.CLIENT_ENTITY, "minecraft:client_entity": {"description": rec["client"]}},
        )
        if write_rc and not wrote_rc:
            writer.rp_json(
                f"render_controllers/{ns}_entity.render_controllers.json",
                _default_render_controllers(ns),
            )
            wrote_rc = True


def _build_atlas(ctx, records: list[dict]) -> None:
    """Todo en un atlas: 1 texture handle para todas las entidades."""
    writer = ctx.writer
    ns = ctx.ns
    usable = [r for r in records if r["png"] is not None]
    cell = ctx.opts.atlas_cell or 64

    plan = None
    atlas_size = 0
    for size in (256, 512, 1024, 2048, 4096):
        plan = plan_grid(len(usable), cell, size)
        if plan is not None:
            atlas_size = size
            break
    if plan is None:
        ctx.result.warn(
            "atlas.too_many",
            "atlas",
            f"{len(usable)} texturas no caben en un atlas de 4096px con celdas de {cell}px: "
            "se escriben sueltas (más texture handles, sigue funcionando)",
        )
        _write_without_atlas(ctx, records)
        return

    pixels = bytearray(atlas_size * atlas_size * 4)
    for rec, slot in zip(usable, plan["slots"]):
        png = rec["png"]
        # La textura se ajusta a la celda conservando proporción.
        scale = min(cell / max(1, png.width), cell / max(1, png.height))
        w = max(1, round(png.width * scale))
        h = max(1, round(png.height * scale))
        blit_into_atlas(pixels, atlas_size, png, {"x": slot["x"], "y": slot["y"], "w": w, "h": h})
        normalize_geometry_to_cell(rec["geo_def"], cell)
        (rec["client"].setdefault("scripts", {}))["pre_animation"] = [
            f"variable.offset_x = {slot['x']} / {atlas_size};",
            f"variable.offset_y = {slot['y']} / {atlas_size};",
            f"variable.scale_x = {w} / {atlas_size};",
            f"variable.scale_y = {h} / {atlas_size};",
        ]
        # Usar materiales vanilla directamente (sin materiales custom)
        material = "entity_alphablend" if rec["stats"]["semi"] else "entity_alphatest"
        rec["client"]["materials"] = {"default": material}
        rec["client"]["textures"] = {"default": _ATLAS_TEXTURE}
        rec["client"]["render_controllers"] = [f"controller.render.{ns}.atlas"]

    writer.rp_blob(
        _ATLAS_TEXTURE + ".png",
        encode_png(atlas_size, atlas_size, pixels),
    )
    # No generar archivo de materiales custom - usar materiales vanilla
    writer.rp_json(
        f"render_controllers/{ns}_entity.render_controllers.json",
        _render_controllers(ns, with_atlas=True),
    )

    # Las que no tienen PNG (solo si --placeholders) van sueltas.
    leftovers = [r for r in records if r["png"] is None]
    if leftovers:
        # El render controller del atlas ya está escrito: no lo pisamos con
        # el de las entidades sueltas.
        _write_without_atlas(ctx, leftovers, write_rc=False)

    for rec in usable:
        writer.rp_json(f"models/entity/{rec['key']}.geo.json", rec["geo_doc"])
        if rec["anims_doc"]:
            writer.rp_json(f"animations/{rec['key']}.animation.json", rec["anims_doc"])
        if rec.get("ctrls_doc"):
            writer.rp_json(
                f"animation_controllers/{rec['key']}.animation_controllers.json",
                rec["ctrls_doc"],
            )
        writer.bp_json(f"entities/{rec['key']}.entity.json", rec["server"])
        writer.rp_json(
            f"entity/{rec['key']}.entity.json",
            {"format_version": versions.CLIENT_ENTITY, "minecraft:client_entity": {"description": rec["client"]}},
        )


# ---------------------------------------------------------------------------
#  Documentos de render
# ---------------------------------------------------------------------------


def _default_render_controllers(ns: str) -> dict:
    return _render_controllers(ns, with_atlas=False)


def _render_controllers(ns: str, with_atlas: bool) -> dict:
    controllers = {
        f"controller.render.{ns}.default": {
            "geometry": "Geometry.default",
            "materials": [{"*": "Material.default"}],
            "textures": ["Texture.default"],
        }
    }
    if with_atlas:
        controllers[f"controller.render.{ns}.atlas"] = {
            "geometry": "Geometry.default",
            "materials": [{"*": "Material.default"}],
            "textures": ["Texture.default"],
            "uv_anim": {
                "offset": ["variable.offset_x", "variable.offset_y"],
                "scale": ["variable.scale_x", "variable.scale_y"],
            },
        }
    return {"format_version": versions.RENDER_CONTROLLER, "render_controllers": controllers}


def _atlas_material(ns: str) -> dict:
    """Material personalizado para atlas que hereda de vanilla materials.
    
    Usa el formato de herencia de Bedrock: nombre_material:material_padre
    Estos heredan de entity_alphatest/alphablend y agregan USE_UV_ANIM
    para soportar el offset del atlas.
    """
    return {
        "materials": {
            "version": "1.0.0",
            f"{ns}_atlas_alphatest:entity_alphatest": {
                "+defines": ["USE_UV_ANIM"]
            },
            f"{ns}_atlas_alphablend:entity_alphablend": {
                "+defines": ["USE_UV_ANIM"]
            }
        }
    }


def _placeholder_entity_png(name: str, size: int = 32) -> Png:
    """Textura placeholder determinista (cuadros claros/oscuros)."""
    seed = sum(name.encode("utf-8")) or 3
    r = (seed * 53) % 160 + 70
    g = (seed * 71) % 160 + 70
    b = (seed * 89) % 160 + 70
    px = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            i = (y * size + x) * 4
            f = 1.0 if ((x // 4) + (y // 4)) % 2 == 0 else 0.75
            px[i] = round(r * f)
            px[i + 1] = round(g * f)
            px[i + 2] = round(b * f)
            px[i + 3] = 255
    return Png(size, size, px)
