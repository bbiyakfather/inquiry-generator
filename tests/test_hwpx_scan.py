# -*- coding: utf-8 -*-
"""회의록 HWPX 스캐너 — build_minutes 라운드트립 + 비양식 graceful + 사이드카 연동."""
import json
import os
import zipfile

import pytest

from src.minutes import build_minutes
from src.scan import hwpx_scan as hx

SAMPLE_DATA = {
    "business_name": "AI 음장 센싱 기반 스마트 홈 보안 모니터링 시스템",
    "meeting_date": "2026. 04. 09.(목) 09:17~09:52",
    "meeting_place": "온라인 화상회의",
    "meeting_topic": "모두의 창업 경진대회 참여 준비 및 창업 활동 현황 논의",
    "participants": ["KIST 김종민 박사", "내비온 장윤화 이사, 김형일 / KST 문준혁"],
    "total_count": 4,
    "sections": [
        {"type": "header", "text": " ■ 주요 회의 내용"},
        {"type": "bullet", "text": "텍스코어 사업 선정 완료"},
        {"type": "sub", "text": "삼성 미래육성 기술재단 멘토링 대기"},
    ],
}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    folder = tmp_path_factory.mktemp("mn_scan")
    out = str(folder / "회의록_경진대회_260409.hwpx")
    res = build_minutes(SAMPLE_DATA, out_path=out)
    assert res["ok"], res.get("error")
    return folder, out


# ---- 라운드트립: 생성한 파일을 스캔해 동일 메타 복원 ----

def test_roundtrip_fields(built):
    _, out = built
    m = hx.parse_minutes_hwpx(out)
    assert m.error == ""
    assert m.business_name == SAMPLE_DATA["business_name"]
    assert m.date == SAMPLE_DATA["meeting_date"]
    assert m.place == SAMPLE_DATA["meeting_place"]
    assert m.topic == SAMPLE_DATA["meeting_topic"]
    assert m.total_count == 4
    assert m.mtime > 0


def test_roundtrip_date_iso(built):
    _, out = built
    m = hx.parse_minutes_hwpx(out)
    assert m.date_iso == "2026-04-09"


def test_date_to_iso_variants():
    assert hx._date_to_iso("2026. 04. 09.(목) 09:17") == "2026-04-09"
    assert hx._date_to_iso("2026년 6월 1일") == "2026-06-01"
    assert hx._date_to_iso("2026-06-11 14:00") == "2026-06-11"
    assert hx._date_to_iso("일시 미정") == ""
    assert hx._date_to_iso("") == ""


# ---- 비양식/손상 파일 graceful ----

def test_non_form_hwpx_listed_with_error(tmp_path):
    """양식 표가 없는 zip(.hwpx) → 예외 없이 목록 포함 + 양식 불일치."""
    p = tmp_path / "회의록_엉뚱한파일_260101.hwpx"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", "<root/>")
    m = hx.parse_minutes_hwpx(str(p))
    assert "양식 불일치" in m.error
    assert m.topic == "엉뚱한파일"     # 파일명 폴백
    assert m.editable is False


def test_not_a_zip_listed_with_error(tmp_path):
    p = tmp_path / "broken.hwpx"
    p.write_bytes(b"this is not a zip")
    m = hx.parse_minutes_hwpx(str(p))
    assert "파일 열기 실패" in m.error
    assert m.topic == "broken"


def test_prvtext_fallback(tmp_path):
    """section0이 비표준이어도 PrvText 포맷이 있으면 메타 복원."""
    p = tmp_path / "회의록_프리뷰만_260301.hwpx"
    prv = ("<회 의 록>\n<사업명><폴백 사업>\n<일  시><2026. 03. 01.(일)>\n"
           "<장  소><본사>\n<회의주제><폴백 주제>\n<참석자><A><(총 3명)>\n")
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Preview/PrvText.txt", prv)
    m = hx.parse_minutes_hwpx(str(p))
    assert m.error == ""
    assert m.business_name == "폴백 사업"
    assert m.topic == "폴백 주제"
    assert m.total_count == 3
    assert m.date_iso == "2026-03-01"


