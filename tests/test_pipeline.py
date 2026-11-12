"""Tests de integración: el pipeline completo de punta a punta.

El fixture `minimod` (conftest.py) es un mod realista en memoria; aquí se
convierte y se comprueba la SALIDA fichero a fichero: BP, RP, índices,
manifiestos, animaciones y el `.mcaddon` empaquetado.
"""

from __future__ import annotations

import json
import zipfile

import pytest

from babelcraft import convert
from babelcraft.model import Overrides
from babelcraft.cli import main as cli_main

from conftest import build_minimod, solid_png


def _j(obj) -> dict:
    return json.loads


def _bp(conv, rel: str) -> dict:
    return json.loads(conv.writer.bp[rel])


def _rp(conv, rel: str) -> dict:
    return json.loads(conv.writer.rp[rel])


def _residues(conv) -> dict[str, str]:
    return {
        e.path: "; ".join(e.notes)
        for e in conv.result.entries
        if e.status.value == "residue"
    }


# ---------------------------------------------------------------------------
#  Conversión base del minimod
# ---------------------------------------------------------------------------


def test_minimod_full_pipeline(tmp_path, minimod):
    conv = convert(minimod, str(tmp_path))
    s = conv.summary()

    # Sin errores del validador: el addon carga tal cual.
    assert conv.errors == []
    assert s["namespace"] == "minimod"
    assert s["loader"] == "fabric"
    assert s["name"] == "Mini Mod"
    assert s["bp_files"] > 0 and s["rp_files"] > 0

    # .mcaddon con los dos packs dentro.
    addon = tmp_path / "mini_mod.mcaddon"
    assert addon.is_file()
    with zipfile.ZipFile(addon) as z:
        names = set(z.namelist())
    assert {"BP_mini_mod/manifest.json", "RP_mini_mod/manifest.json"} <= names
    assert "BP_mini_mod/items/minimod_ruby.json" in names
    assert "RP_mini_mod/entity/minimod_gob.entity.json" in names

    # Los árboles BP/RP también quedan en disco para editar a mano.
    assert (tmp_path / "BP_mini_mod" / "manifest.json").is_file()
    assert (tmp_path / "RP_mini_mod" / "manifest.json").is_file()

    # Ítems: plano, handheld y 3D.
    ruby = _bp(conv, "items/minimod_ruby.json")
    assert ruby["format_version"] == "1.20.10"
    assert ruby["minecraft:item"]["components"]["minecraft:icon"] == "minimod_item_ruby"
    sword = _bp(conv, "items/minimod_ruby_sword.json")
    assert sword["format_version"] == "1.20.30"  # hand_equipped exige 1.20.30
    assert sword["minecraft:item"]["components"]["minecraft:hand_equipped"] is True
    gem = _bp(conv, "items/minimod_ruby_gem.json")
    assert gem["minecraft:item"]["components"]["minecraft:icon"] == "minimod_item_ruby_gem"

    # Icono registrado en el índice que el juego exige.
    idx = _rp(conv, "textures/item_texture.json")
    assert idx["texture_data"]["minimod_item_ruby"] == {"textures": "textures/minimod/item/ruby"}
    assert idx["texture_data"]["minimod_item_ruby_sword"] == {"textures": "textures/minimod/item/ruby_sword"}

    # Attachable del ítem 3D (esquema bi_* de Geyser).
    att = _rp(conv, "attachables/minimod_ruby_gem.attachable.json")
    desc = att["minecraft:attachable"]["description"]
    assert desc["geometry"]["default"] == "geometry.minimod_ruby_gem"
    assert desc["animations"]["firstperson_head"] == "animation.minimod.disable"
    assert "minimod_ruby_gem.thirdperson_main_hand" in json.dumps(att)
    assert "attachables/minimod_ruby_gem.attachable.json" in conv.writer.rp

    # Bloques: cubo (sin geometría) y multipart (con geometría).
    block = _bp(conv, "blocks/minimod_ruby_block.json")["minecraft:block"]
    comps = block["components"]
    assert comps["minecraft:loot"] == "loot_tables/minimod/blocks/ruby_block.json"
    assert "minecraft:geometry" not in comps  # cubo completo: lo dibuja el motor
    assert comps["minecraft:material_instances"]["*"]["texture"] == "minimod_block_ruby_block"
    fence = _bp(conv, "blocks/minimod_ruby_fence.json")["minecraft:block"]
    assert fence["components"]["minecraft:geometry"] == {"identifier": "geometry.minimod_ruby_fence"}
    assert fence["components"]["minecraft:collision_box"]["height"] == 1

    # blocks.json (RP) con format_version y la textura del cubo.
    blocks_json = _rp(conv, "blocks.json")
    assert blocks_json["format_version"] == [1, 1, 0]
    assert blocks_json["minimod:ruby_block"]["textures"] == {"texture": "minimod_block_ruby_block"}

    # Loot tables emitidas y enganchadas.
    assert "loot_tables/minimod/blocks/ruby_block.json" in conv.writer.bp
    assert "loot_tables/minimod/entities/gob.json" in conv.writer.bp
    gob_bp = _bp(conv, "entities/minimod_gob.entity.json")["minecraft:entity"]
    assert gob_bp["components"]["minecraft:loot"] == "loot_tables/minimod/entities/gob.json"

    # Recetas: 4 tipos convertidos (ruby_smelt queda como residuo: ruby_ore no existe).
    recipes = [p for p in conv.writer.bp if p.startswith("recipes/")]
    assert len(recipes) == 4
    shaped = _bp(conv, "recipes/minimod_ruby_block.json")["minecraft:recipe_shaped"]
    assert shaped["unlock"] == [{"item": "minimod:ruby"}]  # derivado de los ingredientes
    cut = _bp(conv, "recipes/minimod_ruby_gem_cut.json")["minecraft:recipe_shapeless"]
    assert cut["tags"] == ["stonecutter"]

    # Entidades: geometría, animaciones con alias idle/walk y render controller.
    assert "models/entity/minimod_gob.geo.json" in conv.writer.rp
    client = _rp(conv, "entity/minimod_gob.entity.json")["minecraft:client_entity"]["description"]
    assert client["geometry"]["default"] == "geometry.minimod_gob"
    assert client["textures"]["default"] == "textures/entity/minimod/gob"
    assert client["animations"] == {
        "idle": "animation.gob.idle",
        "walk": "animation.gob.walk",
    }
    assert client["scripts"]["animate"] == [
        {"walk": "query.modified_move_speed > 0.05"},
        {"idle": "query.modified_move_speed <= 0.05"},
    ]
    assert "textures/entity/minimod/gob.png" in conv.writer.rp

    # La poda quitó el hueso muerto y el adelgazado el keyframe redundante.
    geo = _rp(conv, "models/entity/minimod_gob.geo.json")
    assert [b["name"] for b in geo["minecraft:geometry"][0]["bones"]] == ["body"]
    anim = _rp(conv, "animations/minimod_gob.animation.json")["animations"]
    assert list(anim["animation.gob.idle"]["bones"]["body"]["rotation"]) == [
        "0.0", "1.0", "3.0", "4.0",
    ]

    # Sonidos.
    snd = _rp(conv, "sounds/sound_definitions.json")["sound_definitions"]
    entry = snd["minimod.entity.gob.hurt"]
    assert entry["category"] == "hostile"
    assert entry["sounds"][0]["name"] == "sounds/minimod/gob/hurt"
    assert "sounds/minimod/gob/hurt.ogg" in conv.writer.rp

    # Lang: claves Bedrock y pack.name.
    en = conv.writer.rp["texts/en_US.lang"].decode("utf-8")
    assert "item.minimod:ruby=Ruby" in en
    assert "tile.minimod:ruby_block.name=Ruby Block" in en
    assert "entity.minimod:gob.name=Gob" in en
    assert "item.spawn_egg.entity.minimod:gob.name=" in en
    assert "pack.name=Mini Mod" in en
    es = conv.writer.rp["texts/es_ES.lang"].decode("utf-8")
    assert "item.minimod:ruby=Rubí" in es

    # Residuo explicado, nunca silencioso.
    residues = _residues(conv)
    assert set(residues) == {
        "minimod:item/ghost",
        "assets/minimod/models/item/ghost.json",
        "lang:item.minimod.mystery",
        "data/minimod/recipe/ruby_smithing.json",
        "data/minimod/recipe/ruby_smelt.json",
    }
    assert "smithing" in residues["data/minimod/recipe/ruby_smithing.json"]
    assert conv.report_path and (tmp_path / "REPORT.md").is_file()


