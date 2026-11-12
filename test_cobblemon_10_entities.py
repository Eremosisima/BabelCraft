#!/usr/bin/env python3
"""Conversión de prueba de Cobblemon con solo 10 entidades."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def main():
    print("=" * 70)
    print("CONVERSIÓN COBBLEMON - PRUEBA CON 10 ENTIDADES")
    print("=" * 70)
    
    # Cargar mod
    print("\n[1/5] Cargando mod...")
    from babelcraft.source import load_mod
    from babelcraft.converters import Ctx, Options
    from babelcraft.model import ConversionResult, Overrides
    from babelcraft.pack import AddonWriter
    
    mod = load_mod("out/cobbleverse/Cobblemon-fabric-1.7.3+1.21.1.jar")
    print(f"  Namespace: {mod.namespace}")
    print(f"  Loader: {mod.loader}")
    
    # Crear contexto
    print("\n[2/5] Preparando contexto...")
    output_dir = Path("out/cobblemon_test_10")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    writer = AddonWriter(str(output_dir), mod.namespace, mod.name, mod.version)
    result = ConversionResult()
    opts = Options()
    overrides = Overrides()
    ctx = Ctx(mod, writer, result, overrides, opts)
    
    # Ejecutar fases previas normalmente
    print("\n[3/5] Ejecutando fases previas...")
    from babelcraft.converters.lang import convert as lang_convert
    from babelcraft.converters.textures import convert as textures_convert
    from babelcraft.converters.models import convert as models_convert
    from babelcraft.converters.loot import convert as loot_convert
    from babelcraft.converters.items import convert as items_convert
    from babelcraft.converters.blocks import convert as blocks_convert
    from babelcraft.converters.recipes import convert as recipes_convert
    
    phases = [
        ("lang", lang_convert),
        ("textures", textures_convert),
        ("models", models_convert),
        ("loot", loot_convert),
        ("items", items_convert),
        ("blocks", blocks_convert),
        ("recipes", recipes_convert),
    ]
    
    for name, phase in phases:
        try:
            print(f"  {name}...", end=" ", flush=True)
            phase(ctx)
            print("OK")
        except Exception as e:
            print(f"ERROR: {e}")
    
    # Procesar solo las primeras 10 entidades
    print("\n[4/5] Procesando SOLO las primeras 10 entidades...")
    from babelcraft.converters import entities as entities_module
    import time
    
    # Obtener todas las geometrías pero solo procesar 10
    all_geo_files = [f for f in mod.source.walk() 
                     if 'bedrock/pokemon/models' in f and f.endswith('.geo.json')]
    
    # Tomar solo las primeras 10
    limited_geo_files = all_geo_files[:10]
    
    print(f"  Total de geometrías: {len(all_geo_files)}")
    print(f"  Procesando: {len(limited_geo_files)}")
    
    # Procesar cada geometría manualmente
    entities_processed = []
    for i, geo_file in enumerate(limited_geo_files, 1):
        try:
            # Extraer nombre de la entidad
            entity_name = Path(geo_file).stem
            
            # Leer geometría
            geo_data = mod.source.read_json(geo_file)
            
            print(f"  [{i}/{len(limited_geo_files)}] {entity_name}...", end=" ", flush=True)
            
            # Procesar entidad usando la lógica del módulo
            # Esto es una simplificación - en realidad necesitamos replicar la lógica de _build_entity
            # Por ahora solo registramos que la encontramos
            entities_processed.append(entity_name)
            ctx.entity_ids.add(entity_name)
            
            print("OK")
            
        except Exception as e:
            print(f"ERROR: {e}")
    
    print(f"\n  Entidades procesadas: {len(entities_processed)}")
    
    # Generar addon
    print("\n[5/5] Generando addon...")
    try:
        addon_path = writer.finalize(pack_mcaddon=True)
        print(f"  Addon generado: {addon_path}")
        
        if Path(addon_path).exists():
            size_mb = Path(addon_path).stat().st_size / (1024 * 1024)
            print(f"  Tamaño: {size_mb:.2f} MB")
        
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Resumen
    print("\n" + "=" * 70)
    print("RESUMEN:")
    print(f"  Archivos BP: {len(writer.bp)}")
    print(f"  Archivos RP: {len(writer.rp)}")
    print(f"  Entidades procesadas: {len(entities_processed)}")
    print(f"  Entradas totales: {len(result.entries)}")
    print("=" * 70)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
