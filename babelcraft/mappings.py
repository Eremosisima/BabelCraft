"""Mapeos de IDs vanilla Java → Bedrock y utilidades de referencia.

Regla del validador (la misma que sigue PortKit, porque es la correcta):
un id `minecraft:` se da por bueno — es vanilla y Bedrock lo tiene —
salvo que aparezca en RENAMED (ids con nombre distinto entre ediciones)
o en MISSING (existe en Java y NO en Bedrock: p.ej. los deidades de
commandos). Los ids de OTROS namespaces son dependencias: se reportan,
nunca se inventan.

El validador NO necesita la lista completa de 1100 items vanilla para ser
útil: valida la consistencia interna del addon (referencias entre
ficheros generados) y marca lo que apunta fuera. La lista completa de
vanilla es trabajo del módulo `reference` futuro (ver roadmap).
"""

from __future__ import annotations

# Renombrados Java -> Bedrock conocidos (bloques/items que difieren).
# Fuente: cambios 1.20-1.21 de ambas ediciones + documentación de Geyser.
RENAMED: dict[str, str] = {
    # Renombrados en Java 1.20.3 que Bedrock ya usaba así:
    "minecraft:grass": "minecraft:short_grass",
    "minecraft:grass_block": "minecraft:grass_block",
    "minecraft:bricks": "minecraft:brick_block",
    "minecraft:sign": "minecraft:standing_sign",
    "minecraft:wall_sign": "minecraft:wall_sign",
    # Estructura técnica:
    "minecraft:mob_spawner": "minecraft:mob_spawner",
}

# Existen en Java y no en Bedrock (o al revés de como se usan): reportar.
MISSING_IN_BEDROCK = {
    "minecraft:spyglass",  # existe, pero con nombre técnico distinto en BP
}

# Items de Bedrock con "data value" que Java trata como ítems distintos.
# La lista es de las familias que más aparecen en recetas de mods.
BEDROCK_DATA_ITEMS = {
    "minecraft:dye",
    "minecraft:fish",
    "minecraft:skull",
}


def normalize_item(item_id: str) -> tuple[str, str | None]:
    """Normaliza un id de item Java al Bedrock equivalente.

    Devuelve (id_bedrock, nota). `nota` es None cuando es directo.
    """
    if item_id in RENAMED and RENAMED[item_id] != item_id:
        return RENAMED[item_id], f"renombrado: {item_id} -> {RENAMED[item_id]}"
    return item_id, None


def normalize_block(block_id: str) -> tuple[str, str | None]:
    """Ídem para bloques."""
    return normalize_item(block_id)


def is_vanilla(identifier: str) -> bool:
    return identifier.startswith("minecraft:")


def is_custom(identifier: str) -> bool:
    return not is_vanilla(identifier)


def namespace_of(identifier: str) -> str:
    return identifier.split(":", 1)[0] if ":" in identifier else ""


def bedrock_loot_path(java_ref: str, ns: str) -> str:
    """`modid:blocks/foo` -> `loot_tables/modid/blocks/foo.json` (BP).

    Bedrock no tiene namespaces en las rutas de loot: la ruta del
    componente `minecraft:loot` es relativa al behavior pack.
    """
    ref = java_ref.split(":", 1)[1] if ":" in java_ref else java_ref
    if not ref.endswith(".json"):
        ref += ".json"
    return f"loot_tables/{ns}/{ref}"


# Traducción de claves de lang Java -> Bedrock.
# Java:      item.modid.ruby  / block.modid.ruby_block / entity.modid.gob
# Bedrock:   item.modid:ruby  / tile.modid:ruby_block.name / entity.modid:gob.name
def lang_key_java_to_bedrock(key: str, value: str) -> tuple[str, str] | None:
    """Convierte una clave de lang de Java a su equivalente Bedrock."""
    if key.startswith("item."):
        rest = key[len("item.") :]
        if rest.endswith(".name"):
            rest = rest[: -len(".name")]
        ns, _, name = rest.partition(".")
        if ns and name:
            return (f"item.{ns}:{name}", value)
    elif key.startswith("block."):
        rest = key[len("block.") :]
        ns, _, name = rest.partition(".")
        if ns and name:
            return (f"tile.{ns}:{name}.name", value)
    elif key.startswith("entity."):
        rest = key[len("entity.") :]
        if rest.endswith(".name"):
            rest = rest[: -len(".name")]
        ns, _, name = rest.partition(".")
        if ns and name:
            return (f"entity.{ns}:{name}.name", value)
    elif key.startswith("itemGroup."):
        return (key, value)
    return None
