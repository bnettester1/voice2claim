"""Đánh giá điều kiện edge/rule — dotted path + op, TUYỆT ĐỐI không eval().

Cú pháp: "<path> <op> <literal>"  ·  "<path> exists"  ·  "<path> not_exists"
  op ∈ ==  !=  >=  <=  >  <  contains  in
  literal: số · 'chuỗi' · "chuỗi" · true/false/null · chuỗi trần (không space)
Điều kiện kép = nối 2 node branch (giữ parser nhỏ, dễ soi).
"""
from __future__ import annotations

import re
from typing import Any

_OPS = ("==", "!=", ">=", "<=", ">", "<", "contains", "in")
_RX = re.compile(
    r"^\s*(?P<path>[\w.\[\]]+)\s+(?P<op>==|!=|>=|<=|>|<|contains|in|exists|not_exists)"
    r"(?:\s+(?P<value>.+?))?\s*$")


def get_path(ctx: Any, path: str) -> Any:
    """'a.b.0.c' → ctx['a']['b'][0]['c'] — thiếu ở đâu trả None ở đó."""
    cur = ctx
    for part in str(path).replace("[", ".").replace("]", "").split("."):
        if part == "":
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.lstrip("-").isdigit():
            idx = int(part)
            cur = cur[idx] if -len(cur) <= idx < len(cur) else None
        else:
            return None
        if cur is None:
            return None
    return cur


def _literal(raw: str | None) -> Any:
    if raw is None:
        return None
    s = raw.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _to_num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "."))
        except ValueError:
            return None
    return None


def _exists(v: Any) -> bool:
    return v not in (None, "", [], {})


def compare(left: Any, op: str, right: Any) -> bool:
    if op == "exists":
        return _exists(left)
    if op == "not_exists":
        return not _exists(left)
    if op == "contains":
        try:
            return str(right).lower() in str(left or "").lower() if \
                not isinstance(left, (list, tuple)) else right in left
        except TypeError:
            return False
    if op == "in":
        try:
            if isinstance(right, str):
                right = [x.strip() for x in right.strip("[]").split(",")]
            return left in right
        except TypeError:
            return False
    if op in ("==", "!="):
        eq = (str(left) == str(right)) if not (
            _to_num(left) is not None and _to_num(right) is not None) \
            else _to_num(left) == _to_num(right)
        return eq if op == "==" else not eq
    ln, rn = _to_num(left), _to_num(right)
    if ln is None or rn is None:
        return False
    return {">": ln > rn, ">=": ln >= rn, "<": ln < rn, "<=": ln <= rn}[op]


def parse(cond: str) -> tuple[str, str, Any]:
    """→ (path, op, value) — ValueError nếu sai cú pháp (validate lúc lưu def)."""
    m = _RX.match(cond or "")
    if not m:
        raise ValueError(f"điều kiện không hợp lệ: {cond!r}")
    op = m.group("op")
    if op in _OPS and m.group("value") is None:
        raise ValueError(f"thiếu vế phải: {cond!r}")
    return m.group("path"), op, _literal(m.group("value"))


def evaluate(cond: str, ctx: dict) -> bool:
    path, op, value = parse(cond)
    return compare(get_path(ctx, path), op, value)
