# -*- coding: utf-8 -*-
"""AI 초안 기초 지침(디렉티브) 편집 기능 — 프롬프트 조립·설정 저장·배선 (네트워크 무의존).

핵심 불변식:
1. 사용자 directive는 str.format을 절대 통과하지 않는다 ({} 포함 안전).
2. 데이터 블록(용역 설명·조건 / 입력)은 directive와 무관하게 항상 첨부된다.
3. 기본값과 동일한 텍스트 저장은 ""(오버라이드 해제)로 정규화된다.
"""
import copy
import unittest.mock as mock

import pytest

from src import api as A
from src.ai import engine, gemini, llm
from src.ai import minutes as minutes_mod
from src.store import config_store as cs

PRICES = {"책임연구원": 7567456, "연구원": 5802624}


def _quote_prompt(directive=None):
    return gemini.build_prompt("테스트 과업입니다", 19000000, False,
                               5000000, PRICES, "2026", directive=directive)


class TestQuoteDirective:
    def test_default_contains_directive_and_data(self):
        p = _quote_prompt()
        assert "정부 학술연구용역 견적 구성 전문가" in p          # 기본 역할
        assert "## 매우 중요한 규칙" in p
        assert "## 용역 설명" in p and "테스트 과업입니다" in p   # 데이터 블록
        assert "## 조건" in p
        assert "19,000,000원" in p
        assert "약 5,000,000원 이내" in p                        # 경비 가이드(조건으로 이동)
        assert "책임연구원 7,567,456원" in p

    def test_custom_directive_replaces_head_keeps_data(self):
        p = _quote_prompt(directive="너는 테스트 봇이다.")
        assert p.startswith("너는 테스트 봇이다.")
        assert "견적 구성 전문가" not in p                       # 기본 지침 미포함
        # 불변식: 데이터 블록은 그대로
        assert "## 용역 설명" in p and "테스트 과업입니다" in p
        assert "## 조건" in p and "19,000,000원" in p

    def test_braces_in_directive_safe(self):
        # 사용자 지침에 중괄호(JSON 예시·{description} 등)가 있어도 크래시 없이 원문 유지
        d = '규칙: {"json": 1} 형식. {description} 같은 표기도 그대로.'
        p = _quote_prompt(directive=d)
        assert d in p
        assert "테스트 과업입니다" in p


class TestMinutesDirective:
    def test_default_contains_directive_and_data(self):
        p = minutes_mod.build_minutes_prompt("회의 메모입니다")
        assert "회의록 작성 전문가" in p
        assert "## 필수 규칙" in p
        assert "## 입력" in p and "회의 메모입니다" in p

    def test_custom_directive_replaces_head_keeps_data(self):
        p = minutes_mod.build_minutes_prompt("회의 메모입니다", directive="너는 회의 요약 봇이다.")
        assert p.startswith("너는 회의 요약 봇이다.")
        assert "회의록 작성 전문가" not in p
        assert "## 입력" in p and "회의 메모입니다" in p

    def test_braces_in_directive_safe(self):
        d = '출력 예: {"sections": []} 그대로 둘 것.'
        p = minutes_mod.build_minutes_prompt("회의 메모입니다", directive=d)
        assert d in p and "회의 메모입니다" in p


class TestEngineDirective:
    def test_defaults_dict_invariants(self):
        # 키 집합이 config_store와 일치 + 비공백 + 자리표시자 0개(.format 미통과 전제)
        assert set(engine.DIRECTIVE_DEFAULTS) == set(cs.AI_PROMPT_DOC_TYPES)
        for v in engine.DIRECTIVE_DEFAULTS.values():
            assert v.strip()
            assert "{" not in v and "}" not in v

    def test_gemini_quote_route_passes_directive(self):
        with mock.patch.object(gemini, "draft_quote",
                               return_value={"ok": True, "draft": {}}) as gd:
            engine.draft_quote("gemini", description="x", target=1000,
                               profit_on=False, expense_budget=0, price_table={},
                               year="2026", api_key="k", model="m", directive="DIR")
        assert gd.call_args.kwargs["directive"] == "DIR"

    def test_openai_quote_route_prompt_starts_with_directive(self):
        with mock.patch.object(llm, "complete_json",
                               return_value={"ok": False, "error": "stop"}) as cj:
            engine.draft_quote("openai", description="x", target=1000,
                               profit_on=False, expense_budget=0, price_table={},
                               year="2026", api_key="k", model="m", directive="DIR")
        prompt = cj.call_args[0][3]        # complete_json(provider, key, model, prompt)
        assert prompt.startswith("DIR")

    def test_minutes_route_passes_directive(self):
        with mock.patch.object(engine._minutes_mod, "draft_minutes",
                               return_value={"ok": True, "draft": {}}) as dm:
            engine.draft_minutes("gemini", description="x", api_key="k",
                                 model="m", directive="DIR")
        assert dm.call_args.kwargs["directive"] == "DIR"


