"""Test rápido: verificar que bp_json() escribe en la ruta correcta entities/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from babelcraft.pack import AddonWriter

# Crear un writer de prueba
print("Creando AddonWriter de prueba...")
writer = AddonWriter("out/test_bp_path", "test", "Test Mod", "1.0.0", minify=True)

# Probar bp_json() con la ruta correcta entities/
print("\nProbando bp_json() con ruta entities/...")
test_data = {
    "format_version": "1.16.0",
    "minecraft:entity": {
        "description": {
            "identifier": "test:test_entity",
            "is_spawnable": True,
            "is_summonable": True
        },
        "components": {
            "minecraft:health": {"value": 20, "max": 20}
        }
    }
}

writer.bp_json("entities/test_entity.json", test_data)
print(f"Archivos en BP después de bp_json(): {len(writer.bp)}")
print(f"Claves en BP: {list(writer.bp.keys())}")

if "entities/test_entity.json" in writer.bp:
    print("[OK] Archivo de entidad escrito en BP con ruta correcta 'entities/'")
else:
    print("[ERROR] Archivo de entidad NO escrito en BP")

# Finalizar y verificar
print("\nFinalizando addon...")
try:
    addon_path = writer.finalize()
    print(f"[OK] Addon generado: {addon_path}")
    
    # Verificar contenido del addon
    import zipfile
    if Path(addon_path).exists():
        with zipfile.ZipFile(addon_path, 'r') as zf:
            bp_files = [f for f in zf.namelist() if f.startswith('BP_')]
            
            print(f"\nArchivos en BP del addon: {len(bp_files)}")
            for f in bp_files:
                print(f"  {f}")
            
            # Verificar específicamente el archivo de entidad
            bp_entity_files = [f for f in bp_files if 'entities/' in f]
            print(f"\nArchivos de entidad en BP del addon: {len(bp_entity_files)}")
            if bp_entity_files:
                print("[OK] Archivos de entidad presentes en BP del addon con ruta 'entities/'")
            else:
                print("[ERROR] Archivos de entidad AUSENTES en BP del addon")
    else:
        print("[ERROR] Addon no generado")
        
except Exception as e:
    print(f"[ERROR] Fallo al finalizar: {e}")
    import traceback
    traceback.print_exc()
