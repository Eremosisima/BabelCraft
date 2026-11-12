# Estrategia de Conversión Java → Bedrock

## Fundamentos

Este documento establece la estrategia de conversión basada en la documentación oficial de Minecraft:
- **Java Edition**: Fabric/Forge mod structure + data/resource packs
- **Bedrock Edition**: Behavior Pack + Resource Pack (1.21.80+)

---

## 1. Estructura de Archivos

### Java (Fabric/Forge)
```
src/main/resources/
├── fabric.mod.json (o META-INF/mods.toml)
├── assets/<namespace>/
│   ├── blockstates/<block>.json
│   ├── models/
│   │   ├── block/<model>.json
│   │   └── item/<model>.json
│   ├── textures/
│   │   ├── block/<texture>.png
│   │   ├── item/<texture>.png
│   │   └── entity/<entity>.png
│   ├── lang/<lang>.json
│   └── sounds.json
└── data/<namespace>/
    ├── recipe/<recipe>.json
    ├── loot_tables/
    │   ├── blocks/<block>.json
    │   └── entities/<entity>.json
    └── tags/
```

### Bedrock (1.21.80+)
```
Behavior Pack/
├── manifest.json
├── blocks/<block>.json          # Comportamiento del bloque
├── items/<item>.json            # Comportamiento del ítem
├── entities/<entity>.json       # [IMPORTANTE] Comportamiento de entidad en PLURAL
├── recipes/<recipe>.json        # Recetas
├── loot_tables/                 # Loot tables
└── spawn_rules/                 # Reglas de spawn

Resource Pack/
├── manifest.json
├── blocks.json                  # Solo sonidos (opcional)
├── textures/
│   ├── item_texture.json        # Shortnames de texturas
│   ├── terrain_texture.json     # Shortnames de texturas
│   └── entity/<entity>.png
├── models/entity/<entity>.geo.json
├── entity/<entity>.entity.json  # [IMPORTANTE] Cliente (visual) en SINGULAR
├── materials/<ns>.material      # Materiales custom
├── render_controllers/          # Render controllers
├── animations/                  # Animaciones
├── animation_controllers/       # Controladores
└── texts/<lang>.lang           # Traducciones
```

**⚠️ NOTA CRÍTICA SOBRE RUTAS DE ENTIDADES:**
- **Behavior Pack (BP)**: `entities/` (plural) - contiene el comportamiento del servidor
- **Resource Pack (RP)**: `entity/` (singular) - contiene la definición visual del cliente

Esta convención es consistente con la estructura oficial de Bedrock y ha sido corregida en BabelCraft.

---

## 2. Bloques (Blocks)

### Java → Bedrock Mapping

| Java | Bedrock | Notas |
|------|---------|-------|
| `assets/<ns>/blockstates/<block>.json` | `BP/blocks/<block>.json` | Comportamiento |
| `assets/<ns>/models/block/<model>.json` | Geometría custom o `minecraft:geometry.full_block` | Desde 1.21.80 |
| Texturas en `terrain_texture.json` | Shortnames con `{"textures": "ruta"}` | Objeto, no string |

### Formato Correcto (1.21.80+)

**BP/blocks/ruby_block.json:**
```json
{
  "format_version": "1.21.80",
  "minecraft:block": {
    "description": {
      "identifier": "demo:die"
    },
    "components": {
      "minecraft:geometry": "minecraft:geometry.full_block",  // O geometría custom
      "minecraft:material_instances": {
        "north": {"texture": "die_3", "render_method": "opaque"},
        "south": {"texture": "die_4", "render_method": "opaque"},
        "east": {"texture": "die_2", "render_method": "opaque"},
        "west": {"texture": "die_5", "render_method": "opaque"},
        "up": {"texture": "die_1", "render_method": "opaque"},
        "down": {"texture": "die_6", "render_method": "opaque"}
      },
      "minecraft:destructible_by_mining": {
        "seconds_to_destroy": 1.5
      },
      "minecraft:destructible_by_explosion": {
        "explosion_resistance": 3
      }
    }
  }
}
```

