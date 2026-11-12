import zipfile
import json

jar_path = 'out/cobbleverse/Cobblemon-fabric-1.7.3+1.21.1.jar'
print(f'Abriendo {jar_path}...')

with zipfile.ZipFile(jar_path) as zf:
    paths = zf.namelist()
    print(f'Total archivos: {len(paths)}')
    
    # Contar geometrías de Cobblemon
    cobblemon_geo = [p for p in paths if 'bedrock/pokemon/models' in p and p.endswith('.geo.json')]
    print(f'Geometrías pokemon: {len(cobblemon_geo)}')
    
    # Contar texturas de pokemon
    pokemon_tex = [p for p in paths if 'textures/pokemon' in p and p.endswith('.png')]
    print(f'Texturas pokemon: {len(pokemon_tex)}')
    
    # Verificar un bulbasaur específico
    bulbasaur_geo = [p for p in paths if 'bulbasaur' in p and p.endswith('.geo.json')]
    bulbasaur_tex = [p for p in paths if 'bulbasaur' in p and p.endswith('.png')]
    
    print(f'\nBulbasaur:')
    print(f'  Geometrías: {len(bulbasaur_geo)}')
    if bulbasaur_geo:
        print(f'    Primera: {bulbasaur_geo[0]}')
    print(f'  Texturas: {len(bulbasaur_tex)}')
    if bulbasaur_tex:
        print(f'    Primera: {bulbasaur_tex[0]}')
    
    # Leer una geometría de ejemplo
    if bulbasaur_geo:
        print(f'\n=== Leyendo geometría de bulbasaur ===')
        geo_data = json.loads(zf.read(bulbasaur_geo[0]))
        print(f'Keys: {list(geo_data.keys())}')
        if 'minecraft:geometry' in geo_data:
            geom = geo_data['minecraft:geometry']
            if isinstance(geom, list) and geom:
                desc = geom[0].get('description', {})
                print(f'Description keys: {list(desc.keys())}')
                if 'texture' in desc:
                    print(f'Textura declarada: {desc["texture"]}')
