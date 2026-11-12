"""Tests de las herramientas de entidades (poda, adelgazado, atlas, AABB)."""

from __future__ import annotations

from babelcraft.entitykit import (
    blit_into_atlas,
    geometry_bounds,
    normalize_geometry_to_cell,
    plan_grid,
    prune_bones,
    thin_animation,
)
from babelcraft.pngcodec import Png


def _geo(bones: list[dict], tw: int = 64, th: int = 64) -> dict:
    return {
        "description": {"identifier": "geometry.test", "texture_width": tw, "texture_height": th},
        "bones": bones,
    }


# ------------------------------------------------------------------ poda


def test_prune_bones_keeps_drawing_and_animated_bones():
    geo = _geo(
        [
            {"name": "root", "pivot": [0, 0, 0]},
            {"name": "body", "parent": "root", "cubes": [{"origin": [0, 0, 0], "size": [1, 1, 1]}]},
            {"name": "locator", "parent": "root", "pivot": [0, 10, 0]},
            {"name": "dead", "parent": "root"},
            {"name": "head", "parent": "root", "pivot": [0, 12, 0]},
        ]
    )
    anims = [{"bones": {"head": {"rotation": {"0.0": [0, 0, 0]}}}}]

    removed = prune_bones(geo, anims)

    assert removed == 2
    assert [b["name"] for b in geo["bones"]] == ["root", "body", "head"]


def test_prune_bones_keeps_ancestors_of_referenced_bones():
    geo = _geo(
        [
            {"name": "root"},
            {"name": "mid", "parent": "root"},
            {"name": "tip", "parent": "mid"},
            {"name": "junk", "parent": "root"},
        ]
    )
    removed = prune_bones(geo, [{"bones": {"tip": {"position": {"0.0": [0, 1, 0]}}}}])

    assert removed == 1
    assert [b["name"] for b in geo["bones"]] == ["root", "mid", "tip"]


def test_prune_bones_keeps_particle_and_sound_locators():
    geo = _geo(
        [
            {"name": "body", "cubes": [{"origin": [0, 0, 0], "size": [1, 1, 1]}]},
            {"name": "particle_slot"},
            {"name": "sound_slot"},
            {"name": "gone"},
        ]
    )
    anims = [
        {
            "particle_effects": {"0.0": {"effect": "smoke", "locator": "particle_slot"}},
            "sound_effects": {"0.5": {"effect": "gob.hurt", "locator": "sound_slot"}},
        }
    ]
    removed = prune_bones(geo, anims)
    assert removed == 1
    names = {b["name"] for b in geo["bones"]}
    assert {"body", "particle_slot", "sound_slot"} <= names
    assert "gone" not in names


def test_prune_bones_tolerates_garbage():
    geo = _geo([{"name": "body", "cubes": [{}]}, "not a bone", {"no_name": True}])
    # No lanza; conserva solo huesos con nombre.
    removed = prune_bones(geo, [None, "x", {"bones": "no"}])
    assert removed == 2
    assert [b["name"] for b in geo["bones"]] == ["body"]
    assert prune_bones({"bones": "no"}, []) == 0
    assert prune_bones({}, []) == 0


# ------------------------------------------------------------- adelgazado


def test_thin_animation_removes_middle_redundant_keyframes():
    anim = {
        "bones": {
            "body": {
                "rotation": {
                    "0.0": [0, 0, 0],
                    "1.0": [0, 0, 0],
                    "2.0": [0, 0, 0],
                    "3.0": [5, 0, 0],
                    "4.0": [5, 0, 0],
                }
            }
        }
    }
    removed = thin_animation(anim)
    assert removed == 1
    keys = list(anim["bones"]["body"]["rotation"])
    assert keys == ["0.0", "2.0", "3.0", "4.0"]


def test_thin_animation_keeps_endpoints_and_short_channels():
    anim = {"bones": {"b": {"scale": {"0.0": [1, 1, 1], "1.0": [1, 1, 1]}}}}
    assert thin_animation(anim) == 0
    assert list(anim["bones"]["b"]["scale"]) == ["0.0", "1.0"]


