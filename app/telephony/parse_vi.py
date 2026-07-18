"""Parser tiếng Việt field-aware cho outbound call — KHÔNG LLM.

Kịch bản có sẵn nên engine biết đang hỏi field nào → parse câu trả lời của
khách bằng rule thuần (số đọc chữ → chữ số, ngày sinh, CCCD, biển số, địa
chỉ). Chạy trên text ĐÃ qua VALSEA correction + apply_itn của pack.
So khớp trên dạng bỏ dấu (normalize_vi) để chịu được biến thể ASR.
"""
from __future__ import annotations

import re

from app.core.triggers import normalize_vi
from app.packs.loader import Pack

# chữ số đọc rời (dạng bỏ dấu) — "nam"/"lam" = 5, "tu" = 4, "muoi" xử lý riêng
_DIGIT = {
    "khong": 0, "mot": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4,
    "nam": 5, "lam": 5, "sau": 6, "bay": 7, "tam": 8, "chin": 9,
}
_TENS_WORD = "muoi"          # "hai mươi", "mười lăm"


def _toks(text: str) -> list[str]:
    return normalize_vi(text).split()


# ---------------------------------------------------------------- số rời
def digits_only(text: str) -> str:
    """Gom MỌI chữ số trong câu (đọc rời từng số hoặc ASR đã ra số).
    "không bảy chín, không tám ba" → "079083"; "079 083" → "079083"."""
    out: list[str] = []
    for t in _toks(text):
        if t.isdigit():
            out.append(t)
        elif t in _DIGIT and t != _TENS_WORD:
            out.append(str(_DIGIT[t]))
    return "".join(out)


# ---------------------------------------------------------------- số 0-99
def _small_number(toks: list[str], i: int) -> tuple[int | None, int]:
    """Đọc một số 0-99 từ vị trí i → (giá trị, vị trí kế). Hiểu 'mười lăm',
    'hai mươi', 'hai mươi mốt', 'ba mươi', số rời, và digits ('20')."""
    if i >= len(toks):
        return None, i
    t = toks[i]
    if t.isdigit():
        return int(t), i + 1
    if t == _TENS_WORD:                      # "mười", "mười lăm"
        val, j = 10, i + 1
        if j < len(toks) and toks[j] in _DIGIT:
            val += _DIGIT[toks[j]]
            j += 1
        return val, j
    if t in _DIGIT:
        val, j = _DIGIT[t], i + 1
        if j < len(toks) and toks[j] == _TENS_WORD:      # "hai mươi (mốt)"
            val, j = val * 10, j + 1
            if j < len(toks) and toks[j] in _DIGIT:
                val += _DIGIT[toks[j]]
                j += 1
        return val, j
    return None, i


def _year(toks: list[str], i: int) -> int | None:
    """Năm sau từ 'năm': '1986' | 'một nghìn chín trăm tám mươi sáu' |
    'một chín tám sáu' | 'tám sáu' (→ 19xx/20xx)."""
    if i < len(toks) and toks[i].isdigit() and len(toks[i]) == 4:
        return int(toks[i])
    # dạng đầy đủ có nghìn/trăm
    if any(t in ("nghin", "ngan") for t in toks[i:i + 6]):
        val = 0
        j = i
        while j < len(toks):
            t = toks[j]
            if t in _DIGIT:
                d = _DIGIT[t]
                if j + 1 < len(toks) and toks[j + 1] in ("nghin", "ngan"):
                    val += d * 1000
                    j += 2
                    continue
                if j + 1 < len(toks) and toks[j + 1] == "tram":
                    val += d * 100
                    j += 2
                    continue
                if j + 1 < len(toks) and toks[j + 1] == _TENS_WORD:
                    val += d * 10
                    j += 2
                    if j < len(toks) and toks[j] in _DIGIT:
                        val += _DIGIT[toks[j]]
                        j += 1
                    continue
                val += d
                j += 1
            elif t in (_TENS_WORD, "linh", "le"):
                j += 1
            else:
                break
        return val if 1900 <= val <= 2099 else None
    # dãy chữ số rời: 'một chín tám sáu' / 'tám sáu'
    ds: list[str] = []
    j = i
    while j < len(toks) and (toks[j] in _DIGIT or toks[j].isdigit()):
        ds.append(str(_DIGIT.get(toks[j], toks[j])))
        j += 1
    s = "".join(ds)
    if len(s) == 4:
        return int(s)
    if len(s) == 2:
        yy = int(s)
        return 1900 + yy if yy >= 30 else 2000 + yy
    return None


