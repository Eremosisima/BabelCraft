"""Diagnóstico simple: convertir 3 entidades usando la API pública."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import babelcraft

# Cargar el mod
jar_path = "out/cobbleverse/Cobblemon-fabric-1.7.3+1.21.1.jar"
print(f"Convirtiendo mod desde {jar_path}...")
print("Limitando a 3 entidades de prueba...")

# Convertir con opciones mínimas
try:
    conv = babelcraft.convert(
        jar_path,
        "out/cobblemon_test_simple",
        variant="",  # sin atlas
        placeholders=False,
        minify=True,
    )
    
    print(f"\nConversión completada")
    print(f"  Namespace: {conv.mod.namespace}")
    print(f"  Addon: {conv.addon_path}")
    print(f"  Archivos en BP: {len(conv.writer.bp)}")
    print(f"  Archivos en RP: {len(conv.writer.rp)}")
    
    # Verificar archivos de entidad en BP
    bp_entity_files = [f for f in conv.writer.bp.keys() if f.startswith("entities/")]
    print(f"\nArchivos de entidad en BP: {len(bp_entity_files)}")
    if bp_entity_files:
        print("Primeros 5:")
        for f in bp_entity_files[:5]:
            print(f"  {f}")
    else:
        print("[ERROR] No hay archivos de entidad en BP!")
        
    # Verificar archivos de entidad en RP
    rp_entity_files = [f for f in conv.writer.rp.keys() if f.startswith("entity/")]
    rp_model_files = [f for f in conv.writer.rp.keys() if f.startswith("models/entity/")]
    print(f"\nArchivos de entidad en RP: {len(rp_entity_files)}")
    print(f"Modelos de entidad en RP: {len(rp_model_files)}")
    
    # Verificar el addon generado
    import zipfile
    if conv.addon_path and Path(conv.addon_path).exists():
        print(f"\nVerificando addon: {conv.addon_path}")
        with zipfile.ZipFile(conv.addon_path, 'r') as zf:
            bp_files = [f for f in zf.namelist() if f.startswith('BP_')]
            rp_files = [f for f in zf.namelist() if f.startswith('RP_')]
            
            print(f"  Archivos en BP del addon: {len(bp_files)}")
            print(f"  Archivos en RP del addon: {len(rp_files)}")
            
            bp_entity_in_addon = [f for f in bp_files if '/entities/' in f]
            print(f"  Archivos de entidad en BP del addon: {len(bp_entity_in_addon)}")
            
            if bp_entity_in_addon:
                print("\nPrimeros 5 archivos de entidad en BP del addon:")
                for f in bp_entity_in_addon[:5]:
                    print(f"  {f}")
            else:
                print("\n[ERROR] BP del addon está vacío de entidades!")
                
except Exception as e:
    print(f"\n[ERROR] Fallo en conversión: {e}")
    import traceback
    traceback.print_exc()
