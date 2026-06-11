# -*- coding: utf-8 -*-
"""기존 HWP 견적서 스캐너 — 한글 실행 없이 olefile로 메타데이터 추출.

PrvText 스트림(UTF-16LE, 최대 1023자)에서 수신처/용역명/견적금액/견적일자를
정규식으로 추출한다. 부족하면 BodyText/Section0(zlib) 텍스트를 폴백으로 파싱.
"""
import os
import re
import struct
import zlib
from dataclasses import dataclass, asdict
from typing import Optional

import olefile

_RE_AMOUNT = re.compile(r"₩\s*([\d,]+)")
_RE_DATE = re.compile(r"견적일자\s*[:：]?\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_RE_QUOTE_NO = re.compile(r"견적번호\s*[:：]?\s*(제?\s*[\w\-]+호?)")
_RE_RECV = re.compile(r"<([^<>]{2,40})\s*귀하")
_RE_RECV_TXT = re.compile(r"^\s*(.{2,40}?)\s*귀하", re.M)
_RE_SVC = re.compile(r"<용\s*역\s*명><([^<>]+)>")
_RE_SVC_TXT = re.compile(r"용\s*역\s*명\s*\n(.+)")


@dataclass
class QuoteMeta:
    path: str
    filename: str
    service_name: str = ""
    recipient: str = ""
    amount: Optional[int] = None
    date: str = ""           # YYYY-MM-DD
    quote_no: str = ""
    source: str = "hwp"      # hwp | json
    editable: bool = False   # 같은 베이스명 .quote.json 존재 여부
    json_path: str = ""
    mtime: float = 0.0
    error: str = ""

    def to_dict(self):
        return asdict(self)


def _read_prvtext(ole) -> str:
    if not ole.exists("PrvText"):
        return ""
    data = ole.openstream("PrvText").read()
    return data.decode("utf-16-le", errors="replace")


def _read_bodytext(ole) -> str:
    """BodyText/Section0 레코드에서 텍스트 추출 (압축 해제)."""
    try:
        if not ole.exists("BodyText/Section0"):
            return ""
        raw = ole.openstream("BodyText/Section0").read()
        # FileHeader 압축 플래그 확인
        hdr = ole.openstream("FileHeader").read()
        compressed = bool(hdr[36] & 0x01) if len(hdr) > 36 else True
        data = zlib.decompress(raw, -15) if compressed else raw
    except Exception:
        return ""
    out = []
    i = 0
    n = len(data)
    while i + 4 <= n:
        h = struct.unpack("<I", data[i:i + 4])[0]
        tag = h & 0x3FF
        size = (h >> 20) & 0xFFF
        i += 4
        if size == 0xFFF:
            if i + 4 > n:
                break
            size = struct.unpack("<I", data[i:i + 4])[0]
            i += 4
        payload = data[i:i + size]
        i += size
        if tag == 67:  # HWPTAG_PARA_TEXT
            chars = []
            j = 0
            while j + 1 < len(payload):
                ch = struct.unpack("<H", payload[j:j + 2])[0]
                if ch >= 32:
                    chars.append(chr(ch))
                    j += 2
                elif ch in (10, 13):
                    chars.append("\n")
                    j += 2
                elif ch in (1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23):
                    j += 16  # 확장 컨트롤 (inline 8 WCHAR)
                else:
                    j += 2
            t = "".join(chars).strip()
            if t:
                out.append(t)
    return "\n".join(out)


def parse_hwp(path: str) -> QuoteMeta:
    meta = QuoteMeta(path=path, filename=os.path.basename(path))
    try:
        meta.mtime = os.path.getmtime(path)
        ole = olefile.OleFileIO(path)
    except Exception as e:
        meta.error = f"파일 열기 실패: {e}"
        return meta
    try:
        prv = _read_prvtext(ole)
        body = ""

        def search(regex, text):
            m = regex.search(text)
            return m if m else None

        # 용역명
        m = search(_RE_SVC, prv)
        if not m:
            body = body or _read_bodytext(ole)
            m = search(_RE_SVC_TXT, body)
        if m:
            meta.service_name = m.group(1).strip()

        # 수신처
        m = search(_RE_RECV, prv)
        if not m:
            body = body or _read_bodytext(ole)
            m = search(_RE_RECV_TXT, body)
        if m:
            recv = m.group(1).strip()
            meta.recipient = recv.split("><")[-1].strip()

        # 금액 (₩ 표기 첫 매치)
        m = search(_RE_AMOUNT, prv) or search(_RE_AMOUNT, body or _read_bodytext(ole))
        if m:
            meta.amount = int(m.group(1).replace(",", ""))

        # 견적일자
        m = search(_RE_DATE, prv) or search(_RE_DATE, body or _read_bodytext(ole))
        if m:
            y, mo, d = m.groups()
            meta.date = f"{y}-{int(mo):02d}-{int(d):02d}"

        # 견적번호
        m = search(_RE_QUOTE_NO, prv) or search(_RE_QUOTE_NO, body or _read_bodytext(ole))
        if m:
            meta.quote_no = m.group(1).strip()
    except Exception as e:
        meta.error = f"파싱 오류: {e}"
    finally:
        ole.close()

    if not meta.service_name:
        # 파일명 기반 best-effort: "내비온_견적서_XXX.hwp" → XXX
        stem = os.path.splitext(meta.filename)[0]
        parts = stem.split("_")
        meta.service_name = parts[-1] if len(parts) > 1 else stem
    return meta


def scan_folder(folder: str) -> list:
    """폴더 내 .hwp 전수 스캔 + .quote.json 연동."""
    results = []
    if not os.path.isdir(folder):
        return results
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith(".hwp"):
            continue
        path = os.path.join(folder, name)
        meta = parse_hwp(path)
        jpath = os.path.splitext(path)[0] + ".quote.json"
        if os.path.exists(jpath):
            meta.editable = True
            meta.json_path = jpath
        results.append(meta)
    return results
