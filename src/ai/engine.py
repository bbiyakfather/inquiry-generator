# -*- coding: utf-8 -*-
"""AI 디스패처 — 선택된 프로바이더로 견적 초안/모델목록/키검증을 라우팅.

gemini는 기존 gemini.draft_quote(재시도·오류매핑·테스트 검증된 경로)를 그대로 쓰고,
openai/anthropic는 공통 프롬프트(gemini.build_prompt)+llm.complete_json으로 처리한다.
정규화(_normalize)와 스키마(RESPONSE_SCHEMA)는 프로바이더 공통으로 재사용한다.
"""
from src.ai import gemini
from src.ai import llm
from src.ai import minutes as _minutes_mod


def draft_minutes(provider: str, *, description: str,
                  api_key: str, model: str, timeout: int = 60) -> dict:
    """프로바이더 공통 회의록 초안. 반환: {ok, draft?/error?, model_error?}"""
    return _minutes_mod.draft_minutes(provider, description, api_key, model, timeout)


def draft_quote(provider: str, *, description: str, target: int, profit_on: bool,
                expense_budget: int, price_table: dict, year: str,
                api_key: str, model: str, timeout: int = 60) -> dict:
    """프로바이더 공통 견적 초안. 반환: {ok, draft?/error?, model_error?}"""
    if not api_key:
        label = llm.PROVIDER_LABELS.get(provider, provider)
        return {"ok": False, "error": f"{label} API 키가 설정되지 않았습니다. 설정 화면에서 입력하세요."}

    if provider == "gemini":
        return gemini.draft_quote(
            description, int(target), profit_on,
            expense_budget=int(expense_budget), price_table=price_table,
            year=year, api_key=api_key, model=model, timeout=timeout)

    prompt = gemini.build_prompt(description, target, profit_on,
                                 expense_budget, price_table, year)
    r = llm.complete_json(provider, api_key, model, prompt,
                          schema=gemini.RESPONSE_SCHEMA, timeout=timeout)
    if not r.get("ok"):
        return r
    return {"ok": True, "draft": gemini._normalize(r["data"])}


def list_models(provider: str, api_key: str) -> dict:
    if provider == "gemini":
        return gemini.list_text_flash_models(api_key)
    return llm.list_models(provider, api_key)


def validate_key(provider: str, api_key: str) -> dict:
    if provider == "gemini":
        return gemini.validate_key(api_key)
    return llm.validate_key(provider, api_key)
