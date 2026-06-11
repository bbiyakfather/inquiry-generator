# -*- coding: utf-8 -*-
"""AI 초안 백엔드 — 모델 마이그레이션 + Gemini 에러 매핑 (네트워크 무의존, 모킹)."""
import unittest.mock as mock

from src import api as A
from src.ai import gemini
from src.ai import llm
from src.ai import engine
from src.store import config_store as cs


class TestModelMigration:
    def _api(self, model):
        a = A.Api.__new__(A.Api)            # __init__ 우회 (config/worker 생성 회피)
        a.cfg = {"gemini": {"model": model}}
        return a

    def test_deprecated_migrated_and_saved(self):
        for old in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-pro"):
            a = self._api(old)
            saved = {}
            with mock.patch.object(A.cs, "save_config", lambda c: saved.setdefault("hit", True)):
                a._migrate_model()
            assert a.cfg["gemini"]["model"] == "gemini-flash-latest"
            assert saved.get("hit") is True

    def test_current_model_preserved_not_saved(self):
        a = self._api("gemini-flash-latest")
        saved = {}
        with mock.patch.object(A.cs, "save_config", lambda c: saved.setdefault("hit", True)):
            a._migrate_model()
        assert a.cfg["gemini"]["model"] == "gemini-flash-latest"
        assert "hit" not in saved

    def test_unknown_model_preserved(self):
        # 사용자가 고른 그 외 유효 모델은 보존
        a = self._api("gemini-3.5-flash")
        with mock.patch.object(A.cs, "save_config", lambda c: None):
            a._migrate_model()
        assert a.cfg["gemini"]["model"] == "gemini-3.5-flash"

    def test_corrupt_gemini_not_dict_no_crash(self):
        # 손상 config(gemini가 문자열)에서도 기동이 막히지 않아야 함
        a = A.Api.__new__(A.Api)
        a.cfg = {"gemini": "broken"}
        a._migrate_model()                      # 예외 없이 통과해야 함
        assert a.cfg["gemini"] == "broken"

    def test_dropdown_disjoint_from_deprecated(self):
        # 불변식: 드롭다운 선택지가 마이그레이션 대상과 겹치면 사용자 선택이 되돌아감
        from src.store.config_store import GEMINI_MODELS
        ids = {m["id"] for m in GEMINI_MODELS}
        assert ids.isdisjoint(A._DEPRECATED_MODELS)


class TestNormalizeServiceName:
    def test_service_name_extracted_and_clamped(self):
        out = gemini._normalize({"service_name": " 기술마케팅 및 수요기업 발굴 용역 ",
                                 "personnel": [], "expenses": []})
        assert out["service_name"] == "기술마케팅 및 수요기업 발굴 용역"

    def test_service_name_missing_is_blank(self):
        out = gemini._normalize({"personnel": [], "expenses": []})
        assert out["service_name"] == ""

    def test_recipient_extracted_and_clamped(self):
        out = gemini._normalize({"recipient": "  한국과학기술연구원  ",
                                 "personnel": [], "expenses": []})
        assert out["recipient"] == "한국과학기술연구원"

    def test_recipient_missing_is_blank(self):
        out = gemini._normalize({"personnel": [], "expenses": []})
        assert out["recipient"] == ""


class TestGeminiErrorMapping:
    _ARGS = dict(description="기술 마케팅 및 수요기업 발굴 용역입니다",
                 target=19000000, profit_on=True, expense_budget=5000000,
                 price_table={"책임연구원": 7567456}, year="2026", api_key="FAKE")

    def test_404_is_model_error_korean(self):
        fake = mock.Mock(status_code=404)
        with mock.patch.object(gemini.requests, "post", return_value=fake):
            r = gemini.draft_quote(model="gemini-2.5-flash", **self._ARGS)
        assert r["ok"] is False
        assert r.get("model_error") is True
        assert "설정" in r["error"] and "모델" in r["error"]

    def test_400_not_found_is_model_error(self):
        fake = mock.Mock(status_code=400, text="models/x is not found for API version")
        with mock.patch.object(gemini.requests, "post", return_value=fake):
            r = gemini.draft_quote(model="bad", **self._ARGS)
        assert r["ok"] is False
        assert r.get("model_error") is True

    def test_403_is_key_error_not_model(self):
        fake = mock.Mock(status_code=403, text="permission denied")
        with mock.patch.object(gemini.requests, "post", return_value=fake):
            r = gemini.draft_quote(**self._ARGS)
        assert r["ok"] is False
        assert not r.get("model_error")
        assert "키" in r["error"]

    def test_no_key_short_circuits(self):
        r = gemini.draft_quote(description="x" * 20, target=1, profit_on=True,
                               expense_budget=0, price_table={}, year="2026", api_key="")
        assert r["ok"] is False
        assert "키" in r["error"]


