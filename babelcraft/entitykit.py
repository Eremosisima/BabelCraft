"""Herramientas de entidades Bedrock: poda, adelgazado, atlas y AABB.

Portado de `CobblemonBedrock/tools/cobblemon2bedrock.js` (código propio
del autor), donde cada técnica se midió sobre las 1074 especies reales:

  - prune_bones: elimina huesos locator/vacíos que no dibujan nada
    (-75% de RAM junto con el resto de la escalera).
  - thin_animation: quita keyframes redundantes en tramos constantes,
    solo en canales numéricos simples (nunca cambia el resultado de la
    interpolación).
  - normalize_geometry_to_cell + blit_into_atlas: todas las texturas de
    entidades en UN atlas (límite oficial de "texture handles": 800
    recomendados, 4000 duros). Las UVs de la geometría pasan a ser
    locales a su celda y un render controller con `uv_anim` aplica el
    desplazamiento global.
  - geometry_bounds: AABB de la geometría, para collision_box derivada
    del modelo real en vez de inventada.
"""

from __future__ import annotations

from .pngcodec import Png


# ------------------------------------------------------------------ poda

def prune_bones(geo_def: dict, anims: list[dict]) -> int:
    """Elimina huesos que no dibujan nada y no son necesarios.

    Se conservan: huesos con cubos, huesos nombrados por una animación
    (rotación/posición/escala, efectos de partícula o sonido con locator)
    y sus ancestros. Devuelve cuántos se eliminaron.
    """
    bones = geo_def.get("bones")
    if not isinstance(bones, list) or not bones:
        return 0

    by_name = {}
    for b in bones:
        if isinstance(b, dict) and b.get("name"):
            by_name[b["name"]] = b

    referenced: set[str] = set()
    for a in anims or []:
        if not isinstance(a, dict):
            continue
        for bones_anim in (a.get("bones"), a.get("animators")):
            if isinstance(bones_anim, dict):
                referenced |= set(bones_anim.keys())
        for key in ("particle_effects", "sound_effects"):
            lst = a.get(key)
            if isinstance(lst, dict):
                for v in lst.values():
                    if isinstance(v, dict) and v.get("locator"):
                        referenced.add(v["locator"])

    keep: set[str] = set()

    def keep_with_ancestors(name: str) -> None:
        cur = name
        guard = 0
        while cur and cur in by_name and cur not in keep and guard < 64:
            keep.add(cur)
            cur = by_name[cur].get("parent")
            guard += 1

    for b in bones:
        if isinstance(b, dict) and b.get("cubes"):
            keep_with_ancestors(b["name"])
    for n in referenced:
        keep_with_ancestors(n)

    before = len(bones)
    geo_def["bones"] = [b for b in bones if isinstance(b, dict) and b.get("name") in keep]
    return before - len(geo_def["bones"])


# -------------------------------------------------------- adelgazado

def _same_vec(a, b) -> bool:
    if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
        return False
    try:
        return all(abs(float(x) - float(y)) <= 1e-9 for x, y in zip(a, b))
    except (TypeError, ValueError):
        # Un keyframe con forma rara (dict de interpolación, cadena...):
        # no es comparable, así que se conserva. Nunca romper la animación.
        return False


def thin_animation(anim: dict) -> int:
    """Quita keyframes redundantes en tramos de valor constante.

    Solo actúa sobre canales con valores numéricos simples (arrays de 3),
    sin pre/post ni interpolación especial: eliminar un punto intermedio
    en un tramo constante no cambia el resultado de la interpolación.
    Devuelve cuántos keyframes eliminó.
    """
    if not isinstance(anim, dict) or not isinstance(anim.get("bones"), dict):
        return 0
    removed = 0
    for bone in anim["bones"].values():
        if not isinstance(bone, dict):
            continue
        for ch in ("rotation", "position", "scale"):
            chv = bone.get(ch)
            if not isinstance(chv, dict) or isinstance(chv, list):
                continue
            try:
                times = sorted(chv.keys(), key=float)
            except (TypeError, ValueError):
                continue  # tiempos no numéricos: no se toca ese canal
            if len(times) < 3:
                continue
            if any(isinstance(chv[t], dict) for t in times):
                continue  # interpolación especial: no tocar
            vals = [chv[t] for t in times]
            keep = [True] * len(times)
            i = 0
            while i < len(vals):
                j = i
                while j + 1 < len(vals) and _same_vec(vals[j + 1], vals[i]):
                    j += 1
                for k in range(i + 1, j):
                    keep[k] = False
                    removed += 1
                i = j + 1
            if not all(keep):
                bone[ch] = {t: v for t, v, k in zip(times, vals, keep) if k}
    return removed


# ------------------------------------------------------------------ atlas

def plan_grid(n: int, cell: int, atlas_size: int, gap: int = 1) -> dict | None:
    """Empaquetado en cuadrícula regular de `n` celdas de `cell` px."""
    cols = (atlas_size + gap) // (cell + gap)
    rows = (atlas_size + gap) // (cell + gap)
    if cols < 1 or rows < 1 or n > cols * rows:
        return None
    slots = []
    i = 0
    for r in range(rows):
        for c in range(cols):
            if i >= n:
                break
            slots.append({"x": c * (cell + gap), "y": r * (cell + gap), "col": c, "row": r})
            i += 1
    return {"slots": slots, "cols": cols, "rows": rows, "cell": cell, "atlas_size": atlas_size}


