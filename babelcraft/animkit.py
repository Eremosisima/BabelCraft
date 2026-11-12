"""Normalización y selección de animaciones GeckoLib -> Bedrock.

Por qué un módulo aparte: las animaciones son el punto donde un conversor
"casi funciona" y luego el mob se queda quieto, o donde un JSON con una
sola clave rara tumba la entidad entera. Aquí se concentra todo lo que
hay que tolerar de los corpus reales:

  - documentos dedicados (``gob.animation.json``), compartidos
    (``common.animation.json``) y en carpetas de GeckoLib 4
    (``animations/entity/``, ``geckolib/animations/``);
  - ``animators`` de GeckoLib 3 -> ``bones`` de Bedrock;
  - ``format_version`` y ``animation_length`` ausentes;
  - keyframes con tiempos no numéricos, valores escalares o
    interpolación ``pre``/``post``;
  - controladores de animación (``animation_controllers``) con estados,
    transiciones y nombres cortos que hay que resolver contra las
    animaciones realmente cargadas.

Nada se inventa: lo que no se puede normalizar se omite y se anota. El
objetivo es que una animación rara no impida convertir la entidad ni el
resto del addon.
"""

from __future__ import annotations

import re

ANIMATION_FORMAT = "1.8.0"
CONTROLLER_FORMAT = "1.8.0"

_BONE_CHANNELS = ("rotation", "position", "scale")
_ANIM_EXTRA_KEYS = (
    "particle_effects",
    "sound_effects",
    "start_delay",
    "blend_weight",
    "override_previous_animation",
)
_STATE_EXTRA_KEYS = (
    "transitions",
    "blend_transition",
    "blend_via_shortest_path",
    "on_entry",
    "on_exit",
    "particle_effects",
    "sound_effects",
)

# Prioridad de slots. Cada animación se asigna como mucho a un slot.
_SLOT_PATTERNS = (
    ("idle", ("idle", "ambient", "rest", "default")),
    ("walk", ("walk", "move")),
    ("run", ("run", "sprint")),
    ("swim", ("swim", "floating", "float")),
    ("fly", ("fly", "glide", "hover")),
    ("attack", ("attack", "swing", "bite", "shoot", "cast")),
    ("death", ("death", "die", "death_loop")),
    ("spawn", ("spawn", "birth", "appear")),
)


# ---------------------------------------------------------------------------
#  Saneado de documentos
# ---------------------------------------------------------------------------


def sanitize_animations(data, notes: list | None = None) -> dict | None:
    """Normaliza un documento de animaciones a Bedrock 1.8.0.

    Devuelve ``{"format_version": ..., "animations": {...}}`` o ``None``
    si no queda ninguna animación utilizable. Cada problema se añade a
    `notes` (si se pasa); nunca lanza por datos malformados.
    """
    note = _note_fn(notes)
    if not isinstance(data, dict):
        note("documento de animaciones ilegible")
        return None
    raw = data.get("animations")
    if not isinstance(raw, dict):
        note("documento sin bloque 'animations' legible")
        return None

    out: dict[str, dict] = {}
    for key, anim in raw.items():
        if not isinstance(key, str) or not key:
            note("animación con nombre inválido: se omite")
            continue
        clean = _sanitize_one(key, anim, note)
        if clean is not None:
            out[key] = clean

    if not out:
        note("sin animaciones utilizables")
        return None
    fmt = data.get("format_version")
    return {
        "format_version": fmt if isinstance(fmt, str) and fmt else ANIMATION_FORMAT,
        "animations": out,
    }


