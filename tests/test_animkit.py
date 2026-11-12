"""Tests del saneado/selección de animaciones y controladores.

Estos tests son el corazón de la robustez del conversor de entidades: un
JSON de animación raro NO puede tumbar la entidad ni el addon. Aquí se
ejercitan los formatos que de verdad aparecen en mods GeckoLib 3/4 y en
documentos compartidos.
"""

from __future__ import annotations

from babelcraft.animkit import (
    ANIMATION_FORMAT,
    CONTROLLER_FORMAT,
    build_aliases,
    controller_alias,
    controller_refs,
    resolve_animation,
    sanitize_animations,
    sanitize_controllers,
    select_slots,
    unique_alias,
)


def _doc(anims: dict, fmt: str | None = "1.8.0") -> dict:
    doc = {"animations": anims}
    if fmt:
        doc["format_version"] = fmt
    return doc


def _anim(bones: dict | None = None, **extra) -> dict:
    out = dict(extra)
    if bones is not None:
        out["bones"] = bones
    return out


# ---------------------------------------------------------------------------
#  sanitize_animations
# ---------------------------------------------------------------------------


def test_sanitize_keeps_clean_document_and_format():
    doc = _doc({"animation.gob.idle": _anim({"body": {"rotation": {"0.0": [0, 0, 0], "1.0": [5, 0, 0]}}})})
    out = sanitize_animations(doc, [])
    assert out == {
        "format_version": "1.8.0",
        "animations": {
            "animation.gob.idle": {
                "bones": {"body": {"rotation": {"0.0": [0, 0, 0], "1.0": [5, 0, 0]}}},
                "animation_length": 1,
            }
        },
    }


def test_sanitize_adds_missing_format_version():
    out = sanitize_animations(_doc({"a.walk": _anim({"b": {"position": {"0.0": [0, 0, 0]}}})}, fmt=None), [])
    assert out["format_version"] == ANIMATION_FORMAT


def test_sanitize_geckolib3_animators_becomes_bones():
    anim = _anim(None, animators={"body": {"rotation": {"0.0": [0, 1, 0]}}})
    notes: list[str] = []
    out = sanitize_animations(_doc({"animation.gob.idle": anim}), notes)
    assert out["animations"]["animation.gob.idle"]["bones"] == {
        "body": {"rotation": {"0.0": [0, 1, 0]}}
    }
    assert any("animators" in n for n in notes)


def test_sanitize_computes_missing_animation_length():
    anim = _anim({"b": {"rotation": {"0.0": [0, 0, 0], "2.5": [1, 0, 0]}}})
    notes: list[str] = []
    out = sanitize_animations(_doc({"a": anim}), notes)
    assert out["animations"]["a"]["animation_length"] == 2.5
    assert any("animation_length" in n for n in notes)


def test_sanitize_keeps_explicit_length_and_recomputes_invalid():
    anim = _anim({"b": {"rotation": {"0.0": [0, 0, 0], "3.0": [1, 0, 0]}}}, animation_length=3)
    out = sanitize_animations(_doc({"a": anim}), [])
    assert out["animations"]["a"]["animation_length"] == 3

    bad = _anim({"b": {"rotation": {"0.0": [0, 0, 0], "2.0": [1, 0, 0]}}}, animation_length="much")
    notes: list[str] = []
    out = sanitize_animations(_doc({"a": bad}), notes)
    assert out["animations"]["a"]["animation_length"] == 2
    assert notes  # la longitud rara quedó anotada


def test_sanitize_drops_invalid_loop():
    notes: list[str] = []
    out = sanitize_animations(
        _doc({
            "a": _anim({"b": {"position": {"0.0": [0, 0, 0]}}}, loop="true"),
            "b": _anim({"b": {"position": {"0.0": [0, 0, 0]}}}, loop=True),
            "c": _anim({"b": {"position": {"0.0": [0, 0, 0]}}}, loop="hold_on_last_frame"),
        }),
        notes,
    )
    anims = out["animations"]
    assert "loop" not in anims["a"]
    assert anims["b"]["loop"] is True
    assert anims["c"]["loop"] == "hold_on_last_frame"
    assert any("loop" in n for n in notes)


