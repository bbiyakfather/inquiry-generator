# -*- coding: utf-8 -*-
"""계산 엔진 골든 테스트.

1) 22M 골든 케이스: 회사가 실제 발행한 HWP 견적서(2023-152호)의 표시값 19개 재현
2) 엑셀 현재 상태 케이스: xlsx 캐시값(data_only)과 raw float 일치
3) 예산 역산 가이드(섹션①) 검증
"""
import pytest

from src.engine.calc import (LaborRow, ExpenseRow, calculate, budget_guide,
                             fmt_won, fmt_pct, round_half_up, pct1)


def _hwp_sample_quote():
    """2023년 발행 견적서: 22,000,000원, 참여율 40%, 0.75개월."""
    labor = [
        LaborRow("책임연구원", 6993408, count=1, rate=0.4, months=0.75),
        LaborRow("연구원", 5362452, count=2, rate=0.4, months=0.75),
        LaborRow("연구보조원", 3584618, count=4, rate=0.4, months=0.75),
    ]
    expenses = [
        ExpenseRow("전문가 활용비", qty_text="5명", unit_price=600000, qty=5),
        ExpenseRow("문헌구입비", qty_text="1식", unit_price=4000000, qty=1),
        ExpenseRow("국내여비", qty_text="-", unit_price=308982),
        ExpenseRow("회의비", qty_text="13명", unit_price=30000, qty=13),
    ]
    return calculate(labor, expenses, profit_on=True, trim=0.0)


class TestHwpGoldenCase22M:
    """실제 발행 견적서의 모든 표시값 재현 (1원/0.1%p 단위)."""

    def setup_method(self):
        self.q = _hwp_sample_quote()

    def test_labor_amounts(self):
        rows = self.q.labor_rows
        assert fmt_won(rows[0].amount) == "2,098,022"
        assert fmt_won(rows[1].amount) == "3,217,471"
        assert fmt_won(rows[2].amount) == "4,301,542"
        assert fmt_won(self.q.labor_total) == "9,617,035"

    def test_labor_ratios(self):
        q = self.q
        assert fmt_pct(q.ratio(q.labor_rows[0].amount)) == "9.5%"
        assert fmt_pct(q.ratio(q.labor_rows[1].amount)) == "14.6%"
        assert fmt_pct(q.ratio(q.labor_rows[2].amount)) == "19.6%"
        assert fmt_pct(q.ratio(q.labor_total)) == "43.7%"

    def test_expense_amounts(self):
        rows = self.q.expense_rows
        assert fmt_won(rows[0].amount) == "3,000,000"
        assert fmt_won(rows[1].amount) == "4,000,000"
        assert fmt_won(rows[2].amount) == "308,982"   # 수량 빈칸 → 단가 그대로
        assert fmt_won(rows[3].amount) == "390,000"
        assert fmt_won(self.q.expense_total) == "7,698,982"

    def test_expense_ratios(self):
        q = self.q
        assert fmt_pct(q.ratio(q.expense_rows[0].amount)) == "13.6%"
        assert fmt_pct(q.ratio(q.expense_rows[1].amount)) == "18.2%"
        assert fmt_pct(q.ratio(q.expense_rows[2].amount)) == "1.4%"
        assert fmt_pct(q.ratio(q.expense_rows[3].amount)) == "1.8%"
        assert fmt_pct(q.ratio(q.expense_total)) == "35.0%"

    def test_summary_block(self):
        q = self.q
        assert fmt_won(q.direct) == "17,316,017"
        assert fmt_pct(q.ratio(q.direct)) == "78.7%"
        assert fmt_won(q.mgmt) == "865,801"
        assert fmt_pct(q.ratio(q.mgmt)) == "3.9%"
        assert fmt_won(q.profit) == "1,818,182"
        assert fmt_pct(q.ratio(q.profit)) == "8.3%"
        assert fmt_won(q.supply) == "20,000,000"      # HWP '총계'
        assert fmt_pct(q.ratio(q.supply)) == "90.9%"
        assert fmt_won(q.vat) == "2,000,000"
        assert fmt_pct(q.ratio(q.vat)) == "9.1%"
        assert fmt_won(q.final) == "22,000,000"
        assert fmt_pct(q.ratio(q.final)) == "100.0%"


