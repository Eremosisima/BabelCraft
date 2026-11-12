"""Tests de los mapeos de IDs vanilla y claves de lang Java -> Bedrock."""

from __future__ import annotations

from babelcraft.mappings import (
    bedrock_loot_path,
    is_custom,
    is_vanilla,
    lang_key_java_to_bedrock,
    namespace_of,
    normalize_block,
    normalize_item,
)


def test_normalize_item_renamed():
    assert normalize_item("minecraft:grass") == (
        "minecraft:short_grass",
        "renombrado: minecraft:grass -> minecraft:short_grass",
    )
    assert normalize_item("minecraft:sign") == ("minecraft:standing_sign", "renombrado: minecraft:sign -> minecraft:standing_sign")


def test_normalize_item_identity_when_no_rename():
    # grass_block está en RENAMED pero apunta a sí mismo: sin nota.
    assert normalize_item("minecraft:grass_block") == ("minecraft:grass_block", None)
    assert normalize_item("minecraft:stone") == ("minecraft:stone", None)
    assert normalize_item("minimod:ruby") == ("minimod:ruby", None)


def test_normalize_block_delegates_to_item():
    assert normalize_block("minecraft:bricks") == ("minecraft:brick_block", "renombrado: minecraft:bricks -> minecraft:brick_block")
    assert normalize_block("minecraft:dirt") == ("minecraft:dirt", None)


def test_vanilla_and_custom_predicates():
    assert is_vanilla("minecraft:stone") is True
    assert is_vanilla("stone") is False
    assert is_custom("minimod:ruby") is True
    assert is_custom("minecraft:stone") is False


def test_namespace_of():
    assert namespace_of("minimod:ruby") == "minimod"
    assert namespace_of("minecraft:stone") == "minecraft"
    assert namespace_of("sin_namespace") == ""


def test_bedrock_loot_path():
    assert bedrock_loot_path("minimod:blocks/ruby_block", "minimod") == "loot_tables/minimod/blocks/ruby_block.json"
    assert bedrock_loot_path("minimod:entities/gob.json", "minimod") == "loot_tables/minimod/entities/gob.json"
    # Referencia sin namespace (rara pero legal en algunos datapacks).
    assert bedrock_loot_path("blocks/foo", "minimod") == "loot_tables/minimod/blocks/foo.json"


def test_lang_key_java_to_bedrock_items():
    assert lang_key_java_to_bedrock("item.minimod.ruby", "Ruby") == ("item.minimod:ruby", "Ruby")
    # La forma con .name también aparece en mods viejos.
    assert lang_key_java_to_bedrock("item.minimod.ruby.name", "Ruby") == ("item.minimod:ruby", "Ruby")


def test_lang_key_java_to_bedrock_blocks_and_entities():
    assert lang_key_java_to_bedrock("block.minimod.ruby_block", "Bloque") == (
        "tile.minimod:ruby_block.name",
        "Bloque",
    )
    assert lang_key_java_to_bedrock("entity.minimod.gob", "Gob") == (
        "entity.minimod:gob.name",
        "Gob",
    )
    assert lang_key_java_to_bedrock("entity.minimod.gob.name", "Gob") == (
        "entity.minimod:gob.name",
        "Gob",
    )


def test_lang_key_java_to_bedrock_passthrough_and_none():
    assert lang_key_java_to_bedrock("itemGroup.minimod", "Mini") == ("itemGroup.minimod", "Mini")
    # Claves que Bedrock no entiende pero tampoco rompen: sin equivalente.
    assert lang_key_java_to_bedrock("subtitles.entity.gob.hurt", "Ouch") is None
    assert lang_key_java_to_bedrock("advancements.minimod.root", "Root") is None
    # Formas incompletas.
    assert lang_key_java_to_bedrock("item.", "x") is None
    assert lang_key_java_to_bedrock("item.minimod.", "x") is None
    assert lang_key_java_to_bedrock("block.solo", "x") is None
