# -*- coding: utf-8 -*-
"""Google AI Studio (Gemini) 기반 견적 구성 초안 생성.

원칙: AI는 인력 구성·경비 항목·문구만 제안한다. 금액 산정은 전부
결정론적 계산 엔진(goal-seek)이 수행하므로 AI의 숫자는 '구성 비중 힌트'로만 쓰인다.

HTTP 호출·재시도·오류 매핑은 llm.complete_json(프로바이더 공통)으로 일원화.
이 모듈은 견적 도메인(스키마·프롬프트·정규화)과 Gemini 모델 목록 조회만 담당한다.
"""
import requests

from src.ai import llm

API_BASE = llm.GEMINI_BASE

GRADES = ["책임연구원", "연구원", "연구보조원", "보조원"]

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "service_name": {"type": "STRING",
                         "description": "용역명/사업명. RFP에 명시된 사업명이 있으면 그대로, 없으면 과업을 대표하는 간결한 명칭 (예: 'OOO 기술마케팅 및 수요기업 발굴 용역')"},
        "period_text": {"type": "STRING",
                        "description": "용역기간 표기 (예: 계약일로부터 3개월)"},
        "recipient": {"type": "STRING",
                      "description": "수신처(발주기관/수요기업) 기관명. RFP에 발주처·수요기업명이 명시돼 있으면 그 기관명, 불명확하면 빈 문자열(임의 추측 금지)"},
        "personnel": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "grade": {"type": "STRING", "enum": GRADES},
                    "count": {"type": "INTEGER", "description": "투입 인원 수"},
                    "months": {"type": "NUMBER", "description": "참여 기간(월)"},
                    "weight": {"type": "NUMBER",
                               "description": "직급별 참여 비중 힌트 0.05~1.0"},
                },
                "required": ["grade", "count", "months", "weight"],
            },
        },
        "expenses": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING",
                             "description": "경비 항목명 (전문가 활용비, 문헌구입비, 국내여비, 회의비, 인쇄 및 디자인비, SW 활용비 등)"},
                    "details": {"type": "ARRAY", "items": {"type": "STRING"},
                                "description": "'- '로 시작하는 내역 불릿 1~4개"},
                    "qty_text": {"type": "STRING",
                                 "description": "수량 표기 (예: 5명, 1식, 4회, -)"},
                    "qty": {"type": "NUMBER", "description": "수량 숫자 (없으면 1)"},
                    "unit_price": {"type": "INTEGER", "description": "단가(원)"},
                },
                "required": ["name", "details", "qty_text", "qty", "unit_price"],
            },
        },
        "rationale": {"type": "STRING", "description": "구성 근거 2~3문장"},
    },
    "required": ["service_name", "period_text", "personnel", "expenses", "rationale"],
}

# 기초 지침(디렉티브) — 설정 화면에서 사용자가 교체 가능한 부분 (UI 노출용 공개 상수).
# 자리표시자를 두지 않는다: 사용자 편집 텍스트와 동일하게 .format을 통과하지 않기 때문.
QUOTE_DIRECTIVE_DEFAULT = """너는 대한민국 정부 학술연구용역 견적 구성 전문가다.
아래 용역에 대해 인력 구성과 경비 항목 구성을 JSON으로 제안하라.

## 매우 중요한 규칙
1. 금액 계산은 시스템이 한다. 너는 절대 합계를 맞추려 하지 마라.
2. personnel의 weight는 직급별 참여율의 '상대 비중'일 뿐이다 (시스템이 목표금액에 맞게 스케일링).
3. 경비 항목 합계는 '## 조건'의 경비 항목 합계 가이드 이내가 되도록 단가×수량을 구성하라 (초과 시 시스템이 경고).
4. 경비 details는 반드시 "- "로 시작하는 한국어 불릿 1~4개. 예: "- 시장참여자 검증/자문"
5. 용역 내용에 맞는 경비만 선택하라 (보통 2~5개 항목).
6. period_text는 "계약일로부터 N주일" 또는 "계약일로부터 N개월" 형식.
7. months는 실제 수행 기간(월). 3주면 0.75.
8. service_name은 과업 내용을 대표하는 간결한 용역명. RFP에 사업명·과제명이 있으면 그대로 사용.
9. recipient는 RFP에 발주기관·수요기업명이 명시된 경우에만 그 기관명을 넣고, 불명확하면 빈 문자열로 둬라(임의 추측 금지)."""

# 데이터 블록 — 시스템이 항상 자동 첨부 (사용자 편집 불가 → 지침이 어떻든 초안 기능 유지).
# 마지막 줄은 규칙 준수 리마인더(긴 첨부 문서 뒤에서도 지침이 유지되도록).
_QUOTE_DATA_TMPL = """## 용역 설명
{description}

## 조건
- 목표 견적금액: {target:,}원 (부가세 포함)
- 이윤 계상: {profit_text}
- 사용 가능한 직급(이 4개만): 책임연구원, 연구원, 연구보조원, 보조원
- {year}년 학술연구용역 인건비 기준단가(월): {price_table}
- 경비 항목 합계 가이드: 약 {expense_budget:,}원 이내

위 지침과 규칙을 반드시 준수하여 JSON으로만 답하라.
"""