class TestExcelCurrentState:
    """엑셀 파일의 캐시값(data_only=True 덤프)과 raw float 일치 검증."""

    def setup_method(self):
        labor = [
            LaborRow("책임연구원", 3783728, count=1, rate=0.15, months=6),
            LaborRow("연구원", 2901312, count=2, rate=0.2808062560332505, months=6),
        ]
        expenses = [
            ExpenseRow("여비", unit_price=60000, qty=2, extra1=3),
            ExpenseRow("인쇄 및 디자인비"),                       # 전부 빈칸 → 0
            ExpenseRow("전문가 활용비", unit_price=300000, qty=4),
            ExpenseRow("SW 활용비", unit_price=1000000, qty=0),   # 수량 0 → 0
            ExpenseRow("문헌구입비", unit_price=1000000),
        ]
        self.q = calculate(labor, expenses, profit_on=True, trim=0.0)

    def test_raw_floats_match_excel_cache(self):
        q = self.q
        assert q.labor_rows[0].amount == 3405355.1999999997          # M11
        assert q.labor_rows[1].amount == 9776478.723652106           # M12
        assert q.labor_total == 13181833.923652105                   # M15
        assert q.expense_total == 2560000                            # M26
        assert q.direct == 15741833.923652105                        # C25
        assert q.mgmt == pytest.approx(787091.6961826053, abs=1e-6)  # C26
        assert q.profit == pytest.approx(1652892.561983471, abs=1e-6)  # C27
        assert q.supply == pytest.approx(18181818.18181818, abs=1e-6)  # C28
        assert q.vat == pytest.approx(1818181.8181818181, abs=1e-6)    # C29
        assert q.total == pytest.approx(19999999.999999996, abs=1e-6)  # C30
        assert fmt_won(q.final) == "20,000,000"                      # C32 표시

    def test_no_profit_variant(self):
        """이윤 없는 버전: 이윤 0, 공급가액 = 인건비+경비+일반관리비."""
        labor = [LaborRow("책임연구원", 3783728, count=1, rate=0.15, months=6)]
        q = calculate(labor, [], profit_on=False)
        assert q.profit == 0.0
        assert q.supply == q.direct + q.mgmt
        assert q.total == q.supply * 1.1


class TestBudgetGuide:
    """섹션① 예산 역산 — 엑셀 캐시값(C12=20,000,000) 대조."""

    def test_guide_20m(self):
        g = budget_guide(20000000, profit_on=True)
        assert g.vat == pytest.approx(1818181.8181818202, abs=1e-4)      # C13
        assert g.cost == pytest.approx(18181818.18181818, abs=1e-4)      # C14
        assert g.profit == pytest.approx(1652892.5619834717, abs=1e-4)   # C15
        assert g.mgmt == pytest.approx(787091.6961826067, abs=1e-4)      # C16
        assert g.direct == pytest.approx(15741833.923652101, abs=1e-4)   # C17
        assert g.labor_target == 10000000                                # C18
        assert g.expense_target == pytest.approx(5741833.923652101, abs=1e-4)  # C19

    def test_guide_no_profit(self):
        g = budget_guide(20000000, profit_on=False)
        assert g.profit == 0.0
        assert g.direct == pytest.approx(g.cost / 1.05, rel=1e-12)


class TestExpenseAmountEdge:
    """경비 금액 엣지케이스 (리뷰 발견 수정 검증)."""

    def test_no_unit_price_is_zero(self):
        # 단가 없이 수량만 있으면 0 (수량값이 금액으로 새는 버그 방지)
        e = ExpenseRow("회의비", qty_text="5명", unit_price=None, qty=5)
        assert e.amount == 0.0

    def test_unit_price_only(self):
        # 단가만(수량 None) → 단가 그대로 (국내여비 일시금 케이스)
        e = ExpenseRow("국내여비", qty_text="-", unit_price=308982)
        assert e.amount == 308982

    def test_unit_times_qty(self):
        e = ExpenseRow("전문가 활용비", qty_text="5명", unit_price=600000, qty=5)
        assert e.amount == 3000000

    def test_qty_zero(self):
        e = ExpenseRow("SW 활용비", unit_price=1000000, qty=0)
        assert e.amount == 0


class TestParseLeadingNum:
    from src.engine.calc import parse_leading_num as _p

    def test_extract(self):
        from src.engine.calc import parse_leading_num as p
        assert p("5명") == 5
        assert p("1식") == 1
        assert p("13명") == 13
        assert p("1,200매") == 1200
        assert p("-") is None
        assert p("") is None
        assert p(None) is None


class TestParseExpensesFallback:
    """qty 없이 qty_text만 있는 구버전/AI 초안 호환 (_parse_expenses 폴백)."""

    def test_qty_fallback_from_text(self):
        from src.api import _parse_expenses
        rows = _parse_expenses([
            {"name": "전문가 활용비", "qty_text": "5명", "unit_price": 600000},  # qty 없음
        ])
        assert rows[0].qty == 5
        assert rows[0].amount == 3000000

    def test_details_string_tolerated(self):
        from src.api import _parse_expenses
        rows = _parse_expenses([
            {"name": "문헌구입비", "details": "- 보고서\n- 자료", "unit_price": 1000000},
        ])
        assert rows[0].details == ["- 보고서", "- 자료"]


class TestRounding:
    def test_half_up_not_bankers(self):
        assert round_half_up(0.5) == 1
        assert round_half_up(1.5) == 2      # 은행가 반올림이면 2지만 round(2.5)=2 케이스가 문제
        assert round_half_up(2.5) == 3      # Python round(2.5)==2 — 우리는 3이어야 함
        assert round_half_up(865800.86) == 865801
        assert round_half_up(19999999.866) == 20000000

    def test_pct1_half_up(self):
        assert pct1(0.19552) == 19.6
        assert pct1(0.0345) == 3.5
        assert pct1(0.13636) == 13.6