**RP/textures/terrain_texture.json:**
```json
{
  "resource_pack_name": "custom_block_resource_pack",
  "texture_name": "atlas.terrain",
  "padding": 8,
  "num_mip_levels": 4,
  "texture_data": {
    "die_1": {"textures": "textures/blocks/die_1"},
    "die_2": {"textures": "textures/blocks/die_2"}
  }
}
```

**RP/blocks.json (opcional, solo sonidos):**
```json
{
  "format_version": "1.21.80",
  "demo:die": {
    "sound": "stone"
  }
}
```

### Reglas de Conversión

1. **Cubo simple**: Usar `minecraft:geometry.full_block` con `material_instances`
2. **Geometría custom**: Generar `.geo.json` en `models/entity/` (no `models/block/`)
3. **blocks.json**: Solo si no hay `material_instances` en BP. Si BP tiene componentes visuales, `blocks.json` solo define sonidos
4. **terrain_texture.json**: Cada textura necesita `{"textures": "ruta"}`, no string directo

---

## 3. Ítems (Items)

### Java → Bedrock Mapping

| Java | Bedrock | Notas |
|------|---------|-------|
| `assets/<ns>/models/item/<item>.json` | `BP/items/<item>.json` | Comportamiento |
| `assets/<ns>/models/item/<item>.json` | `RP/attachables/<item>.attachable.json` | Visual 3D |
| `item.<ns>.<item>` en lang | `tile.<ns>:<item>.name` en .lang | Traducción |

### Formato Correcto

**BP/items/ruby.json:**
```json
{
  "format_version": "1.21.30",
  "minecraft:item": {
    "description": {
      "identifier": "demo:ruby",
      "menu_category": {
        "category": "items"
      }
    },
    "components": {
      "minecraft:icon": "demo_ruby",
      "minecraft:max_stack_size": 64
    }
  }
}
```

**RP/textures/item_texture.json:**
```json
{
  "resource_pack_name": "demo",
  "texture_name": "atlas.items",
  "texture_data": {
    "demo_ruby": {"textures": "textures/items/ruby"}
  }
}
```

---

## 4. Entidades (Entities)

### Java → Bedrock Mapping

| Java | Bedrock | Notas |
|------|---------|-------|
| Código Java (.class) | `BP/entities/<entity>.json` | Comportamiento |
| GeckoLib modelo | `RP/models/entity/<entity>.geo.json` | Geometría |
| GeckoLib animaciones | `RP/animations/<entity>.animation.json` | Animaciones |
| `assets/<ns>/textures/entity/<entity>.png` | `RP/textures/entity/<entity>.png` | Textura |
| N/A | `RP/entity/<entity>.entity.json` | Cliente (visual) |

### Formato Correcto

**BP/entities/robot.json:**
```json
{
  "format_version": "1.12.0",
  "minecraft:entity": {
    "description": {
      "identifier": "demo:robot",
      "is_spawnable": true,
      "is_summonable": true
    },
    "components": {
      "minecraft:physics": {},
      "minecraft:health": {"value": 20, "max": 20},
      "minecraft:movement": {"value": 0.25}
    }
  }
}
```

**RP/entity/robot.entity.json:**
```json
{
  "format_version": "1.10.0",
  "minecraft:client_entity": {
    "description": {
      "identifier": "demo:robot",
      "materials": {
        "default": "entity"  // O material custom
      },
      "textures": {
        "default": "textures/entity/robot"
      },
      "geometry": {
        "default": "geometry.robot"
      },
      "render_controllers": [
        "controller.render.robot"
      ],
      "spawn_egg": {
        "base_color": "#505152",
        "overlay_color": "#3b9dff"
      }
    }
  }
}
```