def build_prompt(description: str, target: int, profit_on: bool,
                 expense_budget: int, price_table: dict, year: str,
                 directive=None) -> str:
    """견적 초안 프롬프트 생성 (프로바이더 공통 — engine 디스패처가 재사용).

    directive: 사용자 지정 기초 지침 (없으면 내장 기본).
    불변식: 사용자 텍스트는 str.format을 절대 통과하지 않는다 ({} 포함 안전).
    """
    head = str(directive or QUOTE_DIRECTIVE_DEFAULT).strip()
    return head + "\n\n" + _QUOTE_DATA_TMPL.format(
        description=description.strip(),
        target=int(target),
        profit_text="포함 (10%)" if profit_on else "미계상 (이윤 없는 버전)",
        year=year,
        price_table=", ".join(f"{g} {p:,}원" for g, p in price_table.items()),
        expense_budget=int(expense_budget),
    )


# 텍스트 생성에 부적합해 드롭다운에서 제외할 모델 키워드 (이미지/음성/임베딩 등)
_NON_TEXT = ("-image", "-tts", "-live", "-audio", "embedding", "imagen",
             "veo", "lyria", "nano-banana", "robotics", "aqa")


def list_text_flash_models(api_key: str, timeout: int = 20) -> dict:
    """generateContent 지원 Flash 텍스트 모델 목록 (드롭다운용). 무과금."""
    try:
        r = requests.get(f"{API_BASE}/models",
                         headers={"x-goog-api-key": api_key}, timeout=timeout)
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        out = []
        for m in r.json().get("models", []):
            name = m.get("name", "").replace("models/", "")
            methods = m.get("supportedGenerationMethods", []) or []
            if "generateContent" not in methods:
                continue
            if "flash" not in name.lower():
                continue
            if any(k in name.lower() for k in _NON_TEXT):
                continue
            out.append(name)
        # 최신(높은 버전) 우선 정렬
        out.sort(reverse=True)
        return {"ok": True, "models": out}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def validate_key(api_key: str, timeout: int = 20) -> dict:
    """키 유효성 확인 (모델 목록 조회 — 무과금)."""
    res = list_text_flash_models(api_key, timeout)
    if res.get("ok"):
        return {"ok": True, "models": res["models"][:12]}
    return res


def draft_quote(description: str, target: int, profit_on: bool,
                expense_budget: int, price_table: dict, year: str,
                api_key: str, model: str = "gemini-flash-latest",
                timeout: int = 60, directive=None) -> dict:
    """AI 구성 초안. 반환: {ok, draft?, error?, model_error?}"""
    if not api_key:
        return {"ok": False, "error": "Gemini API 키가 설정되지 않았습니다. 설정 화면에서 입력하세요."}

    prompt = build_prompt(description, target, profit_on, expense_budget,
                          price_table, year, directive=directive)
    r = llm.complete_json("gemini", api_key, model, prompt,
                          schema=RESPONSE_SCHEMA, timeout=timeout,
                          temperature=0.3)
    if not r.get("ok"):
        return r
    return {"ok": True, "draft": _normalize(r["data"])}


def _normalize(draft: dict) -> dict:
    """스키마 강제 + 안전 클램프."""
    out = {"service_name": str(draft.get("service_name", "")).strip()[:80],
           "period_text": str(draft.get("period_text", "")).strip(),
           "recipient": str(draft.get("recipient", "")).strip()[:60],
           "rationale": str(draft.get("rationale", "")).strip(),
           "personnel": [], "expenses": []}
    seen = set()
    for p in draft.get("personnel", []):
        g = str(p.get("grade", "")).strip()
        if g not in GRADES or g in seen:
            continue
        seen.add(g)
        out["personnel"].append({
            "grade": g,
            "count": max(0, min(20, int(p.get("count", 0) or 0))),
            "months": max(0.25, min(36.0, float(p.get("months", 1) or 1))),
            "weight": max(0.05, min(1.0, float(p.get("weight", 0.5) or 0.5))),
        })
    for e in draft.get("expenses", [])[:8]:
        details = [("- " + str(d).lstrip("- ").strip())
                   for d in (e.get("details") or []) if str(d).strip()][:4]
        try:
            unit = max(0, int(e.get("unit_price", 0) or 0))
            qty = max(0.0, float(e.get("qty", 1) or 1))
        except Exception:
            unit, qty = 0, 1
        out["expenses"].append({
            "name": str(e.get("name", "")).strip()[:30] or "기타 경비",
            "details": details,
            "qty_text": str(e.get("qty_text", "")).strip()[:15] or "-",
            "unit_price": unit,
            "qty": qty,
        })
    return out
