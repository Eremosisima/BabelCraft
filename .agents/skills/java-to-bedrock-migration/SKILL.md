---
name: java-to-bedrock-migration
description: Migra contenido de Minecraft Java (mods, resource packs, datapacks y modpacks como Cobbleverse) a addons de Bedrock usando BabelCraft, con merge por procedencia, validación, iteración y documentación de residuos. Úsala cuando el usuario pida convertir un mod/pack/modpack Java a Bedrock, depurar un .mcaddon generado, o mejorar cobertura/mecánicas del conversor.
---

# Java → Bedrock Migration Skill

## Objetivo
Convertir contenido Java a Bedrock de forma fiel cuando sea posible, adaptada cuando sea necesario, y explícitamente residual cuando no exista equivalente portable.

## Cuándo usarla
- Conversión de `.jar`, `.zip`, carpeta de mod/datapack/resource pack o modpack (mrpack/overrides).
- Depuración de errores en Bedrock (Molang, animaciones, referencias rotas, T-pose, texturas faltantes, items no funcionales).
- Mejora de Cobblemon/Cobbleverse u otros packs con mecánicas parciales (poké balls, ítems, spawns, assets).

## Entradas y contexto a recolectar
- Fuente(s): rutas a jar/zip/carpeta/mrpack, overrides, RPs/DPs, descargas.
- Identidad esperada: namespace/modid/nombre/versión.
- Restricciones: alcance (solo base, pack completo), tiempo, rendimiento (mobile/desktop), y nivel de fidelidad de mecánicas.
- Evidencia runtime: content log de Bedrock, capturas/errores reportados.

## Flujo de trabajo

### 1) Inventario y grafo de procedencia
- Identificar todos los orígenes y su prioridad de overlay (base → overrides → descargas → extras).
- Construir/actualizar un grafo o inventario: `fuente -> tipo de contenido -> destino/uso -> estado esperado`.
- En modpacks, detectar archivos disponibles localmente vs. referenciados por índice.

### 2) Descargas y seguridad (si aplica)
- Descargar solo desde orígenes confiables (p.ej. CDN oficial del índice).
- Verificar hashes (SHA-512/SHA-1) y tamaño; descartar archivos inválidos.
- Priorizar contenido relevante para conversión (assets/datos/ecosistema) sobre mods de rendimiento/UI.

### 3) Merge de fuentes
- Fusionar `assets/` y `data/` preservando orden de precedencia.
- Forzar metadatos de identidad cuando haya múltiples namespaces para evitar detección errónea.
- Registrar qué capas aportaron contenido (trazabilidad).

### 4) Conversión (BabelCraft)
- Ejecutar conversión base (`python -m babelcraft convert <source> -o <out>` o script especializado).
- Usar opciones según objetivo: `--atlas`, `--variant`, `--placeholders` (solo si se desea), `--overrides`.
- Para modpacks complejos, usar scripts de merge dedicados (ej. `convert_cobbleverse.py`).

### 5) Validación y diagnóstico
- Revisar `REPORT.md` y resumen (`converted/adapted/residue/errors/warnings`).
- Construir/actualizar grafos de:
  - **Cobertura** (qué se convirtió y qué no, por causa)
  - **Referencias** (animaciones, geometrías, texturas, controllers, lang, spawn/loot)
- Correlacionar errores del validador con content log de Bedrock.

### 6) Correcciones e iteración
- **Molang/animaciones**: sanitizar queries no soportadas, expresiones malformadas, `catmullrom` con datos no constantes, y eliminar animaciones vacías.
- **Refs rotas**: alinear nombres/ids, evitar colisiones de archivos (p.ej. attachable vs entity animations), asegurar controllers/render controllers.
- **Ítems/Poké Balls**: mejorar resolución de texturas (`layer0`, subcarpetas), clasificación de componentes y mecánicas aproximadas (lanzables/consumibles) sin fingir captura/lógica completa.
- **Entidades/spawn**: verificar rutas `entities/` (BP) vs `entity/` (RP), spawn rules y componentes mínimos.
- Reconvertir tras cambios; repetir validación/pruebas.

### 7) Persistencia de conocimiento
- Actualizar grafo de procedencia/estado, learnings y limitaciones.
- Documentar decisiones, parches aplicados y próximos pasos para futuras migraciones.

## Heurísticas y aprendizajes clave
- T-pose: suele ser animación no encontrada/no referenciada, script de animación roto o controller inconsistente.
- Muchos errores de Molang vienen de reemplazos parciales que dejan expresiones truncadas; validar forma final.
- Attachables y entidades pueden colisionar por nombre de archivo; separar rutas/archivos de animación.
- En modpacks, la identidad detectada puede ser incorrecta si hay múltiples namespaces; forzar metadatos de merge.
- Descargas “relevantes y verificadas” mejoran cobertura más que descargar todo el índice sin criterio.

## Límites esperados (declarar explícitamente)
- Lógica Java, IA avanzada, batallas/captura real, GUIs, economía, y gran parte de worldgen/estructuras NBT no son portables automáticamente.
- Poké Balls/ítems pueden ser funcionales de forma aproximada; mecánicas completas requieren Script API, entidades dedicadas y sistemas adicionales.

## Entregables mínimos
- `.mcaddon` y/o BP/RP generados
- `REPORT.md` (cobertura, adaptaciones, residuos, errores/warnings)
- Grafo/inventario actualizado (procedencia y estado)
- Notas de learnings y limitaciones para la siguiente iteración
