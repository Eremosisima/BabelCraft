# Learnings: Java → Bedrock Migration (BabelCraft / Cobbleverse)

Este documento captura aprendizajes prácticos para construir/mantener un conversor, agente o skill capaz de migrar contenido de Minecraft Java (mods, resource packs, datapacks, modpacks) a addons de Bedrock.

## 1. Principios

- **Nunca fingir**: convertir solo lo que tiene equivalente fiel o adaptable; lo no portable debe quedar como residuo con causa.
- **Declarativo primero**: modelos, texturas, animaciones, recetas, loot, lang y definiciones de contenido son el núcleo convertible.
- **Lógica Java = residuo**: bytecode, IA, sistemas de batalla/captura, GUIs complejas, mecánicas custom y gran parte de worldgen no se traducen automáticamente.
- **Validar en runtime Bedrock**: el content log es fuente de verdad para errores de Molang, referencias rotas, formatos y comportamiento.

## 2. Estructura y formatos Bedrock (errores comunes evitados)

- BP entidades: `behavior_packs/<bp>/entities/*.json` (plural `entities/`).
- RP client entities: `resource_packs/<rp>/entity/*.json` (singular `entity/`).
- `item_texture.json` / `terrain_texture.json`: entradas como `{"textures": "path/sin_extension"}`.
- Geometría de bloques custom: identificador en formato Bedrock esperado (p.ej. `{"identifier":"geometry..."}`) y ubicación correcta en `models/blocks/` o `models/entity/` según uso.
- Evitar `*.material` custom cuando el motor no los reconoce; preferir materiales vanilla (`entity_alphatest`, etc.) salvo casos validados.
- Atlas de texturas: reduce handles, pero requiere UV/refs coherentes; usar para rendimiento (especialmente móvil/muchos mobs).

## 3. Entidades, modelos y animaciones

- **Geometrías (GeckoLib/Bedrock-like)**: preservar identificadores originales cuando sea posible; no renombrar arbitrariamente si rompe referencias.
- **Render controllers**: asegurar `Geometry.default`, `Material.default`, `Texture.default` (o arrays/keys consistentes con la client entity).
- **Animaciones**:
  - Sanitizar Molang no soportado en Bedrock (p.ej. queries custom `q.r.*`, `q.input_*`, `q.has_entity`, `q.sound`, etc.) reemplazando por valores seguros o eliminando efectos/scripts inválidos.
  - Tras reemplazos, validar expresiones (paréntesis balanceados, parámetros correctos en `math.clamp`, evitar operadores huérfanos/truncados).
  - `catmullrom`/precomputed cubic requiere datos constantes; degradar/colapsar a valores constantes o `linear` cuando haya Molang/incompatibilidades.
  - Eliminar animaciones que queden sin huesos ni efectos tras sanitización para evitar errores `anim.bones`.
  - Verificar referencias: scripts/controllers/client entities no deben apuntar a animaciones inexistentes (`can't find animation ...`).
- **Attachables**: generar animaciones de attachable en archivos separados (`*.attachable.animation.json`) para evitar colisiones con animaciones de entidad/bloque.
- **Diagnóstico típico**: T-pose suele indicar animación no encontrada/no reproducida, script/alias incorrecto, controller/anim ref rota o geometría/material/texture mismatch.

## 4. Ítems y Poké Balls (aproximaciones)

- Resolver texturas desde modelos Java (`textures.layer0` / paths declarados) y soportar subcarpetas (`textures/item/poke_balls/...`).
- Clasificar ítems por heurística/nombre/datos para componentes Bedrock (comida/consumible, equipo, stack, hand_equipped, cooldown, use_animation).
- **Poké Balls**: mecánica base viable como ítems lanzables (`minecraft:throwable` + `minecraft:projectile`) como aproximación.
  - No equivale a captura real de Cobblemon (requiere entidad/proyectil dedicada, colisiones/eventos, Script API, estado de Pokémon, UI/almacenamiento).
- Documentar claramente límites: efectos de pociones, evolución, TMs, held items, curación avanzada, etc. suelen ser parciales o no portables.

## 5. Conversión de modpacks (Cobbleverse) y procedencia

- Un modpack requiere **merge por capas**: base mod + resource packs + datapacks + overrides + descargas verificadas.
- **Procedencia/orden de overlay importa**: últimos overlays pueden sobrescribir assets; registrar orden y fuentes para depurar conflictos.
- **Identidad del source fusionado**: en merges multi-namespace, forzar metadatos (`fabric.mod.json`/pack info) para que el conversor detecte namespace/loader correctos.
- No todos los mods del índice estarán disponibles/convertibles: priorizar contenido declarativo y ecosistema relevante (Cobblemon y addons con assets).
- Muchos residuos son esperados (worldgen, estructuras NBT, funciones, advancements, lógica Java, shaders, UI mods).

## 6. Seguridad y descargas

- Descargar solo desde orígenes confiables esperados (p.ej. `https://cdn.modrinth.com/...`).
- Verificar **hashes (SHA-512/SHA-1)** y tamaño contra el índice; eliminar artefactos inválidos.
- Preferir selección “correspondiente” (contenido relevante) sobre descarga masiva de mods de rendimiento/UI sin valor para conversión.
- No ejecutar jars descargados; usarlos como fuentes de assets/datos cuando aplique.

## 7. Grafos útiles para mejorar el conversor

- **Cobertura**: fuente/namespace/tipo → convertido/adaptado/residuo/error + causa (priorización y métricas).
- **Referencias**: entidad/ítem/bloque ↔ geometría, texturas, animaciones, controllers, spawn/loot/lang (detección de refs rotas).
- **Procedencia/overlay**: índice, overrides, descargas y orden de merge → origen final de cada archivo (trazabilidad y conflictos).
- **Rendimiento**: dimensiones de texturas, uso de atlas, complejidad de modelos/animaciones para optimización.

## 8. Flujo operativo recomendado (agente/skill)

1. **Inventariar fuente**: tipo (jar/zip/carpeta/modpack), namespaces, assets/datos disponibles, dependencias.
2. **Construir grafo de procedencia** (modpacks): qué entra, de dónde y en qué orden.
3. **Merge seguro** (si aplica): base + overlays + descargas verificadas.
4. **Convertir** con pipeline determinista (lang/textures/models/loot/items/blocks/recipes/entities/sounds + hooks de mecánicas).
5. **Validar**: validador estructural + reporte de cobertura + revisión de referencias.
6. **Probar en Bedrock**: importar addon, revisar content log, probar entidades/ítems/spawns clave.
7. **Iterar**: corregir sanitización, refs, componentes, y re-ejecutar; documentar residuos/límites.
8. **Persistir learnings**: actualizar grafo, reporte y notas de decisiones para futuras migraciones.