class TestSchemaConversion:
    def test_gemini_to_jsonschema_lowercases_and_locks(self):
        std = llm.gemini_to_jsonschema(gemini.RESPONSE_SCHEMA)
        assert std["type"] == "object"
        assert std["additionalProperties"] is False
        assert set(std["required"]) >= {"service_name", "personnel", "expenses"}
        # 중첩 배열 아이템도 변환
        person = std["properties"]["personnel"]["items"]
        assert person["type"] == "object"
        assert person["properties"]["count"]["type"] == "integer"
        assert person["additionalProperties"] is False

    def test_dynamic_key_object_unrepresentable(self):
        # additionalProperties가 스키마면 strict json_schema로 표현 불가 → None
        sch = {"type": "OBJECT",
               "properties": {"m": {"type": "OBJECT",
                                    "additionalProperties": {"type": "STRING"}}}}
        assert llm.gemini_to_jsonschema(sch) is None

    def test_extract_json_strips_fences(self):
        assert llm._extract_json('```json\n{"a": 1}\n```') == {"a": 1}
        assert llm._extract_json('답: {"b": 2} 끝') == {"b": 2}


class TestProviderDispatch:
    _ARGS = dict(description="기술 마케팅 및 수요기업 발굴 용역입니다",
                 target=19000000, profit_on=True, expense_budget=5000000,
                 price_table={"책임연구원": 7567456}, year="2026")

    def test_gemini_routes_to_gemini_module(self):
        with mock.patch.object(gemini, "draft_quote",
                               return_value={"ok": True, "draft": {}}) as gd:
            r = engine.draft_quote("gemini", api_key="K", model="gemini-flash-latest",
                                   **self._ARGS)
        assert r["ok"] and gd.called

    def test_openai_routes_through_llm(self):
        payload = {"service_name": "x", "period_text": "", "personnel": [],
                   "expenses": [], "rationale": ""}
        with mock.patch.object(llm, "complete_json",
                               return_value={"ok": True, "data": payload}) as cj:
            r = engine.draft_quote("openai", api_key="K", model="gpt-5.1", **self._ARGS)
        assert r["ok"] and cj.called
        assert cj.call_args[0][0] == "openai"        # provider
        assert "draft" in r

    def test_missing_key_blocks(self):
        r = engine.draft_quote("anthropic", api_key="", model="claude-opus-4-8",
                               **self._ARGS)
        assert r["ok"] is False and "키" in r["error"]


class TestLLMErrorMapping:
    def test_openai_404_is_model_error(self):
        fake = mock.Mock(status_code=404, text="model gpt-x does not exist")
        with mock.patch.object(llm.requests, "post", return_value=fake):
            r = llm.complete_json("openai", "K", "gpt-x", "p")
        assert r["ok"] is False and r.get("model_error") is True

    def test_openai_401_is_key_error(self):
        fake = mock.Mock(status_code=401, text="invalid api key")
        with mock.patch.object(llm.requests, "post", return_value=fake):
            r = llm.complete_json("openai", "bad", "gpt-5.1", "p")
        assert r["ok"] is False and not r.get("model_error")
        assert "키" in r["error"]

    def test_anthropic_404_is_model_error(self):
        fake = mock.Mock(status_code=404, text="not_found_error")
        with mock.patch.object(llm.requests, "post", return_value=fake):
            r = llm.complete_json("anthropic", "K", "claude-x", "p")
        assert r["ok"] is False and r.get("model_error") is True

    def test_anthropic_success_parses_text_block(self):
        fake = mock.Mock(status_code=200)
        fake.json.return_value = {"content": [{"type": "text", "text": '{"ok": 1}'}]}
        with mock.patch.object(llm.requests, "post", return_value=fake):
            r = llm.complete_json("anthropic", "K", "claude-opus-4-8", "p")
        assert r["ok"] and r["data"] == {"ok": 1}


class TestMultiProviderConfig:
    def _cfg(self):
        import copy
        return copy.deepcopy(cs.DEFAULT_CONFIG)

    def test_default_provider_is_gemini(self):
        assert cs.get_provider(self._cfg()) == "gemini"

    def test_set_and_get_provider(self):
        cfg = self._cfg()
        with mock.patch.object(cs, "save_config", lambda c: None):
            cs.set_provider(cfg, "anthropic")
        assert cs.get_provider(cfg) == "anthropic"

    def test_unknown_provider_rejected(self):
        cfg = self._cfg()
        with mock.patch.object(cs, "save_config", lambda c: None):
            try:
                cs.set_provider(cfg, "bogus")
                assert False, "should raise"
            except ValueError:
                pass

    def test_per_provider_model_independent(self):
        cfg = self._cfg()
        with mock.patch.object(cs, "save_config", lambda c: None):
            cs.set_ai_model(cfg, "openai", "gpt-5")
            cs.set_ai_model(cfg, "anthropic", "claude-sonnet-4-6")
        assert cs.get_ai_model(cfg, "openai") == "gpt-5"
        assert cs.get_ai_model(cfg, "anthropic") == "claude-sonnet-4-6"
        assert cs.get_ai_model(cfg, "gemini") == "gemini-flash-latest"

    def test_gemini_key_backcompat(self):
        # gemini 키는 최상위 cfg['gemini']에 저장되어 get_ai_key/get_gemini_key 동일
        cfg = self._cfg()
        with mock.patch.object(cs, "save_config", lambda c: None):
            cs.set_ai_key(cfg, "gemini", "GKEY")
        assert cfg["gemini"]["api_key_enc"]  # 최상위에 저장됨
