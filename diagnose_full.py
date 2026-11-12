"""Diagnóstico completo de conversión de Cobblemon."""
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

# Crear contexto de conversión
writer = AddonWriter("out/cobblemon_diag_full", mod.namespace, mod.name, mod.version, minify=True)
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

# Verificar archivos en el Behavior Pack
print("\n=== Archivos en Behavior Pack ===")
bp_files = list(writer.bp.keys())
print(f"Total archivos en BP: {len(bp_files)}")

bp_entity_files = [f for f in bp_files if f.startswith("entities/")]
print(f"Archivos de entidad en BP: {len(bp_entity_files)}")
if bp_entity_files:
    print("Primeros 10:")
    for f in bp_entity_files[:10]:
        print(f"  {f}")

# Verificar archivos en el Resource Pack
print("\n=== Archivos en Resource Pack ===")
rp_files = list(writer.rp.keys())
print(f"Total archivos en RP: {len(rp_files)}")

rp_model_files = [f for f in rp_files if f.startswith("models/entity/")]
rp_entity_files = [f for f in rp_files if f.startswith("entity/")]
print(f"Modelos de entidad en RP: {len(rp_model_files)}")
print(f"Definiciones de entidad en RP: {len(rp_entity_files)}")

if rp_model_files:
    print("Primeros 10 modelos:")
    for f in rp_model_files[:10]:
        print(f"  {f}")

# Mostrar estadísticas de conversión
print("\n=== Estadísticas de conversión ===")
converted = [e for e in entity_entries if e.status.value == "converted"]
adapted = [e for e in entity_entries if e.status.value == "adapted"]
residue = [e for e in entity_entries if e.status.value == "residue"]

print(f"Convertidas: {len(converted)}")
print(f"Adaptadas: {len(adapted)}")
print(f"Residuos: {len(residue)}")

if residue:
    print("\nPrimeros 5 residuos:")
    for e in residue[:5]:
        print(f"  {e.path}")
        if hasattr(e, 'notes') and e.notes:
            for note in e.notes[:2]:
                print(f"    - {note}")