def test_minimod_placeholders_fill_missing_art(tmp_path, minimod_files):
    conv = convert(minimod_files, str(tmp_path), placeholders=True)
    assert conv.errors == []

    residues = _residues(conv)
    # El smithing y la receta de horno con ítem inexistente siguen siendo residuos,
    # pero el arte ausente ya no tumba los ítems.
    assert set(residues) == {
        "minimod:item/ghost",  # la textura referenciada no existe en el jar
        "data/minimod/recipe/ruby_smithing.json",
        "data/minimod/recipe/ruby_smelt.json",
    }
    assert "items/minimod_ghost.json" in conv.writer.bp
    assert "items/minimod_mystery.json" in conv.writer.bp
    idx = _rp(conv, "textures/item_texture.json")
    assert idx["texture_data"]["minimod_item_ghost"] == {"textures": "textures/minimod/item/ghost"}
    assert "textures/minimod/item/ghost.png" in conv.writer.rp
    ghost_entry = next(
        e for e in conv.result.entries if e.path == "assets/minimod/models/item/ghost.json"
    )
    assert ghost_entry.status.value == "adapted"
    assert any("placeholder" in n for n in ghost_entry.notes)


def test_minimod_atlas_single_texture_handle(tmp_path, minimod_files):
    conv = convert(minimod_files, str(tmp_path), atlas=True)
    assert conv.errors == []

    assert "textures/entity/atlas.png" in conv.writer.rp
    # Ya no generamos archivos .material personalizados
    assert "materials/minimod.material" not in conv.writer.rp
    rcs = _rp(conv, "render_controllers/minimod_entity.render_controllers.json")
    atlas_rc = rcs["render_controllers"]["controller.render.minimod.atlas"]
    assert atlas_rc["uv_anim"]["scale"] == ["variable.scale_x", "variable.scale_y"]

    # Las dos entidades apuntan al atlas y llevan las variables de celda.
    for name in ("gob", "gob_blue"):
        client = _rp(conv, f"entity/minimod_{name}.entity.json")["minecraft:client_entity"]["description"]
        assert client["textures"]["default"] == "textures/entity/atlas"
        # Ahora usamos materiales vanilla directamente (sin materiales custom)
        assert client["materials"]["default"] in ("entity_alphatest", "entity_alphablend")
        assert client["render_controllers"] == ["controller.render.minimod.atlas"]
        pre = client["scripts"]["pre_animation"]
        assert any("variable.offset_x" in line for line in pre)
    # gob_blue no tiene animaciones propias en el mod fuente: en modo atlas
    # sigue existiendo, solo que sin mapa `animations` (nada que animar).
    # Las animaciones idle/walk de gob siguen en su mapa.
    gob = _rp(conv, "entity/minimod_gob.entity.json")["minecraft:client_entity"]["description"]
    assert gob["animations"]["idle"] == "animation.gob.idle"
    assert gob["scripts"]["animate"][0] == {"walk": "query.modified_move_speed > 0.05"}


