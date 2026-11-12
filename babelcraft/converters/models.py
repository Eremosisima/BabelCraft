"""Fase models: modelos Java -> geometría Bedrock + attachables.

Convenciones de conversión (verificadas contra convertidores probados en
producción, p.ej. java2bedrock y el esquema bi_* de Geyser):

  **Coordenadas**: Bedrock está espejado en X respecto al espacio de
  modelo de Java. Un elemento Java `from/to` se convierte:

      origen Bedrock = [8 - to_x, from_y, from_z - 8]   (espejo X)

  **Rotaciones de elemento**: Java `{axis, angle, origin}` ->
  Bedrock `rotation = [-ang, 0, 0] | [0, -ang, 0] | [0, 0, +ang]`, con
  el pivote espejado igual que el origen.

  **Caras**: north/south se copian tal cual; east/west se INTERCAMBIAN
  (el espejo X invierte la dirección de vista) con flip horizontal
  (uv_size negativo); up/down se copian con rotación 180° (uv en la
  esquina opuesta y tamaños negativos).

  **UVs por defecto**: cuando una cara Java no declara `uv`, se calculan
  de la posición del elemento (reglas del formato Java).

  **Attachables** (ítems 3D en mano): geometría con cadena de huesos
  `bi` (binding al hueco) -> `bi_x` -> `bi_y` -> `bi_z` (cubos), y las
  transformaciones `display` de Java se convierten en ANIMACIONES por
  hueco (tercera/primera persona, mano izq/der, cabeza), que es el
  esquema que usa Geyser en producción.
"""

from __future__ import annotations

from .. import versions
from ..model import Kind, Status, slug

# --------------------------------------------------------------------------
#  Plantillas vanilla mínimas (equivalentes funcionales propios)
# --------------------------------------------------------------------------

_CUBE_FACES = ("north", "south", "east", "west", "up", "down")


def _cube(keymap: dict) -> dict:
    """Un cubo 0..16 cuyas caras usan las claves de textura de `keymap`."""
    faces = {}
    for f in _CUBE_FACES:
        faces[f] = {"texture": "#" + keymap[f]}
    return {
        "elements": [
            {"from": [0, 0, 0], "to": [16, 16, 16], "faces": faces}
        ]
    }


_BUILTIN = {
    "minecraft:block/block": {"elements": None, "textures": {}},
    "minecraft:block/cube": _cube({f: f for f in _CUBE_FACES}),
    "minecraft:block/cube_all": _cube({f: "all" for f in _CUBE_FACES}),
    "minecraft:block/cube_bottom_top": _cube(
        {"north": "side", "south": "side", "east": "side", "west": "side", "up": "top", "down": "bottom"}
    ),
    "minecraft:block/cube_column": _cube(
        {"north": "side", "south": "side", "east": "side", "west": "side", "up": "end", "down": "end"}
    ),
    "minecraft:block/cube_column_horizontal": _cube(
        {"north": "side", "south": "side", "east": "side", "west": "side", "up": "end", "down": "end"}
    ),
    "minecraft:block/cross": {
        "elements": [
            {
                "from": [0.8, 0, 8], "to": [15.2, 16, 8.1],
                "rotation": {"origin": [8, 8, 8], "axis": "y", "angle": 45},
                "faces": {f: {"texture": "#cross"} for f in ("north", "south", "east", "west")},
            },
            {
                "from": [0.8, 0, 8], "to": [15.2, 16, 8.1],
                "rotation": {"origin": [8, 8, 8], "axis": "y", "angle": -45},
                "faces": {f: {"texture": "#cross"} for f in ("north", "south", "east", "west")},
            },
        ]
    },
    "minecraft:item/generated": {"flat": True, "textures": {"layer0": ""}},
    "minecraft:item/handheld": {"flat": True, "textures": {"layer0": ""}},
    "minecraft:item/handheld_rod": {"flat": True, "textures": {"layer0": ""}},
}


# --------------------------------------------------------------------------
#  Resolución de padres
# --------------------------------------------------------------------------

