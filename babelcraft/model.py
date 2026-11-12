"""Modelo central: el mod de Java leído, el resultado de la conversión y
el libro de cuentas del que cuelga todo el informe.

Filosofía (heredada de LuaCraft): **nunca fingir**. Cada fichero de entrada
acaba en una de tres casillas — `converted` (fiel), `adapted` (convertido
con pérdidas documentadas) o `residue` (sin equivalente, con la razón
exacta y qué hacer a mano). Nada se descarta en silencio.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum


class Kind(str, Enum):
    """Tipo de contenido que representa un fichero de entrada."""

    ITEM = "item"
    BLOCK = "block"
    ENTITY = "entity"
    RECIPE = "recipe"
    LOOT_TABLE = "loot_table"
    LANG = "lang"
    TEXTURE = "texture"
    MODEL = "model"
    SOUND = "sound"
    TAG = "tag"
    ANIMATION = "animation"
    GEOMETRY = "geometry"
    ADVANCEMENT = "advancement"
    WORLDGEN = "worldgen"
    STRUCTURE = "structure"
    FUNCTION = "function"
    METADATA = "metadata"
    BYTECODE = "bytecode"
    OTHER = "other"


class Status(str, Enum):
    CONVERTED = "converted"  # fiel al original
    ADAPTED = "adapted"      # convertido con pérdidas (ver notes)
    RESIDUE = "residue"      # sin equivalente directo en Bedrock


@dataclass
class Entry:
    """Un fichero de entrada y su destino en la conversión."""

    path: str                 # ruta relativa dentro del jar/carpeta
    kind: Kind
    status: Status = Status.RESIDUE
    notes: list[str] = field(default_factory=list)  # qué se perdió / qué hacer

    def note(self, msg: str) -> None:
        if msg not in self.notes:
            self.notes.append(msg)


@dataclass
class Finding:
    """Un problema detectado por el validador sobre la SALIDA."""

    severity: str  # "error" | "warn" | "info"
    code: str      # p.ej. "ref.texture_missing"
    path: str      # fichero del addon afectado
    message: str


@dataclass
class Overrides:
    """Valores que el bytecode no puede dar y el usuario ajusta a mano.

    Java define dureza, vida, comida o durabilidad en código; traducirlos
    exigiría descompilar. En su lugar el conversor aplica defaults
    razonables y este fichero (opcional, `--overrides overrides.json`)
    deja fijar los valores exactos sacados del código fuente del mod.
    """

    items: dict = field(default_factory=dict)     # "ns:id" -> {"max_stack_size": .., "food": {...}, ...}
    blocks: dict = field(default_factory=dict)   # "ns:id" -> {"seconds_to_destroy": .., ...}
    entities: dict = field(default_factory=dict) # "ns:id" -> {"health": .., "width": .., ...}
    menu: dict = field(default_factory=dict)     # "ns:id" -> "construction" | "items" | "nature" | ...

    @staticmethod
    def load(path: str) -> "Overrides":
        import json
        import os

        o = Overrides()
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for key in ("items", "blocks", "entities", "menu"):
                if isinstance(data.get(key), dict):
                    setattr(o, key, data[key])
        return o

    def item(self, ident: str) -> dict:
        return self.items.get(ident, {})

    def block(self, ident: str) -> dict:
        return self.blocks.get(ident, {})

    def entity(self, ident: str) -> dict:
        return self.entities.get(ident, {})


@dataclass
class SourceMod:
    """Un mod de Java (o un datapack+resourcepack) ya leído."""

    source: "Source"                 # lector (carpeta o zip)
    namespace: str = "babelcraft"     # namespace principal del mod
    name: str = ""                    # nombre legible
    version: str = "1.0.0"
    loader: str = "desconocido"      # fabric | forge | neoforge | datapack
    loaders: list = field(default_factory=list)
    java_version: int = 0            # major de los .class (8, 17, 21...)
    class_strings: set = field(default_factory=set)     # ids ns:id del bytecode
    mentions_geckolib: bool = False
    ids_from_bytecode: set = field(default_factory=set)  # ids totales (todas las ns)
    foreign_namespaces: set = field(default_factory=set)


@dataclass
class ConversionResult:
    """El libro de cuentas: entradas + hallazgos del validador."""

    entries: list[Entry] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    identifiers: set = field(default_factory=set)  # ids custom emitidos (ns:id)

    def entry(self, path: str, kind: Kind) -> Entry:
        for e in self.entries:
            if e.path == path:
                return e
        e = Entry(path=path, kind=kind)
        self.entries.append(e)
        return e

    def converted(self, path: str, kind: Kind, notes: list[str] | None = None) -> Entry:
        e = self.entry(path, kind)
        e.status = Status.CONVERTED if e.status is not Status.ADAPTED else Status.ADAPTED
        for n in notes or []:
            e.note(n)
        return e

    def adapted(self, path: str, kind: Kind, note: str) -> Entry:
        e = self.entry(path, kind)
        e.status = Status.ADAPTED
        e.note(note)
        return e

    def residue(self, path: str, kind: Kind, reason: str) -> Entry:
        e = self.entry(path, kind)
        if e.status in (Status.CONVERTED, Status.ADAPTED):
            # El fichero se convirtió en parte; el resto queda explicado.
            e.status = Status.ADAPTED
            e.note(reason)
        else:
            e.status = Status.RESIDUE
            e.note(reason)
        return e

    def error(self, code: str, path: str, message: str) -> None:
        self.findings.append(Finding("error", code, path, message))

    def warn(self, code: str, path: str, message: str) -> None:
        self.findings.append(Finding("warn", code, path, message))

    def info(self, code: str, path: str, message: str) -> None:
        self.findings.append(Finding("info", code, path, message))

    def coverage(self) -> dict[str, dict[str, int]]:
        """Tabla kind -> {converted, adapted, residue, total}."""
        table: dict[str, dict[str, int]] = {}
        for e in self.entries:
            row = table.setdefault(e.kind.value, {"converted": 0, "adapted": 0, "residue": 0, "total": 0})
            row[e.status.value] += 1
            row["total"] += 1
        return table


_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def slug(name: str) -> str:
    """Nombre de fichero/identificador seguro para Bedrock (a-z0-9_).

    Los acentos se pliegan a ASCII (Vacío -> vacio, no vac_o): los nombres
    de fichero del addon viajan por rutas de Windows/zip donde lo no-ASCII
    es fuente de problemas, y un nombre ilegible rompe la trazaabilidad
    del informe.
    """
    folded = unicodedata.normalize("NFKD", name.lower())
    ascii_folded = "".join(c for c in folded if not unicodedata.combining(c))
    s = _SLUG_RE.sub("_", ascii_folded).strip("_")
    return s or "x"
