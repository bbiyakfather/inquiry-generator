# -*- coding: utf-8 -*-
"""doc_types 유형별 폴더 — 기본값/병합/마이그레이션/폴백."""
import copy

from src.store import config_store as cs


def test_default_config_has_doc_types():
    assert "doc_types" in cs.DEFAULT_CONFIG
    assert cs.DEFAULT_CONFIG["doc_types"]["quote"] == {"folder": ""}
    assert cs.DEFAULT_CONFIG["doc_types"]["minutes"] == {"folder": "", "template_path": ""}


def test_merge_promotes_doc_types_for_old_config():
    """구버전 config.json(doc_types 없음)을 로드해도 기본 구조가 채워진다."""
    old = {"last_folder": r"C:\old", "company": {"name": "테스트"}}
    merged = cs._merge(cs.DEFAULT_CONFIG, old)
    assert merged["doc_types"]["quote"]["folder"] == ""
    assert merged["doc_types"]["minutes"]["folder"] == ""
    assert merged["last_folder"] == r"C:\old"


def test_migrate_copies_last_folder_once():
    cfg = cs._merge(cs.DEFAULT_CONFIG, {"last_folder": r"C:\work\quotes"})
    changed = cs.migrate_doc_type_folders(cfg)
    assert changed is True
    assert cfg["doc_types"]["quote"]["folder"] == r"C:\work\quotes"
    # 재호출 시 변경 없음 (1회성)
    assert cs.migrate_doc_type_folders(cfg) is False


def test_migrate_does_not_overwrite_existing():
    cfg = cs._merge(cs.DEFAULT_CONFIG, {
        "last_folder": r"C:\old",
        "doc_types": {"quote": {"folder": r"C:\new"}},
    })
    assert cs.migrate_doc_type_folders(cfg) is False
    assert cfg["doc_types"]["quote"]["folder"] == r"C:\new"


def test_migrate_noop_when_no_last_folder():
    cfg = copy.deepcopy(cs.DEFAULT_CONFIG)
    assert cs.migrate_doc_type_folders(cfg) is False
    assert cfg["doc_types"]["quote"]["folder"] == ""


# ---- Api._doc_folder 폴백 (Api 인스턴스 없이 함수 로직만 검증하기 위해
#      api 모듈을 import하고 cfg를 직접 주입) ----

def _api_with_cfg(cfg):
    from src.api import Api
    api = Api.__new__(Api)  # __init__ 우회 (config 파일 I/O 없이)
    api.cfg = cfg
    return api


def test_doc_folder_prefers_doc_types():
    api = _api_with_cfg({
        "last_folder": r"C:\legacy",
        "doc_types": {"quote": {"folder": r"C:\q"}, "minutes": {"folder": r"C:\m"}},
    })
    assert api._doc_folder("quote") == r"C:\q"
    assert api._doc_folder("minutes") == r"C:\m"


def test_doc_folder_falls_back_to_last_folder():
    """quote·minutes 모두 비어 있으면 last_folder 폴백 —
    기존 회의록이 견적 폴더에 생성돼 온 연속성."""
    api = _api_with_cfg({
        "last_folder": r"C:\legacy",
        "doc_types": {"quote": {"folder": ""}, "minutes": {"folder": ""}},
    })
    assert api._doc_folder("quote") == r"C:\legacy"
    assert api._doc_folder("minutes") == r"C:\legacy"


def test_doc_folder_missing_section_safe():
    api = _api_with_cfg({"last_folder": ""})
    assert api._doc_folder("quote") == ""
    assert api._doc_folder("minutes") == ""
