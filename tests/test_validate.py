"""Tests del validador estructural sobre addons sintéticos.

Estrategia: se construye un addon válido completo (los mismos documentos
que produce el pipeline) y se verifica que el validador lo acepta en
silencio; después se rompe UNA cosa a la vez y se comprueba que aparece
exactamente el código de hallazgo esperado. El validador no puede dar
falsos positivos (romper packs buenos) ni falsos negativos (dejar pasar
packs rotos).
"""

from __future__ import annotations

import copy
import json

from babelcraft.model import ConversionResult
from babelcraft.pack import AddonWriter
from babelcraft.validate import validate

BP_UUID = "00000000-1111-2222-3333-444444444444"
RP_UUID = "00000000-5555-6666-7777-888888888888"
MOD_UUID = "00000000-9999-aaaa-bbbb-cccccccccccc"


def _manifest(uid: str, mtype: str) -> dict:
    return {
        "format_version": 2,
        "header": {
            "name": "pack.name",
            "description": "pack.description",
            "uuid": uid,
            "version": [1, 0, 0],
            "min_engine_version": [1, 21, 60],
        },
        "modules": [
            {"type": mtype, "uuid": MOD_UUID, "version": [1, 0, 0]}
        ],
    }


def _writer() -> AddonWriter:
    return AddonWriter(".", "ns", "Test Addon", "1.0.0")


def build_valid_addon() -> AddonWriter:
    """Addon mínimo pero completo: item, bloque, receta, loot, entidad."""
    writer = _writer()

    bp = _manifest(BP_UUID, "data")
    bp["dependencies"] = [{"uuid": RP_UUID, "version": [1, 0, 0]}]
    writer.bp_json("manifest.json", bp)
    writer.rp_json("manifest.json", _manifest(RP_UUID, "resources"))

    # Ítem con icono registrado.
    writer.bp_json("items/ns_ruby.json", {
        "format_version": "1.20.10",
        "minecraft:item": {
            "description": {
                "identifier": "ns:ruby",
                "menu_category": {"category": "items"},
            },
            "components": {"minecraft:icon": "ns_item_ruby"},
        },
    })
    writer.rp_json("textures/item_texture.json", {
        "texture_data": {"ns_item_ruby": "textures/ns/item/ruby"},
    })
    writer.rp_blob("textures/ns/item/ruby.png", b"\x89PNG fake")

    # Bloque con material, loot y geometría.
    writer.bp_json("blocks/ns_table.json", {
        "format_version": "1.21.30",
        "minecraft:block": {
            "description": {"identifier": "ns:table"},
            "components": {
                "minecraft:material_instances": {"*": {"texture": "ns_block_table"}},
                "minecraft:loot": "loot_tables/ns/blocks/table.json",
                "minecraft:collision_box": True,
            },
        },
    })
    writer.rp_json("textures/terrain_texture.json", {
        "texture_data": {"ns_block_table": "textures/ns/block/table"},
    })
    writer.rp_blob("textures/ns/block/table.png", b"\x89PNG fake")
    writer.rp_json("blocks.json", {
        "format_version": [1, 1, 0],
        "ns:table": {"textures": {"texture": "ns_block_table"}},
    })
    writer.bp_json("loot_tables/ns/blocks/table.json", {
        "pools": [{"rolls": 1, "entries": [{"type": "item", "name": "ns:ruby"}]}],
    })

    # Receta con unlock y resultado emitido.
    writer.bp_json("recipes/ns_table.json", {
        "format_version": "1.20.10",
        "minecraft:recipe_shaped": {
            "description": {"identifier": "ns:table"},
            "tags": ["crafting_table"],
            "pattern": ["RR", "SS"],
            "key": {
                "R": {"item": "ns:ruby"},
                "S": {"item": "minecraft:stick"},
            },
            "unlock": [{"item": "ns:ruby"}],
            "result": {"item": "ns:table", "count": 1},
        },
    })

    # Entidad completa: geometría, animación, controlador y loot.
    writer.rp_json("models/entity/ns_gob.geo.json", {
        "format_version": "1.12.0",
        "minecraft:geometry": [{
            "description": {"identifier": "geometry.ns_gob", "texture_width": 64,
                            "texture_height": 64},
            "bones": [{"name": "body", "pivot": [0, 0, 0]}],
        }],
    })
    writer.rp_json("animations/ns_gob.animation.json", {
        "format_version": "1.8.0",
        "animations": {
            "animation.gob.idle": {
                "loop": True,
                "animation_length": 1,
                "bones": {"body": {"rotation": {"0.0": [0, 0, 0], "1.0": [5, 0, 0]}}},
            },
        },
    })
    writer.rp_json("animation_controllers/ns_gob.animation_controllers.json", {
        "format_version": "1.10.0",
        "animation_controllers": {
            "controller.animation.gob": {
                "initial_state": "default",
                "states": {"default": {"animations": ["idle"]}},
            },
        },
    })
    writer.rp_json("render_controllers/ns_entity.render_controllers.json", {
        "format_version": "1.10.0",
        "render_controllers": {
            "controller.render.ns_entity": {
                "geometry": "Geometry.default",
                "materials": [{"*": "Material.default"}],
                "textures": ["Texture.default"],
            },
        },
    })
    writer.rp_json("entity/ns_gob.entity.json", {
        "format_version": "1.10.0",
        "minecraft:client_entity": {
            "description": {
                "identifier": "ns:gob",
                "materials": {"default": "entity_alphatest"},
                "textures": {"default": "textures/entity/ns/gob"},
                "geometry": {"default": "geometry.ns_gob"},
                "animations": {
                    "idle": "animation.gob.idle",
                    "ctrl": "controller.animation.gob",
                },
                "render_controllers": ["controller.render.ns_entity"],
                "spawn_egg": {"base_color": "#00FF00", "overlay_color": "#008000"},
            },
        },
    })
    writer.rp_blob("textures/entity/ns/gob.png", b"\x89PNG fake")
    writer.bp_json("entities/ns_gob.entity.json", {
        "format_version": "1.21.0",
        "minecraft:entity": {
            "description": {"identifier": "ns:gob", "is_spawnable": True,
                            "is_summonable": True},
            "components": {
                "minecraft:loot": "loot_tables/ns/entities/gob.json",
                "minecraft:collision_box": {"width": 0.8, "height": 1.2},
                "minecraft:health": {"value": 10, "max": 10},
            },
        },
    })
    writer.bp_json("loot_tables/ns/entities/gob.json", {
        "pools": [{"rolls": 1, "entries": [{"type": "item", "name": "ns:ruby"}]}],
    })

    # Attachable del ítem 3D.
    writer.rp_json("attachables/ns_ruby_gem.attachable.json", {
        "format_version": "1.10.0",
        "minecraft:attachable": {
            "description": {
                "identifier": "ns:ruby_gem",
                "materials": {"default": "entity_alphatest"},
                "textures": {"default": "textures/ns/item/ruby"},
                "geometry": {"default": "geometry.ns_ruby_gem"},
                "animations": {"hold": "animation.gob.idle"},
                "render_controllers": ["controller.render.ns_entity"],
                "scripts": {"animate": ["hold"]},
            },
        },
    })
    writer.rp_json("models/entity/ns_ruby_gem.geo.json", {
        "format_version": "1.12.0",
        "minecraft:geometry": [{
            "description": {"identifier": "geometry.ns_ruby_gem", "texture_width": 16,
                            "texture_height": 16},
            "bones": [{"name": "bi", "pivot": [0, 0, 0]}],
        }],
    })
    return writer


