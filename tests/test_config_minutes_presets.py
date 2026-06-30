# -*- coding: utf-8 -*-
"""회의록 Preset 저장소 — 스키마/전용 마이그레이션/동기화/갤러리 플래그 (Wave 2 B-1/B-3).

config.json·앱 데이터 폴더 오염 방지를 위해 save_config·_presets_dir를 패치한다.
"""
import copy
import os

import pytest

from src.store import config_store as cs


@pytest.fixture(autouse=True)
def _no_disk(monkeypatch, tmp_path):
    monkeypatch.setattr(cs, "save_config", lambda cfg: None)
    pdir = str(tmp_path / "minutes_templates")
    os.makedirs(pdir, exist_ok=True)
    monkeypatch.setattr(cs, "_presets_dir", lambda: pdir)


def _cfg():
    return copy.deepcopy(cs.DEFAULT_CONFIG)


# ── migrate_minutes_presets (적대리뷰 #4: _merge 비의존 시딩) ──────────────────

def test_seed_builtin_when_absent():
    cfg = _cfg()
    assert cs.migrate_minutes_presets(cfg) is True
    presets = cfg["doc_types"]["minutes"]["presets"]
    assert len(presets) == 1
    assert presets[0]["is_builtin"] is True
    assert presets[0]["id"] == "builtin"
    # 멱등
    assert cs.migrate_minutes_presets(cfg) is False


def test_builtin_always_first_with_user_presets():
    cfg = _cfg()
    cfg["doc_types"]["minutes"]["presets"] = [
        {"id": "u1", "name": "내양식", "template_path": "x.hwpx",
         "is_builtin": False, "created": ""},
    ]
    assert cs.migrate_minutes_presets(cfg) is True
    presets = cfg["doc_types"]["minutes"]["presets"]
    assert presets[0]["is_builtin"] is True
    assert [p["id"] for p in presets[1:]] == ["u1"]


def test_recover_non_list_presets():
    cfg = _cfg()
    cfg["doc_types"]["minutes"]["presets"] = "broken"
    assert cs.migrate_minutes_presets(cfg) is True
    presets = cfg["doc_types"]["minutes"]["presets"]
    assert isinstance(presets, list) and presets[0]["is_builtin"]


def test_drop_corrupt_entries_and_canonicalize_builtin():
    cfg = _cfg()
    cfg["doc_types"]["minutes"]["presets"] = [
        {"id": "builtin", "name": "헌것", "is_builtin": True},   # canonical 교체
        "junk",                                                   # 비 dict
        {"name": "id없음"},                                       # id 누락
        {"id": "u9", "name": "정상", "template_path": "y.hwpx",
         "is_builtin": False},
    ]
    assert cs.migrate_minutes_presets(cfg) is True
    presets = cfg["doc_types"]["minutes"]["presets"]
    assert [p["id"] for p in presets] == ["builtin", "u9"]
    assert presets[0]["name"] == "기본 회의록 양식"


# ── gallery_autoshow (기본 true, 9-d) ────────────────────────────────────────

def test_gallery_autoshow_default_true():
    assert cs.get_minutes_gallery_autoshow(_cfg()) is True


def test_gallery_autoshow_toggle():
    cfg = _cfg()
    cs.set_minutes_gallery_autoshow(cfg, False)
    assert cs.get_minutes_gallery_autoshow(cfg) is False
    cs.set_minutes_gallery_autoshow(cfg, True)
    assert cs.get_minutes_gallery_autoshow(cfg) is True


# ── add / select / delete / rename + template_path 동기화 (단일 출처) ─────────

def test_add_then_select_reflects_template_path(tmp_path):
    cfg = _cfg()
    tpl = str(tmp_path / "a.hwpx")
    open(tpl, "w").close()
    p = cs.add_minutes_preset(cfg, tpl, "양식A")
    assert p["name"] == "양식A" and not p["is_builtin"]
    cs.select_minutes_preset(cfg, p["id"])
    assert cs.get_minutes_tpl(cfg) == tpl


def test_select_builtin_clears_template_path(tmp_path):
    cfg = _cfg()
    tpl = str(tmp_path / "a.hwpx")
    open(tpl, "w").close()
    p = cs.add_minutes_preset(cfg, tpl)
    cs.select_minutes_preset(cfg, p["id"])
    assert cs.get_minutes_tpl(cfg) == tpl
    cs.select_minutes_preset(cfg, "builtin")
    assert cs.get_minutes_tpl(cfg) == ""


def test_delete_active_preset_falls_back_to_builtin(tmp_path):
    cfg = _cfg()
    tpl = str(tmp_path / "a.hwpx")
    open(tpl, "w").close()
    p = cs.add_minutes_preset(cfg, tpl)
    cs.select_minutes_preset(cfg, p["id"])
    assert cs.get_minutes_tpl(cfg) == tpl
    cs.delete_minutes_preset(cfg, p["id"])
    assert cs.get_minutes_tpl(cfg) == ""
    assert p["id"] not in [x["id"] for x in cs.get_minutes_presets(cfg)]


def test_delete_builtin_rejected():
    with pytest.raises(ValueError):
        cs.delete_minutes_preset(_cfg(), "builtin")


def test_rename_builtin_rejected():
    with pytest.raises(ValueError):
        cs.rename_minutes_preset(_cfg(), "builtin", "새이름")


def test_rename_user_preset(tmp_path):
    cfg = _cfg()
    tpl = str(tmp_path / "a.hwpx")
    open(tpl, "w").close()
    p = cs.add_minutes_preset(cfg, tpl, "old")
    cs.rename_minutes_preset(cfg, p["id"], "new")
    names = {x["id"]: x["name"] for x in cs.get_minutes_presets(cfg)}
    assert names[p["id"]] == "new"


def test_copy_minutes_template_into_app_folder(tmp_path):
    src = tmp_path / "src.hwpx"
    src.write_bytes(b"hwpx-bytes")
    dst = cs.copy_minutes_template(str(src))
    assert os.path.isfile(dst)
    assert os.path.dirname(dst).endswith("minutes_templates")
    with open(dst, "rb") as f:
        assert f.read() == b"hwpx-bytes"
    # 원본 삭제해도 사본 유지 (9-c 견고성)
    os.remove(src)
    assert os.path.isfile(dst)


def test_copy_minutes_template_avoids_clobber(tmp_path):
    a = tmp_path / "dup.hwpx"
    a.write_bytes(b"A")
    b = tmp_path / "sub" / "dup.hwpx"
    os.makedirs(b.parent)
    b.write_bytes(b"B")
    d1 = cs.copy_minutes_template(str(a))
    d2 = cs.copy_minutes_template(str(b))
    assert d1 != d2
    assert os.path.isfile(d1) and os.path.isfile(d2)