def _sanitize_one(key: str, anim, note) -> dict | None:
    if not isinstance(anim, dict):
        note(f"animación {key}: no es un objeto")
        return None

    bones = anim.get("bones")
    if not isinstance(bones, dict):
        legacy = anim.get("animators")
        if isinstance(legacy, dict):
            bones = legacy
            note(f"{key}: 'animators' (GeckoLib) -> 'bones' (Bedrock)")
        else:
            bones = None

    has_effects = any(
        isinstance(anim.get(k), dict) and anim.get(k)
        for k in ("particle_effects", "sound_effects")
    )
    if not bones and not has_effects:
        note(f"animación {key}: sin huesos ni efectos; se omite")
        return None

    out: dict = {}
    if "loop" in anim:
        loop = anim["loop"]
        if isinstance(loop, bool) or loop == "hold_on_last_frame":
            out["loop"] = loop
        else:
            note(f"{key}: loop={loop!r} no válido; se omite (Bedrock asume false)")

    if isinstance(bones, dict):
        clean_bones: dict[str, dict] = {}
        for bname, bdata in bones.items():
            if not isinstance(bname, str) or not bname or not isinstance(bdata, dict):
                continue
            cb = _sanitize_bone(bname, bdata, key, note)
            if cb:
                clean_bones[bname] = cb
        if clean_bones:
            out["bones"] = clean_bones
        elif not has_effects:
            note(f"animación {key}: huesos sin canales válidos; se omite")
            return None

    for k in _ANIM_EXTRA_KEYS:
        if k in anim and isinstance(anim[k], (dict, list, bool, int, float, str)):
            if k == "particle_effects":
                # Sanitizar particle_effects para eliminar queries inválidos
                sanitized_effects = _sanitize_particle_effects(anim[k], note)
                if sanitized_effects:
                    out[k] = sanitized_effects
            else:
                out[k] = anim[k]

    length = _as_float(anim.get("animation_length"))
    if length is None or length <= 0:
        computed = _max_time(out)
        if computed > 0:
            length = computed
            note(f"{key}: animation_length ausente; calculado {length:g}s")
    if length is not None and length > 0:
        out["animation_length"] = _round(length)
    return out


def _sanitize_bone(bname: str, data: dict, anim_key: str, note) -> dict:
    out: dict = {}
    for ch in _BONE_CHANNELS:
        if ch not in data:
            continue
        chv = data[ch]
        # Valor escalar (canal completo = constante numérica).
        if isinstance(chv, (int, float)) and not isinstance(chv, bool):
            if ch == "scale":
                out[ch] = _round(float(chv))
            else:
                note(f"{anim_key}.{bname}.{ch}: valor escalar no válido; se omite")
            continue
        # Valor estático (canal completo = lista [x, y, z] con Molang o números).
        if isinstance(chv, list):
            clean_vec = _sanitize_vec(chv, note)
            if clean_vec is not None:
                out[ch] = clean_vec
            else:
                note(f"{anim_key}.{bname}.{ch}: lista estática sin valores legibles; se omite")
            continue
        if not isinstance(chv, dict):
            note(f"{anim_key}.{bname}.{ch}: formato no reconocido; se omite")
            continue

        clean: dict = {}
        for t, v in chv.items():
            tf = _as_float(t)
            if tf is None or tf < 0:
                note(f"{anim_key}.{bname}.{ch}: tiempo {t!r} no numérico; se omite")
                continue
            key = str(t)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                clean[key] = _round(float(v))
            elif isinstance(v, str):
                # Molang en keyframe: reemplazar queries inválidos con valores por defecto
                if _has_invalid_molang(v):
                    replaced = _replace_invalid_molang(v)
                    note(f"{anim_key}.{bname}.{ch}: query inválido reemplazado: {v[:30]}... -> {replaced[:30]}...")
                    clean[key] = replaced
                elif _is_molang(v):
                    clean[key] = v
                else:
                    note(f"{anim_key}.{bname}.{ch}: keyframe {t!r} con string no-Molang; se omite")
            elif isinstance(v, list):
                clean_vec = _sanitize_vec(v, note)
                if clean_vec is not None:
                    clean[key] = clean_vec
                else:
                    note(f"{anim_key}.{bname}.{ch}: keyframe {t!r} sin valores legibles; se omite")
            elif isinstance(v, dict):
                # Keyframe con interpolación pre/post
                item = {}
                lerp_mode = v.get("lerp_mode")
                # Bedrock: catmullrom/precomputed cubic requiere datos constantes;
                # para evitar errores, degradamos a linear y colapsamos a valor simple.
                use_simple = isinstance(lerp_mode, str) and lerp_mode.lower() == "catmullrom"
                for k in ("pre", "post", "lerp_mode"):
                    if k not in v:
                        continue
                    val = v[k]
                    if k == "lerp_mode":
                        if isinstance(val, str):
                            if val.lower() == "catmullrom":
                                item[k] = "linear"
                            else:
                                item[k] = val
                    elif isinstance(val, (int, float)) and not isinstance(val, bool):
                        item[k] = _round(float(val))
                    elif isinstance(val, str):
                        if _has_invalid_molang(val):
                            item[k] = _replace_invalid_molang(val)
                        elif _is_molang(val):
                            item[k] = val
                    elif isinstance(val, list):
                        # pre/post pueden ser listas [x, y, z]
                        clean_vec = _sanitize_vec(val, note)
                        if clean_vec is not None:
                            item[k] = clean_vec
                # Si era catmullrom, colapsar a un valor constante simple (post > pre)
                if use_simple:
                    simple_val = item.get("post", item.get("pre"))
                    if simple_val is not None:
                        # solo permitir valores constantes (números/listas numéricas)
                        if isinstance(simple_val, (int, float)) and not isinstance(simple_val, bool):
                            clean[key] = _round(float(simple_val))
                            continue
                        if isinstance(simple_val, list) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in simple_val):
                            clean[key] = [_round(float(x)) for x in simple_val]
                            continue
                        # si no es constante, degradar a linear y conservar estructura sin catmullrom
                        item["lerp_mode"] = "linear"
                    else:
                        note(f"{anim_key}.{bname}.{ch}: keyframe {t!r} catmullrom sin valor usable; se omite")
                        continue
                if item:
                    clean[key] = item
                else:
                    note(f"{anim_key}.{bname}.{ch}: keyframe {t!r} sin valor legible; se omite")
            else:
                note(f"{anim_key}.{bname}.{ch}: keyframe {t!r} sin valor legible; se omite")
        if clean:
            out[ch] = clean
    
    # relative_to: dict con claves 'model' y/o 'parent' (bool). Se preserva.
    rt = data.get("relative_to")
    if isinstance(rt, dict):
        clean_rt = {k: v for k, v in rt.items() if k in ("model", "parent") and isinstance(v, bool)}
        if clean_rt:
            out["relative_to"] = clean_rt
    
    return out


