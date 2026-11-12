"""Origen de datos: carpeta, .jar o .zip, con una sola interfaz.

Un mod de Java es un ZIP: `fabric.mod.json` o `META-INF/mods.toml` +
`data/<ns>/...` (datapack) + `assets/<ns>/...` (resourcepack) + `.class`.
Un datapack vanilla es una carpeta con `pack.mcmeta` + `data/`. Un
resourcepack es carpeta con `pack.mcmeta` + `assets/`. Los tres se leen
igual desde aquí.

Detalles que importan:
  - `namespace`: se deduce de los metadatos y de las carpetas `data/` y
    `assets/`; es la pieza que decide qué ids son "del mod" (convertir) y
    cuáles son de terceros (dependencia: reportar).
  - los `.class` se escanean con `javaclass` para evidencia de registros.
  - TOML de Forge se parsea a mano (stdlib no trae tomllib en 3.10; el
    subset de mods.toml es trivial y no merece una dependencia).
"""

from __future__ import annotations

import io
import json
import re
import zipfile

from .javaclass import extract_ids, mentions_any, read_class
from .model import SourceMod


class Source:
    """Lector unificado de carpeta o ZIP."""

    def __init__(self, root: str | dict):
        self.kind = ""
        self._files: list[str] = []
        self._zip: zipfile.ZipFile | None = None
        self._root = ""
        if isinstance(root, dict):
            # En memoria (tests): {"ruta": bytes}
            self.kind = "memoria"
            self._mem = root
            self._files = sorted(root)
            self.read_bytes = self._read_mem
            self.walk = self._walk_mem
            self.exists = self._exists_mem
        else:
            import os

            root = str(root)
            if os.path.isdir(root):
                self.kind = "carpeta"
                self._root = root
                self._files = self._walk_disk(root)
                self.read_bytes = self._read_disk
                self.walk = self._walk_disk_lazy
                self.exists = self._exists_disk
            elif os.path.isfile(root):
                self.kind = "jar/zip"
                self._zip = zipfile.ZipFile(root)
                # testzip() tarda mucho en jars grandes (67s en 135 MB).
                # Si está corrupto, fallará al leer ficheros individuales.
                if os.environ.get("BABELCRAFT_TESTZIP") == "1":
                    bad = self._zip.testzip()
                    if bad is not None:
                        raise ValueError(f"ZIP corrupto en {bad}")
                self._files = sorted(
                    n for n in self._zip.namelist() if not n.endswith("/")
                )
                self.read_bytes = self._read_zip
                self.walk = self._walk_zip
                self.exists = self._exists_zip
            else:
                raise ValueError(f"No existe: {root}")

    # --- API ------------------------------------------------------------

    def read_bytes(self, rel: str) -> bytes:  # type: ignore[misc]
        raise NotImplementedError

    def walk(self) -> list[str]:  # type: ignore[misc]
        raise NotImplementedError

    def exists(self, rel: str) -> bool:  # type: ignore[misc]
        raise NotImplementedError

    def read_json(self, rel: str) -> object:
        return json.loads(self.read_bytes(rel).decode("utf-8-sig"))

    def read_json_or(self, rel: str, default=None):
        try:
            return self.read_json(rel)
        except (KeyError, ValueError, zipfile.BadZipFile, OSError):
            return default

    def glob(self, prefix: str, suffix: str = "") -> list[str]:
        return [f for f in self._files if f.startswith(prefix) and f.endswith(suffix)]

    def copy_all(self, suffixes: tuple[str, ...], exclude_prefixes: tuple[str, ...] = ()) -> list[str]:
        out = []
        for f in self._files:
            if f.endswith(suffixes) and not f.startswith(exclude_prefixes):
                out.append(f)
        return out

    # --- Implementaciones -------------------------------------------------

    def _read_mem(self, rel: str) -> bytes:
        return self._mem[rel]

    def _walk_mem(self) -> list[str]:
        return list(self._files)

    def _exists_mem(self, rel: str) -> bool:
        return rel in self._mem

    def _read_disk(self, rel: str) -> bytes:
        import os

        with open(_join(self._root, rel), "rb") as f:
            return f.read()

    def _walk_disk_lazy(self) -> list[str]:
        return list(self._files)

    def _exists_disk(self, rel: str) -> bool:
        import os

        return os.path.isfile(_join(self._root, rel))

    def _read_zip(self, rel: str) -> bytes:
        assert self._zip is not None
        return self._zip.read(rel)

    def _walk_zip(self) -> list[str]:
        return list(self._files)

    def _exists_zip(self, rel: str) -> bool:
        return rel in self._files

    @staticmethod
    def _walk_disk(root: str) -> list[str]:
        import os

        acc: list[str] = []
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, root).replace("\\", "/")
                acc.append(rel)
        return sorted(acc)