def test_sanitize_drops_bad_keyframes_keeps_good_ones():
    anim = _anim({
        "body": {
            "rotation": {
                "abc": [0, 0, 0],          # tiempo no numérico
                "-1": [0, 0, 0],           # tiempo negativo
                "0.0": [0, 0, 0],          # válido
                "1.0": "no soy lista",     # valor ilegible
                "2.0": 5,                  # valor escalar: válido en Bedrock
                "3.0": [1, 2, 3],          # válido
                "4.0": {"pre": [0, 0, 0], "post": [1, 0, 0], "lerp_mode": "catmullrom"},
            }
        }
    })
    notes: list[str] = []
    out = sanitize_animations(_doc({"a": anim}), notes)
    rot = out["animations"]["a"]["bones"]["body"]["rotation"]
    assert list(rot) == ["0.0", "2.0", "3.0", "4.0"]
    assert rot["2.0"] == 5
    # catmullrom se degrada/colapsa a valor constante para evitar errores de Bedrock
    assert rot["4.0"] == [1, 0, 0]
    assert len(notes) >= 3  # cada descarte queda explicado


def test_sanitize_scalar_scale_ok_scalar_rotation_dropped():
    anim = _anim({"b": {"rotation": 30, "scale": 2}})
    notes: list[str] = []
    out = sanitize_animations(_doc({"a": anim}), notes)
    bone = out["animations"]["a"]["bones"]["b"]
    assert bone == {"scale": 2}
    assert any("escalar" in n for n in notes)


def test_sanitize_keeps_effects_only_animation():
    anim = {"particle_effects": {"0.5": {"effect": "smoke", "locator": "mouth"}}}
    out = sanitize_animations(_doc({"a": anim}), [])
    assert "bones" not in out["animations"]["a"]
    assert out["animations"]["a"]["particle_effects"]["0.5"]["locator"] == "mouth"
    assert out["animations"]["a"]["animation_length"] == 0.5


def test_sanitize_drops_animation_without_bones_or_effects():
    notes: list[str] = []
    out = sanitize_animations(_doc({"a": _anim({"b": {}}), "b": {"loop": True}}), notes)
    assert out is None
    assert any("sin huesos" in n or "huesos sin canales" in n for n in notes)
    assert any("sin huesos" in n for n in notes)


def test_sanitize_empty_or_garbage_documents():
    assert sanitize_animations(None, []) is None
    assert sanitize_animations("nope", []) is None
    assert sanitize_animations([], []) is None
    assert sanitize_animations({"format_version": "1.8.0"}, []) is None
    assert sanitize_animations({"animations": []}, []) is None
    assert sanitize_animations({"animations": {"a": 3, "b": "x"}}, []) is None


def test_sanitize_skips_non_string_names_and_bad_bones():
    notes: list[str] = []
    out = sanitize_animations(
        _doc({
            123: _anim({"b": {"position": {"0.0": [0, 0, 0]}}}),
            "ok": _anim({"good": {"position": {"0.0": [0, 0, 0]}}}),
            "bad": _anim({"b": "not a dict", 7: {"position": {"0.0": [0, 0, 0]}}}),
        }),
        notes,
    )
    assert set(out["animations"]) == {"ok"}
    assert any("nombre inválido" in n for n in notes)


def test_sanitize_preserves_extra_fields():
    anim = _anim(
        {"b": {"rotation": {"0.0": [0, 0, 0]}}},
        blend_weight=0.5,
        start_delay=0.1,
        override_previous_animation=True,
    )
    out = sanitize_animations(_doc({"a": anim}), [])
    a = out["animations"]["a"]
    assert a["blend_weight"] == 0.5
    assert a["start_delay"] == 0.1
    assert a["override_previous_animation"] is True


# ---------------------------------------------------------------------------
#  Alias y slots
# ---------------------------------------------------------------------------


def test_build_aliases_unique_for_same_short_name():
    doc = _doc({
        "animation.gob.idle": _anim({"b": {"position": {"0.0": [0, 0, 0]}}}),
        "animation.wisp.idle": _anim({"b": {"position": {"0.0": [0, 0, 0]}}}),
    })
    alias_map, by_name = build_aliases(doc)
    assert alias_map == {"idle": "animation.gob.idle", "idle_2": "animation.wisp.idle"}
    assert by_name == {"animation.gob.idle": "idle", "animation.wisp.idle": "idle_2"}


def test_build_aliases_tolerates_bad_doc():
    assert build_aliases(None) == ({}, {})
    assert build_aliases({"animations": {"a": _anim({"b": {"rotation": {"0": [0]}}})}})[0].keys() == {"a"}


def test_unique_alias():
    assert unique_alias("walk", set()) == "walk"
    assert unique_alias("walk", {"walk"}) == "walk_2"
    assert unique_alias("walk", {"walk", "walk_2", "walk_3"}) == "walk_4"
    assert unique_alias("", set()) == "anim"