# Queries de Cobblemon/mods que NO existen en Bedrock y deben reemplazarse
# Patrón general para todos los queries q.r.* (rider queries)
_INVALID_MOLANG_PATTERNS = [
    # Patrón general para queries de rider (q.r.*)
    r"q\.r\.[a-z_]+(\([^)]*\))?",  # q.r.anything() o q.r.anything
    # Queries específicos de entidad custom (no soportados en Bedrock)
    r"q\.has_entity",
    r"q\.is_riding",
    r"q\.is_being_ridden",
    # Queries de sonido custom (no soportados en Bedrock)
    r"q\.sound",
    # Queries de animación custom (no soportados en Bedrock)
    r"q\.anim_progress",
    r"q\.custom_",
    # Queries de input (no soportados en Bedrock para entidades)
    r"q\.input_[a-z_]+(\([^)]*\))?",  # q.input_up(), q.input_down(), etc.
]


def _has_invalid_molang(s: str) -> bool:
    """Detecta si un string contiene queries de Molang no soportados en Bedrock."""
    if not s:
        return False
    for pattern in _INVALID_MOLANG_PATTERNS:
        if re.search(pattern, s, re.IGNORECASE):
            return True
    return False


def _sanitize_particle_effects(data, note) -> dict | None:
    """Sanitiza particle_effects eliminando queries inválidos.
    
    Los particle_effects pueden tener scripts con queries como q.input_up()
    que no son soportados en Bedrock para entidades.
    """
    if not isinstance(data, dict):
        return None
    
    sanitized = {}
    for time_key, effect_data in data.items():
        if not isinstance(effect_data, dict):
            continue
        
        # Crear copia del efecto
        effect_copy = {}
        for key, value in effect_data.items():
            if key == "pre_effect_script":
                # Sanitizar el script
                if isinstance(value, str):
                    if _has_invalid_molang(value):
                        note(f"particle_effects[{time_key}].{key}: query inválido detectado, reemplazado con '0'")
                        effect_copy[key] = "0"
                    else:
                        effect_copy[key] = value
                else:
                    effect_copy[key] = value
            else:
                effect_copy[key] = value
        
        sanitized[time_key] = effect_copy
    
    return sanitized if sanitized else None