def run(writer: AddonWriter) -> ConversionResult:
    result = ConversionResult()
    validate(writer, result)
    return result


def codes(result: ConversionResult, severity: str = "error") -> set[str]:
    return {f.code for f in result.findings if f.severity == severity}


# ---------------------------------------------------------------------------
#  El addon bueno pasa en silencio
# ---------------------------------------------------------------------------


def test_valid_addon_produces_no_errors():
    result = run(build_valid_addon())
    assert result.findings == [] or all(
        f.severity == "info" for f in result.findings
    ), [f for f in result.findings if f.severity != "info"]
    assert codes(result) == set()


def test_valid_addon_reports_file_counts():
    result = run(build_valid_addon())
    infos = [f for f in result.findings if f.severity == "info"]
    assert any(f.code == "limits.files" for f in infos)


# ---------------------------------------------------------------------------
#  JSON y manifiestos
# ---------------------------------------------------------------------------


def test_invalid_json_and_bom():
    writer = build_valid_addon()
    writer.rp["entity/ns_gob.entity.json"] = b"{ roto"
    writer.bp["items/ns_ruby.json"] = b"\xef\xbb\xbf" + json.dumps({"a": 1}).encode()
    result = run(writer)
    assert "json.invalid" in codes(result)
    assert "json.bom" in codes(result)