**RP/render_controllers/robot.render_controllers.json:**
```json
{
  "format_version": "1.8.0",
  "render_controllers": {
    "controller.render.robot": {
      "geometry": "Geometry.default",
      "materials": [{"*": "Material.default"}],
      "textures": ["Texture.default"]
    }
  }
}
```

### Materiales Custom

**RP/materials/demo.material:**
```json
{
  "materials": {
    "version": "1.0.0",
    "demo_atlas_alphatest:entity_alphatest": {
      "+defines": ["USE_UV_ANIM"]
    },
    "demo_atlas_alphablend:entity_alphablend": {
      "+defines": ["USE_UV_ANIM"]
    }
  }
}
```

**Formato**: `nombre_material:material_padre` con `+defines` (prefijo `+`) para heredar

---

## 5. Recetas (Recipes)

### Java → Bedrock Mapping

| Java Type | Bedrock Type |
|-----------|--------------|
| `minecraft:crafting_shaped` | `minecraft:recipe_shaped` |
| `minecraft:crafting_shapeless` | `minecraft:recipe_shapeless` |
| `minecraft:smelting` | `minecraft:recipe_furnace` |
| `minecraft:blasting` | `minecraft:recipe_furnace` (tag: blast_furnace) |
| `minecraft:smoking` | `minecraft:recipe_furnace` (tag: smoker) |
| `minecraft:stonecutting` | `minecraft:recipe_shapeless` (tag: stonecutter) |
| `minecraft:smithing_transform` | No tiene equivalente directo |

### Formato Correcto

**BP/recipes/ruby_block.json:**
```json
{
  "format_version": "1.20.10",
  "minecraft:recipe_shaped": {
    "description": {
      "identifier": "demo:ruby_block"
    },
    "tags": ["crafting_table"],
    "pattern": [
      "RRR",
      "RRR",
      "RRR"
    ],
    "key": {
      "R": {"item": "demo:ruby"}
    },
    "unlock": [{"item": "demo:ruby"}],
    "result": {
      "item": "demo:ruby_block",
      "count": 1
    }
  }
}
```

### Validaciones Críticas

1. **Input/Output deben existir**: Si un ítem no está en `ctx.item_ids`, la receta queda como residuo
2. **Unlock obligatorio**: Bedrock requiere `unlock` en todas las recetas
3. **Tags específicos**: Cada tipo de receta tiene tags específicos

---

## 6. Idiomas (Languages)

### Java → Bedrock Mapping

| Java | Bedrock |
|------|---------|
| `item.<ns>.<item>=Name` | `item.<ns>:<item>.name=Name` |
| `block.<ns>.<block>=Name` | `tile.<ns>:<block>.name=Name` |
| `entity.<ns>.<entity>=Name` | `entity.<ns>:<entity>.name=Name` |
| N/A | `item.spawn_egg.entity.<ns>:<entity>.name=Spawn <Entity>` |

**Archivo**: `RP/texts/en_US.lang` (y otros idiomas)

---

## 7. Problemas Identificados en BabelCraft

### Críticos (Errores de Bedrock)

1. **❌ terrain_texture.json e item_texture.json**: 
   - **Problema**: Escriben strings directos `"ruta"`
   - **Correcto**: `{"textures": "ruta"}`
   - **Fix**: ✅ Ya implementado en `pack.py`

2. **❌ Materials format**:
   - **Problema**: `"+defines": [...]` sin prefijo `+` o formato incorrecto
   - **Correcto**: Herencia con `nombre:padre` y `+defines`
   - **Fix**: ✅ Ya implementado en `entities.py`

3. **❌ Block geometry location**:
   - **Problema**: Geometrías en `models/block/`
   - **Correcto**: `models/entity/` (Bedrock no usa `models/block/`)
   - **Fix**: ✅ Ya implementado en `blocks.py` y `models.py`

4. **❌ Block geometry format**:
   - **Problema**: `"minecraft:geometry": "geometry.name"` (string)
   - **Correcto**: `{"identifier": "geometry.name"}` (objeto)
   - **Fix**: ✅ Ya implementado en `blocks.py`