def resolve_model(ctx, path: str) -> dict | None:
    """Carga un modelo Java con su cadena de `parent` resuelta.

    Devuelve {elements, textures, display, flat} o None si no se puede
    leer. La herencia es: elementos del hijo si los tiene, si no los del
    padre; texturas mezcladas (el hijo manda); display mezclado por slot.
    """
    if path in ctx.model_cache:
        return ctx.model_cache[path]

    data = ctx.mod.source.read_json_or(path)
    if not isinstance(data, dict):
        ctx.model_cache[path] = None
        return None

    resolved: dict = {"elements": [], "textures": {}, "display": {}, "flat": False, "held": False}
    _merge(ctx, resolved, data, depth=0)
    ctx.model_cache[path] = resolved
    return resolved


def _merge(ctx, resolved: dict, data: dict, depth: int) -> None:
    if depth > 16:
        return  # cadena de padres circular o demasiado profunda
    parent = data.get("parent")
    if isinstance(parent, str):
        if parent in _BUILTIN:
            _merge_builtin(resolved, _BUILTIN[parent])
        else:
            ppath = _parent_path(parent, ctx.ns)
            if ppath and ctx.mod.source.exists(ppath):
                pdata = ctx.mod.source.read_json_or(ppath)
                if isinstance(pdata, dict):
                    _merge(ctx, resolved, pdata, depth + 1)
            elif not parent.startswith("builtin/"):
                resolved.setdefault("_missing_parents", []).append(parent)

    if isinstance(data.get("textures"), dict):
        resolved["textures"].update(data["textures"])
    if data.get("elements"):
        resolved["elements"] = data["elements"]
    if data.get("display") and isinstance(data["display"], dict):
        for slot, tr in data["display"].items():
            if isinstance(tr, dict):
                resolved["display"][slot] = tr
    if parent in ("minecraft:item/generated", "minecraft:item/handheld", "minecraft:item/handheld_rod"):
        resolved["flat"] = True
    if parent in ("minecraft:item/handheld", "minecraft:item/handheld_rod"):
        resolved["held"] = True


def _merge_builtin(resolved: dict, builtin: dict) -> None:
    if builtin.get("flat"):
        resolved["flat"] = True
    if builtin.get("elements"):
        # Las plantillas definen sus caras por clave (#north, #all...).
        resolved["elements"] = builtin["elements"]
        resolved.setdefault("_builtin_textures", {})


def _parent_path(parent: str, ns: str) -> str | None:
    pns, _, ref = parent.partition(":")
    if not ref:
        return None
    return f"assets/{pns or ns}/models/{ref}.json"


def iter_model_texture_refs(resolved: dict) -> set[str]:
    """Ids de textura (`ns:block/ruby`) que usa un modelo ya resuelto."""
    out: set[str] = set()
    for value in (resolved.get("textures") or {}).values():
        if isinstance(value, str) and value and not value.startswith("#"):
            out.add(value)
    return out


def flat_texture(resolved: dict) -> str | None:
    """Textura de icono de un modelo plano (item/generated)."""
    tex = resolved.get("textures") or {}
    for key in ("layer0", "layer1", "layer2"):
        v = tex.get(key)
        if isinstance(v, str) and v and not v.startswith("#"):
            return v
    for v in tex.values():
        if isinstance(v, str) and v and not v.startswith("#"):
            return v
    return None


# --------------------------------------------------------------------------
#  Geometría
# --------------------------------------------------------------------------

def texture_size_of(ctx, tex_id: str | None) -> tuple[int, int]:
    """Tamaño real del PNG de una textura (para UVs). Default 16x16."""
    if not tex_id:
        return 16, 16
    rpath = ctx.tex_rpaths.get(tex_id)
    if not rpath:
        return 16, 16
    from ..pngcodec import png_info

    info = png_info(ctx.writer.rp.get(rpath + ".png", b""))
    if info:
        return info["width"], info["height"]
    return 16, 16


def material_name(tex_id: str) -> str:
    """Nombre de instancia de material para una textura."""
    ref = tex_id.split(":", 1)[1] if ":" in tex_id else tex_id
    return slug(ref.replace("/", "_"))


