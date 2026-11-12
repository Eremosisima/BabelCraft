"""Generar addon de Cobblemon con las primeras 20 entidades - CORREGIDO."""
import sys
import json
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from babelcraft.pack import AddonWriter
from babelcraft.source import load_mod
from babelcraft.animkit import sanitize_animations, build_aliases


def convert_items(mod, writer):
    """Convierte items del mod a Bedrock.
    
    Convierte:
    - Pokeballs (todos los tipos)
    - Berries (todas las variedades)
    - Items de batalla (pociones, hierbas, etc.)
    - Items especiales (MTs, piedras evolutivas, etc.)
    """
    ns = mod.namespace
    item_count = 0
    
    # Buscar todos los modelos de items
    for model_path in mod.source.glob("assets/cobblemon/models/item/"):
        if not model_path.endswith(".json"):
            continue
        
        # Extraer nombre del item
        item_name = model_path.split("/")[-1].replace(".json", "")
        
        # Leer modelo
        try:
            model_data = mod.source.read_json(model_path)
        except:
            continue
        
        # Determinar tipo de item
        item_def = {
            "format_version": "1.16.100",
            "minecraft:item": {
                "description": {
                    "identifier": f"cobblemon:{item_name}",
                    "category": "items"
                },
                "components": {
                    "minecraft:max_stack_size": 64
                }
            }
        }
        
        # Configurar componentes específicos según el tipo de item
        if "pokeball" in item_name.lower() or "ball" in item_name.lower():
            item_def["minecraft:item"]["components"]["minecraft:max_stack_size"] = 64
            item_def["minecraft:item"]["components"]["minecraft:hand_equipped"] = True
        elif "berry" in item_name.lower():
            item_def["minecraft:item"]["components"]["minecraft:food"] = {
                "nutrition": 2,
                "saturation_modifier": "low"
            }
            item_def["minecraft:item"]["components"]["minecraft:max_stack_size"] = 64
        
        # Escribir definición del item en BP
        writer.bp_json(f"items/cobblemon_{item_name}.json", item_def)
        
        # Buscar textura del item
        tex_found = False
        for tex_path in mod.source.glob("assets/cobblemon/textures/item/"):
            if tex_path.endswith(f"{item_name}.png"):
                tex_data = mod.source.read_bytes(tex_path)
                writer.rp_blob(f"textures/items/cobblemon/{item_name}.png", tex_data)
                
                # Registrar en item_texture.json
                writer.add_item_texture(f"cobblemon_{item_name}", f"textures/items/cobblemon/{item_name}")
                
                # Crear modelo de item para el RP
                item_model = {
                    "format_version": "1.16.100",
                    "minecraft:item_model": {
                        "description": {
                            "identifier": f"cobblemon:{item_name}",
                            "texture": f"cobblemon_{item_name}"
                        }
                    }
                }
                writer.rp_json(f"models/item/cobblemon_{item_name}.json", item_model)
                
                tex_found = True
                item_count += 1
                break
        
        if not tex_found:
            # Intentar con nombres alternativos
            alt_names = [
                item_name.replace("_model", ""),
                item_name.replace("_cast", ""),
            ]
            for alt_name in alt_names:
                if alt_name == item_name:
                    continue
                for tex_path in mod.source.glob("assets/cobblemon/textures/item/"):
                    if tex_path.endswith(f"{alt_name}.png"):
                        tex_data = mod.source.read_bytes(tex_path)
                        writer.rp_blob(f"textures/items/cobblemon/{item_name}.png", tex_data)
                        writer.add_item_texture(f"cobblemon_{item_name}", f"textures/items/cobblemon/{item_name}")
                        
                        item_model = {
                            "format_version": "1.16.100",
                            "minecraft:item_model": {
                                "description": {
                                    "identifier": f"cobblemon:{item_name}",
                                    "texture": f"cobblemon_{item_name}"
                                }
                            }
                        }
                        writer.rp_json(f"models/item/cobblemon_{item_name}.json", item_model)
                        
                        item_count += 1
                        tex_found = True
                        break
                if tex_found:
                    break
    
    print(f"  [OK] Items convertidos: {item_count}")