def _join(root: str, rel: str) -> str:
    import os

    return os.path.join(root, *rel.split("/"))


# --------------------------------------------------------------------------
#  Metadatos de loaders
# --------------------------------------------------------------------------

def _parse_mods_toml(text: str) -> dict:
    """Subset de TOML que usa `META-INF/mods.toml` / `neoforge.mods.toml`.

    Solo hace falta [[mods]] y [[dependencies.<id>]]: pares clave=valor y
    algún array de tablas. Sin tipos exóticos.
    """
    data: dict = {}
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[["):
            name = line[2:-2].strip()
            if name == "mods":
                current = {}
                data.setdefault("mods", []).append(current)
            elif name.startswith("dependencies."):
                current = {}
                data.setdefault("dependencies", []).append(current)
            continue
        if line.startswith("["):
            current = None
            continue
        if "=" in line and current is not None:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            current[key] = value
    return data


def detect_loader(src: Source) -> tuple[str, list[str]]:
    loaders: list[str] = []
    if src.exists("fabric.mod.json"):
        loaders.append("fabric")
    if src.exists("META-INF/mods.toml"):
        loaders.append("forge")
    if src.exists("neoforge.mods.toml"):
        loaders.append("neoforge")
    if src.exists("quilt.mod.json"):
        loaders.append("quilt")
    if not loaders and (src.glob("data/") or src.glob("assets/") or src.exists("pack.mcmeta")):
        loaders.append("datapack")
    primary = loaders[0] if loaders else "desconocido"
    return primary, loaders


def load_mod(path_or_source) -> SourceMod:
    """Lee metadatos + bytecode y construye el SourceMod.

    Es la primera fase del pipeline: sin namespace y sin evidencia de
    registros, el resto no puede distinguir contenido propio de ruido.
    """
    src = path_or_source if isinstance(path_or_source, Source) else Source(path_or_source)
    mod = SourceMod(source=src)
    mod.loader, mod.loaders = detect_loader(src)

    # --- Nombre, namespace y versión desde los metadatos.
    explicit_ns = False
    if src.exists("fabric.mod.json") or src.exists("quilt.mod.json"):
        meta = src.read_json_or("fabric.mod.json") or src.read_json_or("quilt.mod.json")
        if isinstance(meta, dict):
            mod.namespace = str(meta.get("id") or mod.namespace)
            mod.name = str(meta.get("name") or mod.namespace)
            mod.version = str(meta.get("version") or mod.version)
            explicit_ns = bool(meta.get("id"))
    elif src.exists("neoforge.mods.toml"):
        data = _parse_mods_toml(src.read_bytes("neoforge.mods.toml").decode("utf-8-sig"))
        _take_forge(mod, data)
        explicit_ns = bool(data.get("mods"))
    elif src.exists("META-INF/mods.toml"):
        data = _parse_mods_toml(src.read_bytes("META-INF/mods.toml").decode("utf-8-sig"))
        _take_forge(mod, data)
        explicit_ns = bool(data.get("mods"))

    # Namespace desde carpetas data/<ns> y assets/<ns> si aún no hay.
    found = set()
    for f in src._files:
        if f.startswith("data/") and f.count("/") >= 2:
            found.add(f.split("/")[1])
        if f.startswith("assets/") and f.count("/") >= 2:
            found.add(f.split("/")[1])
    found.discard("minecraft")
    # Datapack puro (sin metadatos de loader): el namespace ES la carpeta.
    if not explicit_ns and found:
        mod.namespace = sorted(found)[0]
    elif not re.fullmatch(r"[a-z0-9_.-]+", mod.namespace) and found:
        mod.namespace = sorted(found)[0]

    # Nombre legible por defecto: DESPUÉS de resolver el namespace, o un
    # datapack sin metadatos se llamaría "babelcraft" en el informe.
    if mod.name == "":
        mod.name = mod.namespace

    # --- Evidencia del bytecode.
    all_ids: set[str] = set()
    supers: set[str] = set()
    versions: set[int] = set()
    class_strings: list[str] = []
    
    # Filtrar clases por namespace para evitar procesar dependencias embebidas
    class_files = [f for f in src._files if f.endswith(".class")]
    
    # Separar clases del mod de clases de dependencias
    mod_classes = []
    dependency_classes = []
    for f in class_files:
        # Las clases del mod suelen estar en com/<modname>/ o <modname>/
        if f"/{mod.namespace}/" in f.lower() or f.startswith(f"{mod.namespace}/"):
            mod_classes.append(f)
        else:
            dependency_classes.append(f)
    
    # Procesar primero las clases del mod (prioridad alta)
    # Luego agregar algunas clases de dependencias si hay espacio
    MAX_CLASSES = 2000  # Límite razonable para mods grandes
    classes_to_process = mod_classes[:MAX_CLASSES]
    
    # Si hay espacio, agregar algunas clases de dependencias para detectar geckolib
    remaining_slots = MAX_CLASSES - len(classes_to_process)
    if remaining_slots > 0 and dependency_classes:
        classes_to_process.extend(dependency_classes[:remaining_slots])
    
    total_classes = len(class_files)
    processed_classes = 0
    skipped_classes = total_classes - len(classes_to_process)
    
    if skipped_classes > 0:
        print(f"Procesando {len(classes_to_process)} de {total_classes} clases (omitidas {skipped_classes} de dependencias)")
    
    for f in classes_to_process:
        info = read_class(src.read_bytes(f))
        if info is None:
            continue
        processed_classes += 1
        versions.add(info.version)
        class_strings.extend(info.strings)
        all_ids |= extract_ids(info.strings, mod.namespace)
        if info.super_name:
            supers.add(info.super_name)
        mod.mentions_geckolib = mod.mentions_geckolib or mentions_any(
            info.strings, ("geckolib", "software/bernie/geckolib")
        )
    
    if processed_classes != len(classes_to_process):
        print(f"Procesadas {processed_classes} clases válidas de {len(classes_to_process)} intentadas")
    mod.ids_from_bytecode = all_ids
    mod.class_strings = {s for s in class_strings if 0 < len(s) < 64}
    mod.java_version = max(versions) if versions else 0
    own = {i for i in all_ids if i.split(":", 1)[0] == mod.namespace}
    mod.foreign_namespaces = {
        i.split(":", 1)[0] for i in all_ids if i.split(":", 1)[0] not in (mod.namespace, "minecraft")
    }
    # Un mod que usa GeckoLib pero no lo embebe: la dependencia es externa.
    if mod.mentions_geckolib:
        mod.foreign_namespaces.discard("geckolib")

    return mod


def _take_forge(mod: SourceMod, data: dict) -> None:
    mods = data.get("mods") or []
    if mods and isinstance(mods, list):
        first = mods[0]
        mod.namespace = str(first.get("modId") or mod.namespace).lower()
        mod.name = str(first.get("displayName") or first.get("modId") or mod.namespace)
        mod.version = str(first.get("version") or mod.version)
