"""Diagnóstico simplificado: convertir solo 3 entidades."""
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
writer = AddonWriter("out/cobblemon_test_3", mod.namespace, mod.name, mod.version, minify=True)
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

# Probar conversión manual de 3 entidades
print("\n=== Convirtiendo 3 entidades manualmente ===")
test_entities = [
    ("assets/cobblemon/bedrock/pokemon/models/0001_bulbasaur/bulbasaur.geo.json", "bulbasaur"),
    ("assets/cobblemon/bedrock/pokemon/models/0004_charmander/charmander.geo.json", "charmander"),
    ("assets/cobblemon/bedrock/pokemon/models/0007_squirtle/squirtle.geo.json", "squirtle"),
]

records = []
for path, name in test_entities:
    print(f"\nProcesando {name}...")
    if mod.source.exists(path):
        print(f"  [OK] Modelo encontrado")
        try:
            rec = entities._build_entity(ctx, path, name)
            if rec:
                print(f"  [OK] Entidad construida")
                print(f"    Key: {rec['key']}")
                print(f"    Texture: {rec['tex_path']}")
                records.append(rec)
            else:
                print(f"  [ERROR] Entidad no construida (retornó None)")
        except Exception as e:
            print(f"  [ERROR] Excepción: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"  [ERROR] Modelo no encontrado")

print(f"\n=== Total entidades construidas: {len(records)} ===")

# Escribir las entidades
if records:
    print("\n=== Escribiendo entidades ===")
    try:
        entities._write_without_atlas(ctx, records)
        print(f"[OK] Entidades escritas")
    except Exception as e:
        print(f"[ERROR] Excepción al escribir: {e}")
        import traceback
        traceback.print_exc()
    
    # Verificar archivos en el Behavior Pack
    print("\n=== Archivos en Behavior Pack ===")
    bp_files = list(writer.bp.keys())
    print(f"Total archivos en BP: {len(bp_files)}")
    
    bp_entity_files = [f for f in bp_files if f.startswith("entities/")]
    print(f"Archivos de entidad en BP: {len(bp_entity_files)}")
    if bp_entity_files:
        print("Archivos:")
        for f in bp_entity_files:
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
        print("Modelos:")
        for f in rp_model_files[:5]:
            print(f"  {f}")
else:
    print("\n[ERROR] No hay entidades para escribir")
