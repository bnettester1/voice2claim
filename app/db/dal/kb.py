"""DAL kho tri thức — kb_documents (sha1 dedupe) + kb_extractions (draft→promote)."""
from __future__ import annotations

import json

from app.db.database import db


def register_document(filename: str, mime: str, kind: str, path: str,
                      size_bytes: int, sha1: str) -> int:
    with db() as conn:
        row = conn.execute("SELECT id FROM kb_documents WHERE sha1=?",
                           (sha1,)).fetchone()
        if row:
            return int(row["id"])
        cur = conn.execute(
            "INSERT INTO kb_documents(filename, mime, kind, path, size_bytes,"
            " sha1) VALUES(?,?,?,?,?,?)",
            (filename, mime, kind, path, size_bytes, sha1))
        return int(cur.lastrowid)


def list_documents() -> list[dict]:
    with db() as conn:
        docs = [dict(r) for r in conn.execute(
            "SELECT * FROM kb_documents ORDER BY created_at DESC")]
        exts = [dict(r) for r in conn.execute(
            "SELECT e.*, d.filename FROM kb_extractions e"
            " JOIN kb_documents d ON d.id = e.doc_id ORDER BY e.id DESC")]
    for e in exts:
        try:
            e["extracted"] = json.loads(e.pop("extracted_json") or "{}")
        except Exception:  # noqa: BLE001
            e["extracted"] = {}
    return {"docs": docs, "extractions": exts}


def get_document(doc_id: int) -> dict | None:
    with db() as conn:
        r = conn.execute("SELECT * FROM kb_documents WHERE id=?",
                         (doc_id,)).fetchone()
        return dict(r) if r else None


def set_doc_status(doc_id: int, status: str, summary: str = "") -> None:
    with db() as conn:
        conn.execute(
            "UPDATE kb_documents SET status=?,"
            " summary=CASE WHEN ?<>'' THEN ? ELSE summary END,"
            " updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            (status, summary, summary, doc_id))


def add_extraction(doc_id: int, extracted: dict, engine: str = "qwen",
                   notes: str = "") -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO kb_extractions(doc_id, engine, extracted_json, notes)"
            " VALUES(?,?,?,?)",
            (doc_id, engine, json.dumps(extracted, ensure_ascii=False), notes))
        return int(cur.lastrowid)


def get_extraction(ext_id: int) -> dict | None:
    with db() as conn:
        r = conn.execute("SELECT * FROM kb_extractions WHERE id=?",
                         (ext_id,)).fetchone()
        if r is None:
            return None
        d = dict(r)
        try:
            d["extracted"] = json.loads(d.pop("extracted_json") or "{}")
        except Exception:  # noqa: BLE001
            d["extracted"] = {}
        return d


def mark_promoted(ext_id: int, def_id: int) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE kb_extractions SET status='promoted',"
            " promoted_workflow_def_id=? WHERE id=?", (def_id, ext_id))
