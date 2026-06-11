# -*- coding: utf-8 -*-
"""패키징 산출물 가드 — MOTW 대응 .exe.config + spec 배선.

배경(tasks/lessons.md 2026-06-11): 다운로드 ZIP 해제 시 Zone.Identifier가 붙은
Python.Runtime.dll을 .NET이 거부해 클라이언트 PC에서 즉사. 방어 장치 2종이
실수로 제거되지 않도록 고정한다.
"""
import os
import re
import xml.etree.ElementTree as ET

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE_CONFIG = os.path.join(ROOT, "내비온 견적서 생성기.exe.config")
SPEC = os.path.join(ROOT, "navion_quote.spec")
APP_PY = os.path.join(ROOT, "app.py")


def test_exe_config_exists_and_valid_xml():
    assert os.path.isfile(EXE_CONFIG), ".exe.config가 프로젝트 루트에 없음"
    tree = ET.parse(EXE_CONFIG)  # 유효 XML이 아니면 여기서 실패
    root = tree.getroot()
    assert root.tag == "configuration"


def test_exe_config_enables_load_from_remote_sources():
    root = ET.parse(EXE_CONFIG).getroot()
    el = root.find("./runtime/loadFromRemoteSources")
    assert el is not None, "loadFromRemoteSources 요소 누락"
    assert el.attrib.get("enabled") == "true"


def test_spec_copies_exe_config_to_dist_root():
    """PyInstaller 6.x는 datas를 _internal/로 보내므로 datas 방식이면 안 된다.
    COLLECT 후 shutil.copy로 EXE 옆 최상위에 배치하는 코드가 spec에 있어야 한다."""
    with open(SPEC, encoding="utf-8") as f:
        spec = f.read()
    assert "내비온 견적서 생성기.exe.config" in spec
    assert re.search(r"shutil\.copy|_shutil\.copy", spec), "COLLECT 후 .exe.config 복사 코드 누락"
    # datas 항목으로 들어가 있으면 _internal로 떨어지므로 금지
    datas_block = spec.split("datas = [", 1)[1].split("]", 1)[0]
    assert ".exe.config" not in datas_block, ".exe.config가 datas에 있음 — _internal로 잘못 배치됨"


def test_app_py_unblocks_dlls_before_webview_import():
    with open(APP_PY, encoding="utf-8") as f:
        src = f.read()
    assert "Zone.Identifier" in src, "app.py MOTW 자가치유 코드 누락"
    # webview import보다 먼저 실행돼야 함 (모듈 최상단 frozen 분기)
    assert src.index("Zone.Identifier") < src.index("import webview"), \
        "MOTW 제거가 import webview 이후에 있음 — clr 로드 전에 실행돼야 함"