def test_minimod_variant_mobile(tmp_path, minimod_files):
    conv = convert(minimod_files, str(tmp_path), variant="mobile")
    assert conv.errors == []
    # Atlas automático + despawn agresivo + IA ligera.
    assert "textures/entity/atlas.png" in conv.writer.rp
    gob = _bp(conv, "entities/minimod_gob.entity.json")["minecraft:entity"]
    despawn = gob["components"]["minecraft:despawn"]["despawn_from_distance"]
    assert despawn == {"min_range": 40, "max_range": 56}
    assert "minecraft:behavior.look_at_player" not in gob["components"]
    # Celda de atlas reducida: la geometría se normaliza a 32px.
    geo = _rp(conv, "models/entity/minimod_gob.geo.json")["minecraft:geometry"][0]
    assert geo["description"]["texture_width"] == 32


def test_minimod_overrides(tmp_path, minimod_files):
    ov = Overrides(
        items={"minimod:ruby": {"max_stack_size": 16, "food": {"nutrition": 4}}},
        blocks={"minimod:ruby_block": {"seconds_to_destroy": 3, "texture": "stone"}},
        entities={"minimod:gob": {"health": 10}},
        menu={"minimod:ruby": "equipment"},
    )
    conv = convert(minimod_files, str(tmp_path), overrides=ov)
    assert conv.errors == []

    ruby = _bp(conv, "items/minimod_ruby.json")["minecraft:item"]
    assert ruby["components"]["minecraft:max_stack_size"] == 16
    assert ruby["components"]["minecraft:food"] == {"nutrition": 4}
    assert ruby["description"]["menu_category"]["category"] == "equipment"

    block = _bp(conv, "blocks/minimod_ruby_block.json")["minecraft:block"]
    assert block["components"]["minecraft:destructible_by_mining"]["seconds_to_destroy"] == 3
    assert block["components"]["minecraft:material_instances"]["*"]["texture"] == "stone"

    gob = _bp(conv, "entities/minimod_gob.entity.json")["minecraft:entity"]
    assert gob["components"]["minecraft:health"] == {"value": 10, "max": 10}

    # 'stone' es un shortname vanilla: el validador avisa, no rompe.
    assert any(f.code == "ref.shortname_unknown" for f in conv.warnings)