# ---- scan_folder: 사이드카 연동 + 필터링 ----

def test_scan_folder_sidecar_editable(built):
    folder, out = built
    jpath = os.path.splitext(out)[0] + ".minutes.json"
    with open(jpath, "w", encoding="utf-8") as fp:
        json.dump({"schema_version": 1, "data": SAMPLE_DATA}, fp, ensure_ascii=False)
    try:
        metas = hx.scan_folder(str(folder))
        assert len(metas) == 1
        assert metas[0].editable is True
        assert metas[0].json_path == jpath
    finally:
        os.remove(jpath)


def test_scan_folder_skips_non_hwpx(tmp_path):
    (tmp_path / "기타.txt").write_text("x", encoding="utf-8")
    (tmp_path / "견적.hwp").write_bytes(b"x")
    assert hx.scan_folder(str(tmp_path)) == []


def test_scan_folder_missing_dir():
    assert hx.scan_folder(r"C:\존재하지않는폴더\xyz") == []


# ---- A-6-3: scan_hwpx_grid cellSpan 추출 + 좌표 라운드트립 ----

from src.minutes.hwpx_minutes import TEMPLATE_MINUTES, _find_cell, _HP  # noqa: E402
from xml.etree import ElementTree as ET  # noqa: E402


def test_grid_cellspan_merged_counts():
    """실측 양식: colspan=2 셀 5개, colspan=3 셀 1개 (A-6-3 수정1)."""
    g = hx.scan_hwpx_grid(TEMPLATE_MINUTES)
    assert g["ok"], g.get("error")
    # 모든 셀에 colspan/rowspan 키가 있어야 함 (기본 1)
    for c in g["cells"]:
        assert c["colspan"] >= 1 and c["rowspan"] >= 1
    span2 = [c for c in g["cells"] if c["colspan"] == 2]
    span3 = [c for c in g["cells"] if c["colspan"] == 3]
    assert len(span2) == 5, f"colspan=2 기대 5, 실제 {len(span2)}"
    assert len(span3) == 1, f"colspan=3 기대 1, 실제 {len(span3)}"


def test_grid_keys_backward_compatible():
    """기존 키(row,col,text) 유지 + colspan/rowspan 추가만."""
    g = hx.scan_hwpx_grid(TEMPLATE_MINUTES)
    c = g["cells"][0]
    assert set(["row", "col", "text", "colspan", "rowspan"]).issubset(c.keys())


def test_grid_roundtrip_find_cell():
    """그리드 좌표 전부가 _find_cell로 실셀을 찾는다 (A-6-3 수정2)."""
    with zipfile.ZipFile(TEMPLATE_MINUTES) as zf:
        root = ET.parse(zf.open("Contents/section0.xml")).getroot()
    tbl = root.find(f".//{_HP}tbl")
    g = hx.scan_hwpx_grid(TEMPLATE_MINUTES)
    for c in g["cells"]:
        assert _find_cell(tbl, c["row"], c["col"]) is not None, \
            f"그리드 좌표 ({c['row']},{c['col']})가 실셀 아님"


def test_grid_no_nested_table_leak():
    """중첩 사진표 셀이 grid에 새지 않는다 (외부 표 직계만 순회).

    중첩표는 (0,0)/(0,1) 좌표를 갖는데, 외부 표 row0은 colSpan=3 단일셀이라
    (0,1)이 존재하지 않는다 → (0,1)이 grid에 있으면 누수.
    """
    g = hx.scan_hwpx_grid(TEMPLATE_MINUTES)
    coords = {(c["row"], c["col"]) for c in g["cells"]}
    assert (0, 1) not in coords, "중첩표 셀이 grid로 누수됨"
    assert len(g["cells"]) == 14