def geometry_from_model(
    ctx,
    resolved: dict,
    geometry_id: str,
    *,
    attachable: bool = False,
) -> tuple[dict | None, list[str], list[str]]:
    """Modelo Java resuelto -> geometría Bedrock.

    Devuelve (geometry_doc, notas, referencias_de_textura_usadas).
    None si el modelo es plano (sin elements): se resuelve como icono.
    """
    elements = resolved.get("elements")
    if not elements or not isinstance(elements, list):
        return None, [], []

    notes: list[str] = []
    texrefs: list[str] = []  # orden de aparición

    cubes = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        cube, el_notes, refs = _element_to_cube(ctx, resolved, el, attachable)
        notes.extend(el_notes)
        for r in refs:
            if r not in texrefs:
                texrefs.append(r)
        if cube:
            cubes.append(cube)

    if not cubes:
        return None, ["modelo sin caras convertibles"], []

    desc = {
        "identifier": geometry_id,
        "texture_width": 16,
        "texture_height": 16,
        "visible_bounds_width": 3,
        "visible_bounds_height": 3,
        "visible_bounds_offset": [0, 0.75, 0],
    }
    if attachable:
        # Cadena bi* para posicionar en cada hueco + binding (1.16.0).
        desc["visible_bounds_offset"] = [0, 1, 0]
        bones = [
            {"name": "bi", "binding": "c.item_slot == 'head' ? 'head' : q.item_slot_to_bone_name(c.item_slot)", "pivot": [0, 8, 0]},
            {"name": "bi_x", "parent": "bi", "pivot": [0, 8, 0]},
            {"name": "bi_y", "parent": "bi_x", "pivot": [0, 8, 0]},
            {"name": "bi_z", "parent": "bi_y", "pivot": [0, 8, 0], "cubes": cubes},
        ]
        fv = "1.16.0"
    else:
        bones = [{"name": "root", "pivot": [0, 0, 0], "cubes": cubes}]
        fv = versions.GEOMETRY

    doc = {"format_version": fv, "minecraft:geometry": [{"description": desc, "bones": bones}]}
    return doc, notes, texrefs


def _element_to_cube(ctx, resolved: dict, el: dict, attachable: bool) -> tuple[dict | None, list[str], list[str]]:
    notes: list[str] = []
    refs: list[str] = []

    fr = _vec3(el.get("from"))
    to = _vec3(el.get("to"))
    if fr is None or to is None:
        return None, ["element sin from/to"], []

    # Espesor cero: Bedrock puede cullear caras coplanares. Se ensancha.
    size = [to[i] - fr[i] for i in range(3)]
    for i in range(3):
        if abs(size[i]) < 0.05:
            size[i] = 0.1
            to[i] = fr[i] + 0.1
            notes.append("plano de espesor 0: se ensancha a 0.1px (Bedrock cullea caras coplanares)")

    # Espejo X: origen = [8 - to_x, from_y, from_z - 8]
    origin = [round(8 - to[0], 4), round(fr[1], 4), round(fr[2] - 8, 4)]

    cube: dict = {"origin": origin, "size": [round(s, 4) for s in size]}

    rot = el.get("rotation")
    if isinstance(rot, dict) and rot.get("angle"):
        piv = _vec3(rot.get("origin")) or [8, 8, 8]
        axis = rot.get("axis")
        ang = float(rot["angle"])
        cube["pivot"] = [round(8 - piv[0], 4), round(piv[1], 4), round(piv[2] - 8, 4)]
        cube["rotation"] = [
            round(-ang if axis == "x" else 0, 4),
            round(-ang if axis == "y" else 0, 4),
            round(ang if axis == "z" else 0, 4),
        ]
        if abs(ang) > 45:
            notes.append(f"rotación de elemento de {ang}°: fuera del rango clásico, revisa el resultado")

    # Caras con UV por defecto calculado de la posición.
    defaults = _default_uvs(fr, to)
    faces = el.get("faces") or {}
    uv_out: dict = {}
    for java_face, fdef in faces.items():
        if java_face not in _FACE_MAP or not isinstance(fdef, dict):
            continue
        tex_ref = _resolve_face_texture(resolved, fdef.get("texture"))
        if tex_ref is None:
            continue
        if tex_ref not in refs:
            refs.append(tex_ref)
        uv = fdef.get("uv") or defaults.get(java_face)
        if not isinstance(uv, list) or len(uv) != 4:
            continue
        tw, th = texture_size_of(ctx, tex_ref)
        face_uv = _java_uv_to_bedrock(java_face, uv, fdef.get("rotation", 0), tw, th, notes)
        if face_uv is None:
            continue
        entry = {"uv": face_uv[0], "uv_size": face_uv[1]}
        if not attachable:
            entry["material_instance"] = material_name(tex_ref)
        uv_out[_FACE_MAP[java_face][0]] = entry

    if not uv_out:
        return None, notes or ["element sin caras con textura resuelta"], refs

    cube["uv"] = uv_out
    return cube, notes, refs