def generate_limited_addon(max_entities=20):
    """Genera un addon con las primeras N entidades de Cobblemon."""
    jar_path = "out/cobbleverse/Cobblemon-fabric-1.7.3+1.21.1.jar"
    out_dir = "out/cobblemon_limited_v2"
    
    print(f"Cargando mod desde {jar_path}...")
    mod = load_mod(jar_path)
    print(f"[OK] Mod cargado: {mod.name}")
    
    # Crear writer
    writer = AddonWriter(out_dir, mod.namespace, mod.name, mod.version, minify=True)
    
    # Buscar las primeras N entidades
    print(f"\nBuscando las primeras {max_entities} entidades...")
    entity_paths = []
    for path in mod.source.glob("assets/cobblemon/bedrock/pokemon/models/"):
        if path.endswith(".geo.json") and len(entity_paths) < max_entities:
            # Extraer nombre de la entidad del path
            # Formato: assets/cobblemon/bedrock/pokemon/models/0001_bulbasaur/bulbasaur.geo.json
            parts = path.split("/")
            if len(parts) >= 2:
                entity_name = parts[-1].replace(".geo.json", "")
                entity_paths.append((path, entity_name))
    
    print(f"[OK] Encontradas {len(entity_paths)} entidades")
    
    # Procesar cada entidad
    for i, (entity_path, entity_name) in enumerate(entity_paths, 1):
        print(f"\n[{i}/{len(entity_paths)}] Procesando {entity_name}...")
        
        # Leer geometría y preservar el identifier original
        geo_data = mod.source.read_json(entity_path)
        
        # Preservar el identifier original de la geometría
        geometry_identifier = None
        if "minecraft:geometry" in geo_data and geo_data["minecraft:geometry"]:
            first_geo = geo_data["minecraft:geometry"][0]
            if "description" in first_geo and "identifier" in first_geo["description"]:
                geometry_identifier = first_geo["description"]["identifier"]
        
        if not geometry_identifier:
            # Fallback: usar el nombre esperado
            geometry_identifier = f"geometry.cobblemon_{entity_name}"
            print(f"  [WARN] Usando identifier fallback: {geometry_identifier}")
        else:
            print(f"  [OK] Geometry identifier: {geometry_identifier}")
        
        # Buscar archivo de animación
        anim_path = None
        for path in mod.source.glob("assets/cobblemon/bedrock/pokemon/animations/"):
            if path.endswith(f"/{entity_name}.animation.json"):
                anim_path = path
                break
        
        has_animations = False
        anim_names = []
        sanitized_animations = None
        if anim_path:
            try:
                anim_data = mod.source.read_json(anim_path)
                if "animations" in anim_data:
                    # Sanitizar animaciones para eliminar queries inválidos
                    notes = []
                    sanitized_animations = sanitize_animations(anim_data, notes)
                    
                    if sanitized_animations and "animations" in sanitized_animations:
                        anim_names = list(sanitized_animations["animations"].keys())
                        has_animations = True
                        print(f"  [OK] Animaciones sanitizadas: {len(anim_names)}")
                        if notes:
                            print(f"  [INFO] Notas de sanitización:")
                            for note in notes[:3]:  # Mostrar solo las primeras 3
                                print(f"    - {note}")
                    else:
                        print(f"  [WARN] No se pudieron sanitizar las animaciones")
            except Exception as e:
                print(f"  [ERROR] Error al procesar animaciones: {e}")
        
        # Crear definición de entidad (BP) con componentes de comportamiento
        entity_def = {
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
                    "minecraft:collision_box": {"width": 0.6, "height": 0.6},
                    "minecraft:movement": {"value": 0.25},
                    "minecraft:movement.basic": {},
                    "minecraft:jump.static": {},
                    "minecraft:navigation.walk": {
                        "can_path_over_water": False,
                        "avoid_water": True,
                        "avoid_damage_blocks": True
                    },
                    "minecraft:behavior.float": {
                        "priority": 0
                    },
                    "minecraft:behavior.random_stroll": {
                        "priority": 6,
                        "speed_multiplier": 0.6
                    },
                    "minecraft:behavior.look_at_player": {
                        "priority": 7,
                        "look_distance": 6.0,
                        "probability": 0.02
                    },
                    "minecraft:behavior.random_look_around": {
                        "priority": 8
                    },
                    "minecraft:type_family": {
                        "family": [entity_name, "mob"]
                    }
                }
            }
        }
        
        # Escribir en BP (ruta entities/ en plural)
        bp_path = f"entities/cobblemon_{entity_name}.entity.json"
        writer.bp_json(bp_path, entity_def)
        
        # Crear spawn rule básica
        spawn_rule = {
            "format_version": "1.8.0",
            "minecraft:spawn_rules": {
                "description": {
                    "identifier": f"cobblemon:{entity_name}",
                    "population_control": "animal"
                },
                "conditions": [
                    {
                        "minecraft:spawns_on_surface": {},
                        "minecraft:brightness_filter": {
                            "min": 7,
                            "max": 15,
                            "adjust_for_weather": True
                        },
                        "minecraft:weight": {
                            "default": 10
                        },
                        "minecraft:herd": {
                            "min_size": 1,
                            "max_size": 3
                        },
                        "minecraft:biome_filter": {
                            "test": "has_biome_tag",
                            "operator": "==",
                            "value": "overworld"
                        }
                    }
                ]
            }
        }
        spawn_path = f"spawn_rules/cobblemon_{entity_name}.json"
        writer.bp_json(spawn_path, spawn_rule)
        
        # Escribir geometría en RP
        rp_geo_path = f"models/entity/cobblemon_{entity_name}.geo.json"
        writer.rp_json(rp_geo_path, geo_data)
        
        # Copiar animación sanitizada si existe
        if has_animations and sanitized_animations:
            rp_anim_path = f"animations/cobblemon_{entity_name}.animation.json"
            writer.rp_json(rp_anim_path, sanitized_animations)
        
        # Crear render controller específico para esta entidad
        rc_def = {
            "format_version": "1.10.0",
            "render_controllers": {
                f"controller.render.cobblemon_{entity_name}": {
                    "geometry": "Geometry.default",
                    "materials": [{"*": "Material.default"}],
                    "textures": ["Texture.default"]
                }
            }
        }
        rc_path = f"render_controllers/cobblemon_{entity_name}.render_controllers.json"
        writer.rp_json(rc_path, rc_def)
        
        # Crear cliente entity definition (RP) con animaciones
        client_def = {
            "format_version": "1.10.0",
            "minecraft:client_entity": {
                "description": {
                    "identifier": f"cobblemon:{entity_name}",
                    "materials": {"default": "entity_alphatest"},
                    "textures": {"default": f"textures/entity/cobblemon/{entity_name}"},
                    "geometry": {"default": geometry_identifier},
                    "render_controllers": [f"controller.render.cobblemon_{entity_name}"]
                }
            }
        }
        
        # Agregar animaciones si existen
        if has_animations and sanitized_animations:
            # NO filtrar animaciones - la sanitización ya reemplazó queries inválidos
            # Solo verificar que las animaciones referenciadas existan
            all_anims = {}
            for anim_name in anim_names:
                # Extraer nombre corto (ej: "animation.bulbasaur.walk" -> "walk")
                short_name = anim_name.split(".")[-1]
                all_anims[short_name] = anim_name
            
            if all_anims:
                client_def["minecraft:client_entity"]["description"]["animations"] = all_anims
                
                # Crear scripts para reproducir animaciones automáticamente
                # Solo referenciar animaciones que EXISTEN en el archivo
                scripts = {"animate": []}
                
                # Animación de caminar cuando se mueve
                # Buscar variantes: walk, ground_walk, run, etc.
                walk_anims = ["walk", "ground_walk", "run", "ground_run"]
                for walk_anim in walk_anims:
                    if walk_anim in all_anims:
                        scripts["animate"].append({walk_anim: "query.modified_move_speed > 0.01"})
                        break
                
                # Animación idle cuando está quieto
                # Buscar variantes: idle, ground_idle, stand, etc.
                idle_anims = ["idle", "ground_idle", "stand", "ground_stand"]
                for idle_anim in idle_anims:
                    if idle_anim in all_anims:
                        scripts["animate"].append({idle_anim: "query.modified_move_speed <= 0.01"})
                        break
                
                # Animación de parpadeo aleatoria (solo si existe)
                if "blink" in all_anims:
                    scripts["animate"].append({"blink": "math.random(0, 100) < 0.5"})
                
                # Animación de llanto aleatoria (solo si existe)
                if "cry" in all_anims:
                    scripts["animate"].append({"cry": "math.random(0, 200) < 0.3"})
                
                # Animación de respiración/idle alternativo
                if "breath" in all_anims:
                    scripts["animate"].append({"breath": "query.modified_move_speed <= 0.01"})
                
                # Animación de render (pose por defecto)
                if "render" in all_anims:
                    scripts["animate"].append({"render": "1.0"})
                
                if scripts["animate"]:
                    client_def["minecraft:client_entity"]["description"]["scripts"] = scripts
                    print(f"  [OK] Animaciones configuradas: {len(all_anims)} disponibles, {len(scripts['animate'])} auto-reproducidas")
        rp_entity_path = f"entity/cobblemon_{entity_name}.entity.json"
        writer.rp_json(rp_entity_path, client_def)
        
        # Copiar textura si existe (buscar con prefijo numérico)
        # Estructura real: assets/cobblemon/textures/pokemon/0001_bulbasaur/bulbasaur.png
        tex_path = None
        for path in mod.source.glob("assets/cobblemon/textures/pokemon/"):
            if path.endswith(".png") and not path.endswith("_shiny.png") and not path.endswith("_female.png") and not path.endswith("_male.png"):
                # Extraer nombre del archivo sin prefijo numérico
                tex_name = path.split("/")[-1].replace(".png", "")
                if tex_name == entity_name:
                    tex_path = path
                    break
        
        if tex_path:
            tex_data = mod.source.read_bytes(tex_path)
            writer.rp_blob(f"textures/entity/cobblemon/{entity_name}.png", tex_data)
            print(f"  [OK] Textura copiada: {tex_path}")
        else:
            print(f"  [WARN] Textura no encontrada para {entity_name}")
    
    # === CONVERSIÓN DE ITEMS ===
    print(f"\n=== Convirtiendo items ===")
    convert_items(mod, writer)
    
    # Generar addon
    print(f"\nGenerando addon...")
    addon_path = writer.finalize()
    print(f"[OK] Addon generado: {addon_path}")
    
    # Verificar contenido
    if Path(addon_path).exists():
        with zipfile.ZipFile(addon_path, 'r') as zf:
            bp_files = [f for f in zf.namelist() if f.startswith('BP_')]
            rp_files = [f for f in zf.namelist() if f.startswith('RP_')]
            
            print(f"\nContenido del addon:")
            print(f"  Archivos en BP: {len(bp_files)}")
            print(f"  Archivos en RP: {len(rp_files)}")
            
            bp_entities = [f for f in bp_files if '/entities/' in f]
            print(f"\n  Entidades en BP (ruta 'entities/'): {len(bp_entities)}")
            if len(bp_entities) > 0:
                print(f"    Lista de entidades:")
                for f in bp_entities:
                    print(f"      - {f}")
            else:
                print("    [ERROR] No se encontraron entidades en BP!")
    
    return addon_path

