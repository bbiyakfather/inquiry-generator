# -*- coding: utf-8 -*-
"""회의록 AI 초안 생성 — MINUTES_SCHEMA / 프롬프트 / 정규화.

멀티 프로바이더(Gemini + OpenAI/Anthropic)를 지원한다.
Gemini는 gemini.py의 _post/_gemini_json 패턴을 그대로 재사용하고,
나머지는 llm.complete_json(schema=MINUTES_SCHEMA)을 경유한다.
"""
import json
import time

import requests

from src.ai.llm import (GEMINI_BASE, complete_json, PROVIDER_LABELS,
                        _extract_json)

# ── 스키마 ─────────────────────────────────────────────────────────────────────

SECTION_TYPES = ["header", "bullet", "sub", "empty"]

MINUTES_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "business_name": {
            "type": "STRING",
            "description": "사업명. 입력에 명시된 사업명 그대로. 없으면 빈 문자열.",
        },
        "meeting_date": {
            "type": "STRING",
            "description": "회의 일시. 예: '2026. 06. 11.(수) 14:00~15:30'. 불명확하면 빈 문자열.",
        },
        "meeting_place": {
            "type": "STRING",
            "description": "장소. 예: '내비온 회의실', '온라인 화상회의(Zoom)'. 불명확하면 빈 문자열.",
        },
        "meeting_topic": {
            "type": "STRING",
            "description": "회의주제 한 줄. 회의의 핵심 안건을 간결하게.",
        },
        "participants": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": (
                "기관별 참석자 줄 목록. 첫 줄이 주관기관. 예: "
                "['내비온 장윤화 이사, 김형일', 'KIST 김종민 박사']"
            ),
        },
        "total_count": {
            "type": "INTEGER",
            "description": "총 참석 인원 수.",
        },
        "sections": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "type": {
                        "type": "STRING",
                        "enum": SECTION_TYPES,
                        "description": (
                            "header=■ 섹션 제목, bullet=1차 항목, "
                            "sub=2차 항목(들여쓰기), empty=빈 줄"
                        ),
                    },
                    "text": {"type": "STRING", "description": "항목 내용."},
                },
                "required": ["type", "text"],
            },
            "description": "회의 내용 문단 목록. 반드시 3개 ■ 섹션 포함 (아래 규칙 참조).",
        },
    },
    "required": [
        "business_name", "meeting_date", "meeting_place", "meeting_topic",
        "participants", "total_count", "sections",
    ],
}

# 기초 지침(디렉티브) — 설정 화면에서 사용자가 교체 가능한 부분 (UI 노출용 공개 상수).
# 자리표시자를 두지 않는다: 사용자 편집 텍스트와 동일하게 .format을 통과하지 않기 때문.
MINUTES_DIRECTIVE_DEFAULT = """\
너는 대한민국 정부지원사업 회의록 작성 전문가다.
아래 회의 메모/녹음 텍스트를 분석해 공식 회의록 JSON을 작성하라.

## 필수 규칙
1. sections는 반드시 다음 3개 ■ 섹션 헤더(type=header)를 포함해야 한다:
   - " ■ 주요 회의 내용"
   - " ■ 주요 내용"
   - " ■ 향후 추진 현황"
2. "■ 향후 추진 현황" 섹션 하위 항목은 기관/담당자별 할 일(기한 포함)을 명시한다.
3. 각 ■ 헤더 앞에 empty 문단을 넣어 시각적 구분을 준다 (첫 번째 헤더 앞은 제외).
4. 개조식 한국어. 문어체 금지. 항목은 간결하게(30자 이내 권장).
5. business_name·meeting_date·meeting_place·participants 등 명시된 정보만 사용.
   불명확하면 빈 문자열·빈 배열·0으로 둔다 — 절대 임의 추측 금지.
6. participants 첫 줄은 주관기관(내비온 또는 발주측) 인원. 줄당 같은 기관 참석자.
7. header text 예: " ■ 주요 회의 내용" (앞에 공백 1개, ■ 기호 필수)."""

# 데이터 블록 — 시스템이 항상 자동 첨부 (사용자 편집 불가 → 지침이 어떻든 초안 기능 유지).
_MINUTES_DATA_TMPL = """## 입력
{description}

위 필수 규칙을 반드시 준수하여 JSON으로만 답하라.
"""