def test_select_slots_exact_and_no_reuse():
    doc = _doc({
        "animation.model.idle": _anim(),
        "animation.model.walk": _anim(),
        "animation.model.attack": _anim(),
    })
    assert select_slots(doc) == {
        "idle": "animation.model.idle",
        "walk": "animation.model.walk",
        "attack": "animation.model.attack",
    }


def test_select_slots_falls_back_run_to_walk():
    doc = _doc({"animation.model.run": _anim()})
    slots = select_slots(doc)
    assert slots["run"] == "animation.model.run"
    assert slots["walk"] == "animation.model.run"  # reutilizado a propósito


def test_select_slots_substring_match_and_ambient():
    doc = _doc({
        "animation.model.walk_slow": _anim(),
        "animation.model.ambient": _anim(),
    })
    slots = select_slots(doc)
    assert slots["idle"] == "animation.model.ambient"
    assert slots["walk"] == "animation.model.walk_slow"


def test_select_slots_priority_idle_ambient_does_not_steal():
    # "ambient" y "idle" son patrones del MISMO slot: gana el orden de
    # patrones (idle), no el orden del diccionario.
    doc = _doc({
        "animation.model.ambient": _anim(),
        "animation.model.idle": _anim(),
    })
    assert select_slots(doc)["idle"] == "animation.model.idle"


def test_select_slots_tolerates_garbage():
    assert select_slots(None) == {}
    assert select_slots({"animations": {}}) == {}
    assert select_slots({"animations": {"a": "x"}}) == {}


# ---------------------------------------------------------------------------
#  resolve_animation
# ---------------------------------------------------------------------------


FULL = {"animation.gob.idle", "animation.gob.walk", "animation.wisp.attack"}


def test_resolve_animation_exact_and_short():
    assert resolve_animation("animation.gob.idle", FULL) == "animation.gob.idle"
    assert resolve_animation("idle", FULL) == "animation.gob.idle"
    assert resolve_animation("attack", FULL) == "animation.wisp.attack"


def test_resolve_animation_suffix_match():
    assert resolve_animation("gob.idle", FULL) == "animation.gob.idle"
    assert resolve_animation("walk", FULL) == "animation.gob.walk"


def test_resolve_animation_no_match():
    assert resolve_animation("xyz", FULL) is None
    assert resolve_animation("", FULL) is None
    assert resolve_animation("idle", set()) is None
    # Los prefijos cortos (< 3 chars) no hacen substring para no casar ruido.
    assert resolve_animation("ob", FULL) is None


# ---------------------------------------------------------------------------
#  Controladores
# ---------------------------------------------------------------------------


def _ctrl_doc(ctrls: dict, fmt: str | None = "1.8.0") -> dict:
    doc = {"animation_controllers": ctrls}
    if fmt:
        doc["format_version"] = fmt
    return doc


def _names_for(anims: dict) -> tuple[set, dict]:
    sanitized = sanitize_animations(_doc(anims))
    assert sanitized is not None
    alias_map, by_name = build_aliases(sanitized)
    return set(sanitized["animations"]), by_name


def test_controller_refs_collects_strings_and_molang():
    data = _ctrl_doc({
        "controller.animation.gob": {
            "initial_state": "idle",
            "states": {
                "idle": {"animations": ["animation.gob.idle", {"animation.gob.walk": "q.x > 1"}]},
                "walk": {"animations": ["animation.gob.walk"]},
            },
        }
    })
    assert controller_refs(data) == {"animation.gob.idle", "animation.gob.walk"}
    assert controller_refs(None) == set()
    assert controller_refs({"animations": {}}) == set()


def test_sanitize_controllers_rewrites_refs_to_aliases():
    full_names, by_name = _names_for({
        "animation.gob.idle": _anim({"b": {"rotation": {"0.0": [0, 0, 0]}}}),
        "animation.gob.walk": _anim({"b": {"rotation": {"0.0": [0, 0, 0]}}}),
    })
    data = _ctrl_doc({
        "controller.animation.gob": {
            "initial_state": "idle",
            "states": {
                "idle": {"animations": ["animation.gob.idle"]},
                "walk": {
                    "animations": [
                        "animation.gob.walk",
                        {"animation.gob.idle": "q.modified_move_speed > 0.1"},
                    ],
                    "transitions": [{"idle": "q.modified_move_speed <= 0.1"}],
                },
            },
        }
    })
    notes: list[str] = []
    out = sanitize_controllers(data, full_names, by_name, notes)
    assert out["format_version"] == CONTROLLER_FORMAT
    ctrl = out["animation_controllers"]["controller.animation.gob"]
    assert ctrl["initial_state"] == "idle"
    assert ctrl["states"]["idle"]["animations"] == ["idle"]
    assert ctrl["states"]["walk"]["animations"] == ["walk", {"idle": "q.modified_move_speed > 0.1"}]
    assert ctrl["states"]["walk"]["transitions"] == [{"idle": "q.modified_move_speed <= 0.1"}]
    assert notes == []


