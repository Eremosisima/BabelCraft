"""Versiones objetivo de Bedrock, centralizadas.

Elección (nov 2026): apuntar a Bedrock 1.21.60 como `min_engine_version`
porque es la línea donde items y bloques data-driven son **estables**
(sin experimentos) y cualquiera con 1.21.60+ lo ejecuta. Los
`format_version` de cada documento son los mínimos documentados para cada
característica concreta que usamos, no el máximo disponible: menos
superficie, menos roturas entre versiones.

Cambiar de objetivo es tocar este fichero y nada más.
"""

# Manifest del pack (BP y RP).
MANIFEST_FORMAT = 2
MIN_ENGINE = [1, 21, 60]

# Documentos
ITEM = "1.20.10"          # icon string + menú, componentes estables
ITEM_HELD = "1.20.30"     # mínimo documentado para minecraft:hand_equipped
BLOCK = "1.21.30"         # traits + material_instances + transformation
RECIPE = "1.20.10"        # tags con datos y unlock; furnace con varias tags

# Los loot tables de Bedrock no llevan format_version: son JSON plano
# (pools/entries). Esta constante existe solo para documentarlo.
LOOT_TABLE = None

CLIENT_ENTITY = "1.10.0"  # formato clásico, probado en CobblemonBedrock
SERVER_ENTITY = "1.16.0"  # ídem
GEOMETRY = "1.12.0"       # per-face UV; 1.16.0 cuando hay binding (attachables)
ANIMATION = "1.8.0"       # animaciones de attachable
ATTACHABLE = "1.10.0"
SOUND_DEFINITIONS = "1.14.0"
RENDER_CONTROLLER = "1.10.0"
MATERIAL = "1.10.0"

# Categorías del menú creativo válidas en Bedrock.
MENU_CATEGORIES = {"construction", "nature", "equipment", "items", "none"}