def build_minutes_prompt(description: str, directive=None) -> str:
    """directive: 사용자 지정 기초 지침 (없으면 내장 기본).
    불변식: 사용자 텍스트는 str.format을 절대 통과하지 않는다 ({} 포함 안전)."""
    head = str(directive or MINUTES_DIRECTIVE_DEFAULT).strip()
    return head + "\n\n" + _MINUTES_DATA_TMPL.format(description=description.strip())


def _normalize_minutes(data: dict) -> dict:
    """스키마 강제 + 안전 클램프."""
    out = {
        "business_name": str(data.get("business_name") or "").strip()[:80],
        "meeting_date":  str(data.get("meeting_date")  or "").strip()[:60],
        "meeting_place": str(data.get("meeting_place") or "").strip()[:60],
        "meeting_topic": str(data.get("meeting_topic") or "").strip()[:80],
        "participants":  [],
        "total_count":   0,
        "sections":      [],
    }

    for line in (data.get("participants") or []):
        s = str(line).strip()
        if s:
            out["participants"].append(s[:100])

    try:
        out["total_count"] = max(0, int(data.get("total_count") or 0))
    except (ValueError, TypeError):
        out["total_count"] = 0

    for sec in (data.get("sections") or []):
        ptype = str(sec.get("type") or "").strip().lower()
        if ptype not in SECTION_TYPES:
            ptype = "empty"
        text = str(sec.get("text") or "").strip()
        out["sections"].append({"type": ptype, "text": text})

    return out


# ── Gemini 직접 경로 ───────────────────────────────────────────────────────────

def _draft_gemini(description: str, api_key: str, model: str, timeout: int,
                  directive=None) -> dict:
    prompt = build_minutes_prompt(description, directive=directive)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": MINUTES_SCHEMA,
        },
    }
    url = f"{GEMINI_BASE}/models/{model}:generateContent"

    last_err = ""
    for attempt in range(3):
        try:
            r = requests.post(
                url, json=payload, timeout=timeout,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})
        except requests.Timeout:
            return {"ok": False, "error": f"Gemini 응답 시간 초과({timeout}초)."}
        except Exception as e:
            return {"ok": False, "error": f"네트워크 오류: {e}"}

        if r.status_code == 200:
            try:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                draft = _extract_json(text)
                return {"ok": True, "draft": _normalize_minutes(draft)}
            except Exception as e:
                last_err = f"응답 파싱 실패: {e}"
                continue
        elif r.status_code == 429:
            delay = 8 * (attempt + 1)
            if attempt < 2:
                time.sleep(min(delay, 30))
                continue
            last_err = "무료 사용량 한도 초과(429). 잠시 후 다시 시도하세요."
        elif r.status_code == 503:
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
                continue
            last_err = "Gemini 서버가 일시적으로 과부하 상태입니다(503)."
        elif r.status_code == 404 or (r.status_code == 400 and "not found" in r.text.lower()):
            return {"ok": False, "model_error": True, "error": (
                f"선택한 AI 모델 '{model}'을(를) 사용할 수 없습니다.\n"
                "설정 화면에서 모델을 변경하세요.")}
        elif r.status_code in (400, 401, 403):
            return {"ok": False, "error": (
                f"API 키 또는 요청 오류 (HTTP {r.status_code}).\n{r.text[:160]}")}
        else:
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
    return {"ok": False, "error": last_err or "Gemini 호출 실패"}


# ── 공개 API ─────────────────────────────────────────────────────────────────

def draft_minutes(provider: str, description: str, api_key: str, model: str,
                  timeout: int = 60, directive=None) -> dict:
    """프로바이더 공통 회의록 초안.
    반환: {ok, draft?: normalized MINUTES_SCHEMA dict, error?, model_error?}
    """
    if not api_key:
        label = PROVIDER_LABELS.get(provider, provider)
        return {"ok": False, "error": f"{label} API 키가 설정되지 않았습니다. 설정 화면에서 입력하세요."}

    if provider == "gemini":
        return _draft_gemini(description, api_key, model, timeout, directive=directive)

    prompt = build_minutes_prompt(description, directive=directive)
    r = complete_json(provider, api_key, model, prompt,
                      schema=MINUTES_SCHEMA, timeout=timeout)
    if not r.get("ok"):
        return r
    return {"ok": True, "draft": _normalize_minutes(r["data"])}
