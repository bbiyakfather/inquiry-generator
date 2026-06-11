# -*- coding: utf-8 -*-
"""HWP 템플릿 커스텀 필드명 → 표준 슬롯명 AI 매핑.

표준 슬롯 카탈로그(107개 필드)를 선택된 AI 프로바이더에 전달하고,
템플릿의 낯선 필드명을 어느 슬롯에 매핑할지 JSON으로 반환받는다.
결과는 템플릿 옆에 .fieldmap.json으로 캐시되며, 생성 시
src/hwp/hwp_writer._load_fieldmap_for()가 이 파일을 읽는다 (포맷 변경 시 양쪽 동기화).

fieldmap.json 구조:
  {
    "version": 1,
    "template": "파일명.hwp",
    "is_standard": false,
    "max_labor": 4,            # 템플릿의 인건비 행 수
    "max_exp": 8,              # 템플릿의 경비 행 수
    "field_map": {
      "recv_org": "recv",      # 템플릿 필드명 → 표준 슬롯명
      "total_won": "final_amt"
    },
    "unmapped": ["unknown_field"]
  }
"""
import json
import os

from src.ai import llm

# 표준 슬롯 카탈로그: 필드명 → 한국어 설명
STANDARD_CATALOG = {
    "recv":            "수신기관명 (누름틀)",
    "quote_no":        "견적번호 (누름틀)",
    "ref_name":        "참조자 이름 (누름틀)",
    "ref_tel":         "참조자 전화번호 (누름틀)",
    "quote_date":      "견적일자 (누름틀)",
    "svc_name":        "용역명 (셀필드)",
    "svc_period":      "용역기간 (셀필드)",
    "amount_kor":      "견적금액 한글 표기 (셀필드)",
    "labor_sum_amt":   "인건비 합계 금액",
    "labor_sum_ratio": "인건비 합계 구성비",
    "exp_sum_amt":     "경비 합계 금액",
    "exp_sum_ratio":   "경비 합계 구성비",
    "subtotal_amt":    "소계(인건비+경비) 금액",
    "subtotal_ratio":  "소계 구성비",
    "mgmt_basis":      "일반관리비 산출 기준 텍스트",
    "mgmt_amt":        "일반관리비 금액",
    "mgmt_ratio":      "일반관리비 구성비",
    "profit_basis":    "이윤 산출 기준 텍스트",
    "profit_amt":      "이윤 금액",
    "profit_ratio":    "이윤 구성비",
    "supply_amt":      "공급가액(총계) 금액",
    "supply_ratio":    "공급가액 구성비",
    "vat_basis":       "부가세 산출 기준 텍스트",
    "vat_amt":         "부가세 금액",
    "vat_ratio":       "부가세 구성비",
    "trim_label":      "절삭 행 라벨",
    "trim_basis":      "절삭 산출 기준 텍스트",
    "trim_amt":        "절삭 금액",
    "trim_ratio":      "절삭 구성비",
    "final_amt":       "최종 견적 금액",
    "final_ratio":     "최종 견적 구성비",
}
# laborN_* (N=1..4), expN_* (N=1..8) 는 프롬프트에서 패턴 설명

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "field_map": {
            "type": "OBJECT",
            "description": "template_field_name → standard_slot_name. 매핑 불가능한 필드는 포함하지 않는다.",
            "additionalProperties": {"type": "STRING"},
        },
        "unmapped": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "표준 슬롯에 대응되지 않는 템플릿 필드명 목록",
        },
    },
    "required": ["field_map", "unmapped"],
}

_PROMPT_TMPL = """당신은 한글(HWP) 견적서 템플릿 필드 분석가입니다.

아래 템플릿에서 발견된 비표준 필드명들을 표준 슬롯명으로 매핑하세요.

## 표준 슬롯 카탈로그
{catalog}

## 연번 패턴 (N=정수)
- laborN_grade / laborN_cnt / laborN_price / laborN_months / laborN_rate / laborN_amt / laborN_ratio
  → N번째 인건비 행의 직급/투입인원/단가/참여기간/참여율/금액/구성비
- expN_name / expN_detail / expN_qty / expN_price / expN_amt / expN_ratio
  → N번째 경비 행의 항목명/내역/수량/단가/금액/구성비

## 매핑 대상 비표준 필드명
{unknown_fields}

## 규칙
1. 의미가 명확히 일치하는 경우에만 매핑한다.
2. 확실하지 않은 필드는 unmapped에 포함한다.
3. 표준 슬롯명을 임의 생성하지 않는다.
4. 연번 패턴 필드는 N을 그대로 유지한다 (예: recv_org → recv, total_won1 → final_amt 불가).
"""


def map_unknown_fields(unknown_fields: list, provider: str = "gemini",
                       api_key: str = "", model: str = "gemini-flash-latest",
                       timeout: int = 30) -> dict:
    """비표준 필드명 → 표준 슬롯명 매핑 (선택된 AI 프로바이더 호출).

    반환: {"ok": bool, "field_map": dict, "unmapped": list, "error"?: str}
    """
    if not unknown_fields:
        return {"ok": True, "field_map": {}, "unmapped": []}
    if not api_key:
        return {"ok": False, "error": "AI API 키가 없어 자동 매핑을 건너뜁니다.",
                "field_map": {}, "unmapped": unknown_fields}

    catalog_lines = "\n".join(f"  {k}: {v}" for k, v in STANDARD_CATALOG.items())
    unknown_lines = "\n".join(f"  - {f}" for f in unknown_fields)
    prompt = _PROMPT_TMPL.format(catalog=catalog_lines, unknown_fields=unknown_lines)

    # field_map은 동적 키 객체라 strict 스키마로 표현 불가 → JSON 모드만 사용(schema=None)
    r = llm.complete_json(provider, api_key, model, prompt, schema=None, timeout=timeout)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error", "AI 호출 실패"),
                "field_map": {}, "unmapped": unknown_fields}
    data = r["data"]
    return {"ok": True,
            "field_map": data.get("field_map", {}) or {},
            "unmapped": data.get("unmapped", []) or []}


def load_fieldmap(template_path: str) -> dict:
    """템플릿 옆 .fieldmap.json 로드. 없으면 빈 dict."""
    path = _fieldmap_path(template_path)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_fieldmap(template_path: str, scan_result: dict, map_result: dict) -> str:
    """스캔 결과 + AI 매핑 결과를 .fieldmap.json으로 저장."""
    path = _fieldmap_path(template_path)
    data = {
        "version": 1,
        "template": os.path.basename(template_path),
        "is_standard": scan_result.get("is_standard", False),
        "max_labor": scan_result.get("max_labor", 4),
        "max_exp": scan_result.get("max_exp", 8),
        "field_map": map_result.get("field_map", {}),
        "unmapped": map_result.get("unmapped", []),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def _fieldmap_path(template_path: str) -> str:
    base = os.path.splitext(template_path)[0]
    return base + ".fieldmap.json"