# ---------------------------------------------------------------- fields
def parse_date(text: str) -> str | None:
    """'hai mươi tháng tư năm một nghìn chín trăm tám mươi sáu' → 20/04/1986.
    Chấp nhận cả dạng ITN sẵn '20/04/1986' hoặc '20 tháng 4 năm 1986'."""
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return f"{d:02d}/{mo:02d}/{y}"
    toks = _toks(text)
    try:
        i_th = toks.index("thang")
    except ValueError:
        return None
    # ngày: số 0-99 kết thúc NGAY TRƯỚC 'tháng' — thử cửa sổ dài trước để
    # "hai mươi tháng" ra 20 chứ không bắt cụt "mươi" = 10
    day = None
    for back in (3, 2, 1):
        j = i_th - back
        if j < 0:
            continue
        val, nxt = _small_number(toks, j)
        if val is not None and nxt == i_th and 1 <= val <= 31:
            day = val
            break
    month, j = _small_number(toks, i_th + 1)
    if day is None or month is None or not 1 <= month <= 12:
        return None
    year = None
    for k in range(j, min(j + 4, len(toks))):
        if toks[k] == "nam":
            year = _year(toks, k + 1)
            if year:
                break
    if year is None:
        return None
    return f"{day:02d}/{month:02d}/{year}"


def parse_id_number(text: str, length: int = 12) -> str | None:
    """CCCD: gom mọi chữ số trong câu trả lời; đúng `length` số thì nhận.
    Dài hơn → lấy dãy `length` số cuối cùng liên tiếp trong chuỗi gom được."""
    s = digits_only(text)
    if len(s) == length:
        return s
    if len(s) > length:
        return s[-length:]
    return None


def parse_digits_tail(text: str, lo: int = 6, hi: int = 9) -> str | None:
    """'Sáu số cuối CCCD' đọc rời/số: nhận lo–hi chữ số (dài hơn lấy đuôi hi)."""
    s = digits_only(text)
    if len(s) < lo:
        return None
    return s if len(s) <= hi else s[-hi:]


_NAME_FILLER = {"da", "vang", "u", "a", "alo", "anh", "chi", "em", "toi",
                "minh", "ten", "la", "cua", "day", "nhe", "nha", "roi", "o"}
_NAME_STOP = {"Anh", "Chị", "Em", "Tôi", "Mình", "Dạ", "Vâng", "Tên", "Là"}


def parse_person_name(text: str) -> str | None:
    """'Anh tên là Nguyễn Tiến Tuấn ạ' → 'Nguyễn Tiến Tuấn'.
    Ưu tiên chuỗi token Viết Hoa dài nhất (bỏ đại từ); fallback: bỏ filler
    rồi Title-Case phần còn lại (≤4 từ)."""
    toks = [t.strip(",.!?") for t in text.split() if t.strip(",.!?")]
    runs: list[list[str]] = []
    cur: list[str] = []
    for t in toks:
        if re.fullmatch(r"[A-ZĐÀ-Ỹ][a-zà-ỹ]+", t) and t not in _NAME_STOP:
            cur.append(t)
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    if runs:
        best = max(runs, key=len)
        if 1 <= len(best) <= 4:
            return " ".join(best)
    rest = [t for t in toks if normalize_vi(t) not in _NAME_FILLER
            and not t.isdigit()]
    if 1 <= len(rest) <= 4:
        return " ".join(w[:1].upper() + w[1:] for w in rest)
    return None