def _replace_invalid_molang(s: str) -> str:
    """Reemplaza queries de Molang no soportados con valores por defecto.
    
    Si el resultado es una expresión malformada, reemplaza toda la expresión con "0".
    """
    if not s:
        return s
    
    result = s
    for pattern in _INVALID_MOLANG_PATTERNS:
        result = re.sub(pattern, "0", result, flags=re.IGNORECASE)
    
    result = _clean_molang_expression(result)
    
    # Validar que la expresión resultante sea válida
    if not _is_valid_molang(result):
        # Si es inválida, reemplazar toda la expresión con "0"
        return "0"
    
    return result


def _is_valid_molang(s: str) -> bool:
    """Valida que una expresión Molang esté bien formada.
    
    Verifica:
    - Paréntesis balanceados
    - Funciones con número correcto de parámetros
    - No hay operadores sin operandos
    """
    if not s or s.strip() == "":
        return False
    
    # Verificar paréntesis balanceados
    open_count = s.count("(")
    close_count = s.count(")")
    if open_count != close_count:
        return False
    
    # Verificar que no haya operadores al final o inicio (excepto - para negativos)
    stripped = s.strip()
    if stripped.endswith(("+", "*", "/")):
        return False
    if stripped.startswith(("+", "*", "/")):
        return False
    
    # Verificar que math.clamp tenga 3 parámetros
    clamp_pattern = r'math\.clamp\s*\([^)]+\)'
    for match in re.finditer(clamp_pattern, s, re.IGNORECASE):
        clamp_call = match.group(0)
        # Contar parámetros (separados por comas, pero respetando paréntesis anidados)
        params_str = clamp_call[clamp_call.index("(")+1:clamp_call.rindex(")")]
        # Contar comas fuera de paréntesis anidados
        depth = 0
        comma_count = 0
        for char in params_str:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif char == ',' and depth == 0:
                comma_count += 1
        # math.clamp necesita exactamente 3 parámetros (2 comas)
        if comma_count != 2:
            return False
    
    # Verificar que no haya números pegados a funciones (ej: "3math.sin")
    if re.search(r'\d+[a-zA-Z_]', s):
        return False
    
    # Verificar que no haya operadores consecutivos sin operandos (excepto negativos)
    # Buscar patrones como "+*", "-/", "*+", etc.
    if re.search(r'[\+\-\*\/][\+\*\/]', s):
        return False
    # Buscar patrones como "*-" al inicio o después de "("
    if re.search(r'[\(\s]\*-', s):
        return False
    
    return True