def test_convert_empty_mod_still_produces_addon(tmp_path):
    conv = convert(
        {"fabric.mod.json": json.dumps({"id": "vacio", "name": "Vacío"}).encode("utf-8")},
        str(tmp_path),
    )
    assert conv.errors == []
    assert (tmp_path / "vacio.mcaddon").is_file()
    assert conv.summary()["converted"] == 0


def test_cli_end_to_end(tmp_path, minimod_files):
    src = tmp_path / "src"
    for rel, data in minimod_files.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    out = tmp_path / "out"

    code = cli_main(["convert", str(src), "-o", str(out), "--placeholders"])
    assert code == 0
    assert (out / "mini_mod.mcaddon").is_file()
    assert (out / "REPORT.md").is_file()

    # Fuente inexistente: error limpio, código 1.
    assert cli_main(["convert", str(tmp_path / "nope"), "-o", str(tmp_path / "o2")]) == 1


# ---------------------------------------------------------------------------
#  Animaciones/controladores GeckoLib (robustez de entidades)
# ---------------------------------------------------------------------------


def _geo_doc(identifier: str, bones: list[dict]) -> dict:
    return {
        "format_version": "1.12.0",
        "minecraft:geometry": [
            {
                "description": {
                    "identifier": identifier,
                    "texture_width": 64,
                    "texture_height": 64,
                },
                "bones": bones,
            }
        ],
    }