def test_manifest_problems():
    writer = build_valid_addon()
    doc = json.loads(writer.rp["manifest.json"])
    doc["header"]["uuid"] = "no-es-un-uuid"
    doc["header"]["version"] = "1.0"
    doc["header"]["min_engine_version"] = [1]
    doc["modules"] = []
    writer.rp_json("manifest.json", doc)
    result = run(writer)
    c = codes(result)
    assert {"manifest.uuid", "manifest.version", "manifest.min_engine", "manifest.modules"} <= c

    # Manifest ausente.
    writer2 = build_valid_addon()
    del writer2.rp["manifest.json"]
    assert "manifest.missing" in codes(run(writer2))


def test_manifest_module_uuid_and_missing_dependency():
    writer = build_valid_addon()
    doc = json.loads(writer.bp["manifest.json"])
    doc["modules"][0]["uuid"] = "x"
    writer.bp_json("manifest.json", doc)
    assert "manifest.module_uuid" in codes(run(writer))

    writer2 = build_valid_addon()
    doc = json.loads(writer2.bp["manifest.json"])
    del doc["dependencies"]
    writer2.bp_json("manifest.json", doc)
    warns = codes(run(writer2), "warn")
    assert "manifest.dependency" in warns


# ---------------------------------------------------------------------------
#  Texturas e índices
# ---------------------------------------------------------------------------


def test_texture_index_missing_png_and_bad_entry():
    writer = build_valid_addon()
    writer.rp_json("textures/item_texture.json", {
        "texture_data": {
            "ns_item_ruby": "textures/ns/item/missing",
            "ns_item_bad": {"no_path": True},
        },
    })
    result = run(writer)
    c = codes(result)
    assert "ref.texture_missing" in c
    assert "index.bad_entry" in codes(result, "warn")


def test_blocks_json_unknown_shortname():
    writer = build_valid_addon()
    writer.rp_json("blocks.json", {
        "format_version": [1, 1, 0],
        "ns:table": {"textures": {"texture": "shortname_ajeno"}},
    })
    warns = codes(run(writer), "warn")
    assert "ref.shortname_unknown" in warns


# ---------------------------------------------------------------------------
#  Ítems y bloques
# ---------------------------------------------------------------------------


def test_item_problems():
    writer = build_valid_addon()
    doc = json.loads(writer.bp["items/ns_ruby.json"])
    doc["minecraft:item"]["description"]["identifier"] = "MAL ID!"
    doc["minecraft:item"]["description"]["menu_category"] = {"category": "raro"}
    doc["minecraft:item"]["components"]["minecraft:icon"] = "shortname_desconocido"
    doc["minecraft:item"]["components"]["minecraft:max_stack_size"] = 500
    writer.bp_json("items/ns_ruby.json", doc)
    result = run(writer)
    c = codes(result)
    assert {"ident.invalid", "ref.item_icon"} <= c
    warns = codes(result, "warn")
    assert {"item.menu", "item.stack"} <= warns


def test_item_without_icon_and_bad_structure():
    writer = build_valid_addon()
    doc = json.loads(writer.bp["items/ns_ruby.json"])
    del doc["minecraft:item"]["components"]["minecraft:icon"]
    writer.bp_json("items/ns_ruby.json", doc)
    assert "item.icon" in codes(run(writer), "warn")

    writer2 = build_valid_addon()
    writer2.bp_json("items/ns_ruby.json", {"format_version": "1.20.10"})
    assert "item.structure" in codes(run(writer2))


def test_block_problems():
    writer = build_valid_addon()
    doc = json.loads(writer.bp["blocks/ns_table.json"])
    doc["minecraft:block"]["components"]["minecraft:geometry"] = "geometry.inexistente"
    doc["minecraft:block"]["components"]["minecraft:loot"] = "loot_tables/ns/missing.json"
    doc["minecraft:block"]["components"]["minecraft:collision_box"] = {"width": -1, "height": 0}
    writer.bp_json("blocks/ns_table.json", doc)
    result = run(writer)
    c = codes(result)
    assert {"ref.geometry", "ref.loot", "block.box"} <= c

    # Bloque sin material_instances: aviso.
    writer2 = build_valid_addon()
    doc = json.loads(writer2.bp["blocks/ns_table.json"])
    del doc["minecraft:block"]["components"]["minecraft:material_instances"]
    writer2.bp_json("blocks/ns_table.json", doc)
    assert "block.material" in codes(run(writer2), "warn")

    # Estructura rota: error.
    writer3 = build_valid_addon()
    writer3.bp_json("blocks/ns_table.json", {"format_version": "1.21.30"})
    assert "block.structure" in codes(run(writer3))


# ---------------------------------------------------------------------------
#  Entidades y attachables
# ---------------------------------------------------------------------------


