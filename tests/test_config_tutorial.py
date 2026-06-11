# -*- coding: utf-8 -*-
"""튜토리얼 1회 노출 플래그 — 기본값과 기존 사용자 설정 승급 검증."""
from src.store.config_store import DEFAULT_CONFIG, _merge


class TestTutorialFlag:
    def test_default_is_unseen(self):
        assert DEFAULT_CONFIG["tutorial"]["seen"] is False

    def test_merge_upgrades_existing_user_config(self):
        # tutorial 키가 없는 기존 config.json도 딥머지로 seen=False 승급
        old_user_cfg = {"last_folder": "C:/quotes", "company": {"name": "내비온"}}
        merged = _merge(DEFAULT_CONFIG, old_user_cfg)
        assert merged["tutorial"]["seen"] is False
        assert merged["last_folder"] == "C:/quotes"

    def test_merge_preserves_seen_true(self):
        merged = _merge(DEFAULT_CONFIG, {"tutorial": {"seen": True}})
        assert merged["tutorial"]["seen"] is True
