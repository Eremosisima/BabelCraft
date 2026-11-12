"""Fixtures compartidas: un mod de ejemplo completo y utilidades de arte.

El fixture `minimod` es un mod de Java mínimo pero realista: ítems planos,
en mano y 3D, bloque cubo y bloque multipart, recetas de todos los tipos,
loot tables de bloque y entidad, una entidad GeckoLib con animaciones,
sonidos y lang en inglés y español. Se construye en memoria, sin tocar
disco, salvo cuando un test necesita un `.jar` de verdad.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from babelcraft.pngcodec import encode_png  # noqa: E402
from babelcraft.source import Source  # noqa: E402

COLORS = {
    "ruby": (200, 30, 60, 255),
    "ruby_sword": (220, 180, 190, 255),
    "ruby_gem": (230, 60, 90, 255),
    "ruby_block": (150, 20, 40, 255),
    "ruby_fence": (150, 20, 40, 255),
    "gob": (90, 180, 90, 255),
    "gob_blue": (90, 90, 220, 255),
}


def solid_png(color: tuple[int, int, int, int], size: int = 16) -> bytes:
    """PNG cuadrado de un color RGBA (arte determinista para los tests)."""
    return encode_png(size, size, bytearray(color * (size * size)))


def _json(data) -> bytes:
    return json.dumps(data).encode("utf-8")


def _item_model(texture: str, parent: str = "minecraft:item/generated") -> dict:
    return {"parent": parent, "textures": {"layer0": texture}}


def build_minimod() -> dict[str, bytes]:
    """Devuelve el mod de ejemplo como `{ruta: bytes}` (Source en memoria)."""
    ns = "minimod"
    files: dict[str, bytes] = {}

    files["fabric.mod.json"] = _json(
        {"schemaVersion": 1, "id": ns, "name": "Mini Mod", "version": "1.2.3"}
    )

    # --- Lang (ingles + espanol).
    files[f"assets/{ns}/lang/en_us.json"] = _json(
        {
            "item.minimod.ruby": "Ruby",
            "item.minimod.ruby_sword": "Ruby Sword",
            "item.minimod.ruby_gem": "Ruby Gem",
            "item.minimod.ghost": "Ghost",
            "item.minimod.mystery": "Mystery",
            "block.minimod.ruby_block": "Ruby Block",
            "block.minimod.ruby_fence": "Ruby Fence",
            "entity.minimod.gob": "Gob",
            "entity.minimod.gob_blue": "Blue Gob",
        }
    )
    files[f"assets/{ns}/lang/es_es.json"] = _json(
        {
            "item.minimod.ruby": "Rubí",
            "item.minimod.ruby_sword": "Espada de rubí",
            "block.minimod.ruby_block": "Bloque de rubí",
            "entity.minimod.gob": "Goblin",
        }
    )

    # --- Modelos de item: plano, en mano y 3D.
    files[f"assets/{ns}/models/item/ruby.json"] = _json(_item_model(f"{ns}:item/ruby"))
    files[f"assets/{ns}/models/item/ruby_sword.json"] = _json(
        _item_model(f"{ns}:item/ruby_sword", "minecraft:item/handheld")
    )
    files[f"assets/{ns}/models/item/ruby_gem.json"] = _json(
        {
            "textures": {"0": f"{ns}:item/ruby_gem"},
            "display": {
                "thirdperson_righthand": {
                    "rotation": [0, 45, 0],
                    "translation": [0, 2, 0],
                    "scale": [0.4, 0.4, 0.4],
                }
            },
            "elements": [
                {
                    "from": [4, 4, 4],
                    "to": [12, 12, 12],
                    "faces": {
                        "north": {"texture": "#0", "uv": [0, 0, 8, 8]},
                        "south": {"texture": "#0", "uv": [0, 0, 8, 8]},
                        "east": {"texture": "#0", "uv": [0, 0, 8, 8]},
                        "west": {"texture": "#0", "uv": [0, 0, 8, 8]},
                        "up": {"texture": "#0", "uv": [0, 0, 8, 8]},
                        "down": {"texture": "#0", "uv": [0, 0, 8, 8]},
                    },
                }
            ],
        }
    )
    # Modelo que apunta a una textura inexistente: debe quedar como residuo.
    files[f"assets/{ns}/models/item/ghost.json"] = _json(_item_model(f"{ns}:item/ghost"))

    # --- Bloque cubo + bloque multipart (valla).
    files[f"assets/{ns}/blockstates/ruby_block.json"] = _json(
        {"variants": {"": {"model": f"{ns}:block/ruby_block"}}}
    )
    files[f"assets/{ns}/models/block/ruby_block.json"] = _json(
        {"parent": "minecraft:block/cube_all", "textures": {"all": f"{ns}:block/ruby_block"}}
    )
    files[f"assets/{ns}/blockstates/ruby_fence.json"] = _json(
        {
            "multipart": [
                {"apply": {"model": f"{ns}:block/ruby_fence_post"}},
                {"when": {"north": "true"}, "apply": {"model": f"{ns}:block/ruby_fence_side"}},
            ]
        }
    )
    fence_faces = {
        face: {"texture": "#texture"}
        for face in ("north", "south", "east", "west", "up", "down")
    }
    files[f"assets/{ns}/models/block/ruby_fence_post.json"] = _json(
        {
            "textures": {"texture": f"{ns}:block/ruby_fence"},
            "elements": [
                {"from": [6, 0, 6], "to": [10, 16, 10], "faces": fence_faces}
            ],
        }
    )
    files[f"assets/{ns}/models/block/ruby_fence_side.json"] = _json(
        {
            "textures": {"texture": f"{ns}:block/ruby_fence"},
            "elements": [
                {"from": [7, 6, 0], "to": [9, 9, 16], "faces": fence_faces}
            ],
        }
    )

    # --- Texturas.
    for name in ("ruby", "ruby_sword", "ruby_gem"):
        files[f"assets/{ns}/textures/item/{name}.png"] = solid_png(COLORS[name])
    files[f"assets/{ns}/textures/block/ruby_block.png"] = solid_png(COLORS["ruby_block"])
    files[f"assets/{ns}/textures/block/ruby_fence.png"] = solid_png(COLORS["ruby_fence"])
    files[f"assets/{ns}/textures/entity/gob.png"] = solid_png(COLORS["gob"])
    files[f"assets/{ns}/textures/entity/gob_blue.png"] = solid_png(COLORS["gob_blue"])

    # --- Recetas: shaped, shapeless, horno y cortapiedras.
    files[f"data/{ns}/recipe/ruby_block.json"] = _json(
        {
            "type": "minecraft:crafting_shaped",
            "pattern": ["###", "###", "###"],
            "key": {"#": {"item": "minimod:ruby"}},
            "result": {"id": "minimod:ruby_block", "count": 1},
        }
    )
    files[f"data/{ns}/recipes/ruby_sword.json"] = _json(
        {
            "type": "minecraft:crafting_shaped",
            "pattern": ["R", "R", "S"],
            "key": {"R": {"item": "minimod:ruby"}, "S": {"item": "minecraft:stick"}},
            "result": {"id": "minimod:ruby_sword", "count": 1},
        }
    )
    files[f"data/{ns}/recipe/ruby_from_block.json"] = _json(
        {
            "type": "minecraft:crafting_shapeless",
            "ingredients": [{"item": "minimod:ruby_block"}],
            "result": {"id": "minimod:ruby", "count": 9},
        }
    )
    files[f"data/{ns}/recipe/ruby_smelt.json"] = _json(
        {
            "type": "minecraft:smelting",
            "ingredient": {"item": "minimod:ruby_ore"},
            "result": {"id": "minimod:ruby"},
            "cookingtime": 200,
            "experience": 0.7,
        }
    )
    files[f"data/{ns}/recipe/ruby_gem_cut.json"] = _json(
        {
            "type": "minecraft:stonecutting",
            "ingredient": {"item": "minimod:ruby_block"},
            "result": "minimod:ruby_gem",
            "count": 4,
        }
    )
    # Tipo sin equivalente: debe quedar como residuo.
    files[f"data/{ns}/recipe/ruby_smithing.json"] = _json(
        {"type": "minecraft:smithing_transform", "template": {"item": "minimod:ruby_gem"}}
    )

    # --- Loot tables.
    files[f"data/{ns}/loot_tables/blocks/ruby_block.json"] = _json(
        {
            "type": "minecraft:block",
            "pools": [
                {
                    "rolls": 1,
                    "entries": [{"type": "minecraft:item", "name": "minimod:ruby_block"}],
                    "conditions": [{"condition": "minecraft:survives_explosion"}],
                    "functions": [{"function": "minecraft:set_count", "count": 1}],
                }
            ],
        }
    )
    files[f"data/{ns}/loot_tables/entities/gob.json"] = _json(
        {
            "type": "minecraft:entity",
            "pools": [
                {
                    "rolls": 1,
                    "entries": [
                        {
                            "type": "minecraft:item",
                            "name": "minimod:ruby",
                            "functions": [
                                {"function": "minecraft:set_count", "count": {"min": 0, "max": 2}}
                            ],
                        }
                    ],
                }
            ],
        }
    )

    # --- Entidades GeckoLib (geometria ya en formato Bedrock).
    def geo(identifier: str) -> dict:
        return {
            "format_version": "1.12.0",
            "minecraft:geometry": [
                {
                    "description": {
                        "identifier": identifier,
                        "texture_width": 64,
                        "texture_height": 64,
                    },
                    "bones": [
                        {
                            "name": "body",
                            "pivot": [0, 0, 0],
                            "cubes": [{"origin": [-4, 0, -2], "size": [8, 12, 4], "uv": [0, 0]}],
                        },
                        {"name": "dead", "pivot": [0, 20, 0]},
                    ],
                }
            ],
        }

    files[f"assets/{ns}/geo/gob.geo.json"] = _json(geo("geometry.gob"))
    files[f"assets/{ns}/geo/gob_blue.geo.json"] = _json(geo("geometry.gob_blue"))
    files[f"assets/{ns}/animations/gob.animation.json"] = _json(
        {
            "format_version": "1.8.0",
            "animations": {
                "animation.gob.idle": {
                    "loop": True,
                    "bones": {
                        "body": {
                            "rotation": {
                                "0.0": [0, 0, 0],
                                "1.0": [0, 5, 0],
                                "2.0": [0, 5, 0],
                                "3.0": [0, 5, 0],
                                "4.0": [0, 6, 0],
                            }
                        }
                    },
                },
                "animation.gob.walk": {
                    "loop": True,
                    "bones": {"body": {"position": {"0.0": [0, 0, 0], "1.0": [0, 1, 0]}}},
                },
            },
        }
    )

    # --- Sonidos.
    files[f"assets/{ns}/sounds.json"] = _json(
        {
            "entity.gob.hurt": {
                "subtitle": "Gob hurts",
                "sounds": [{"name": "gob/hurt", "volume": 0.8}],
            }
        }
    )
    files[f"assets/{ns}/sounds/gob/hurt.ogg"] = b"OggS\x00fake-audio-for-tests"

    return files


@pytest.fixture
def minimod_files() -> dict[str, bytes]:
    return build_minimod()


@pytest.fixture
def minimod(minimod_files) -> Source:
    return Source(minimod_files)
