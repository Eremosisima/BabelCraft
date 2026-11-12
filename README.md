# BabelCraft

**Convierte mods de Minecraft Java Edition en addons nativos de Bedrock Edition (`.mcaddon`).**

BabelCraft lee un `.jar`, `.zip` o una carpeta con `data/` + `assets/` (mod, datapack o
resourcepack), convierte el contenido **declarativo** a los formatos de Bedrock y escribe un
informe que dice, fichero a fichero, qué se convirtió fiel, qué se adaptó con pérdidas y qué
quedó fuera y por qué.

No es un emulador ni un puente de crossplay: genera un addon que funciona en Bedrock normal,
sin Geyser.

```
babelcraft convert MiMod.jar -o salida
```

---

## Por qué existe

Los conversores que hay suelen dejar fuera dos cosas:

1. **Entidades.** Casi todos convierten ítems, bloques y recetas, pero los mobs se quedan por
   el camino porque su lógica vive en Java. BabelCraft no traduce el cerebro del mob: reensambla
   su **modelo, textura y animaciones** (los mods modernos usan GeckoLib, cuyo formato ya es el
   de Bedrock) y le da el comportamiento mínimo para existir como criatura.
2. **Optimización para móvil.** Un addon con cientos de texturas agota los *texture handles* de
   Bedrock (800 recomendados, 4000 duros). BabelCraft puede meter todas las texturas de
   entidades en **un solo atlas**, podar huesos vacíos y adelgazar animaciones — técnicas
   medidas sobre corpus reales.

Principio de diseño: **nunca fingir**. Si algo no tiene equivalente fiel, se marca como
`residuo` con la razón exacta; no se inventa un icono, una textura ni un comportamiento.

---

## Instalación

Requiere **Python 3.9+**. Solo biblioteca estándar: sin dependencias.

```bash
pip install .
# o, para desarrollo:
pip install -e .
```

También funciona sin instalar:

```bash
python -m babelcraft convert MiMod.jar -o salida
```

---

## Uso

```bash
babelcraft convert <fuente> -o <carpeta> [opciones]
```

| Opción | Qué hace |
|---|---|
| `-o, --out` | Carpeta de salida (por defecto `babelcraft_out`). |
| `--variant mobile\|desktop` | Perfil de rendimiento: activa atlas y despawn por distancia. `mobile` usa celdas de 32 px y despawn 40; `desktop`, celdas de 64 y despawn 64. |
| `--max-texture PX` | Reduce cada textura para que su lado mayor no pase de `PX` (vecino más próximo, conserva pixel art). |
| `--atlas` / `--no-atlas` | Fuerza o desactiva el atlas de entidades. |
| `--atlas-cell PX` | Lado de cada celda del atlas (0 = automático). |
| `--placeholders` | Genera arte placeholder cuando falte una textura. Sin esta opción, esos ítems/entidades quedan como residuo (no se inventa arte). |
| `--no-thin` | No adelgaza animaciones. |
| `--no-prune` | No poda huesos vacíos de las geometrías. |
| `--no-minify` | Escribe JSON con indentación (más fácil de leer, más pesado al cargar). |
| `--overrides JSON` | Valores que el bytecode no puede dar: comida, durabilidad, dureza, vida... |
| `--lang IDIOMA` | Idioma principal de salida (por defecto `en_US`). |
| `--report RUTA` | Dónde escribir el informe (por defecto `<salida>/REPORT.md`). |

Códigos de salida: `0` si el addon se generó sin errores del validador (puede haber avisos),
`1` si hay errores o la fuente no se pudo leer, `2` si los argumentos son incorrectos.

### API

```python
import babelcraft

conv = babelcraft.convert("MiMod.jar", "salida", variant="mobile", placeholders=True)
print(conv.addon_path)          # .../salida/mimod.mcaddon
print(conv.report_path)         # .../salida/REPORT.md
print(conv.summary())           # cifras: convertidos, adaptados, residuos, errores...
```

### Overrides

Java define dureza, vida, comida o durabilidad en **código**. BabelCraft aplica valores por
defecto razonables y deja fijar los exactos con un JSON:

```json
{
  "items": {
    "mimod:ruby": { "max_stack_size": 16, "food": { "nutrition": 4, "saturation_modifier": 0.3 } }
  },
  "blocks": {
    "mimod:ruby_block": { "seconds_to_destroy": 3.5, "explosion_resistance": 6, "sound": "metal", "light_emission": 7 }
  },
  "entities": {
    "mimod:gob": { "health": 30, "movement": 0.28, "width": 0.7, "height": 1.4 }
  },
  "menu": {
    "mimod:ruby": "items",
    "mimod:ruby_block": "construction"
  }
}
```

En bloques, `"texture": "stone"` reutiliza un shortname de Bedrock (vanilla u otro addon) cuando
la textura Java no tiene equivalente automático.

---

## Qué convierte

