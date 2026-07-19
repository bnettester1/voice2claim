"""Action Executor — PDF chuẩn ngành (fpdf2, font hệ thống hỗ trợ tiếng Việt),
ticket store (Core System Console), TTS xác nhận (VALSEA, cache pre-generate),
DocumentComposer (narrative từ VALSEA formatting / fallback template — không
LLM ngoài, 18/07)."""
from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx
from fpdf import FPDF

from app.config import settings
from app.core import valsea
from app.core.form_state import FormStore, _empty
from app.packs.loader import ActionSpec, Pack

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(exist_ok=True)
TTS_CACHE = ROOT / "assets" / "tts_cache"
TTS_CACHE.mkdir(parents=True, exist_ok=True)

_FONT_CANDIDATES = [
    ("/System/Library/Fonts/Supplemental/Tahoma.ttf",
     "/System/Library/Fonts/Supplemental/Tahoma Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", None),
    ("/System/Library/Fonts/Supplemental/Times New Roman.ttf",
     "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"),
    # Linux (server deploy — Ubuntu fonts-dejavu hỗ trợ tiếng Việt đủ)
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
     "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
]

PDF_TITLES = {
    "towing_request": "PHIẾU YÊU CẦU CỨU HỘ",
    "injury_confirmation": "PHIẾU XÁC NHẬN CÓ NGƯỜI BỊ THƯƠNG",
    "multi_vehicle_report": "BIÊN BẢN VA CHẠM LIÊN HOÀN",
    "theft_report": "BÁO CÁO MẤT CẮP PHỤ TÙNG",
    "surveyor_visit": "PHIẾU HẸN GIÁM ĐỊNH HIỆN TRƯỜNG",
    "e_prescription": "ĐƠN THUỐC ĐIỆN TỬ",
    "outpatient_order": "PHIẾU CHỈ ĐỊNH ĐIỀU TRỊ NGOẠI TRÚ",
    "exam_slip": "PHIẾU KHÁM BỆNH VÀ ĐƠN THUỐC",
    "lab_order": "PHIẾU CHỈ ĐỊNH CẬN LÂM SÀNG",
    "follow_up": "PHIẾU HẸN TÁI KHÁM",
    "contract_update": "PHIẾU BỔ SUNG THÔNG TIN HỢP ĐỒNG BẢO HIỂM",
    "callcenter_intake": "PHIẾU TIẾP NHẬN YÊU CẦU QUA TỔNG ĐÀI TỰ ĐỘNG",
    "contract_issue": "HỢP ĐỒNG BẢO HIỂM VẬT CHẤT XE (BẢN KÝ ĐIỆN TỬ)",  # E12
    "claim_report": "BIÊN BẢN GIÁM ĐỊNH HIỆN TRƯỜNG (AI BÓC BĂNG)",      # E12
    "form_submission": "",  # dùng form.title của pack
}

ORG_LINE = {
    "insurance_motor": "CÔNG TY BẢO HIỂM — TRUNG TÂM GIÁM ĐỊNH & BỒI THƯỜNG",
    "healthcare_exam": "PHÒNG KHÁM ĐA KHOA — HỆ THỐNG BỆNH ÁN ĐIỆN TỬ",
    "insurance_contract": "CÔNG TY BẢO HIỂM — TRUNG TÂM CHĂM SÓC KHÁCH HÀNG & THẨM ĐỊNH",
    "insurance_callcenter": "CÔNG TY BẢO HIỂM — TỔNG ĐÀI CSKH TỰ ĐỘNG 24/7",
}


def _find_font() -> tuple[str, str | None]:
    for reg, bold in _FONT_CANDIDATES:
        if Path(reg).exists():
            return reg, (bold if bold and Path(bold).exists() else None)
    raise RuntimeError("Không tìm thấy font TTF hỗ trợ tiếng Việt")


def _fmt_value(v: Any) -> str:
    if isinstance(v, list):
        return "\n".join(f"• {x}" for x in v)
    return str(v)