# Java face -> (nombre Bedrock, flip_h, flip_180)
# flip_h: la cara se ve desde el lado contrario tras el espejo X
# flip_180: Bedrock mapea el rect up/down girado 180° respecto a Java
_FACE_MAP = {
    "north": ("north", False, False),
    "south": ("south", False, False),
    "east": ("west", True, False),   # espejo X: east Java = west Bedrock
    "west": ("east", True, False),
    "up": ("up", False, True),
    "down": ("down", False, True),
}


def _java_uv_to_bedrock(java_face: str, uv: list, rot: int, tw: int, th: int, notes: list[str]):
    """UV [u1,v1,u2,v2] Java (espacio textura) -> (uv, uv_size) Bedrock.

    `uv_size` negativo = flip de ese eje: así se expresan el espejo y la
    rotación 180 sin tocar los píxeles.
    """
    u1, v1, u2, v2 = uv
    if u2 < u1:
        u1, u2 = u2, u1  # Java admite rectángulos invertidos
    if v2 < v1:
        v1, v2 = v2, v1
    du, dv = u2 - u1, v2 - v1

    bedrock_face, flip_h, flip_180 = _FACE_MAP[java_face]
    fx = flip_h
    fy = False
    if flip_180:
        fx, fy = not fx, True

    # Rotación declarada de la cara Java (0/90/180/270).
    if rot in (90, 270):
        notes.append(f"rotación de cara {rot}° en {java_face}: sin equivalente directo, cara sin rotar")
        rot = 0
    if rot == 180:
        fx, fy = not fx, not fy

    out_u = u2 if fx else u1
    out_v = v2 if fy else v1
    return [round(out_u, 3), round(out_v, 3)], [round(-du if fx else du, 3), round(-dv if fy else dv, 3)]


def _default_uvs(fr: list, to: list) -> dict:
    """UVs por defecto de un elemento sin `uv` en las caras (formato Java)."""
    x1, y1, z1 = fr
    x2, y2, z2 = to
    return {
        "down": [x1, 16 - z2, x2, 16 - z1],
        "up": [x1, z1, x2, z2],
        "north": [16 - x2, 16 - y2, 16 - x1, 16 - y1],
        "south": [x1, 16 - y2, x2, 16 - y1],
        "west": [z1, 16 - y2, z2, 16 - y1],
        "east": [16 - z2, 16 - y2, 16 - z1, 16 - y1],
    }


def _resolve_face_texture(resolved: dict, ref) -> str | None:
    """`#all` -> textures['all']; `ns:block/x` directo."""
    if not isinstance(ref, str) or not ref:
        return None
    if ref.startswith("#"):
        value = (resolved.get("textures") or {}).get(ref[1:])
        if isinstance(value, str) and value and not value.startswith("#"):
            return value
        return None
    return ref


def _vec3(v) -> list | None:
    if isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v):
        return [float(x) for x in v]
    return None


# --------------------------------------------------------------------------
#  Attachables (ítems 3D en mano)
# --------------------------------------------------------------------------

# Defaults de vanilla cuando el modelo Java no declara un slot display.
_D_THIRD = {"rotation": [75, 45, 0], "translation": [0, 2.5, 0], "scale": [0.375] * 3}
_D_FIRST = {"rotation": [0, 45, 0], "translation": [0, 0, 0], "scale": [0.4] * 3}
_D_HEAD = {"rotation": [0, 0, 0], "translation": [0, 0, 0], "scale": [0.625] * 3}


def _slot(display: dict, name: str, fallback: dict) -> tuple[list, list, list]:
    d = display.get(name) or fallback
    # Valores por defecto seguros para evitar KeyError
    default_rotation = [0, 0, 0]
    default_translation = [0, 0, 0]
    default_scale = [1, 1, 1]
    return (
        list(d.get("rotation", fallback.get("rotation", default_rotation))),
        list(d.get("translation", fallback.get("translation", default_translation))),
        list(d.get("scale", fallback.get("scale", default_scale))),
    )