| Contenido Java | Destino Bedrock |
|---|---|
| `assets/<ns>/models/item/*.json` | `BP/items/*.json` con `minecraft:icon` shortname y, si es 3D, attachable + geometría + animaciones por hueco. |
| `blockstates/*.json` y `blocks/*.json` (1.21.2+) | `BP/blocks/*.json` (`format_version` 1.21.30) con `material_instances`, caja de colisión medida, loot y `blocks.json`. |
| `data/<ns>/recipe(s)/*.json` | `BP/recipes/*.json`: shaped, shapeless, stonecutter y horno (`furnace`, `blast_furnace`, `smoker`, `campfire`+`soul_campfire`), con `unlock` obligatorio. |
| `data/<ns>/loot_table(s)/*.json` | `BP/loot_tables/<ns>/...` (pools/entries/conditions/functions compatibles). |
| `assets/<ns>/geo` / `models/entity` (GeckoLib) | `RP/models/entity/*.geo.json` + entidad cliente/servidor + huevo de invocación. |
| `assets/<ns>/animations` | `RP/animations/*.animation.json`, conectadas a idle/walk por Molang cuando se pueden identificar. |
| `assets/<ns>/lang/*.json` | `RP/texts/<Idioma>.lang` con las claves de ítem/bloque/entidad traducidas. |
| `assets/<ns>/textures/**/*.png` | `RP/textures/<ns>/...` + `item_texture.json` / `terrain_texture.json`. |
| `assets/<ns>/sounds.json` + `.ogg` | `RP/sounds/sound_definitions.json` + ficheros. |

Target: `min_engine_version [1,21,60]`. Los `format_version` de cada documento son los mínimos
documentados para la característica concreta que se usa, no el máximo disponible. Todo está
centralizado en `babelcraft/versions.py`.

---

## Los tres estados

Cada fichero de entrada acaba en una de tres casillas, y el informe las lista:

- **`converted`** — fiel al original.
- **`adapted`** — convertido con pérdidas documentadas (p. ej. una textura animada recortada a
  su primer fotograma, o un bloque con variantes de estado reducido a su primera variante).
- **`residue`** — sin equivalente fiel; se explica la razón y qué hacer a mano.

Además, el **validador estructural** comprueba la salida contra reglas reales de Bedrock:
JSON válido y sin BOM, manifests con UUIDs correctos, texturas referenciadas que existen,
geometrías/animaciones/render controllers que existen, loot tables que existen, recetas con
`unlock` y patrones coherentes, y los límites de *texture handles*. Un `error` significa que el
addon no cargará bien; un aviso, que funciona con pérdidas.

---

## Pipeline

Por fases deterministas, en este orden (las dependencias van de arriba abajo):

1. `lang` — tablas de idioma (nombres para todo lo demás).
2. `textures` — copia de PNG, recorte de animadas, reducción y registro en los índices.
3. `models` — modelos 3D → geometría Bedrock + attachables.
4. `loot` — loot tables (antes de ítems y bloques, que enganchan su componente `minecraft:loot`).
5. `items` — ítems con evidencia (modelo/lang/bytecode) + overrides.
6. `blocks` — bloques, cubo por defecto o geometría custom, colisión medida del modelo.
7. `recipes` — recetas.
8. `entities` — GeckoLib → Bedrock, con atlas/poda/adelgazado opcionales.
9. `sounds` — definiciones y ficheros.

Cada fase captura sus propios fallos: una no tumba al resto; el fallo se registra como hallazgo.

---

## Optimización de entidades

Con `--atlas` (o cualquier `--variant`):

- Todas las texturas de entidades van a **una imagen** (`RP/textures/entity/atlas.png`).
- Las UV de cada geometría se reescalan a su celda y un render controller con `uv_anim` aplica
  offset/escala por entidad.
- Se escribe el material con `USE_UV_ANIM` (sin él, `uv_anim` no hace nada).
- La poda de huesos y el adelgazado de animaciones quitan trabajo que no se ve, sin cambiar el
  resultado.

Con `--variant mobile` además se activa el despawn por distancia para que las criaturas de chunks
lejanos no sigan consumiendo CPU/RAM.

---

## Límites conocidos (documentados, no silenciosos)

- **Lógica Java** (IA, metas, hechizos, eventos, comandos): requiere la Script API. El conversor
  deja la base física de la criatura y marca el resto.
- **Spawn natural**: no se deduce del código; se configura a mano.
- **Variantes de bloque con estado**: se usa la primera variante y se anota; el mapeo completo a
  `permutations`/estados es trabajo manual.
- **Texturas vanilla en modelos custom**: si el shortname de Bedrock no se deriva del id Java, se
  marca y se resuelve con `--overrides` (`"texture": "..."`).
- **Recetas de horno con tag de entrada**: Bedrock solo admite un ítem en la entrada; se reporta.
- **Sonidos ligados a eventos de entidad**: se definen, pero hay que conectarlos a los eventos.
- **Bytecode**: solo se leen las cadenas del *constant pool* como evidencia de registros. Los ids
  que solo viven en bytecode y no tienen arte/modelo/lang quedan como residuo: convertirlos sería
  inventar su icono.
- **Animaciones de ítems/bloques animados**: Bedrock no soporta tiras verticales en ítems custom;
  se usa el primer fotograma.

---

## Tests

```bash
python -m pytest tests
```

La suite cubre el códec PNG, el lector de `.class`, las utilidades de entidades, los mapeos, la
detección de fuente y el pipeline completo sobre un mod de fixture (ítems planos/en mano/3D,
bloque cubo y multipart, recetas, loot, entidad GeckoLib, sonidos, lang en español y atlas).

---

## Licencia

MIT © The BabelCraft Authors. Ver [LICENSE](LICENSE).

Los mods convertidos conservan la licencia de sus autores: revisa que permitan redistribuir
derivados antes de publicar un addon generado.