def _clean_molang_expression(expr: str) -> str:
    """Limpia una expresión Molang después de reemplazar queries inválidos.
    
    Maneja casos como:
    - "+algo" -> "algo"
    - "0 * algo" -> "0"
    - "0 + algo" -> "algo"
    - "algo + 0" -> "algo"
    - "0 - algo" -> "-algo"
    - Expresiones malformadas -> "0"
    """
    if not expr:
        return "0"
    
    # Eliminar espacios extra
    expr = expr.strip()
    
    # Si la expresión está vacía después de limpiar, devolver "0"
    if not expr:
        return "0"
    
    # Si comienza con un operador binario (+, *, /), eliminarlo
    # (excepto - que puede ser un negativo)
    if expr.startswith(('+', '*', '/')):
        expr = expr[1:].strip()
    
    # Si termina con un operador, es malformada
    if expr.endswith(('+', '-', '*', '/')):
        return "0"
    
    # Verificar paréntesis balanceados
    open_parens = expr.count("(")
    close_parens = expr.count(")")
    if open_parens != close_parens:
        return "0"
    
    # Si hay paréntesis sin cerrar o sin abrir, es malformada
    depth = 0
    for char in expr:
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth < 0:
                return "0"
    if depth != 0:
        return "0"
    
    # Simplificar expresiones con 0
    # "0 * algo" -> "0"
    expr = re.sub(r'\b0\s*\*\s*[^\s]+', '0', expr)
    # "algo * 0" -> "0"
    expr = re.sub(r'[^\s]+\s*\*\s*0\b', '0', expr)
    
    # "0 + algo" -> "algo"
    expr = re.sub(r'\b0\s*\+\s*', '', expr)
    # "algo + 0" -> "algo"
    expr = re.sub(r'\s*\+\s*0\b', '', expr)
    
    # "0 - algo" -> "-(algo)"
    expr = re.sub(r'\b0\s*\-\s*(\w)', r'-\1', expr)
    
    # Limpiar espacios extra
    expr = re.sub(r'\s+', ' ', expr).strip()
    
    # Si la expresión quedó vacía o solo con operadores, devolver "0"
    if not expr or expr in ('+', '-', '*', '/'):
        return "0"
    
    # Si después de limpiar todavía hay operadores malformados, devolver "0"
    if not _is_valid_molang(expr):
        return "0"
    
    return expr


def _is_molang(s: str) -> bool:
    """Heurística: un string es Molang plausible si contiene patrones típicos
    de Molang (math.*, query.*, variable.*, alias.*, o referencias con '.').
    Strings arbitrarios sin estos patrones se rechazan.
    
    NOTA: Los queries inválidos (q.r.*, q.sound, etc.) se permiten y se
    reemplazarán con valores por defecto en _replace_invalid_molang.
    """
    if not s:
        return False
    s_lower = s.lower()
    
    # Patrones típicos de Molang
    molang_prefixes = ("math.", "query.", "variable.", "alias.", "context.", "temp.")
    if any(s_lower.startswith(p) or f"({p}" in s_lower or f" {p}" in s_lower for p in molang_prefixes):
        return True
    # Operadores o referencias con puntos (ej: "query.life_time")
    if "." in s and any(op in s for op in ("+", "-", "*", "/", "(", ")", "=", "<", ">")):
        return True
    # Referencias con punto (ej: "geometry.some_bone")
    if "." in s and not s.startswith("."):
        return True
    return False


def _sanitize_vec(vec: list, note) -> list | None:
    """Limpia un vector [x, y, z]: acepta números y strings Molang.
    
    Devuelve None si ningún elemento es legible. Preserva el orden y tipo
    de cada componente (número o string).
    
    Reemplaza queries no soportados en Bedrock con valores por defecto (0).
    """
    if not isinstance(vec, list) or len(vec) < 2:
        return None
    clean = []
    for elem in vec[:3]:  # máximo 3 componentes (x, y, z)
        if isinstance(elem, (int, float)) and not isinstance(elem, bool):
            clean.append(_round(float(elem)))
        elif isinstance(elem, str):
            # Molang: reemplazar queries inválidos con valores por defecto
            if _has_invalid_molang(elem):
                replaced = _replace_invalid_molang(elem)
                note(f"Molang con query no soportado reemplazado: {elem[:40]}... -> {replaced[:40]}...")
                clean.append(replaced)
            else:
                clean.append(elem)
    return clean if clean else None


# ---------------------------------------------------------------------------
#  Alias y slots
# ---------------------------------------------------------------------------


def build_aliases(anims_doc: dict | None) -> tuple[dict[str, str], dict[str, str]]:
    """Devuelve (alias -> nombre completo, nombre completo -> alias)."""
    alias_map: dict[str, str] = {}
    by_name: dict[str, str] = {}
    if not isinstance(anims_doc, dict):
        return alias_map, by_name
    for full in (anims_doc.get("animations") or {}):
        if not isinstance(full, str):
            continue
        alias = unique_alias(_short(full), alias_map)
        alias_map[alias] = full
        by_name[full] = alias
    return alias_map, by_name