def attachable_animation_doc(anim_ns: str, key: str, display: dict) -> dict:
    """Animaciones por hueco para el attachable (esquema bi_*).

    Las fórmulas son las del esquema que Geyser usa en producción para
    reproducir los `display` de Java en Bedrock.
    """
    a = f"animation.{anim_ns}.{key}"
    tr_r, tt_r, ts_r = _slot(display, "thirdperson_righthand", _D_THIRD)
    tr_l, tt_l, ts_l = _slot(display, "thirdperson_lefthand", display.get("thirdperson_righthand") or _D_THIRD)
    fr_r, ft_r, fs_r = _slot(display, "firstperson_righthand", _D_FIRST)
    fr_l, ft_l, fs_l = _slot(display, "firstperson_lefthand", display.get("firstperson_righthand") or _D_FIRST)
    hr, ht, hs = _slot(display, "head", _D_HEAD)

    def third(rot, tr, sc):
        return {"loop": True, "bones": {
            "bi_x": {"rotation": [-rot[0], 0, 0], "position": [-tr[0], tr[1], tr[2]], "scale": list(sc)},
            "bi_y": {"rotation": [0, -rot[1], 0]},
            "bi_z": {"rotation": [0, 0, rot[2]]},
            "bi": {"rotation": [90, 0, 0], "position": [0, 13, -3]},
        }}

    def first(rot, tr, sc):
        any_rot = any(rot)
        return {"loop": True, "bones": {
            "bi": {"rotation": [90, 60, -40], "position": [4, 10, 4], "scale": 1.5},
            "bi_x": {"rotation": [-rot[0], 0.1, 0.1] if any_rot else [0.1, 0.1, 0.1],
                     "position": [-tr[0], tr[1], -tr[2]], "scale": list(sc)},
            "bi_y": {"rotation": [0, -rot[1], 0]},
            "bi_z": {"rotation": [0, 0, rot[2]]},
        }}

    return {
        "format_version": versions.ANIMATION,
        "animations": {
            a + ".thirdperson_main_hand": third(tr_r, tt_r, ts_r),
            a + ".thirdperson_off_hand": third(tr_l, tt_l, ts_l),
            a + ".firstperson_main_hand": first(fr_r, ft_r, fs_r),
            a + ".firstperson_off_hand": first(fr_l, ft_l, fs_l),
            a + ".head": {"loop": True, "bones": {
                "bi_x": {"rotation": [-hr[0], 0, 0],
                         "position": [-ht[0] * 0.625, ht[1] * 0.625, ht[2] * 0.625],
                         "scale": [v * 0.625 for v in hs]},
                "bi_y": {"rotation": [0, -hr[1], 0]},
                "bi_z": {"rotation": [0, 0, hr[2]]},
                "bi": {"position": [0, 19.5, 0]},
            }},
        },
    }


def disable_animation_doc(anim_ns: str) -> dict:
    """Anula el attachable en primera persona sobre la cabeza."""
    return {
        "format_version": versions.ANIMATION,
        "animations": {
            f"animation.{anim_ns}.disable": {
                "loop": True, "override_previous_animation": True,
                "bones": {"bi": {"scale": 0}},
            }
        },
    }


