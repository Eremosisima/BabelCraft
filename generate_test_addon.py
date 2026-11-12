"""Generar addon de prueba con 3 entidades de Cobblemon."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from babelcraft.pack import AddonWriter
from babelcraft.source import load_mod
from babelcraft.converters.entities import convert

def generate_test_addon():
    """Genera un addon con solo 3 entidades de prueba."""
    # Cargar el mod
    jar_path = "out/cobbleverse/Cobblemon-fabric-1.7.3+1.21.1.jar"
    print(f"Cargando mod desde {jar_path}...")
    mod = load_mod(jar_path)
    print(f"[OK] Mod cargado: {mod.name}")
    
    # Crear writer
    out_dir = "out/cobblemon_test_3entities"
    writer = AddonWriter(out_dir, mod.namespace, mod.name, mod.version, minify=True)
    
    # Definir las 3 entidades de prueba
    test_entities = [
        "assets/cobblemon/bedrock/pokemon/models/0001_bulbasaur/bulbasaur.geo.json",
        "assets/cobblemon/bedrock/pokemon/models/0004_charmander/charmander.geo.json",
        "assets/cobblemon/bedrock/pokemon/models/0007_squirtle/squirtle.geo.json",
    ]
    
    print(f"\nConvirtiendo {len(test_entities)} entidades...")
    
    # Convertir cada entidad
    for entity_path in test_entities:
        entity_name = Path(entity_path).stem
        print(f"  Procesando {entity_name}...")
        
        # Leer geometría
        if not mod.source.exists(entity_path):
            print(f"    [ERROR] Modelo no encontrado: {entity_path}")
            continue
        
        geo_data = mod.source.read_json(entity_path)
        
        # Crear datos mínimos de entidad
        entity_data = {
            "format_version": "1.16.0",
            "minecraft:entity": {
                "description": {
                    "identifier": f"cobblemon:{entity_name}",
                    "is_spawnable": True,
                    "is_summonable": True
                },
                "components": {
                    "minecraft:health": {"value": 20, "max": 20},
                    "minecraft:physics": {},
                    "minecraft:pushable": {"is_pushable": True, "is_pushable_by_piston": True},
                    "minecraft:collision_box": {"width": 0.6, "height": 0.6}
                }
            }
        }
        
        # Escribir entidad en BP (entities/ en plural)
        writer.bp[f"entities/cobblemon_{entity_name}.entity.json"] = json.dumps(entity_data, separators=(",", ":")).encode("utf-8")
        print(f"    [OK] Entidad escrita en BP: entities/cobblemon_{entity_name}.entity.json")
        
        # Escribir geometría en RP
        writer.rp[f"models/entity/cobblemon_{entity_name}.geo.json"] = json.dumps(geo_data, separators=(",", ":")).encode("utf-8")
        print(f"    [OK] Geometría escrita en RP: models/entity/cobblemon_{entity_name}.geo.json")
        
        # Crear cliente entity definition
        client_entity = {
            "format_version": "1.10.0",
            "minecraft:client_entity": {
                "description": {
                    "identifier": f"cobblemon:{entity_name}",
                    "materials": {"default": "entity_alphatest"},
                    "textures": {"default": f"textures/entity/cobblemon/{entity_name}"},
                    "geometry": {"default": f"geometry.cobblemon_{entity_name}"},
                    "render_controllers": ["controller.render.default"]
                }
            }
        }
        writer.rp[f"entity/cobblemon_{entity_name}.entity.json"] = json.dumps(client_entity, separators=(",", ":")).encode("utf-8")
        print(f"    [OK] Cliente entity escrito en RP: entity/cobblemon_{entity_name}.entity.json")
    
    # Generar addon
    print(f"\nGenerando addon...")
    addon_path = writer.finalize()
    print(f"[OK] Addon generado: {addon_path}")
    
    # Verificar contenido
    import zipfile
    if Path(addon_path).exists():
        with zipfile.ZipFile(addon_path, 'r') as zf:
            bp_files = [f for f in zf.namelist() if f.startswith('BP_')]
            rp_files = [f for f in zf.namelist() if f.startswith('RP_')]
            
            print(f"\nContenido del addon:")
            print(f"  Archivos en BP: {len(bp_files)}")
            print(f"  Archivos en RP: {len(rp_files)}")
            
            bp_entities = [f for f in bp_files if '/entities/' in f]
            print(f"\n  Entidades en BP (ruta 'entities/'): {len(bp_entities)}")
            for f in bp_entities:
                print(f"    - {f}")
    
    return addon_path

if __name__ == "__main__":
    try:
        addon_path = generate_test_addon()
        print(f"\n[OK] Addon generado exitosamente: {addon_path}")
    except Exception as e:
        print(f"\n[ERROR] Error generando addon: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