def unique_alias(base: str, used) -> str:
    alias = base or "anim"
    i = 1
    while alias in used:
        i += 1
        alias = f"{base}_{i}"
    return alias


def select_slots(anims_doc: dict | None) -> dict[str, str]:
    """Asigna animaciones a slots (idle, walk, ...) con prioridad estable.

    Primero busca coincidencia exacta del último segmento del nombre
    (``...gob.idle`` -> ``idle``); después, subcadena. Una animación no
    se reutiliza en dos slots. ``walk`` cae a ``run`` si no hay otra.
    """
    if not isinstance(anims_doc, dict):
        return {}
    keys = [k for k in (anims_doc.get("animations") or {}) if isinstance(k, str)]
    used: set[str] = set()
    slots: dict[str, str] = {}

    for slot, patterns in _SLOT_PATTERNS:
        hit = next(
            (
                k
                for p in patterns
                for k in keys
                if k not in used and _short(k) == p
            ),
            None,
        )
        if hit is None:
            hit = next(
                (
                    k
                    for p in patterns
                    for k in keys
                    if k not in used and len(p) >= 3 and p in k.lower()
                ),
                None,
            )
        if hit is not None:
            slots[slot] = hit
            used.add(hit)

    if "walk" not in slots and "run" in slots:
        slots["walk"] = slots["run"]
    return slots


def _short(name: str) -> str:
    s = str(name).split(".")[-1].lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s).strip("_")
    return s or "anim"


# ---------------------------------------------------------------------------
#  Controladores de animación
# ---------------------------------------------------------------------------


def controller_refs(data) -> set[str]:
    """Nombres de animación referenciados por los estados de un doc."""
    refs: set[str] = set()
    if not isinstance(data, dict):
        return refs
    ctrls = data.get("animation_controllers")
    if not isinstance(ctrls, dict):
        return refs
    for ctrl in ctrls.values():
        states = ctrl.get("states") if isinstance(ctrl, dict) else None
        if not isinstance(states, dict):
            continue
        for state in states.values():
            if not isinstance(state, dict):
                continue
            anims = state.get("animations")
            if isinstance(anims, list):
                for a in anims:
                    if isinstance(a, str) and a:
                        refs.add(a)
                    elif isinstance(a, dict):
                        refs |= {k for k in a if isinstance(k, str) and k}
    return refs


def sanitize_controllers(
    data,
    full_names: set[str],
    by_name: dict[str, str],
    notes: list | None = None,
) -> dict | None:
    """Normaliza ``animation_controllers`` y resuelve nombres cortos a alias.

    Devuelve ``{"format_version": ..., "animation_controllers": {...}}`` o
    ``None``. Los nombres de animación de cada estado se sustituyen por el
    alias del client entity (Bedrock los resuelve contra ese mapa). Si una
    referencia no existe, se conserva y se anota para que el usuario lo
    vea en el informe.
    """
    note = _note_fn(notes)
    if not isinstance(data, dict):
        return None
    raw = data.get("animation_controllers")
    if not isinstance(raw, dict) or not raw:
        return None

    out: dict[str, dict] = {}
    for ctrl_id, ctrl in raw.items():
        if not isinstance(ctrl_id, str) or not ctrl_id or not isinstance(ctrl, dict):
            note("controlador con nombre o cuerpo inválido: se omite")
            continue
        states = ctrl.get("states")
        if not isinstance(states, dict) or not states:
            note(f"{ctrl_id}: sin 'states'; se omite")
            continue

        clean_states: dict[str, dict] = {}
        for state_name, state in states.items():
            if not isinstance(state_name, str) or not isinstance(state, dict):
                note(f"{ctrl_id}: estado inválido {state_name!r}; se omite")
                continue
            clean_states[state_name] = _sanitize_state(
                ctrl_id, state_name, state, full_names, by_name, note
            )
        if not clean_states:
            note(f"{ctrl_id}: sin estados utilizables; se omite")
            continue

        clean: dict = {"states": clean_states}
        initial = ctrl.get("initial_state")
        if isinstance(initial, str) and initial in clean_states:
            clean["initial_state"] = initial
        else:
            clean["initial_state"] = next(iter(clean_states))
            if initial is not None:
                note(f"{ctrl_id}: initial_state {initial!r} no existe; se usa el primero")
        out[ctrl_id] = clean

    if not out:
        return None
    fmt = data.get("format_version")
    return {
        "format_version": fmt if isinstance(fmt, str) and fmt else CONTROLLER_FORMAT,
        "animation_controllers": out,
    }


