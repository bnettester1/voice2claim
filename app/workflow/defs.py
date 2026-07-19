"""Hợp đồng graph JSON của workflow_defs + validate + catalog node type.

graph = {"nodes":[{id,type,label,config{}}],
         "edges":[{from,to,when?,label?,else?}]}
Điều kiện `when` nằm TRÊN edge (node branch chỉ là điểm rẽ trực quan).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.workflow import expr

# catalog: icon cho viz + field cho editor mini-form (S6)
NODE_TYPES: dict[str, dict] = {
    "start":            {"icon": "🏁", "editable": ["expects"]},
    "collect_form":     {"icon": "📝", "editable": ["fields", "mode", "role"]},
    "crm_lookup":       {"icon": "🔎", "editable": ["query_from", "verify_from"]},
    "ai_assess":        {"icon": "🤖", "editable": ["base", "rules", "second_opinion"]},
    "branch":           {"icon": "🔀", "editable": []},
    "gen_pdf":          {"icon": "📄", "editable": ["template", "pack_id"]},
    "send_email":       {"icon": "✉️", "editable": ["template_id", "to", "subject"]},
    "wait_event":       {"icon": "⏳", "editable": ["event"]},
    "human_task":       {"icon": "👤", "editable": ["role", "title", "decision", "form"]},
    "transcribe_media": {"icon": "🎙️", "editable": ["media_from", "narrative"]},
    "auto_call":        {"icon": "📞", "editable": ["say", "mode", "wait"]},
    "fire_action":      {"icon": "⚡", "editable": ["pack_id", "action_id"]},
    "update_record":    {"icon": "🗄️", "editable": ["entity", "set"]},
    "end":              {"icon": "🏆", "editable": ["outcome"]},
}
# node có side-effect ngoài context → recover/replay phải check step done trước
SIDE_EFFECT_TYPES = {"gen_pdf", "send_email", "human_task", "auto_call",
                     "fire_action", "update_record"}


class NodeDef(BaseModel):
    id: str
    type: str
    label: str = ""
    config: dict = Field(default_factory=dict)


class EdgeDef(BaseModel):
    from_: str = Field(alias="from")
    to: str
    when: str = ""
    label: str = ""
    else_: bool = Field(default=False, alias="else")

    model_config = {"populate_by_name": True}


class GraphSpec(BaseModel):
    nodes: list[NodeDef]
    edges: list[EdgeDef]

    def node(self, node_id: str) -> NodeDef | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def start_node(self) -> NodeDef:
        return next(n for n in self.nodes if n.type == "start")

    def out_edges(self, node_id: str) -> list[EdgeDef]:
        return [e for e in self.edges if e.from_ == node_id]

    def next_node(self, node_id: str, ctx: dict) -> str:
        """Chọn edge: `when` đúng đầu tiên theo thứ tự khai báo → `else` → edge
        trơn duy nhất. Không khớp gì = lỗi định tuyến (runner set failed)."""
        edges = self.out_edges(node_id)
        if not edges:
            raise LookupError(f"node '{node_id}' không có edge ra")
        for e in edges:
            if e.when and expr.evaluate(e.when, ctx):
                return e.to
        for e in edges:
            if e.else_:
                return e.to
        plain = [e for e in edges if not e.when and not e.else_]
        if len(plain) == 1:
            return plain[0].to
        raise LookupError(f"node '{node_id}': không edge nào khớp điều kiện")


def validate_graph(graph: dict) -> list[str]:
    """→ danh sách lỗi (rỗng = hợp lệ). Dùng cho editor + trước khi seed."""
    errors: list[str] = []
    try:
        g = GraphSpec.model_validate(graph)
    except Exception as exc:  # noqa: BLE001
        return [f"schema: {str(exc)[:200]}"]

    ids = [n.id for n in g.nodes]
    if len(ids) != len(set(ids)):
        errors.append("id node trùng nhau")
    for n in g.nodes:
        if n.type not in NODE_TYPES:
            errors.append(f"{n.id}: type '{n.type}' không tồn tại")
    starts = [n for n in g.nodes if n.type == "start"]
    if len(starts) != 1:
        errors.append(f"phải có đúng 1 node start (đang có {len(starts)})")
    if not any(n.type == "end" for n in g.nodes):
        errors.append("thiếu node end")
    idset = set(ids)
    for e in g.edges:
        if e.from_ not in idset:
            errors.append(f"edge từ node lạ '{e.from_}'")
        if e.to not in idset:
            errors.append(f"edge tới node lạ '{e.to}'")
        if e.when:
            try:
                expr.parse(e.when)
            except ValueError as exc:
                errors.append(f"edge {e.from_}→{e.to}: {exc}")
    for n in g.nodes:
        if n.type != "end" and not g.out_edges(n.id):
            errors.append(f"{n.id}: không có edge ra")
        if n.type == "end" and g.out_edges(n.id):
            errors.append(f"{n.id}: node end không được có edge ra")
    if not errors and starts:
        seen, queue = {starts[0].id}, [starts[0].id]
        while queue:
            for e in g.out_edges(queue.pop()):
                if e.to not in seen:
                    seen.add(e.to)
                    queue.append(e.to)
        for nid in idset - seen:
            errors.append(f"{nid}: không thể tới từ start")
    return errors
