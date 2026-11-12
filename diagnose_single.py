"""Diagnóstico rápido de conversión de entidades para Cobblemon."""
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
writer = AddonWriter("out/cobblemon_diag3", mod.namespace, mod.name, mod.version, minify=True)
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
cobblemon_geo_paths = []
for path in mod.source.glob(cobblemon_prefix):
    if path.endswith(".geo.json") and "/models/" in path:
        cobblemon_geo_count += 1
        if len(cobblemon_geo_paths) < 5:
            cobblemon_geo_paths.append(path)
print(f"Geometrías en layout Cobblemon: {cobblemon_geo_count}")
if cobblemon_geo_paths:
    print("Primeras 5:")
    for p in cobblemon_geo_paths:
        print(f"  {p}")

# Probar conversión de una sola entidad
print("\n=== Probando conversión de bulbasaur ===")
bulbasaur_path = "assets/cobblemon/bedrock/pokemon/models/0001_bulbasaur/bulbasaur.geo.json"
if mod.source.exists(bulbasaur_path):
    print(f"[OK] Modelo encontrado: {bulbasaur_path}")
    
    # Leer la geometría
    geo_data = mod.source.read_json(bulbasaur_path)
    print(f"Geometría cargada, keys: {list(geo_data.keys())}")
    
    # Intentar construir la entidad
    try:
        rec = entities._build_entity(ctx, bulbasaur_path, "bulbasaur")
        if rec:
            print(f"[OK] Entidad construida exitosamente")
            print(f"  Name: {rec['name']}")
            print(f"  Ident: {rec['ident']}")
            print(f"  Key: {rec['key']}")
            print(f"  Geometry ID: {rec['geometry_id']}")
            print(f"  Texture path: {rec['tex_path']}")
            print(f"  Notes: {rec['notes']}")
        else:
            print(f"[ERROR] Entidad no construida (retornó None)")
    except Exception as e:
        print(f"[ERROR] Error construyendo entidad: {e}")
        import traceback
        traceback.print_exc()
else:
    print(f"[ERROR] Modelo no encontrado: {bulbasaur_path}")

# Verificar si hay errores en el resultado
print("\n=== Errores en resultado ===")
errors = [e for e in result.entries if e.severity == "error"]
print(f"Total errores: {len(errors)}")
if errors:
    for e in errors[:10]:
        print(f"  {e.path}: {e.message}")
