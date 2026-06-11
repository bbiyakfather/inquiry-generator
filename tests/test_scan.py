# -*- coding: utf-8 -*-
"""원본 HWP 견적서 스캔 회귀 테스트 (파일 읽기만, 수정 없음)."""
import os

import pytest

from src.scan.hwp_scan import parse_hwp, scan_folder

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGINAL = os.path.join(BASE, "내비온_견적서_저가의 고효율 라이다 센서 사업 타당성 분석 용역.hwp")


@pytest.mark.skipif(not os.path.exists(ORIGINAL), reason="원본 견적서 없음")
class TestParseOriginal:
    def setup_method(self):
        self.meta = parse_hwp(ORIGINAL)

    def test_service_name(self):
        assert self.meta.service_name == "저가의 고효율 라이다 센서 사업 타당성 분석 용역"

    def test_amount(self):
        assert self.meta.amount == 22000000

    def test_date(self):
        assert self.meta.date == "2023-11-23"

    def test_recipient(self):
        assert "한국과학기술연구원" in self.meta.recipient

    def test_quote_no(self):
        assert "2023-152" in self.meta.quote_no

    def test_no_error(self):
        assert self.meta.error == ""


@pytest.mark.skipif(not os.path.exists(ORIGINAL), reason="원본 견적서 없음")
def test_scan_folder_finds_original():
    results = scan_folder(BASE)
    names = [m.filename for m in results]
    assert any("라이다" in n for n in names)