class TestConfigStorePrompts:
    def test_default_config_shape(self):
        assert cs.DEFAULT_CONFIG["ai_prompts"] == {"quote": "", "minutes": ""}

    def test_merge_upgrades_old_config(self):
        # ai_prompts 없는 구버전 config도 로드 시 기본형으로 승급
        merged = cs._merge(cs.DEFAULT_CONFIG, {"gemini": {"model": "x"}})
        assert merged["ai_prompts"] == {"quote": "", "minutes": ""}

    def test_roundtrip(self):
        cfg = copy.deepcopy(cs.DEFAULT_CONFIG)
        with mock.patch.object(cs, "save_config", lambda c: None):
            cs.set_ai_prompt(cfg, "quote", "나만의 지침")
        assert cs.get_ai_prompt(cfg, "quote") == "나만의 지침"
        assert cs.get_ai_prompt(cfg, "minutes") == ""

    def test_invalid_doc_type_raises(self):
        cfg = copy.deepcopy(cs.DEFAULT_CONFIG)
        with pytest.raises(ValueError):
            cs.set_ai_prompt(cfg, "unknown", "x")

    def test_non_string_value_defended(self):
        cfg = copy.deepcopy(cs.DEFAULT_CONFIG)
        cfg["ai_prompts"]["quote"] = 123
        assert cs.get_ai_prompt(cfg, "quote") == ""


def _api():
    a = A.Api.__new__(A.Api)               # __init__ 우회 (기존 테스트 관례)
    a.cfg = copy.deepcopy(cs.DEFAULT_CONFIG)
    return a


class TestApiSetAiPrompt:
    def test_custom_saved_normalized(self):
        a = _api()
        with mock.patch.object(cs, "save_config", lambda c: None):
            r = a.set_ai_prompt("minutes", "  나만의 지침\r\n둘째 줄  ")
        assert r["ok"] and r["custom"] is True
        assert r["text"] == "나만의 지침\n둘째 줄"
        assert a.cfg["ai_prompts"]["minutes"] == "나만의 지침\n둘째 줄"

    def test_same_as_default_clears_override(self):
        # 기본값을 \r\n·꼬리 개행만 바꿔 저장해도 "" (기본값 동결 방지)
        a = _api()
        text = engine.DIRECTIVE_DEFAULTS["quote"].replace("\n", "\r\n") + "\r\n"
        with mock.patch.object(cs, "save_config", lambda c: None):
            r = a.set_ai_prompt("quote", text)
        assert r["ok"] and r["custom"] is False and r["text"] == ""
        assert a.cfg["ai_prompts"]["quote"] == ""

    def test_empty_clears_override(self):
        a = _api()
        a.cfg["ai_prompts"]["quote"] = "이전 지침"
        with mock.patch.object(cs, "save_config", lambda c: None):
            r = a.set_ai_prompt("quote", "   ")
        assert r["ok"] and r["custom"] is False
        assert a.cfg["ai_prompts"]["quote"] == ""

    def test_invalid_doc_type(self):
        a = _api()
        r = a.set_ai_prompt("unknown", "x")
        assert not r["ok"]

    def test_too_long_rejected(self):
        a = _api()
        r = a.set_ai_prompt("quote", "가" * (A._AI_PROMPT_MAX + 1))
        assert not r["ok"] and "너무" in r["error"]

    def test_get_config_exposes_prompts_and_defaults(self):
        a = _api()
        a.cfg["ai_prompts"]["minutes"] = "커스텀"
        c = a.get_config()["config"]
        assert c["ai_prompts"] == {"quote": "", "minutes": "커스텀"}
        assert c["ai_prompt_defaults"] == engine.DIRECTIVE_DEFAULTS


class TestDraftDirectiveWiring:
    def test_ai_draft_passes_override_or_none(self):
        for stored, expected in [("커스텀 지침", "커스텀 지침"), ("", None)]:
            a = _api()
            a.cfg["ai_prompts"]["quote"] = stored
            with mock.patch.object(A.ai_engine, "draft_quote",
                                   return_value={"ok": False, "error": "stop"}) as dq:
                r = a.ai_draft({"description": "충분히 긴 과업 설명입니다", "target": 19000000})
            assert r["error"] == "stop"
            assert dq.call_args.kwargs["directive"] == expected

    def test_minutes_draft_passes_override_or_none(self):
        for stored, expected in [("커스텀 지침", "커스텀 지침"), ("", None)]:
            a = _api()
            a.cfg["ai_prompts"]["minutes"] = stored
            with mock.patch.object(A.ai_engine, "draft_minutes",
                                   return_value={"ok": False, "error": "stop"}) as dm:
                r = a.minutes_draft({"description": "회의 메모입니다"})
            assert r["error"] == "stop"
            assert dm.call_args.kwargs["directive"] == expected