def test_thin_animation_does_not_touch_special_interpolation():
    anim = {
        "bones": {
            "b": {
                "rotation": {
                    "0.0": [0, 0, 0],
                    "1.0": {"post": [0, 0, 0]},
                    "2.0": [0, 0, 0],
                }
            }
        }
    }
    assert thin_animation(anim) == 0
    assert len(anim["bones"]["b"]["rotation"]) == 3


def test_thin_animation_tolerates_bad_times_and_values():
    anim = {"bones": {"b": {"rotation": {"a": [0, 0, 0], "1": "bad", "2": [0, 0, 0]}}}}
    assert thin_animation(anim) == 0
    assert thin_animation({"bones": {}}) == 0
    assert thin_animation({"bones": []}) == 0
    assert thin_animation(None) == 0


# ------------------------------------------------------------------ atlas


def test_plan_grid_fits_and_rejects():
    plan = plan_grid(4, 32, 128)
    assert plan is not None
    assert plan["cols"] == 3 and plan["rows"] == 3
    assert len(plan["slots"]) == 4
    assert plan["slots"][0] == {"x": 0, "y": 0, "col": 0, "row": 0}
    assert plan["slots"][1] == {"x": 33, "y": 0, "col": 1, "row": 0}

    assert plan_grid(4, 64, 128) is None
    assert plan_grid(0, 64, 128)["slots"] == []
    assert plan_grid(1, 64, 32) is None


def test_normalize_geometry_to_cell_scales_uvs():
    geo = _geo(
        [
            {
                "name": "body",
                "cubes": [
                    {
                        "origin": [0, 0, 0],
                        "size": [1, 1, 1],
                        "uv": [0, 0, 8, 8],
                        "uv_size": [8, 8],
                        "box_uv": {"uv": [2, 2], "uv_size": [4, 4]},
                    }
                ],
            }
        ],
        tw=32,
        th=32,
    )
    assert normalize_geometry_to_cell(geo, 16) is True
    cube = geo["bones"][0]["cubes"][0]
    assert cube["uv"] == [0, 0, 4, 4]
    assert cube["uv_size"] == [4, 4]
    assert cube["box_uv"] == {"uv": [1, 1], "uv_size": [2, 2]}
    assert geo["description"]["texture_width"] == 16
    assert geo["description"]["texture_height"] == 16
    assert normalize_geometry_to_cell({"bones": []}, 16) is False


def test_blit_into_atlas_copies_nearest_pixels_and_clips():
    src = Png(2, 2, bytearray([
        255, 0, 0, 255, 0, 255, 0, 255,
        0, 0, 255, 255, 255, 255, 255, 255,
    ]))
    dst = bytearray(4 * 4 * 4)
    blit_into_atlas(dst, 4, src, {"x": 1, "y": 1, "w": 2, "h": 2})

    def pixel(x, y):
        i = (y * 4 + x) * 4
        return tuple(dst[i:i + 4])

    assert pixel(1, 1) == (255, 0, 0, 255)
    assert pixel(2, 1) == (0, 255, 0, 255)
    assert pixel(1, 2) == (0, 0, 255, 255)
    assert pixel(2, 2) == (255, 255, 255, 255)
    assert pixel(0, 0) == (0, 0, 0, 0)

    # Celda que sale del atlas: no lanza y pinta solo lo que cabe.
    dst2 = bytearray(4 * 4 * 4)
    blit_into_atlas(dst2, 4, src, {"x": 3, "y": 3, "w": 4, "h": 4})
    assert tuple(dst2[(3 * 4 + 3) * 4:(3 * 4 + 3) * 4 + 4]) == (255, 0, 0, 255)


# ------------------------------------------------------------------ bounds


def test_geometry_bounds_measures_all_cubes():
    geo = _geo(
        [
            {"name": "a", "cubes": [{"origin": [-4, 0, -2], "size": [8, 12, 4]}]},
            {"name": "b", "cubes": [{"origin": [-2, 12, -2], "size": [4, 4, 4]}]},
            {"name": "no_cube"},
            {"name": "bad", "cubes": [{"origin": [0, 0], "size": [1, 1, 1]}]},
        ]
    )
    assert geometry_bounds(geo) == (-4.0, 0.0, -2.0, 4.0, 16.0, 2.0)


def test_geometry_bounds_none_without_cubes():
    assert geometry_bounds(_geo([{"name": "a"}])) is None
    assert geometry_bounds({"bones": "no"}) is None