def test_sanitize_controllers_resolves_short_names():
    full_names, by_name = _names_for({
        "animation.gob.idle": _anim({"b": {"rotation": {"0.0": [0, 0, 0]}}}),
    })
    data = _ctrl_doc({
        "controller.animation.gob": {
            "states": {"default": {"animations": ["idle"]}},
        }
    })
    out = sanitize_controllers(data, full_names, by_name, [])
    assert out["animation_controllers"]["controller.animation.gob"]["states"]["default"]["animations"] == ["idle"]


def test_sanitize_controllers_keeps_unresolved_ref_with_note():
    full_names, by_name = _names_for({
        "animation.gob.idle": _anim({"b": {"rotation": {"0.0": [0, 0, 0]}}}),
    })
    data = _ctrl_doc({
        "controller.animation.gob": {
            "states": {
                "default": {"animations": ["no_existe", "animation.gob.idle"]},
            },
        }
    })
    notes: list[str] = []
    out = sanitize_controllers(data, full_names, by_name, notes)
    state = out["animation_controllers"]["controller.animation.gob"]["states"]["default"]
    assert state["animations"] == ["no_existe", "idle"]
    assert any("no_existe" in n for n in notes)


def test_sanitize_controllers_initial_state_fallback():
    full_names, by_name = _names_for({"animation.gob.idle": _anim({"b": {"rotation": {"0.0": [0, 0, 0]}}})})
    data = _ctrl_doc({
        "controller.animation.gob": {
            "initial_state": "ghost_state",
            "states": {"first": {"animations": ["idle"]}, "second": {}},
        }
    })
    notes: list[str] = []
    out = sanitize_controllers(data, full_names, by_name, notes)
    ctrl = out["animation_controllers"]["controller.animation.gob"]
    assert ctrl["initial_state"] == "first"
    assert any("initial_state" in n for n in notes)


def test_sanitize_controllers_filters_garbage():
    full_names, by_name = _names_for({"animation.gob.idle": _anim({"b": {"rotation": {"0.0": [0, 0, 0]}}})})
    data = _ctrl_doc({
        "controller.animation.good": {
            "states": {"default": {"animations": ["idle"], "blend_transition": 0.2}},
        },
        "controller.animation.no_states": {"states": []},
        "controller.animation.bad_states": {"states": {"x": "no dict"}},
        123: {"states": {"default": {}}},
        "controller.animation.none": None,
    })
    notes: list[str] = []
    out = sanitize_controllers(data, full_names, by_name, notes)
    assert set(out["animation_controllers"]) == {"controller.animation.good"}
    assert out["animation_controllers"]["controller.animation.good"]["states"]["default"]["blend_transition"] == 0.2
    assert len(notes) >= 3  # cada controlador descartado quedó anotado


def test_sanitize_controllers_bad_transitions_and_animations():
    full_names, by_name = _names_for({"animation.gob.idle": _anim({"b": {"rotation": {"0.0": [0, 0, 0]}}})})
    data = _ctrl_doc({
        "controller.animation.gob": {
            "states": {
                "default": {
                    "animations": ["idle", None, 42, {"idle": "q.x"}],
                    "transitions": "no soy lista",
                },
            },
        }
    })
    notes: list[str] = []
    out = sanitize_controllers(data, full_names, by_name, notes)
    state = out["animation_controllers"]["controller.animation.gob"]["states"]["default"]
    assert state["animations"] == ["idle", {"idle": "q.x"}]
    assert "transitions" not in state
    assert any("transiciones" in n for n in notes)


def test_sanitize_controllers_none_for_empty_or_garbage():
    full_names, by_name = _names_for({"animation.gob.idle": _anim({"b": {"rotation": {"0.0": [0, 0, 0]}}})})
    assert sanitize_controllers(None, full_names, by_name, []) is None
    assert sanitize_controllers({}, full_names, by_name, []) is None
    assert sanitize_controllers({"animation_controllers": []}, full_names, by_name, []) is None
    assert sanitize_controllers({"animation_controllers": {"a": {"states": {}}}}, full_names, by_name, []) is None


def test_controller_alias_stable():
    assert controller_alias("controller.animation.gob") == "controller_gob"
    assert controller_alias("controller.animation.gob.something") == "controller_something"
    assert controller_alias("") == "controller_anim"