def build_wispmod() -> dict[str, bytes]:
    """Mod GeckoLib 4 con animaciones compartidas, controladores y caso raro.

    - ``wisp``: carpeta ``animations/entity/`` (GeckoLib 4) + controlador.
    - ``rock``: la animación se llama como el IDENTIFICADOR declarado en la
      geometría, no como el fichero (caso típico de mods reales).
    - ``ghost_e``: entidad sin textura (residuo / placeholder).
    - ``common.animation.json``: documento compartido con animaciones de
      OTRO mob: solo se toman las que mencionan a la entidad.
    """
    ns = "wispmod"
    files: dict[str, bytes] = {}

    def w(rel: str, obj) -> None:
        files[rel] = json.dumps(obj).encode("utf-8")

    w("fabric.mod.json", {"id": ns, "name": "Wisp Mod"})
    w(f"assets/{ns}/lang/en_us.json", {
        "entity.wispmod.wisp": "Wisp",
        "entity.wispmod.rock": "Rock Golem",
        "entity.wispmod.ghost_e": "Ghost E",
    })

    body_bones = [
        {"name": "body", "pivot": [0, 0, 0],
         "cubes": [{"origin": [-2, 0, -2], "size": [4, 6, 4], "uv": [0, 0]}]},
    ]
    w(f"assets/{ns}/geo/wisp.geo.json", _geo_doc("geometry.wisp", body_bones))
    w(f"assets/{ns}/geo/rock.geo.json", _geo_doc(
        "geometry.stone_golem",
        [{"name": "body", "pivot": [0, 0, 0],
          "cubes": [{"origin": [-4, 0, -4], "size": [8, 16, 8], "uv": [0, 0]}]}],
    ))
    w(f"assets/{ns}/geo/ghost_e.geo.json", _geo_doc("geometry.ghost_e", body_bones))

    # Animaciones de wisp: carpeta GeckoLib 4 + 'animators' de GeckoLib 3.
    w(f"assets/{ns}/animations/entity/wisp.animation.json", {
        "format_version": "1.8.0",
        "animations": {
            "animation.wisp.idle": {
                "loop": True,
                "animators": {"body": {"rotation": {"0.0": [0, 0, 0], "1.0": [5, 0, 0]}}},
            },
            "animation.wisp.attack": {
                "loop": True,
                "bones": {"body": {"rotation": {"0.0": [0, 0, 0], "0.5": [20, 0, 0]}}},
            },
        },
    })
    # Animación de rock, nombrada por el identificador declarado.
    w(f"assets/{ns}/animations/stone_golem.animation.json", {
        "animations": {
            "animation.stone_golem.idle": {
                "loop": True,
                "bones": {"body": {"position": {"0.0": [0, 0, 0], "1.0": [0, 1, 0]}}},
            },
        },
    })
    # Documento compartido: una animación de wisp y otra de otro mob.
    w(f"assets/{ns}/animations/common.animation.json", {
        "format_version": "1.8.0",
        "animations": {
            "animation.wisp.fly": {
                "loop": True,
                "bones": {"body": {"position": {"0.0": [0, 0, 0], "2.0": [0, 3, 0]}}},
            },
            "animation.mimic.attack": {
                "loop": True,
                "bones": {"body": {"rotation": {"0.0": [0, 0, 0]}}},
            },
        },
    })
    # Controlador con estados, transiciones y molang.
    w(f"assets/{ns}/animation_controllers/wisp.animation_controllers.json", {
        "format_version": "1.10.0",
        "animation_controllers": {
            "controller.animation.wisp": {
                "initial_state": "default",
                "states": {
                    "default": {
                        "animations": ["animation.wisp.idle"],
                        "transitions": [{"attack": "q.is_charging"}],
                    },
                    "attack": {
                        "animations": [{"animation.wisp.attack": "q.is_charging"}],
                        "transitions": [{"default": "!q.is_charging"}],
                    },
                },
            },
        },
    })

    files[f"assets/{ns}/textures/entity/wisp.png"] = solid_png((90, 200, 255, 255))
    files[f"assets/{ns}/textures/entity/rock.png"] = solid_png((120, 120, 120, 255))
    return files


