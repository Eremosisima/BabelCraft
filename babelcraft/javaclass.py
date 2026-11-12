"""Lector mínimo de ficheros `.class` de Java (solo el constant pool).

Por qué: los ítems y bloques de un mod de Java se registran en **bytecode**
(`Registry.register(...)`), no en JSON. Sin leer el bytecode no hay forma de
saber qué contenido existe realmente, y convertir "todo lo que aparezca en
un lang" produce entidades e ítems fantasma.

Qué extraemos (y qué no):
  - Extraemos: todas las cadenas UTF-8 del constant pool y el nombre de la
    clase. De ahí salen los ids con namespace que el código menciona
    (`modid:ruby`), las referencias a APIs (GeckoLib) y nombres de clase.
  - No extraemos: el flujo de ejecución. Emparejar `register(...)` con su
    argumento exigiría un analizador de bytecode completo. En su lugar, el
    conjunto de ids del bytecode se cruza con la evidencia JSON (lang,
    modelos, blockstates, recetas, tags): un id se declara solo cuando hay
    segunda prueba independiente. Un id que solo vive en el bytecode queda
    listado en el informe como evidencia sin salida.

Formato referencia: JVM Spec §4.1 (ClassFile) y §4.4 (Constant Pool).
"""

from __future__ import annotations

import struct

# Tamaños de las entradas del constant pool, en bytes que siguen al tag.
# CONSTANT_Utf8 y las referencias (Class, String, ...) llevan u2 de más.
_SIZES = {
    1: 2,   # Utf8: length u2
    3: 4,   # Integer: u4
    4: 4,   # Float: u4
    5: 8,   # Long: u8 (¡ocupa 2 huecos del pool!)
    6: 8,   # Double: u8 (¡ocupa 2 huecos del pool!)
    7: 2,   # Class: name_index u2
    8: 2,   # String: string_index u2
    9: 4,   # Fieldref: u2 u2
    10: 4,  # Methodref: u2 u2
    11: 4,  # InterfaceMethodref: u2 u2
    12: 4,  # NameAndType: u2 u2
    15: 3,  # MethodHandle: u1 u2
    16: 2,  # MethodType: u2
    17: 4,  # Dynamic: u2 u2
    18: 4,  # InvokeDynamic: u2 u2
    19: 2,  # Module: u2
    20: 2,  # Package: u2
}

_NS_ID_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_-.:/")


class ClassInfo:
    """Lo que se puede leer de un .class sin descompilar."""

    __slots__ = ("name", "strings", "super_name", "interfaces", "version")

    def __init__(self, name: str, strings: list[str], super_name: str, interfaces: list[str], version: int):
        self.name = name  # nombre interno, con / (p.ej. com/ejemplo/ModRuby)
        self.strings = strings  # todas las cadenas UTF-8 del pool
        self.super_name = super_name
        self.interfaces = interfaces
        self.version = version  # major version de la clase


def class_ref(pool: list, buf: bytes, pos: int, count: int) -> str:
    """Lee un u2 (índice al pool) en `pos` y lo resuelve a nombre de clase."""
    try:
        (idx,) = struct.unpack(">H", buf[pos : pos + 2])
    except struct.error:
        return ""
    v = pool[idx] if 0 < idx < count else None
    if isinstance(v, tuple) and v[0] == "idx" and isinstance(pool[v[1]], str):
        return pool[v[1]]
    return ""


def read_class(buf: bytes) -> ClassInfo | None:
    """Parsea un .class. None si no es una clase válida o no se entiende."""
    if len(buf) < 10 or buf[:4] != b"\xCA\xFE\xBA\xBE":
        return None
    minor, major = struct.unpack(">HH", buf[4:8])
    (count,) = struct.unpack(">H", buf[8:10])

    pool: list = [None] * count  # índice 1..count-1
    p = 10
    i = 1
    try:
        while i < count:
            tag = buf[p]
            size = _SIZES.get(tag)
            if size is None:
                return None  # tag desconocido: mejor rendirse que corromper
            if tag == 1:
                (ln,) = struct.unpack(">H", buf[p + 1 : p + 3])
                raw = buf[p + 3 : p + 3 + ln]
                try:
                    pool[i] = raw.decode("utf-8", "replace")
                except Exception:
                    pool[i] = ""
                p += 3 + ln
            else:
                if tag in (7, 8, 19, 20):
                    # Guardamos el índice u2 para resolverlo después.
                    pool[i] = ("idx", struct.unpack(">H", buf[p + 1 : p + 3])[0])
                elif tag == 15:
                    # MethodHandle: u1 (kind) + u2 (index) tras el tag.
                    pool[i] = ("mh", buf[p + 1], struct.unpack(">H", buf[p + 2 : p + 4])[0])
                p += 1 + size
            i += 2 if tag in (5, 6) else 1  # long/double ocupan dos huecos
    except (struct.error, IndexError):
        return None

    def utf(idx: int) -> str:
        v = pool[idx] if 0 < idx < count else None
        return v if isinstance(v, str) else ""

    # Acceder a la clase (this_class), la superclase y las interfaces.
    # Ojo: entre el pool y this_class va access_flags (u2, JVM Spec §4.1).
    try:
        (this_idx,) = struct.unpack(">H", buf[p + 2 : p + 4])
        (super_idx,) = struct.unpack(">H", buf[p + 4 : p + 6])
        (if_count,) = struct.unpack(">H", buf[p + 6 : p + 8])
    except struct.error:
        return None
    interfaces = [class_ref(pool, buf, p + 8 + 2 * k, count) for k in range(if_count)]

    def class_name(idx: int) -> str:
        v = pool[idx] if 0 < idx < count else None
        if isinstance(v, tuple) and v[0] == "idx" and isinstance(pool[v[1]], str):
            return pool[v[1]]
        return ""

    strings = [s for s in pool if isinstance(s, str)]
    return ClassInfo(class_name(this_idx), strings, class_name(super_idx), interfaces, major)


def extract_ids(strings: list[str], namespace: str) -> set[str]:
    """Ids con namespace `ns:id` mencionados por el código de un mod.

    Reglas:
      - solo minúsculas y caracteres válidos de id (ni espacios ni acentos);
      - se ignoran los de `minecraft:` (referencias a vanilla) salvo que el
        propio mod sea de ese namespace (caso datapack puro);
      - los de otros namespaces se ignoran aquí (dependencias); el informe
        los lista aparte.
    """
    out: set[str] = set()
    for s in strings:
        if not s or len(s) > 96 or ":" not in s:
            continue
        if not _NS_ID_CHARS.issuperset(s):
            continue
        ns, _, path = s.partition(":")
        if not ns or not path or ns == "java":
            continue
        if ns == "minecraft" and namespace != "minecraft":
            continue
        out.add(s)
    return out


def mentions_any(strings: list[str], needles: tuple[str, ...]) -> bool:
    """¿El pool de constantes menciona alguna de estas cadenas?"""
    return any(n in s for s in strings for n in needles)