def _sanitize_state(
    ctrl_id: str,
    state_name: str,
    state: dict,
    full_names: set[str],
    by_name: dict[str, str],
    note,
) -> dict:
    out: dict = {}

    anims = state.get("animations")
    if isinstance(anims, list):
        clean_anims: list = []
        for ref in anims:
            if isinstance(ref, str) and ref:
                full = resolve_animation(ref, full_names)
                if full is not None:
                    clean_anims.append(by_name.get(full, ref))
                else:
                    clean_anims.append(ref)
                    note(
                        f"{ctrl_id}.{state_name}: animación {ref!r} no encontrada; "
                        "se conserva el nombre y puede no reproducirse"
                    )
            elif isinstance(ref, dict):
                entry = {}
                for ref_name, molang in ref.items():
                    if not isinstance(ref_name, str):
                        continue
                    full = resolve_animation(ref_name, full_names)
                    alias = by_name.get(full, ref_name) if full else ref_name
                    entry[alias] = molang
                    if full is None:
                        note(f"{ctrl_id}.{state_name}: animación {ref_name!r} no encontrada")
                if entry:
                    clean_anims.append(entry)
        if clean_anims:
            out["animations"] = clean_anims
        elif anims:
            note(f"{ctrl_id}.{state_name}: sin animaciones válidas")

    for key in _STATE_EXTRA_KEYS:
        if key not in state:
            continue
        value = state[key]
        if key == "transitions":
            clean_tr = [
                {k: v for k, v in tr.items() if isinstance(k, str) and isinstance(v, str)}
                for tr in value
                if isinstance(tr, dict)
            ] if isinstance(value, list) else []
            clean_tr = [tr for tr in clean_tr if tr]
            if clean_tr:
                out["transitions"] = clean_tr
            elif value:
                note(f"{ctrl_id}.{state_name}: transiciones no válidas; se omiten")
        elif isinstance(value, (dict, list, bool, int, float, str)):
            out[key] = value
    return out


def resolve_animation(ref: str, full_names: set[str]) -> str | None:
    """Resuelve un nombre corto (``idle``) al nombre completo cargado."""
    if not ref or not full_names:
        return None
    if ref in full_names:
        return ref
    ref_short = _short(ref)
    for full in full_names:
        if _short(full) == ref_short:
            return full
    low = ref.lower()
    for full in full_names:
        fl = full.lower()
        if fl.endswith("." + low) or fl.endswith("_" + low):
            return full
    if len(low) >= 3:
        for full in full_names:
            if low in full.lower():
                return full
    return None


def controller_alias(ctrl_id: str) -> str:
    """Alias estable para un controlador dentro del client entity."""
    return "controller_" + _short(ctrl_id)


# ---------------------------------------------------------------------------
#  Utilidades numéricas
# ---------------------------------------------------------------------------


def _max_time(anim: dict) -> float:
    mx = 0.0
    bones = anim.get("bones")
    if isinstance(bones, dict):
        for bone in bones.values():
            if not isinstance(bone, dict):
                continue
            for ch in _BONE_CHANNELS:
                d = bone.get(ch)
                if isinstance(d, dict):
                    for t in d:
                        tf = _as_float(t)
                        if tf is not None:
                            mx = max(mx, tf)
    for k in ("particle_effects", "sound_effects"):
        d = anim.get(k)
        if isinstance(d, dict):
            for t in d:
                tf = _as_float(t)
                if tf is not None:
                    mx = max(mx, tf)
    return mx


def _as_float(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _round(value: float) -> float | int:
    out = round(value, 4)
    return int(out) if out == int(out) else out


def _note_fn(notes: list | None):
    if notes is None:
        return lambda _msg: None
    return notes.append