if __name__ == "__main__":
    try:
        addon_path = generate_limited_addon(max_entities=20)
        print(f"\n[OK] Addon generado exitosamente: {addon_path}")
    except Exception as e:
        print(f"\n[ERROR] Error generando addon: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def convert_items(mod, writer):
    """Convierte items del mod a Bedrock.
    
    Convierte:
    - Pokeballs (todos los tipos)
    - Berries (todas las variedades)
    - Items de batalla (pociones, hierbas, etc.)
    - Items especiales (MTs, piedras evolutivas, etc.)
    """
    ns = mod.namespace
    item_count = 0
    
    # Buscar todos los modelos de items
    for model_path in mod.source.glob("assets/cobblemon/models/item/"):
        if not model_path.endswith(".json"):
            continue
        
        # Extraer nombre del item
        item_name = model_path.split("/")[-1].replace(".json", "")
        
        # Leer modelo
        try:
            model_data = mod.source.read_json(model_path)
        except:
            continue
        
        # Determinar tipo de item
        item_def = {
            "format_version": "1.16.100",
            "minecraft:item": {
                "description": {
                    "identifier": f"cobblemon:{item_name}",
                    "category": "items"
                },
                "components": {
                    "minecraft:max_stack_size": 64
                }
            }
        }
        
        # Configurar componentes específicos según el tipo de item
        if "pokeball" in item_name.lower() or "ball" in item_name.lower():
            item_def["minecraft:item"]["components"]["minecraft:max_stack_size"] = 64
            item_def["minecraft:item"]["components"]["minecraft:hand_equipped"] = True
        elif "berry" in item_name.lower():
            item_def["minecraft:item"]["components"]["minecraft:food"] = {
                "nutrition": 2,
                "saturation_modifier": "low"
            }
            item_def["minecraft:item"]["components"]["minecraft:max_stack_size"] = 64
        
        # Escribir definición del item en BP
        writer.bp_json(f"items/cobblemon_{item_name}.json", item_def)
        
        # Buscar textura del item
        tex_found = False
        for tex_path in mod.source.glob("assets/cobblemon/textures/item/"):
            if tex_path.endswith(f"{item_name}.png"):
                tex_data = mod.source.read_bytes(tex_path)
                writer.rp_blob(f"textures/items/cobblemon/{item_name}.png", tex_data)
                
                # Registrar en item_texture.json
                writer.add_item_texture(f"cobblemon_{item_name}", f"textures/items/cobblemon/{item_name}")
                
                # Crear modelo de item para el RP
                item_model = {
                    "format_version": "1.16.100",
                    "minecraft:item_model": {
                        "description": {
                            "identifier": f"cobblemon:{item_name}",
                            "texture": f"cobblemon_{item_name}"
                        }
                    }
                }
                writer.rp_json(f"models/item/cobblemon_{item_name}.json", item_model)
                
                tex_found = True
                item_count += 1
                break
        
        if not tex_found:
            # Intentar con nombres alternativos
            alt_names = [
                item_name.replace("_model", ""),
                item_name.replace("_cast", ""),
            ]
            for alt_name in alt_names:
                if alt_name == item_name:
                    continue
                for tex_path in mod.source.glob("assets/cobblemon/textures/item/"):
                    if tex_path.endswith(f"{alt_name}.png"):
                        tex_data = mod.source.read_bytes(tex_path)
                        writer.rp_blob(f"textures/items/cobblemon/{item_name}.png", tex_data)
                        writer.add_item_texture(f"cobblemon_{item_name}", f"textures/items/cobblemon/{item_name}")
                        
                        item_model = {
                            "format_version": "1.16.100",
                            "minecraft:item_model": {
                                "description": {
                                    "identifier": f"cobblemon:{item_name}",
                                    "texture": f"cobblemon_{item_name}"
                                }
                            }
                        }
                        writer.rp_json(f"models/item/cobblemon_{item_name}.json", item_model)
                        
                        item_count += 1
                        tex_found = True
                        break
                if tex_found:
                    break
    
    print(f"  [OK] Items convertidos: {item_count}")