def attachable_doc(ns: str, ident: str, key: str, texture_rpath: str, geometry_id: str, controller: str) -> dict:
    a = f"animation.{ns}.{key}"
    return {
        "format_version": versions.ATTACHABLE,
        "minecraft:attachable": {
            "description": {
                "identifier": ident,
                "materials": {"default": "entity_alphatest", "enchanted": "entity_alphatest_glint"},
                "textures": {
                    "default": texture_rpath,
                    "enchanted": "textures/misc/enchanted_item_glint",
                },
                "geometry": {"default": geometry_id},
                "scripts": {
                    "pre_animation": [
                        "v.main_hand = c.item_slot == 'main_hand';",
                        "v.off_hand = c.item_slot == 'off_hand';",
                        "v.head = c.item_slot == 'head';",
                    ],
                    "animate": [
                        {"thirdperson_main_hand": "v.main_hand && !c.is_first_person"},
                        {"thirdperson_off_hand": "v.off_hand && !c.is_first_person"},
                        {"thirdperson_head": "v.head && !c.is_first_person"},
                        {"firstperson_main_hand": "v.main_hand && c.is_first_person"},
                        {"firstperson_off_hand": "v.off_hand && c.is_first_person"},
                        {"firstperson_head": "v.head && c.is_first_person"},
                    ],
                },
                "animations": {
                    "thirdperson_main_hand": a + ".thirdperson_main_hand",
                    "thirdperson_off_hand": a + ".thirdperson_off_hand",
                    "thirdperson_head": a + ".head",
                    "firstperson_main_hand": a + ".firstperson_main_hand",
                    "firstperson_off_hand": a + ".firstperson_off_hand",
                    # La de 'disable' la escribe disable_animation_doc(ns):
                    # es UNA sola animación compartida por todos los ítems.
                    "firstperson_head": f"animation.{ns}.disable",
                },
                "render_controllers": [controller],
            }
        },
    }


def item_render_controller(controller_id: str) -> dict:
    """Render controller propio para attachables (no dependemos de vanilla)."""
    return {
        "format_version": versions.RENDER_CONTROLLER,
        "render_controllers": {
            controller_id: {
                "geometry": "Geometry.default",
                "materials": [{"*": "Material.default"}],
                "textures": ["Texture.default", "Texture.enchanted"],
            }
        },
    }


# --------------------------------------------------------------------------
#  Fase
# --------------------------------------------------------------------------

CONTROLLER_ID = "controller.render.{ns}_item"


def convert(ctx) -> None:
    """Genera attachables para ítems con modelo 3D propio.

    Los ítems planos (item/generated) no necesitan geometría: Bedrock los
    dibuja como sprite desde item_texture.json. Los modelos con elements
    sí: se convierten en geometría + attachable + animaciones por hueco.
    """
    mod, writer, result = ctx.mod, ctx.writer, ctx.result
    ns = ctx.ns
    controller = CONTROLLER_ID.format(ns=ns)
    wrote_controller = False

    for path in mod.source.glob(f"assets/{ns}/models/item/"):
        if not path.endswith(".json"):
            continue
        name = path.rsplit("/", 1)[-1][:-5]
        resolved = resolve_model(ctx, path)
        if not resolved or resolved.get("flat"):
            continue  # plano: la fase items lo trata como icono

        ident = f"{ns}:{name}"
        geometry_id = f"geometry.{ns}_{name}"
        geo, notes, texrefs = geometry_from_model(ctx, resolved, geometry_id, attachable=True)
        if geo is None:
            e = result.residue(path, Kind.MODEL, "; ".join(notes) or "modelo sin geometría convertible")
            continue

        # Textura del attachable: primera del modelo (multi-textura se
        # reporta; un attachable renderiza una textura por pasada).
        tex_id = texrefs[0] if texrefs else None
        tex_rpath = ctx.tex_rpaths.get(tex_id or "")
        if tex_rpath is None:
            result.residue(path, Kind.MODEL, f"sin textura convertible para el modelo (refs: {texrefs})")
            continue
        if len(texrefs) > 1:
            notes.append(
                "modelo multi-textura: en mano solo se aplica la primera "
                f"({tex_id}); usa un attachable manual por textura si necesitas el resto"
            )

        key = slug(f"{ns}_{name}")
        writer.rp_json(f"models/entity/{key}.geo.json", geo)
        writer.rp_json(f"animations/{key}.animation.json", attachable_animation_doc(ns, key, resolved.get("display") or {}))
        writer.rp_json(f"attachables/{key}.attachable.json", attachable_doc(ns, ident, key, tex_rpath, geometry_id, controller))
        if not wrote_controller:
            writer.rp_json(f"render_controllers/{ns}_item.render_controllers.json", item_render_controller(controller))
            writer.rp_json(f"animations/{ns}_disable.animation.json", disable_animation_doc(ns))
            wrote_controller = True

        e = result.entry(path, Kind.MODEL)
        e.status = Status.CONVERTED if not notes else Status.ADAPTED
        e.notes.extend(notes)
        ctx.item_ids.add(ident)  # tiene modelo 3D: es un ítem real
        ctx.attachable_icons[ident] = tex_id  # icono de inventario del ítem 3D
