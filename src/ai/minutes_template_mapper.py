# -*- coding: utf-8 -*-
"""회의록 HWPX 템플릿 표 구조 → 데이터 슬롯별 셀좌표 AI 매핑.

견적서의 src/ai/template_mapper.py 와 같은 역할을 HWPX(셀 좌표) 방식으로 수행한다.
커스텀 회의록 양식의 표를 스캔(src/scan/hwpx_scan.scan_hwpx_grid)한 그리드를
AI에 주고, 각 표준 슬롯의 값이 들어갈 셀(row,col)을 받는다.
결과는 템플릿 옆 .minutes.fieldmap.json 으로 캐시되며 build_minutes(cell_map=)로 전달된다.

minutes.fieldmap.json 구조:
  {
    "version": 1,
    "template": "파일명.hwpx",
    "is_standard": false,         # DEFAULT_CELLS 와 동일하면 true
    "cell_map": {"business_name": [1,1], "meeting_date": [2,1], ...},
    "unmapped": ["content"]       # 셀을 못 찾은 슬롯
  }
"""
import json
import os

from src.ai import llm
from src.minutes.hwpx_minutes import DEFAULT_CELLS

# 표준 데이터 슬롯 → 한국어 설명 (AI 매핑 대상)
MINUTES_SLOTS = {
    "business_name": "사업명 (값이 들어갈 셀)",
    "meeting_date":  "회의 일시 (값이 들어갈 셀)",
    "meeting_place": "회의 장소 (값이 들어갈 셀)",
    "meeting_topic": "회의 주제/안건 (값이 들어갈 셀)",
    "participants":  "참석자 명단 (다중 줄이 들어갈 셀)",
    "total_count":   "총 참석 인원 '(총 N명)' (값이 들어갈 셀)",
    "content":       "회의 내용 본문 (섹션·본문이 들어갈 셀)",
}

_PROMPT_TMPL = """당신은 한글(HWPX) 회의록 표 양식 분석가입니다.

아래는 회의록 양식 표의 모든 셀입니다. 각 셀은 (행,열): 텍스트 형식이며,
텍스트는 라벨(예: "사업명", "일 시")이거나 기존 샘플값입니다.
보통 라벨 셀 옆/아래의 빈 셀 또는 샘플값 셀이 실제 '값이 들어갈 셀'입니다.

## 표 셀 목록
{grid}

## 채워야 할 표준 슬롯
{slots}

## 작업
각 표준 슬롯에 대해, 그 값이 실제로 입력될 셀의 좌표 [행, 열]을 cell_map으로 반환하세요.
- 라벨 셀(예: "사업명"이라고 적힌 셀)이 아니라, 값이 들어갈 셀의 좌표를 지정합니다.
- 좌표는 위 목록의 (행,열) 숫자를 그대로 사용합니다.
- 적절한 셀을 찾을 수 없는 슬롯은 cell_map에 넣지 말고 unmapped에 슬롯명을 넣으세요.
- 슬롯명을 임의로 만들지 않습니다(목록의 7개만 사용).

JSON으로만 답하세요:
{{"cell_map": {{"business_name": [행,열], ...}}, "unmapped": ["slot", ...]}}
"""


def map_minutes_cells(grid_cells: list, provider: str = "gemini",
                      api_key: str = "", model: str = "gemini-flash-latest",
                      timeout: int = 30) -> dict:
    """표 그리드 → 슬롯별 셀좌표 매핑 (선택된 AI 프로바이더 호출).

    반환: {"ok": bool, "cell_map": {slot: [r,c]}, "unmapped": [slot], "error"?: str}
    """
    if not api_key:
        return {"ok": False, "error": "AI API 키가 없어 자동 분석을 건너뜁니다.",
                "cell_map": {}, "unmapped": list(MINUTES_SLOTS.keys())}

    grid_lines = "\n".join(
        f"  ({c['row']},{c['col']}): {c['text'] or '(빈 셀)'}" for c in grid_cells)
    slot_lines = "\n".join(f"  {k}: {v}" for k, v in MINUTES_SLOTS.items())
    prompt = _PROMPT_TMPL.format(grid=grid_lines, slots=slot_lines)

    # cell_map은 동적 키 객체라 strict 스키마 불가 → JSON 모드(schema=None)
    r = llm.complete_json(provider, api_key, model, prompt, schema=None, timeout=timeout)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error", "AI 호출 실패"),
                "cell_map": {}, "unmapped": list(MINUTES_SLOTS.keys())}

    data = r["data"] or {}
    raw_map = data.get("cell_map", {}) or {}
    cell_map, unmapped = {}, list(data.get("unmapped", []) or [])
    # 검증: 알려진 슬롯 + [정수,정수] 형태만 수용
    for slot, rc in raw_map.items():
        if slot not in MINUTES_SLOTS:
            continue
        try:
            cell_map[slot] = [int(rc[0]), int(rc[1])]
        except (TypeError, ValueError, IndexError):
            if slot not in unmapped:
                unmapped.append(slot)
    # 매핑 안 된 슬롯 보충
    for slot in MINUTES_SLOTS:
        if slot not in cell_map and slot not in unmapped:
            unmapped.append(slot)
    return {"ok": True, "cell_map": cell_map, "unmapped": unmapped}


def _is_standard(cell_map: dict) -> bool:
    """cell_map 이 표준 양식 좌표(DEFAULT_CELLS)와 완전히 동일하면 True."""
    if set(cell_map.keys()) != set(DEFAULT_CELLS.keys()):
        return False
    for slot, (r, c) in DEFAULT_CELLS.items():
        rc = cell_map.get(slot)
        if not rc or int(rc[0]) != r or int(rc[1]) != c:
            return False
    return True


def _fieldmap_path(template_path: str) -> str:
    base = os.path.splitext(template_path)[0]
    return base + ".minutes.fieldmap.json"


def load_minutes_fieldmap(template_path: str) -> dict:
    """템플릿 옆 .minutes.fieldmap.json 로드. 없으면 빈 dict."""
    path = _fieldmap_path(template_path)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_minutes_fieldmap(template_path: str, map_result: dict) -> str:
    """AI 매핑 결과를 .minutes.fieldmap.json 으로 저장."""
    path = _fieldmap_path(template_path)
    cell_map = map_result.get("cell_map", {})
    data = {
        "version": 1,
        "template": os.path.basename(template_path),
        "is_standard": _is_standard(cell_map),
        "cell_map": cell_map,
        "unmapped": map_result.get("unmapped", []),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path
