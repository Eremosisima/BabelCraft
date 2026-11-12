"""Interfaz base para conversores de mecánicas específicas de mods."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..model import SourceMod
from ..pack import AddonWriter


@dataclass
class MechanicsContext:
    mod: SourceMod
    writer: AddonWriter
    namespace: str = ""
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.namespace:
            self.namespace = getattr(self.mod, "namespace", "") or "custom"

    def note(self, msg: str) -> None:
        self.notes.append(msg)


@runtime_checkable
class MechanicsConverter(Protocol):
    """Conversor opcional para mecánicas no declarativas/específicas."""

    id: str
    name: str

    def matches(self, mod: SourceMod) -> bool:
        """Devuelve True si este conversor aplica al mod."""
        ...

    def convert(self, ctx: MechanicsContext) -> None:
        """Aplica conversiones/artefactos específicos al addon."""
        ...


_REGISTRY: list[MechanicsConverter] = []


def register(converter: MechanicsConverter) -> None:
    for i, existing in enumerate(_REGISTRY):
        if getattr(existing, "id", None) == getattr(converter, "id", None):
            _REGISTRY[i] = converter
            return
    _REGISTRY.append(converter)


def converters() -> list[MechanicsConverter]:
    return list(_REGISTRY)


def detect_mechanics(mod: SourceMod) -> list[MechanicsConverter]:
    return [c for c in _REGISTRY if c.matches(mod)]
