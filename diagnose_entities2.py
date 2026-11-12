"""Diagnóstico de conversión de entidades para Cobblemon."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from babelcraft.source import load_mod
from babelcraft.converters import Options, Ctx
from babelcraft.pack import AddonWriter
from babelcraft.model import ConversionResult, Overrides
from babelcraft.converters import entities

# Abrir el jar
jar_path = "out/cobbleverse/Cobblemon-fabric-1.7.3+1.21.1.jar"
print(f"Abriendo {jar_path}...")

# Cargar el mod
mod = load_mod(jar_path)
print(f"Mod cargado: {mod.name} v{mod.version}")
print(f"Namespace: {mod.namespace}")
print(f"Loader: {mod.loader}")

# Crear contexto de conversión
writer = AddonWriter("out/cobblemon_diag2", mod.namespace, mod.name, mod.version, minify=True)
result = ConversionResult()
overrides = Overrides()
opts = Options()

ctx = Ctx(
    mod=mod,
    writer=writer,
    result=result,
    overrides=overrides,
    opts=opts,
)

# Contar geometrías disponibles
print("\n=== Contando geometrías ===")
geo_count = 0
for fmt in ("assets/{}/geo", "assets/{}/models/entity", "assets/{}/geckolib/models"):
    prefix = fmt.format(mod.namespace) + "/"
    for path in mod.source.glob(prefix):
        if path.endswith(".json"):
            geo_count += 1
print(f"Geometrías en layouts estándar: {geo_count}")

# Contar geometrías de Cobblemon
cobblemon_prefix = f"assets/{mod.namespace}/bedrock/"
cobblemon_geo_count = 0
for path in mod.source.glob(cobblemon_prefix):
    if path.endswith(".geo.json") and "/models/" in path:
        cobblemon_geo_count += 1
print(f"Geometrías en layout Cobblemon: {cobblemon_geo_count}")

# Ejecutar conversión de entidades
print("\n=== Ejecutando conversión de entidades ===")
try:
    entities.convert(ctx)
    print(f"Conversión completada")
except Exception as e:
    print(f"Error durante conversión: {e}")
    import traceback
    traceback.print_exc()

# Contar resultados
print("\n=== Resultados ===")
entity_entries = [e for e in result.entries if e.kind.value == "entity"]
print(f"Total de entradas de entidad: {len(entity_entries)}")

converted = [e for e in entity_entries if e.status.value == "converted"]
adapted = [e for e in entity_entries if e.status.value == "adapted"]
residue = [e for e in entity_entries if e.status.value == "residue"]

print(f"Convertidas: {len(converted)}")
print(f"Adaptadas: {len(adapted)}")
print(f"Residuos: {len(residue)}")

# Mostrar primeros 5 residuos
if residue:
    print("\n=== Primeros 5 residuos ===")
    for e in residue[:5]:
        print(f"  {e.path}")
        for note in e.notes:
            print(f"    - {note}")

# Contar archivos en el Behavior Pack
print("\n=== Archivos en Behavior Pack ===")
bp_entity_files = [f for f in writer.bp.keys() if f.startswith("entities/")]
print(f"Archivos de entidad en BP: {len(bp_entity_files)}")
if bp_entity_files:
    print("Primeros 5:")
    for f in bp_entity_files[:5]:
        print(f"  {f}")

# Contar archivos en el Resource Pack
print("\n=== Archivos en Resource Pack ===")
rp_model_files = [f for f in writer.rp.keys() if f.startswith("models/entity/")]
rp_entity_files = [f for f in writer.rp.keys() if f.startswith("entity/")]
print(f"Modelos de entidad en RP: {len(rp_model_files)}")
print(f"Definiciones de entidad en RP: {len(rp_entity_files)}")

if rp_model_files:
    print("Primeros 5 modelos:")
    for f in rp_model_files[:5]:
        print(f"  {f}")
