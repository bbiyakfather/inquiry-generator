# -*- coding: utf-8 -*-
"""회의록 HWPX 스캐너 — 한글 실행 없이 zipfile + ElementTree로 메타데이터 추출.

대상 양식: templates/회의록_양식.hwpx (7행×3열 표 — src/minutes/hwpx_minutes.py 참조)
  row 1 col 1: 사업명 / row 2: 일시 / row 3: 장소 / row 4: 회의주제
  row 5 col 2: "(총 N명)"

1차: Contents/section0.xml 셀 직접 파싱 (이 양식으로 만든 모든 파일에 견고)
2차: Preview/PrvText.txt 정규식 (build_minutes가 기록하는 고정 포맷)
폴백: 파일명 stem을 topic으로, error="양식 불일치" — 목록에서 빠지지 않게
      (hwp_scan.parse_hwp의 파일명 폴백 UX와 일관)
"""
import os
import re
import zipfile
from dataclasses import dataclass, asdict
from typing import Optional
from xml.etree import ElementTree as ET

# 셀 탐색 로직·네임스페이스는 생성 엔진과 단일 소스 공유 (중복 금지)
from src.minutes.hwpx_minutes import _HP, _find_cell

_RE_TOTAL = re.compile(r"총\s*(\d+)\s*명")
_RE_DATE_ISO = re.compile(r"(\d{4})[-.\s년]+(\d{1,2})[-.\s월]+(\d{1,2})")
# PrvText 포맷: "<사업명><...>" (hwpx_minutes.build_minutes step 7이 기록)
_RE_PRV = {
    "business_name": re.compile(r"<사업명><([^>]*)>"),
    "date": re.compile(r"<일\s*시><([^>]*)>"),
    "place": re.compile(r"<장\s*소><([^>]*)>"),
    "topic": re.compile(r"<회의주제><([^>]*)>"),
}


@dataclass
class MinutesMeta:
    path: str
    filename: str
    business_name: str = ""
    topic: str = ""
    date: str = ""            # 원문 (예: "2026. 04. 09.(목) 09:17~09:52")
    date_iso: str = ""        # YYYY-MM-DD (통계용 best-effort, 실패 시 "")
    place: str = ""
    total_count: Optional[int] = None
    source: str = "hwpx"
    editable: bool = False    # 같은 베이스명 .minutes.json 존재 여부
    json_path: str = ""
    mtime: float = 0.0
    error: str = ""

    def to_dict(self):
        return asdict(self)


def _cell_text(tbl, row, col) -> str:
    """셀 내 모든 문단의 텍스트를 줄바꿈으로 합쳐 반환."""
    tc = _find_cell(tbl, row, col)
    if tc is None:
        return ""
    sublist = tc.find(f"{_HP}subList")
    if sublist is None:
        return ""
    lines = []
    for p in sublist.findall(f"{_HP}p"):
        parts = [t.text or "" for t in p.findall(f".//{_HP}t")]
        line = "".join(parts).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _date_to_iso(date_str: str) -> str:
    m = _RE_DATE_ISO.search(date_str or "")
    if not m:
        return ""
    y, mo, d = m.groups()
    try:
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    except ValueError:
        return ""


def _parse_section0(zf: zipfile.ZipFile, meta: MinutesMeta) -> bool:
    """section0.xml 셀 파싱. 양식 표를 찾아 topic을 채우면 True."""
    try:
        with zf.open("Contents/section0.xml") as fp:
            root = ET.parse(fp).getroot()
    except (KeyError, ET.ParseError):
        return False
    tbl = root.find(f".//{_HP}tbl")
    if tbl is None:
        return False
    meta.business_name = _cell_text(tbl, 1, 1)
    meta.date = _cell_text(tbl, 2, 1)
    meta.place = _cell_text(tbl, 3, 1)
    meta.topic = _cell_text(tbl, 4, 1)
    m = _RE_TOTAL.search(_cell_text(tbl, 5, 2))
    if m:
        meta.total_count = int(m.group(1))
    return bool(meta.topic or meta.business_name)


def _parse_prvtext(zf: zipfile.ZipFile, meta: MinutesMeta) -> bool:
    """Preview/PrvText.txt 정규식 폴백."""
    try:
        with zf.open("Preview/PrvText.txt") as fp:
            text = fp.read().decode("utf-8", errors="replace")
    except KeyError:
        return False
    for field, rx in _RE_PRV.items():
        m = rx.search(text)
        if m:
            setattr(meta, field, m.group(1).strip())
    m = _RE_TOTAL.search(text)
    if m:
        meta.total_count = int(m.group(1))
    return bool(meta.topic or meta.business_name)


def parse_minutes_hwpx(path: str) -> MinutesMeta:
    meta = MinutesMeta(path=path, filename=os.path.basename(path))
    try:
        meta.mtime = os.path.getmtime(path)
    except OSError:
        pass
    try:
        with zipfile.ZipFile(path) as zf:
            ok = _parse_section0(zf, meta)
            if not ok:
                ok = _parse_prvtext(zf, meta)
    except (zipfile.BadZipFile, OSError) as e:
        ok = False
        meta.error = f"파일 열기 실패: {e}"
    if not ok and not meta.error:
        meta.error = "양식 불일치 (내비온 회의록 양식 아님)"
    if not meta.topic:
        # 파일명 기반 best-effort: "회의록_XXX_260409.hwpx" → XXX
        stem = os.path.splitext(meta.filename)[0]
        parts = stem.split("_")
        meta.topic = parts[1] if len(parts) >= 2 and parts[0] == "회의록" else stem
    meta.date_iso = _date_to_iso(meta.date)
    return meta


def scan_folder(folder: str) -> list:
    """폴더 내 .hwpx 전수 스캔 + .minutes.json 사이드카 연동."""
    results = []
    if not os.path.isdir(folder):
        return results
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith(".hwpx"):
            continue
        path = os.path.join(folder, name)
        meta = parse_minutes_hwpx(path)
        jpath = os.path.splitext(path)[0] + ".minutes.json"
        if os.path.exists(jpath):
            meta.editable = True
            meta.json_path = jpath
        results.append(meta)
    return results