def normalize_geometry_to_cell(geo_def: dict, cell_size: int) -> bool:
    """Reescala las UVs de la geometría al espacio de su celda del atlas.

    La geometría conserva `texture_width` original en cuanto a
    proporción, pero declara la CELDA como espacio UV. El render
    controller con `uv_anim` aplica después el offset y la escala global.
    El escalado aquí y en `blit_into_atlas` debe ser el mismo, o la
    textura se desincroniza de sus caras.
    """
    if not isinstance(geo_def, dict) or not isinstance(geo_def.get("description"), dict):
        return False
    desc = geo_def["description"]
    tw = desc.get("texture_width") or cell_size
    th = desc.get("texture_height") or cell_size
    su, sv = cell_size / tw, cell_size / th

    def r3(v: float) -> float:
        return round(v, 3)

    def scale_pair(vals: list) -> list:
        return [r3(vals[0] * su), r3(vals[1] * sv)]

    def scale_uv(vals: list) -> list:
        # [x, y] (box UV) o [x, y, w, h] (GeckoLib 3 en caras): ambos se
        # reescalan, cada eje con su factor.
        if len(vals) == 4:
            return [r3(vals[0] * su), r3(vals[1] * sv), r3(vals[2] * su), r3(vals[3] * sv)]
        return scale_pair(vals)

    def scale_face(face: dict) -> None:
        if isinstance(face.get("uv"), list):
            face["uv"] = scale_uv(face["uv"])
        if isinstance(face.get("uv_size"), list):
            face["uv_size"] = scale_pair(face["uv_size"])

    for bone in geo_def.get("bones") or []:
        if not isinstance(bone, dict):
            continue
        for cube in bone.get("cubes") or []:
            if not isinstance(cube, dict):
                continue
            uv = cube.get("uv")
            if isinstance(uv, list) and len(uv) in (2, 4):
                cube["uv"] = scale_uv(uv)
            box_uv = cube.get("box_uv")
            if isinstance(box_uv, dict):
                for key in ("uv", "uv_size"):
                    if isinstance(box_uv.get(key), list):
                        box_uv[key] = scale_pair(box_uv[key])
            if isinstance(cube.get("uv_size"), list):
                cube["uv_size"] = scale_pair(cube["uv_size"])
            faces = cube.get("faces")
            if isinstance(faces, dict):
                for face in faces.values():
                    if isinstance(face, dict):
                        scale_face(face)

    desc["texture_width"] = cell_size
    desc["texture_height"] = cell_size
    return True


def blit_into_atlas(dst: bytearray, dst_size: int, src: Png, cell: dict) -> None:
    """Pinta una textura en su celda del atlas (vecino más próximo)."""
    sw, sh = cell["w"], cell["h"]
    su, sv = src.width / sw, src.height / sh
    for y in range(sh):
        dy = cell["y"] + y
        if dy < 0 or dy >= dst_size:
            continue
        for x in range(sw):
            dx = cell["x"] + x
            if dx < 0 or dx >= dst_size:
                continue
            sx = min(src.width - 1, int(x * su))
            sy = min(src.height - 1, int(y * sv))
            si = (sy * src.width + sx) * 4
            di = (dy * dst_size + dx) * 4
            dst[di] = src.pixels[si]
            dst[di + 1] = src.pixels[si + 1]
            dst[di + 2] = src.pixels[si + 2]
            dst[di + 3] = src.pixels[si + 3]


# ------------------------------------------------------------------ bounds

def geometry_bounds(geo_def: dict) -> tuple[float, float, float, float, float, float] | None:
    """AABB (x0,y0,z0,x1,y1,z1) de todos los cubos de la geometría.

    En espacio Bedrock: x/z en [-8..8], y en [0..16] aprox. Lo usan las
    cajas de colisión de bloques y entidades: medidas del modelo real,
    no inventadas.
    """
    x0 = y0 = z0 = 1e9
    x1 = y1 = z1 = -1e9
    any_cube = False
    for bone in geo_def.get("bones") or []:
        if not isinstance(bone, dict):
            continue
        for cube in bone.get("cubes") or []:
            if not isinstance(cube, dict):
                continue
            o, s = cube.get("origin"), cube.get("size")
            if not isinstance(o, list) or not isinstance(s, list) or len(o) != 3 or len(s) != 3:
                continue
            any_cube = True
            x0 = min(x0, o[0], o[0] + s[0])
            x1 = max(x1, o[0], o[0] + s[0])
            y0 = min(y0, o[1], o[1] + s[1])
            y1 = max(y1, o[1], o[1] + s[1])
            z0 = min(z0, o[2], o[2] + s[2])
            z1 = max(z1, o[2], o[2] + s[2])
    if not any_cube:
        return None
    return (x0, y0, z0, x1, y1, z1)