# ---------------------------------------------------------------- PDF
def render_pdf(
    pack: Pack,
    template: str,
    values: dict[str, Any],
    ticket_id: str,
    narrative: str = "",
    audit: dict | None = None,
) -> Path:
    reg, bold = _find_font()
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.add_font("VN", "", reg)
    pdf.add_font("VN", "B", bold or reg)

    org = ORG_LINE.get(pack.id, "DOANH NGHIỆP TÍCH HỢP VOICE-TO-FORM")
    title = PDF_TITLES.get(template) or pack.form.title.upper()

    pdf.set_font("VN", "", 9)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 5, org, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("VN", "B", 15)
    pdf.cell(0, 10, title, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("VN", "", 9)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 5,
             f"Số: {ticket_id}   ·   Ngày lập: {time.strftime('%d/%m/%Y %H:%M')}   ·   Kênh: Voice-to-Form (VALSEA ASR)",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # bảng field theo section của pack
    label_w, page_w = 58, pdf.w - pdf.l_margin - pdf.r_margin
    for section in pack.form.sections:
        rows = [(f.label, values.get(f.name)) for f in section.fields
                if not _empty(values.get(f.name))]
        if not rows:
            continue
        pdf.set_font("VN", "B", 10.5)
        pdf.set_fill_color(235, 239, 248)
        pdf.cell(page_w, 7, "  " + section.title, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("VN", "", 10)
        for label, val in rows:
            pdf.set_x(pdf.l_margin)          # luôn bắt đầu row từ lề trái
            y0 = pdf.get_y()
            pdf.set_font("VN", "B", 9.5)
            pdf.multi_cell(label_w, 6, label, border="LTB")
            h_label = pdf.get_y() - y0
            pdf.set_xy(pdf.l_margin + label_w, y0)
            pdf.set_font("VN", "", 10)
            pdf.multi_cell(page_w - label_w, 6, _fmt_value(val), border="RTB")
            h_val = pdf.get_y() - y0
            pdf.set_xy(pdf.l_margin, y0 + max(h_label, h_val))  # cân 2 cột + reset X
        pdf.ln(1.5)

    if narrative:
        pdf.set_font("VN", "B", 10.5)
        pdf.cell(0, 7, "Tóm tắt diễn biến (AI tổng hợp từ hội thoại)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("VN", "", 10)
        pdf.multi_cell(0, 5.5, narrative)
        pdf.ln(2)

    pdf.ln(4)
    y = pdf.get_y()
    pdf.set_font("VN", "", 9)
    pdf.set_text_color(70, 70, 70)
    pdf.multi_cell(page_w / 2, 5, "Người lập / duyệt\n(ký, ghi rõ họ tên)", align="C")
    pdf.set_xy(pdf.l_margin + page_w / 2, y)
    audit = audit or {}
    audit_line = "Hệ thống xác nhận\n" + " · ".join(
        s for s in [
            f"score {audit['score']}" if audit.get("score") is not None else "",
            f"arm {audit['arm_ms']}ms" if audit.get("arm_ms") is not None else "",
            f"người duyệt: {audit['reviewer']}" if audit.get("reviewer") else "",
        ] if s) or "Hệ thống xác nhận"
    pdf.multi_cell(page_w / 2, 5, audit_line, align="C")

    out = OUT_DIR / f"{template}_{ticket_id}.pdf"
    pdf.output(str(out))
    return out


# ---------------------------------------------------------------- Tickets
@dataclass
class TicketStore:
    tickets: list[dict] = field(default_factory=list)
    logs: list[dict] = field(default_factory=list)
    _seq: int = 11
    listeners: list[Callable[[str, dict], None]] = field(default_factory=list)

    def next_id(self) -> str:
        self._seq += 1
        return f"TCK-{self._seq:04d}"

    def add(self, ticket: dict) -> None:
        self.tickets.insert(0, ticket)
        self._emit("ticket", ticket)

    def log(self, message: str, level: str = "info") -> None:
        entry = {"ts": time.strftime("%H:%M:%S"), "msg": message, "level": level}
        self.logs.insert(0, entry)
        del self.logs[200:]
        self._emit("log", entry)

    def _emit(self, kind: str, data: dict) -> None:
        for fn in list(self.listeners):
            try:
                fn(kind, data)
            except Exception:  # noqa: BLE001
                pass


ticket_store = TicketStore()


# ---------------------------------------------------------------- TTS cache
def _tts_path(text: str) -> Path:
    import hashlib
    return TTS_CACHE / (hashlib.sha1(text.encode()).hexdigest()[:16] + ".wav")


async def tts_cached(text: str, client: httpx.AsyncClient | None = None) -> bytes | None:
    p = _tts_path(text)
    if p.exists():
        return p.read_bytes()
    try:
        audio = await valsea.tts(text, client=client)
        p.write_bytes(audio)
        return audio
    except Exception:  # noqa: BLE001
        return None


async def pregenerate_tts(packs: dict[str, Pack]) -> None:
    """Chạy nền lúc khởi động — cache mọi câu tts_confirm để demo phát tức thì."""
    async with httpx.AsyncClient(timeout=60) as client:
        for pack in packs.values():
            for a in pack.actions:
                if a.tts_confirm and not _tts_path(a.tts_confirm).exists():
                    await tts_cached(a.tts_confirm, client=client)
                    await asyncio.sleep(0.3)


# ---------------------------------------------------------------- Narrative
def _extract_narrative(fmt: dict) -> str:
    """Rút chuỗi tóm tắt tiếng Việt từ kết quả formatting (nếu có)."""
    for key in ("summary", "notes"):
        v = fmt.get(key)
        if isinstance(v, str) and len(v) > 30:
            return v
    return ""


async def compose_narrative(
    pack: Pack, transcript: str, values: dict,
    client: httpx.AsyncClient | None = None,
) -> tuple[str, dict | None]:
    """→ (narrative tiếng Việt, service_log dict nếu có).
    Insurance: service_log (EN, đính ticket) + meeting_minutes cho narrative VN.
    Không LLM ngoài (18/07): formatting không ra tiếng Việt → template từ field."""
    service_log: dict | None = None
    narrative = ""
    try:
        if pack.id == "insurance_motor":
            service_log = await valsea.formatting(transcript, "service_log", client=client)
        fmt = await valsea.formatting(transcript, "meeting_minutes", client=client)
        narrative = _extract_narrative(fmt)
    except Exception:  # noqa: BLE001
        pass
    if not _looks_vietnamese(narrative):
        narrative = _template_narrative(pack, values)
    return narrative, service_log


def _looks_vietnamese(text: str) -> bool:
    import re
    return bool(text) and bool(
        re.search(r"[àáảãạăâđèéẻẽẹêìíỉĩịòóỏõọôơùúủũụưỳýỷỹỵ]", text.lower()))


def _template_narrative(pack: Pack, values: dict) -> str:
    """Fallback KHÔNG LLM: ghép tường thuật biên bản từ field đã điền."""
    def has(k: str) -> bool:
        return not _empty(values.get(k))

    def lst(k: str) -> str:
        v = values.get(k)
        return "; ".join(str(x) for x in v) if isinstance(v, list) else str(v)

    p: list[str] = []
    if pack.id == "insurance_motor":
        if has("ten_khach_hang"):
            p.append(f"Khách hàng {values['ten_khach_hang']} khai báo sự cố"
                     + (f" {values['nguyen_nhan']}" if has("nguyen_nhan") else "")
                     + (f" tại {values['vi_tri']}" if has("vi_tri") else "") + ".")
        if has("xe_khach"):
            p.append("Phương tiện: " + str(values["xe_khach"])
                     + (f", biển số {values['bien_so_xe_khach']}"
                        if has("bien_so_xe_khach") else "") + ".")
        if has("hu_hong_xe_khach"):
            p.append("Ghi nhận hư hỏng: " + lst("hu_hong_xe_khach") + ".")
        if has("thuong_tich"):
            p.append("Tình trạng người: " + str(values["thuong_tich"]) + ".")
        if has("xe_lien_quan"):
            p.append("Xe liên quan: " + lst("xe_lien_quan") + ".")
    elif pack.id == "healthcare_exam":
        if has("ten_benh_nhan"):
            p.append(f"Bệnh nhân {values['ten_benh_nhan']}"
                     + (f", {values['tuoi']} tuổi" if has("tuoi") else "")
                     + (f", khám vì {values['ly_do_kham']}"
                        if has("ly_do_kham") else "") + ".")
        if has("chan_doan"):
            p.append("Chẩn đoán: " + str(values["chan_doan"]) + ".")
        if has("thuoc_moi"):
            p.append("Kê đơn: " + lst("thuoc_moi") + ".")
        if has("tai_kham"):
            p.append("Hẹn tái khám " + str(values["tai_kham"]) + ".")
    elif pack.id == "insurance_contract":
        if has("ten_khach_hang"):
            p.append(f"Đã liên hệ khách hàng {values['ten_khach_hang']} bổ sung "
                     "thông tin hợp đồng qua cuộc gọi tự động.")
        done = [f.label for f in pack.all_fields()
                if f.required and not _empty(values.get(f.name))]
        if done:
            p.append("Đã thu thập: " + ", ".join(done) + ".")
    return " ".join(p)


# ---------------------------------------------------------------- Priority
def compute_priority(store: FormStore, service_log: dict | None) -> str:
    injury = store.fields.get("thuong_tich")
    if injury is not None and not _empty(injury.value):
        return "CAO"
    fr = (service_log or {}).get("customer_frustration_level", "")
    if str(fr).lower() in ("high", "very_high", "severe"):
        return "CAO"
    if str(fr).lower() == "medium":
        return "TRUNG BÌNH"
    return "TRUNG BÌNH" if service_log else "THƯỜNG"


# ---------------------------------------------------------------- Execute
async def execute_action(
    pack: Pack,
    action: ActionSpec,
    store: FormStore,
    transcript: str = "",
    arm_ms: float | None = None,
    reviewer: str = "",
    score: int | None = None,
    client: httpx.AsyncClient | None = None,
    recording_url: str = "",
) -> dict:
    """Chạy thật: narrative → PDF → ticket → webhook log → TTS. Trả payload cho UI."""
    ticket_id = ticket_store.next_id()
    values = store.snapshot()
    narrative, service_log = await compose_narrative(pack, transcript, values, client)

    pdf_path = render_pdf(
        pack, action.template or "form_submission", values, ticket_id,
        narrative=narrative,
        audit={"score": score, "arm_ms": round(arm_ms) if arm_ms else None,
               "reviewer": reviewer},
    )
    priority = compute_priority(store, service_log)
    ticket = {
        "id": ticket_id,
        "ts": time.strftime("%H:%M:%S"),
        "action": action.id,
        "action_label": action.label,
        "pack": pack.id,
        "pack_icon": pack.icon,
        "priority": priority,
        "status": "webhook 200",
        "pdf": f"/pdf/{pdf_path.name}",
        "recording": recording_url,
        "fields_count": len(values),
        "service_log": service_log,
        "audit": {"score": score, "arm_ms": arm_ms, "reviewer": reviewer},
    }
    ticket_store.add(ticket)
    ticket_store.log(
        f"POST /webhook/{'claims' if pack.id.startswith('insurance') else 'his'} "
        f"action={action.id} fields={len(values)} priority={priority} → 200 OK")
    ticket_store.log(f"PDF render {pdf_path.name} → ok {pdf_path.stat().st_size // 1024}KB")

    tts_b64 = None
    if action.tts_confirm:
        audio = await tts_cached(action.tts_confirm, client=client)
        if audio:
            tts_b64 = base64.b64encode(audio).decode()
            ticket_store.log(f"VALSEA TTS xác nhận ({len(audio)//1024}KB) → ok")

    return {"ticket": {k: v for k, v in ticket.items() if k != "service_log"},
            "service_log": service_log, "narrative": narrative,
            "pdf_url": ticket["pdf"], "tts_b64": tts_b64}
