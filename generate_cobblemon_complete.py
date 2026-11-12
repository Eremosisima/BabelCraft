"""Generar addon completo de Cobblemon con todas las entidades."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import babelcraft

def generate_cobblemon_addon():
    """Genera un addon completo de Cobblemon con todas las entidades."""
    jar_path = "out/cobbleverse/Cobblemon-fabric-1.7.3+1.21.1.jar"
    out_dir = "out/cobblemon_complete"
    
    print(f"Convirtiendo mod desde {jar_path}...")
    print("Esto puede tardar varios minutos...")
    
    # Usar la API pública de BabelCraft
    conv = babelcraft.convert(
        jar_path,
        out_dir,
        variant="",  # sin atlas para esta prueba
        placeholders=False,
        minify=True,
    )
    
    print(f"\n[OK] Conversión completada")
    print(f"  Namespace: {conv.mod.namespace}")
    print(f"  Addon: {conv.addon_path}")
    print(f"  Errores: {len(conv.errors)}")
    print(f"  Advertencias: {len(conv.warnings)}")
    
    # Verificar contenido
    import zipfile
    if Path(conv.addon_path).exists():
        with zipfile.ZipFile(conv.addon_path, 'r') as zf:
            bp_files = [f for f in zf.namelist() if f.startswith('BP_')]
            rp_files = [f for f in zf.namelist() if f.startswith('RP_')]
            
            print(f"\nContenido del addon:")
            print(f"  Archivos en BP: {len(bp_files)}")
            print(f"  Archivos en RP: {len(rp_files)}")
            
            bp_entities = [f for f in bp_files if '/entities/' in f]
            print(f"\n  Entidades en BP (ruta 'entities/'): {len(bp_entities)}")
            if len(bp_entities) > 0:
                print(f"    Primeras 10 entidades:")
                for f in bp_entities[:10]:
                    print(f"      - {f}")
                if len(bp_entities) > 10:
                    print(f"    ... y {len(bp_entities) - 10} más")
            else:
                print("    [ERROR] No se encontraron entidades en BP!")
    
    return conv.addon_path

if __name__ == "__main__":
    try:
        addon_path = generate_cobblemon_addon()
        print(f"\n[OK] Addon generado exitosamente: {addon_path}")
    except Exception as e:
        print(f"\n[ERROR] Error generando addon: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
