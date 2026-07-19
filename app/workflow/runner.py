"""WorkflowRunner — đi graph, persist từng bước, WAIT thoát coroutine,
resume hoàn toàn event-driven qua CAS status (idempotent với double-click).
"""
from __future__ import annotations

import asyncio
import json

import httpx

from app.config import settings
from app.db.database import run_db
from app.db.dal import erp as dal_erp
from app.db.dal import workflow as dal_wf
from app.workflow.defs import SIDE_EFFECT_TYPES, GraphSpec
from app.workflow.expr import get_path
from app.workflow.nodes import EXECUTORS, Deps, NodeError

_MAX_STEPS_PER_ADVANCE = 60          # chống vòng lặp graph cấu hình sai


class WorkflowRunner:
    def __init__(self) -> None:
        self._locks: dict[int, asyncio.Lock] = {}
        self._client: httpx.AsyncClient | None = None

    # ---------------- hạ tầng ----------------
    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=90)
        return self._client

    @property
    def base_url(self) -> str:
        return (settings.public_base or "http://localhost:8321").rstrip("/")

    def _lock(self, run_id: int) -> asyncio.Lock:
        return self._locks.setdefault(run_id, asyncio.Lock())

    # ---------------- start / advance ----------------
    async def start(self, def_key: str, context: dict | None = None,
                    channel: str = "api", version: int | None = None) -> int:
        d = await run_db(dal_wf.get_def_by_key, def_key, version)
        if d is None:
            raise LookupError(f"không có workflow '{def_key}'")
        graph = GraphSpec.model_validate(d["graph"])
        ctx = dict(context or {})
        ctx.setdefault("_wf_name", d["name"])
        cust = ctx.get("customer") or {}
        run_id = await run_db(
            dal_wf.create_run, d["id"], ctx, channel,
            cust.get("id"), ctx.get("claim_id"), ctx.get("policy_id"),
            (ctx.get("ticket") or {}).get("id"), graph.start_node().id)
        asyncio.create_task(self._advance(run_id))
        return run_id

    async def _advance(self, run_id: int) -> None:
        async with self._lock(run_id):
            for _ in range(_MAX_STEPS_PER_ADVANCE):
                run = await run_db(dal_wf.get_run, run_id, False)
                if run is None or run["status"] != "running":
                    return
                graph = GraphSpec.model_validate(run["graph"])
                node = graph.node(run["current_node"])
                ctx = run["context"]
                if node is None:
                    await run_db(dal_wf.finish_run, run_id, "failed", "",
                                 f"node '{run['current_node']}' không tồn tại")
                    return

                # idempotency crash-recovery: side-effect node đã done → chỉ route
                prev = await run_db(dal_wf.latest_step, run_id, node.id)
                if prev and prev["status"] == "completed" \
                        and node.type in SIDE_EFFECT_TYPES:
                    try:
                        ctx.update(json.loads(prev["output_json"] or "{}"))
                    except Exception:  # noqa: BLE001
                        pass
                    if not await self._route(run_id, graph, node, ctx):
                        return
                    continue

                attempt = (prev["attempt"] + 1) if prev else 1
                step_id = await run_db(
                    dal_wf.start_step, run_id, node.id, node.type, attempt,
                    {"config": node.config})
                deps = Deps(client=self.client, base_url=self.base_url,
                            run_id=run_id, step_id=step_id)
                try:
                    result = await EXECUTORS[node.type](node, ctx, deps)
                except NodeError as exc:
                    await run_db(dal_wf.finish_step, step_id, "failed",
                                 None, str(exc))
                    await run_db(dal_wf.finish_run, run_id, "failed", "",
                                 f"{node.id}: {exc}")
                    return
                except Exception as exc:  # noqa: BLE001
                    await run_db(dal_wf.finish_step, step_id, "failed",
                                 None, f"{type(exc).__name__}: {exc}")
                    await run_db(dal_wf.finish_run, run_id, "failed", "",
                                 f"{node.id}: {type(exc).__name__}: {str(exc)[:150]}")
                    return

                ctx.update(result.patch)
                await self._sync_links(run_id, ctx)

                if result.kind == "wait":
                    await run_db(dal_wf.finish_step, step_id, "waiting",
                                 result.patch, "", result.wait_event)
                    await run_db(dal_wf.set_run, run_id,
                                 status=result.wait_status, context=ctx)
                    return
                if result.kind == "end":
                    await run_db(dal_wf.finish_step, step_id, "completed",
                                 result.patch)
                    await run_db(dal_wf.set_run, run_id, context=ctx)
                    await run_db(dal_wf.finish_run, run_id, "done",
                                 result.outcome)
                    await self._auto_metrics(run_id, ctx, result.outcome)
                    return

                await run_db(dal_wf.finish_step, step_id, "completed",
                             result.patch)
                if not await self._route(run_id, graph, node, ctx):
                    return
            await run_db(dal_wf.finish_run, run_id, "failed", "",
                         f"vượt {_MAX_STEPS_PER_ADVANCE} bước/lượt — nghi vòng lặp")

    async def _route(self, run_id: int, graph: GraphSpec, node, ctx: dict) -> bool:
        try:
            nxt = graph.next_node(node.id, ctx)
        except LookupError as exc:
            await run_db(dal_wf.finish_run, run_id, "failed", "", str(exc))
            return False
        await run_db(dal_wf.set_run, run_id, current_node=nxt, context=ctx)
        return True

    async def _sync_links(self, run_id: int, ctx: dict) -> None:
        links = {}
        cust = ctx.get("customer") or {}
        if cust.get("id"):
            links["customer_id"] = cust["id"]
        for key in ("claim_id", "policy_id"):
            if ctx.get(key):
                links[key] = ctx[key]
        if (ctx.get("ticket") or {}).get("id"):
            links["ticket_id"] = ctx["ticket"]["id"]
        if links:
            await run_db(dal_wf.set_run, run_id, **links)

    async def _auto_metrics(self, run_id: int, ctx: dict, outcome: str) -> None:
        """Flywheel: auto-metrics mỗi run (nguồn 'auto', không cần người chấm)."""
        try:
            fields = ctx.get("fields") or {}
            filled = sum(1 for v in fields.values() if v not in (None, "", []))
            criteria = {"outcome": outcome, "fields_filled": filled,
                        "mails": len(ctx.get("mails") or []),
                        "missing_expected": len(ctx.get("missing_expected") or [])}
            from app.db.database import db
            with db() as conn:
                conn.execute(
                    "INSERT INTO evaluations(run_id, rater_kind, rater_id,"
                    " score, comment, criteria_json)"
                    " VALUES(?, 'auto', '', NULL, ?, ?)"
                    " ON CONFLICT(run_id, rater_kind, rater_id) DO UPDATE SET"
                    " criteria_json = excluded.criteria_json",
                    (run_id, f"outcome={outcome}",
                     json.dumps(criteria, ensure_ascii=False)))
        except Exception:  # noqa: BLE001
            pass

    # ---------------- resume ----------------
    async def resume_token(self, token: str, payload: dict | None = None) -> int | None:
        """Link ký/sự kiện ngoài → CAS consume + CAS run status → advance."""
        ev = await run_db(dal_wf.consume_token, token, payload)
        if ev is None or not ev.get("run_id"):
            return None
        run_id = int(ev["run_id"])
        return await self._resume(run_id, ev["key"], payload or {})

    async def resume_task(self, task: dict, payload: dict | None = None) -> int | None:
        """Task done (dal_erp.complete_task xong) → resume run đang chờ."""
        run_id = task.get("run_id")
        if not run_id:
            return None
        await run_db(dal_wf.push_event, "task.completed", run_id,
                     {"task_id": task["id"], "outcome": task.get("outcome"),
                      **(payload or {})}, "ui", task.get("step_run_id"))
        return await self._resume(int(run_id), "task.completed", payload or {},
                                  task=task)

    async def _resume(self, run_id: int, event_key: str, payload: dict,
                      task: dict | None = None) -> int | None:
        ok = await run_db(dal_wf.cas_run_status, run_id,
                          ("waiting_event", "waiting_task"), "running")
        if not ok:                              # double-click / đã resume rồi
            return None
        run = await run_db(dal_wf.get_run, run_id, False)
        graph = GraphSpec.model_validate(run["graph"])
        node = graph.node(run["current_node"])
        ctx = run["context"]

        wstep = await run_db(dal_wf.waiting_step, run_id)
        out_patch: dict = {}
        if event_key == "esign.signed":
            ctx["signed_at"] = payload.get("signed_at", "")
            ctx["signed_name"] = payload.get("signed_name", "")
            out_patch = {"signed_at": ctx["signed_at"]}
        elif event_key == "task.completed" and task is not None:
            try:
                data = json.loads(task.get("data_json") or "{}")
            except Exception:  # noqa: BLE001
                data = {}
            out_key = (data.get("out")
                       or get_path(node.config, "out") or "task") if node else "task"
            result = dict((data.get("result") or {}))
            # tasks.outcome (approved/rejected/completed — CHECK của DB) →
            # decision trong graph dùng approve/reject cho dễ đọc điều kiện
            result["decision"] = {"approved": "approve",
                                  "rejected": "reject"}.get(
                str(task.get("outcome") or ""), task.get("outcome"))
            result["note"] = task.get("outcome_note", "")
            if out_key == "fields":            # CSR bổ sung field còn thiếu
                fields = dict(ctx.get("fields") or {})
                fields.update({k: v for k, v in result.items()
                               if k not in ("decision", "note")})
                ctx["fields"] = fields
            else:
                ctx[out_key] = result
            out_patch = {out_key: result}
        else:
            ctx.setdefault("events", []).append(
                {"key": event_key, "payload": payload})

        if wstep:
            await run_db(dal_wf.finish_step, wstep["id"], "completed",
                         out_patch)
        if node is not None:
            try:
                nxt = graph.next_node(node.id, ctx)
            except LookupError as exc:
                await run_db(dal_wf.finish_run, run_id, "failed", "", str(exc))
                return run_id
            await run_db(dal_wf.set_run, run_id, current_node=nxt, context=ctx)
        asyncio.create_task(self._advance(run_id))
        return run_id

    async def retry(self, run_id: int) -> bool:
        ok = await run_db(dal_wf.cas_run_status, run_id, ("failed",), "running")
        if not ok:
            return False
        asyncio.create_task(self._advance(run_id))
        return True

    async def recover(self) -> int:
        """Khởi động: run 'running' chết dở → interrupt step + re-advance."""
        ids = await run_db(dal_wf.runs_to_recover)
        for rid in ids:
            await run_db(dal_wf.interrupt_running_steps, rid)
            asyncio.create_task(self._advance(rid))
        return len(ids)


runner = WorkflowRunner()


async def complete_task_and_resume(task_id: int, outcome: str,
                                   outcome_note: str = "",
                                   payload: dict | None = None,
                                   actor_id: str = "") -> dict | None:
    """API hoàn tất task: đóng task (DAL) rồi resume workflow nếu có."""
    task = await run_db(dal_erp.complete_task, task_id, outcome, outcome_note,
                        payload, actor_id)
    if task is None:
        return None
    await runner.resume_task(task, payload)
    return task
