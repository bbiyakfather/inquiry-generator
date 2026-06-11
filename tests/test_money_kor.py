# -*- coding: utf-8 -*-
import pytest

from src.engine.money_kor import num_to_kor, amount_kor


class TestNumToKor:
    @pytest.mark.parametrize("n,expected", [
        (22000000, "이천이백만"),
        (42000000, "사천이백만"),
        (20000000, "이천만"),
        (100000000, "일억"),
        (13500000, "일천삼백오십만"),
        (1234567, "일백이십삼만사천오백육십칠"),
        (10000, "일만"),
        (1454621, "일백사십오만사천육백이십일"),
        (300000, "삼십만"),
        (1000000000000, "일조"),
        (55000000, "오천오백만"),
    ])
    def test_keep_il(self, n, expected):
        assert num_to_kor(n, keep_il=True) == expected

    @pytest.mark.parametrize("n,expected", [
        (13500000, "천삼백오십만"),
        (100000000, "일억"),     # 만/억 등 큰 단위의 1은 '일' 유지
        (1234567, "백이십삼만사천오백육십칠"),
    ])
    def test_short_style(self, n, expected):
        assert num_to_kor(n, keep_il=False) == expected

    def test_zero(self):
        assert num_to_kor(0) == "영"


class TestAmountKor:
    def test_hwp_sample_format(self):
        # 실제 견적서 표기와 동일해야 함
        assert amount_kor(22000000) == "금이천이백만원정 (₩ 22,000,000), 부가세 포함"

    def test_vat_excluded(self):
        assert amount_kor(1000000, vat_included=False).endswith("부가세 별도")