def test_geckolib_animations_and_controllers(tmp_path):
    conv = convert(build_wispmod(), str(tmp_path))
    assert conv.errors == []

    # Controlador emitido con los nombres reescritos a alias del client entity.
    ctrl = _rp(conv, "animation_controllers/wispmod_wisp.animation_controllers.json")
    ctrl_doc = ctrl["animation_controllers"]["controller.animation.wisp"]
    assert ctrl_doc["initial_state"] == "default"
    assert ctrl_doc["states"]["default"]["animations"] == ["idle"]
    assert ctrl_doc["states"]["default"]["transitions"] == [{"attack": "q.is_charging"}]
    assert ctrl_doc["states"]["attack"]["animations"] == [{"attack": "q.is_charging"}]

    # Client entity: alias de animaciones + controlador, y animate al controlador.
    client = _rp(conv, "entity/wispmod_wisp.entity.json")["minecraft:client_entity"]["description"]
    assert client["animations"]["idle"] == "animation.wisp.idle"
    assert client["animations"]["attack"] == "animation.wisp.attack"
    assert client["animations"]["fly"] == "animation.wisp.fly"
    assert client["animations"]["controller_wisp"] == "controller.animation.wisp"
    assert client["scripts"]["animate"] == ["controller_wisp"]

    # 'animators' (GeckoLib 3) se convirtió a 'bones' Bedrock.
    anims = _rp(conv, "animations/wispmod_wisp.animation.json")["animations"]
    assert "animators" not in json.dumps(anims)
    assert anims["animation.wisp.idle"]["bones"]["body"]["rotation"]["1.0"] == [5, 0, 0]
    assert anims["animation.wisp.idle"]["animation_length"] == 1  # calculada

    # El documento compartido solo aporta las animaciones de wisp.
    assert "animation.wisp.fly" in anims
    assert "animation.mimic.attack" not in anims

    # Animación encontrada por el identificador declarado (stone_golem).
    rock_client = _rp(conv, "entity/wispmod_rock.entity.json")["minecraft:client_entity"]["description"]
    assert rock_client["animations"]["idle"] == "animation.stone_golem.idle"
    assert rock_client["scripts"]["animate"] == ["idle"]

    # Entidad sin textura: residuo explicado, no inventada.
    residues = _residues(conv)
    assert "assets/wispmod/geo/ghost_e.geo.json" in residues
    assert "sin textura" in residues["assets/wispmod/geo/ghost_e.geo.json"]
    assert "entities/wispmod_ghost_e.entity.json" not in conv.writer.bp


def test_geckolib_entity_placeholder_when_missing_texture(tmp_path):
    conv = convert(build_wispmod(), str(tmp_path), placeholders=True)
    assert conv.errors == []
    assert "entities/wispmod_ghost_e.entity.json" in conv.writer.bp
    assert "textures/entity/wispmod/ghost_e.png" in conv.writer.rp


def test_broken_animation_does_not_kill_entity(tmp_path):
    """Un JSON de animación corrupto NO puede tumbar la entidad."""
    files = build_wispmod()
    files["assets/wispmod/animations/entity/wisp.animation.json"] = b"{esto no es json"
    conv = convert(files, str(tmp_path))
    assert conv.errors == []

    # La entidad se emite igual: geometría + textura intactas.
    client = _rp(conv, "entity/wispmod_wisp.entity.json")["minecraft:client_entity"]["description"]
    assert client["geometry"]["default"] == "geometry.wispmod_wisp"
    assert client["textures"]["default"] == "textures/entity/wispmod/wisp"
    assert "models/entity/wispmod_wisp.geo.json" in conv.writer.rp

    # Lo que sobrevive del documento compartido se conserva: solo la
    # animación que menciona a la entidad, nunca la del otro mob.
    assert client["animations"] == {
        "fly": "animation.wisp.fly",
        "controller_wisp": "controller.animation.wisp",
    }

    # El controlador se mantiene con sus referencias no resueltas ANOTADAS
    # (Bedrock las tolera: no reproducen, pero no rompen la entidad). Nada
    # se pierde en silencio.
    notes = "\n".join(n for e in conv.result.entries for n in e.notes)
    assert "animation.wisp.idle" in notes
    assert "animation.wisp.attack" in notes
    # La animación del fichero corrupto queda contada como residuo, nunca
    # en silencio.
    residues = _residues(conv)
    assert "assets/wispmod/animations/entity/wisp.animation.json" in residues
    assert "ilegible" in residues["assets/wispmod/animations/entity/wisp.animation.json"]