def test_entity_and_attachable_references():
    writer = build_valid_addon()
    doc = json.loads(writer.rp["entity/ns_gob.entity.json"])
    d = doc["minecraft:client_entity"]["description"]
    d["textures"]["default"] = "textures/entity/ns/missing"
    d["geometry"]["default"] = "geometry.inexistente"
    d["animations"]["idle"] = "animation.inexistente"
    d["animations"]["ctrl"] = "controller.animation.inexistente"
    d["render_controllers"] = ["controller.render.inexistente"]
    d["spawn_egg"] = {"base_color": "verde", "overlay_color": "#008000"}
    writer.rp_json("entity/ns_gob.entity.json", doc)
    result = run(writer)
    c = codes(result)
    assert {"ref.texture_missing", "ref.geometry", "ref.animation",
            "ref.animation_controller", "ref.render_controller"} <= c
    assert "entity.spawn_egg" in codes(result, "warn")

    # Attachable con textura y geometría rotas.
    writer2 = build_valid_addon()
    doc = json.loads(writer2.rp["attachables/ns_ruby_gem.attachable.json"])
    doc["minecraft:attachable"]["description"]["textures"]["default"] = "textures/ns/missing"
    doc["minecraft:attachable"]["description"]["geometry"]["default"] = "geometry.missing"
    doc["minecraft:attachable"]["description"]["animations"]["hold"] = "animation.missing"
    writer2.rp_json("attachables/ns_ruby_gem.attachable.json", doc)
    c = codes(run(writer2))
    assert {"ref.texture_missing", "ref.geometry", "ref.animation"} <= c


def test_attachable_bad_structure_and_bad_identifier():
    writer = build_valid_addon()
    writer.rp_json("attachables/ns_ruby_gem.attachable.json", {"format_version": "1.10.0"})
    assert "attachable.structure" in codes(run(writer))

    writer2 = build_valid_addon()
    doc = json.loads(writer2.rp["attachables/ns_ruby_gem.attachable.json"])
    doc["minecraft:attachable"]["description"]["identifier"] = "ID MALO!"
    writer2.rp_json("attachables/ns_ruby_gem.attachable.json", doc)
    assert "ident.invalid" in codes(run(writer2))


def test_entity_bp_problems():
    writer = build_valid_addon()
    doc = json.loads(writer.bp["entities/ns_gob.entity.json"])
    doc["minecraft:entity"]["components"]["minecraft:loot"] = "loot_tables/ns/missing.json"
    doc["minecraft:entity"]["components"]["minecraft:collision_box"] = {"width": 0, "height": 0}
    doc["minecraft:entity"]["components"]["minecraft:health"] = {"value": 20, "max": 10}
    writer.bp_json("entities/ns_gob.entity.json", doc)
    result = run(writer)
    assert "ref.loot" in codes(result)
    assert "entity.box" in codes(result)
    assert "entity.health" in codes(result, "warn")


def test_scripts_animate_alias_unknown():
    writer = build_valid_addon()
    doc = json.loads(writer.rp["attachables/ns_ruby_gem.attachable.json"])
    doc["minecraft:attachable"]["description"]["scripts"]["animate"] = [
        "hold", {"desconocido": "q.x"}, "otro",
    ]
    writer.rp_json("attachables/ns_ruby_gem.attachable.json", doc)
    warns = codes(run(writer), "warn")
    assert warns == {"ref.animation_alias"}


# ---------------------------------------------------------------------------
#  Documentos de animación y controladores
# ---------------------------------------------------------------------------


def test_animation_doc_problems():
    writer = build_valid_addon()
    doc = json.loads(writer.rp["animations/ns_gob.animation.json"])
    doc.pop("format_version")
    doc["animations"]["animation.gob.idle"]["loop"] = "siempre"
    doc["animations"]["animation.gob.idle"]["animation_length"] = 0.5  # keyframes > length
    writer.rp_json("animations/ns_gob.animation.json", doc)
    result = run(writer)
    warns = codes(result, "warn")
    assert {"anim.format", "anim.loop"} <= warns
    assert any(f.code == "anim.length" and "recorta" in f.message for f in result.findings)

    # Animación sin huesos ni efectos / documento sin bloque.
    writer2 = build_valid_addon()
    writer2.rp_json("animations/ns_gob.animation.json", {
        "format_version": "1.8.0",
        "animations": {"animation.gob.idle": {"loop": True, "bones": {}}},
    })
    assert "anim.bones" in codes(run(writer2))

    writer3 = build_valid_addon()
    writer3.rp_json("animations/ns_gob.animation.json", {"format_version": "1.8.0"})
    assert "anim.structure" in codes(run(writer3))


