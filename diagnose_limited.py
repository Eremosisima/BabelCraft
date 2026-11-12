"""Diagnóstico: convertir 3 entidades y generar addon completo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from babelcraft.core.source import Source
from babelcraft.core.converter import ConversionContext
from babelcraft.converters import entities

# Cargar el mod
jar_path = "out/cobbleverse/Cobblemon-fabric-1.7.3+1.21.1.jar"
print(f"Cargando mod desde {jar_path}...")
source = Source(jar_path)
ctx = ConversionContext(source, "out/cobblemon_test_limited", {})

# Filtrar solo 3 entidades de prueba
test_entities = [
    "assets/cobblemon/bedrock/pokemon/models/0001_bulbasaur/bulbasaur.geo.json",
    "assets/cobblemon/bedrock/pokemon/models/0004_charmander/charmander.geo.json",
    "assets/cobblemon/bedrock/pokemon/models/0007_squirtle/squirtle.geo.json",
]

print(f"\nProcesando {len(test_entities)} entidades de prueba...")
for path in test_entities:
    if source.exists(path):
        try:
            entities._process_entity(ctx, path)
            print(f"  [OK] {path}")
        except Exception as e:
            print(f"  [ERROR] {path}: {e}")
    else:
        print(f"  [NOT FOUND] {path}")

print("\nVerificando archivos en writer...")
print(f"  Archivos en BP: {len(ctx.writer.bp)}")
print(f"  Archivos en RP: {len(ctx.writer.rp)}")

if ctx.writer.bp:
    print("\nArchivos en BP:")
    for path in sorted(ctx.writer.bp.keys()):
        print(f"  {path}")

print("\nGenerando addon...")
try:
    addon_path = ctx.writer.finalize()
    print(f"[OK] Addon generado: {addon_path}")
    
    # Verificar contenido del addon
    import zipfile
    with zipfile.ZipFile(addon_path, 'r') as zf:
        bp_files = [f for f in zf.namelist() if f.startswith('BP_')]
        rp_files = [f for f in zf.namelist() if f.startswith('RP_')]
        
        print(f"\nContenido del addon:")
        print(f"  Archivos en BP: {len(bp_files)}")
        print(f"  Archivos en RP: {len(rp_files)}")
        
        if bp_files:
            print("\nArchivos en BP del addon:")
            for f in sorted(bp_files)[:10]:
                print(f"  {f}")
        else:
            print("\n[ERROR] BP está vacío en el addon!")
            
except Exception as e:
    print(f"[ERROR] Fallo al generar addon: {e}")
    import traceback
    traceback.print_exc()
