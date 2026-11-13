"""Analizador estático ligero para expresiones Molang.

Objetivo: validar sintaxis básica, detectar patrones incompatibles y
producir una forma sanitizada segura para Bedrock cuando sea posible.

No es un parser completo de todas las extensiones de Molang, pero cubre
los casos más comunes en animaciones convertidas (aritmética, funciones,
llamadas query/math/variable, condicionales simples, comparaciones).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

# Prefijos/queries que suelen no ser portables desde mods Java (Cobblemon, etc.)
INVALID_QUERY_PREFIXES = (
    "q.r.",
    "query.r.",
    "q.input_",
    "query.input_",
)

INVALID_QUERY_NAMES = {
    "q.has_entity",
    "query.has_entity",
    "q.is_riding",
    "query.is_riding",
    "q.is_being_ridden",
    "query.is_being_ridden",
    "q.sound",
    "query.sound",
    "q.anim_progress",
    "query.anim_progress",
}

_TOKEN_RE = re.compile(
    r"""
    (?P<WS>\s+)
  | (?P<NUMBER>(?:\d+\.\d*|\.\d+|\d+))
  | (?P<IDENT>[A-Za-z_][A-Za-z0-9_.]*)
  | (?P<STRING>'[^']*'|"[^"]*")
  | (?P<OP>>=|<=|==|!=|&&|\|\||[+\-*/%<>!?=,:;])
  | (?P<PAREN>[(){}\[\]])
  | (?P<UNKNOWN>.)
    """,
    re.VERBOSE,
)


@dataclass
class MolangAnalysis:
    source: str
    valid: bool
    sanitized: str
    issues: list[str] = field(default_factory=list)
    unsupported_queries: list[str] = field(default_factory=list)
    tokens: list[tuple[str, str]] = field(default_factory=list)


def tokenize(expr: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    for m in _TOKEN_RE.finditer(expr):
        kind = m.lastgroup or "UNKNOWN"
        value = m.group(0)
        if kind == "WS":
            continue
        tokens.append((kind, value))
    return tokens


def _has_balanced_delimiters(tokens: Iterable[tuple[str, str]]) -> bool:
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    opens = set(pairs.values())
    for kind, val in tokens:
        if kind != "PAREN":
            continue
        if val in opens:
            stack.append(val)
        elif val in pairs:
            if not stack or stack[-1] != pairs[val]:
                return False
            stack.pop()
    return not stack


def _detect_unsupported(expr: str) -> list[str]:
    found: list[str] = []
    low = expr.lower()
    for name in INVALID_QUERY_NAMES:
        if name in low:
            found.append(name)
    # prefijos/dinámicos
    for m in re.finditer(r"\b(?:q|query)\.(?:r|input_)[a-z0-9_]*(?:\s*\([^)]*\))?", expr, re.IGNORECASE):
        found.append(m.group(0))
    # dedupe preservando orden
    seen = set()
    out = []
    for x in found:
        xl = x.lower()
        if xl not in seen:
            seen.add(xl)
            out.append(x)
    return out


def _strip_invalid_queries(expr: str) -> str:
    out = expr
    # llamadas/patrones comunes de queries no portables -> 0
    patterns = [
        r"\b(?:q|query)\.r\.[a-z0-9_]*\s*\([^)]*\)",
        r"\b(?:q|query)\.r\.[a-z0-9_]*\b",
        r"\b(?:q|query)\.input_[a-z0-9_]*\s*\([^)]*\)",
        r"\b(?:q|query)\.input_[a-z0-9_]*\b",
        r"\b(?:q|query)\.has_entity\b\s*\([^)]*\)?",
        r"\b(?:q|query)\.is_riding\b\s*\([^)]*\)?",
        r"\b(?:q|query)\.is_being_ridden\b\s*\([^)]*\)?",
        r"\b(?:q|query)\.sound\b\s*\([^)]*\)?",
        r"\b(?:q|query)\.anim_progress\b\s*\([^)]*\)?",
    ]
    for pat in patterns:
        out = re.sub(pat, "0", out, flags=re.IGNORECASE)
    return out


def _cleanup_expression(expr: str) -> str:
    s = expr.strip()
    if not s:
        return "0"
    # eliminar ';' finales sobrantes en expresiones simples
    s = re.sub(r";\s*$", "", s)
    # remover operadores binarios colgantes al inicio/fin
    s = re.sub(r"^[+*/%,]+", "", s).strip()
    s = re.sub(r"[+\-*/%,?:=<>&|!]+$", "", s).strip()
    # simplificaciones seguras
    for _ in range(5):
        prev = s
        s = re.sub(r"\b0\s*\*\s*([^+\-]+)", "0", s)
        s = re.sub(r"([^+\-]+)\s*\*\s*0\b", "0", s)
        s = re.sub(r"\b0\s*\+\s*", "", s)
        s = re.sub(r"\s*\+\s*0\b", "", s)
        s = re.sub(r"\(\s*0\s*\)", "0", s)
        s = re.sub(r"\s+", " ", s).strip()
        if s == prev:
            break
    if not s or s in {"+", "-", "*", "/", "(", ")", ","}:
        return "0"
    return s


def _basic_syntax_ok(expr: str, tokens: list[tuple[str, str]]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not tokens:
        return False, ["expresión vacía"]
    if not _has_balanced_delimiters(tokens):
        issues.append("delimitadores desbalanceados")

    # detectar tokens desconocidos/operadores problemáticos obvios
    bad = [v for k, v in tokens if k == "UNKNOWN"]
    if bad:
        issues.append(f"tokens desconocidos: {''.join(bad[:5])}")

    # evitar secuencias de operadores inválidas comunes
    ops = {"+", "-", "*", "/", "%", ">", "<", ">=", "<=", "==", "!=", "&&", "||", "?", ":", "=", ","}
    prev_kind = None
    prev_val = None
    for kind, val in tokens:
        if prev_kind == "OP" and kind == "OP" and prev_val in ops and val in ops:
            # permitir unarios simples como (* -x) o (, -x) no representado aquí; ser conservador
            if not (val == "-" and prev_val in {"(", ",", "?", ":", "=", "+", "-", "*", "/", "%", ">", "<", ">=", "<=", "==", "!=", "&&", "||"}):
                issues.append(f"secuencia de operadores inválida: {prev_val}{val}")
                break
        prev_kind, prev_val = kind, val

    # math.clamp debe tener 3 argumentos (heurística textual)
    for m in re.finditer(r"\bmath\.clamp\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)", expr, re.IGNORECASE):
        args = [a for a in m.group(1).split(",") if a.strip()]
        if len(args) != 3:
            issues.append("math.clamp con número de argumentos != 3")
            break

    # detectar llamadas con paréntesis de cierre faltante ya lo cubre balanceo; aquí llamadas truncadas obvias
    if re.search(r"\b[a-zA-Z_][\w.]*\s*\([^)]*$", expr):
        issues.append("llamada/agrupación truncada")

    return len(issues) == 0, issues


def analyze_molang(expr: str) -> MolangAnalysis:
    src = expr or ""
    unsupported = _detect_unsupported(src)
    sanitized = _strip_invalid_queries(src) if unsupported else src
    sanitized = _cleanup_expression(sanitized)
    tokens = tokenize(sanitized)
    ok, issues = _basic_syntax_ok(sanitized, tokens)

    # Si sigue inválido tras sanitizar, degradar a constante segura
    if not ok:
        issues.append("degradado a constante segura '0'")
        sanitized = "0"
        tokens = tokenize(sanitized)
        ok = True

    if unsupported:
        issues.insert(0, f"queries no portables detectadas: {', '.join(unsupported[:5])}")

    return MolangAnalysis(
        source=src,
        valid=ok,
        sanitized=sanitized,
        issues=issues,
        unsupported_queries=unsupported,
        tokens=tokens,
    )


def is_valid_molang(expr: str) -> bool:
    return analyze_molang(expr).valid


def sanitize_molang(expr: str) -> str:
    return analyze_molang(expr).sanitized
