# -*- coding: utf-8 -*-
"""회의록 관리 API 레벨 — generate 사이드카 / scan stats / delete 양 모드 / load.

Api()는 실제 config.json을 읽으므로 __init__을 우회하고 cfg를 직접 주입한다
(test_config_doc_types와 동일 패턴). 전부 COM 불필요 — 기본 pytest로 실행.
"""
import json
import os
from datetime import date as _date

import pytest

from src.api import Api


def _api(minutes_folder=""):
    api = Api.__new__(Api)
    api.cfg = {
        "last_folder": "",
        "doc_types": {"quote": {"folder": ""},
                      "minutes": {"folder": minutes_folder}},
    }
    return api


SAMPLE = {
    "business_name": "테스트 사업",
    "meeting_date": "2026. 04. 09.(목) 09:17~09:52",
    "meeting_place": "본사 회의실",
    "meeting_topic": "API 레벨 검증 회의",
    "participants": ["내비온 김형일"],
    "total_count": 1,
    "sections": [{"type": "header", "text": " ■ 주요 회의 내용"},
                 {"type": "bullet", "text": "검증 항목 점검"}],
}


@pytest.fixture()
def workdir(tmp_path):
    return str(tmp_path)


def test_generate_minutes_writes_sidecar(workdir):
    api = _api(workdir)
    r = api.generate_minutes({"data": SAMPLE})
    assert r["ok"], r.get("error")
    assert os.path.isfile(r["path"])
    assert r["json_path"].endswith(".minutes.json")
    assert os.path.isfile(r["json_path"])
    with open(r["json_path"], encoding="utf-8") as fp:
        store = json.load(fp)
    assert store["data"] == SAMPLE


def test_generate_requires_topic(workdir):
    api = _api(workdir)
    r = api.generate_minutes({"data": {"meeting_topic": ""}})
    assert not r["ok"]


def test_scan_minutes_folder_stats(workdir):
    api = _api(workdir)
    # 1건: 과거 날짜(2026-04) + 사이드카(editable)
    r1 = api.generate_minutes({"data": SAMPLE})
    assert r1["ok"]
    # 1건: 이번 달 날짜 + 사이드카 제거(편집 불가)
    today = _date.today()
    cur = dict(SAMPLE, meeting_topic="이번달 회의",
               meeting_date=f"{today.year}. {today.month:02d}. 15.(월)")
    r2 = api.generate_minutes({"data": cur})
    assert r2["ok"]
    os.remove(r2["json_path"])

    r = api.scan_minutes_folder()
    assert r["ok"]
    assert r["folder"] == workdir
    assert r["stats"]["total"] == 2
    assert r["stats"]["this_month"] == 1
    assert r["stats"]["editable"] == 1
    topics = {m["topic"] for m in r["minutes"]}
    assert topics == {"API 레벨 검증 회의", "이번달 회의"}


def test_scan_includes_orphan_sidecar(workdir):
    api = _api(workdir)
    r1 = api.generate_minutes({"data": SAMPLE})
    os.remove(r1["path"])  # hwpx만 삭제 → 고아 사이드카
    r = api.scan_minutes_folder()
    assert r["stats"]["total"] == 1
    m = r["minutes"][0]
    assert m["source"] == "json"
    assert m["editable"] is True
    assert m["topic"] == SAMPLE["meeting_topic"]


def test_scan_empty_folder_config():
    api = _api("")
    r = api.scan_minutes_folder()
    assert r["ok"]
    assert r["folder"] == ""
    assert r["minutes"] == []


def test_load_minutes_roundtrip(workdir):
    api = _api(workdir)
    r1 = api.generate_minutes({"data": SAMPLE})
    r = api.load_minutes(r1["json_path"])
    assert r["ok"]
    assert r["data"] == SAMPLE


def test_load_minutes_missing():
    api = _api("")
    r = api.load_minutes(r"C:\없는경로\x.minutes.json")
    assert not r["ok"]


def test_delete_minutes_json_only(workdir):
    api = _api(workdir)
    r1 = api.generate_minutes({"data": SAMPLE})
    r = api.delete_minutes({"path": r1["path"], "json_path": r1["json_path"],
                            "also_files": False})
    assert r["ok"]
    assert not os.path.exists(r1["json_path"])
    assert os.path.exists(r1["path"])      # hwpx는 남음


def test_delete_minutes_also_files(workdir):
    api = _api(workdir)
    r1 = api.generate_minutes({"data": SAMPLE})
    r = api.delete_minutes({"path": r1["path"], "json_path": r1["json_path"],
                            "also_files": True})
    assert r["ok"]
    assert not os.path.exists(r1["json_path"])
    assert not os.path.exists(r1["path"])
    assert len(r["removed"]) == 2


def test_delete_minutes_nothing():
    api = _api("")
    r = api.delete_minutes({"path": r"C:\없는경로\x.hwpx", "json_path": "",
                            "also_files": False})
    assert not r["ok"]


def test_get_minutes_template():
    api = _api("")
    r = api.get_minutes_template()
    assert r["ok"]
    assert r["exists"] is True
    assert r["name"].endswith(".hwpx")


# ── 양식 스캔 fieldmap 캐시 보호 (AI 실패 시 기존 매핑 보존) ──────────────────

def test_scan_minutes_template_ai_failure_keeps_existing_fieldmap(workdir):
    """API 키 없음 등으로 AI 매핑이 실패해도, 이전의 정상 fieldmap을
    빈 매핑으로 덮어쓰지 않아야 한다 (재스캔 중 일시 오류 보호)."""
    import shutil
    from src.minutes.hwpx_minutes import TEMPLATE_MINUTES
    from src.ai.minutes_template_mapper import (save_minutes_fieldmap,
                                                load_minutes_fieldmap)
    tpl = os.path.join(workdir, "커스텀양식.hwpx")
    shutil.copy2(TEMPLATE_MINUTES, tpl)
    good = {"cell_map": {"business_name": [2, 2], "meeting_topic": [3, 1]},
            "unmapped": []}
    save_minutes_fieldmap(tpl, good)

    api = _api(workdir)          # AI 키 없음 → map_minutes_cells 실패 경로
    r = api.scan_minutes_template(tpl)
    assert r["ok"] and r.get("ai_error")
    kept = load_minutes_fieldmap(tpl)
    assert kept["cell_map"] == good["cell_map"]   # 기존 매핑 보존


def test_scan_minutes_template_first_scan_caches_even_on_ai_failure(workdir):
    """기존 캐시가 없으면 AI 실패라도 fieldmap을 생성해 둔다 (스캔 사실 기록)."""
    import shutil
    from src.minutes.hwpx_minutes import TEMPLATE_MINUTES
    from src.ai.minutes_template_mapper import load_minutes_fieldmap
    tpl = os.path.join(workdir, "신규양식.hwpx")
    shutil.copy2(TEMPLATE_MINUTES, tpl)

    api = _api(workdir)
    r = api.scan_minutes_template(tpl)
    assert r["ok"] and r.get("ai_error")
    fm = load_minutes_fieldmap(tpl)
    assert fm and fm["cell_map"] == {}