5. **❌ blocks.json con geometry**:
   - **Problema**: Se escribe `blocks.json` incluso con geometría custom
   - **Correcto**: Solo si NO hay `material_instances` en BP
   - **Fix**: ✅ Ya implementado en `blocks.py`

6. **❌ Recipe validation**:
   - **Problema**: Recetas con ítems inexistentes
   - **Correcto**: Validar que input/output existan
   - **Fix**: ✅ Ya implementado en `recipes.py`

### Pendientes de Verificación

1. **⚠️ Entity materials**:
   - Verificar que los materials custom se referencien correctamente
   - Verificar herencia `entity_alphatest` / `entity_alphablend`

2. **⚠️ Render controllers**:
   - Verificar formato de arrays: `[{"*": "Material.default"}]`
   - Verificar referencias `Geometry.default`, `Material.default`, `Texture.default`

3. **⚠️ Format versions**:
   - Blocks: `1.21.80` (requerido para geometría explícita)
   - Items: `1.21.30`
   - Entities BP: `1.12.0`
   - Entities RP: `1.10.0`
   - Recipes: `1.20.10`
   - Materials: No usa `format_version` (formato especial)
   - Render controllers: `1.8.0`
   - Animations: `1.8.0`

4. **⚠️ Animation keyframes**:
   - Filtrar strings que no sean Molang válido
   - Preservar Molang: `query.*`, `variable.*`, `math.*`

---

## 8. Plan de Acción

### Fase 1: Validación de Fixes Actuales
- [ ] Ejecutar tests con minimod
- [ ] Generar addon de prueba
- [ ] Importar en Bedrock y validar
- [ ] Corregir errores que aparezcan

### Fase 2: Optimización
- [ ] Validar format versions
- [ ] Optimizar materials custom
- [ ] Validar render controllers
- [ ] Optimizar geometría de bloques

### Fase 3: Pruebas con Mods Reales
- [ ] Probar con mod pequeño
- [ ] Probar con Cobblemon (mod grande)
- [ ] Validar performance y límites

---

## 9. Referencias Oficiales

### Documentación Bedrock
- [Minecraft Creator Documentation](https://learn.microsoft.com/en-us/minecraft/creator/)
- [Resource Packs](https://learn.microsoft.com/en-us/minecraft/creator/documents/resourcepack)
- [Behavior Packs](https://learn.microsoft.com/en-us/minecraft/creator/documents/behaviorpack)
- [Custom Blocks](https://learn.microsoft.com/en-us/minecraft/creator/documents/addcustomdieblock)
- [Custom Entities](https://learn.microsoft.com/en-us/minecraft/creator/documents/introductiontoaddentity)
- [Materials](https://learn.microsoft.com/en-us/minecraft/creator/documents/material-files)
- [Entity Properties](https://learn.microsoft.com/en-us/minecraft/creator/documents/introductiontoentityproperties)

### Documentación Java
- [Fabric Documentation](https://docs.fabricmc.net/)
- [Forge Documentation](https://docs.minecraftforge.net/)
- [Data Packs](https://minecraft.wiki/w/Data_pack)

### Herramientas
- [Blockbench](https://www.blockbench.net/) - Modelado y animación
- [UUID Generator](https://www.uuidgenerator.net/) - UUIDs para manifests
- [Minecraft Samples](https://github.com/microsoft/minecraft-samples) - Ejemplos oficiales

---

## 10. Principios de Diseño

1. **Nunca fingir**: Si algo no se puede convertir fielmente, marcar como residuo
2. **Validación estricta**: Cada JSON debe cumplir el schema de Bedrock
3. **Documentación oficial**: Seguir las specs de Microsoft/Mojang
4. **Testing iterativo**: Probar en Bedrock después de cada cambio
5. **Cobertura completa**: Reportar TODO lo que no se convierte y por qué

---

**Última actualización**: 2026-11-11
**Estado**: En desarrollo (Fase 1)