def test_animation_controller_doc_problems():
    writer = build_valid_addon()
    doc = json.loads(writer.rp["animation_controllers/ns_gob.animation_controllers.json"])
    ctrl = doc["animation_controllers"]["controller.animation.gob"]
    ctrl["initial_state"] = "ghost"
    ctrl["states"]["default"]["animations"] = "no lista"
    ctrl["states"]["default"]["transitions"] = "no lista"
    writer.rp_json("animation_controllers/ns_gob.animation_controllers.json", doc)
    result = run(writer)
    warns = codes(result, "warn")
    assert {"anim.controller_initial", "anim.controller_animations",
            "anim.controller_transitions"} <= warns

    # Sin estados / estructura rota / estado no objeto.
    writer2 = build_valid_addon()
    writer2.rp_json("animation_controllers/ns_gob.animation_controllers.json", {
        "format_version": "1.10.0",
        "animation_controllers": {"controller.animation.gob": {"states": {}}},
    })
    c = codes(run(writer2))
    assert {"anim.controller_states"} <= c

    writer3 = build_valid_addon()
    writer3.rp_json("animation_controllers/ns_gob.animation_controllers.json", {
        "format_version": "1.10.0",
        "animation_controllers": {"controller.animation.gob": "no dict"},
    })
    assert "anim.controller_structure" in codes(run(writer3))

    writer4 = build_valid_addon()
    doc = json.loads(writer4.rp["animation_controllers/ns_gob.animation_controllers.json"])
    doc["animation_controllers"]["controller.animation.gob"]["states"]["x"] = "no dict"
    writer4.rp_json("animation_controllers/ns_gob.animation_controllers.json", doc)
    assert "anim.controller_state" in codes(run(writer4))


# ---------------------------------------------------------------------------
#  Recetas y loot
# ---------------------------------------------------------------------------


def test_recipe_problems():
    writer = build_valid_addon()
    doc = json.loads(writer.bp["recipes/ns_table.json"])
    doc["minecraft:recipe_shaped"]["unlock"] = []
    writer.bp_json("recipes/ns_table.json", doc)
    assert "recipe.unlock" in codes(run(writer))

    writer2 = build_valid_addon()
    doc = json.loads(writer2.bp["recipes/ns_table.json"])
    del doc["minecraft:recipe_shaped"]["result"]
    doc["minecraft:recipe_shaped"]["pattern"] = ["RX"]
    writer2.bp_json("recipes/ns_table.json", doc)
    c = codes(run(writer2))
    assert {"recipe.result", "recipe.key"} <= c

    # Dos recetas en un documento: estructura rota.
    writer3 = build_valid_addon()
    doc = json.loads(writer3.bp["recipes/ns_table.json"])
    doc["minecraft:recipe_furnace"] = {"description": {"identifier": "ns:x"}}
    writer3.bp_json("recipes/ns_table.json", doc)
    assert "recipe.structure" in codes(run(writer3))


def test_recipe_result_not_emitted_is_warning():
    writer = build_valid_addon()
    doc = json.loads(writer.bp["recipes/ns_table.json"])
    doc["minecraft:recipe_shaped"]["result"] = {"item": "ns:no_emitido"}
    writer.bp_json("recipes/ns_table.json", doc)
    assert "recipe.result_unknown" in codes(run(writer), "warn")


def test_loot_table_problems():
    writer = build_valid_addon()
    writer.bp_json("loot_tables/ns/blocks/table.json", {"pools": "no lista"})
    assert "loot.pools" in codes(run(writer))

    writer2 = build_valid_addon()
    writer2.bp_json("loot_tables/ns/blocks/table.json", {"pools": ["no dict"]})
    assert "loot.pool" in codes(run(writer2))


# ---------------------------------------------------------------------------
#  Límites de Bedrock
# ---------------------------------------------------------------------------


def test_texture_handle_limits():
    writer = build_valid_addon()
    # 900 texturas: aviso de recomendación de atlas.
    for i in range(900):
        writer.rp_blob(f"textures/ns/fill/t{i}.png", b"\x89PNG")
    warns = codes(run(writer), "warn")
    assert "limits.texture_handles" in warns

    writer2 = build_valid_addon()
    for i in range(4100):
        writer2.rp_blob(f"textures/ns/fill/t{i}.png", b"\x89PNG")
    assert "limits.texture_handles" in codes(run(writer2))


# ---------------------------------------------------------------------------
#  Sobre la salida REAL del pipeline: el validador la acepta entera
# ---------------------------------------------------------------------------


def test_pipeline_output_validates_clean(tmp_path, minimod):
    from babelcraft import convert

    conv = convert(minimod, str(tmp_path))
    assert conv.errors == []
    assert all(f.severity != "error" for f in conv.result.findings)