def parse_plate(text: str) -> str | None:
    """Biển số: '51K, một hai ba chấm bốn lăm' → '51K-123.45'.
    Ưu tiên dạng đã chuẩn trong text; không thì ghép serie + 5 số quanh 'chấm'."""
    flat = re.sub(r"\s+", " ", text.upper())
    m = re.search(r"\b(\d{2}[A-Z]{1,2}\d?)\s*[- ]?\s*(\d{3})[.\s]?(\d{2})\b", flat)
    if m:
        return f"{m.group(1)}-{m.group(2)}.{m.group(3)}"
    m = re.search(r"\b(\d{2}[A-Z]{1,2}\d?)\b", flat)
    if not m:
        return None
    serie = m.group(1)
    tail = text[m.end():]
    toks = _toks(tail)
    ds: list[str] = []
    dot_at = -1
    for t in toks:
        if t == "cham":
            dot_at = len(ds)
        elif t.isdigit():
            ds.extend(list(t))
        elif t in _DIGIT and t != _TENS_WORD:
            ds.append(str(_DIGIT[t]))
        if len(ds) >= 5:
            break
    if len(ds) < 5:
        return None
    if dot_at not in (3,):               # mặc định 3+2
        dot_at = 3
    return f"{serie}-{''.join(ds[:dot_at])}.{''.join(ds[dot_at:dot_at + 2])}"


_ADDR_LEAD = re.compile(
    r"^(?:dạ|vâng|à|ừ|anh|chị|em|tôi|mình)?\s*(?:đang|hiện)?\s*(?:ở|tại|là)\s*",
    re.IGNORECASE)


def parse_address(text: str) -> str | None:
    """Địa chỉ: giữ nguyên văn, chỉ bỏ filler mở đầu ('anh đang ở…') và chuyển
    cụm số đọc chữ sau 'số/phường/quận' thành chữ số."""
    s = text.strip().strip(".。")
    s = _ADDR_LEAD.sub("", s, count=1).strip()
    if len(s) < 6:
        return None

    def _num_after(m: re.Match) -> str:
        kw, words = m.group(1), m.group(2)
        val, nxt = _small_number(_toks(words), 0)
        if val is None or nxt < len(_toks(words)):
            return m.group(0)
        return f"{kw} {val} "

    # "số mười hai" → "số 12"; "phường bốn" → "phường 4"; "quận ba" → "quận 3"
    s = re.sub(
        r"(?i)\b(số|phường|quận)\s+((?:[a-zà-ỹ]+\s?){1,3}?)(?=\s*(?:đường|phố|phường|quận|huyện|thành|tỉnh|,|$))",
        _num_after, s)
    s = re.sub(r"\s+,", ",", re.sub(r"\s+", " ", s)).strip()
    return s[0].upper() + s[1:] if s else None


def parse_field(pack: Pack, fieldname: str, heard: str) -> object | None:
    """Điểm vào duy nhất: field kịch bản + câu khách nói → giá trị chuẩn hoá."""
    spec = pack.field(fieldname)
    if spec is None or not heard.strip():
        return None
    if fieldname == "ngay_sinh" or spec.type == "date":
        return parse_date(heard)
    if fieldname == "so_cccd":
        return parse_id_number(heard, 12)
    if fieldname == "cccd_cuoi":
        return parse_digits_tail(heard, 6, 9)
    if fieldname == "ho_ten":
        return parse_person_name(heard)
    if fieldname == "bien_so_xe":
        return parse_plate(heard)
    if fieldname == "dia_chi_lien_he":
        return parse_address(heard)
    v = heard.strip().strip(".。")
    return v if v else None
