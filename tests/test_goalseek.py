# -*- coding: utf-8 -*-
"""Goal-seek 회귀 테스트 — 엑셀 Claude Log의 실제 사용 케이스 기반."""
import pytest

from src.engine.calc import LaborRow, ExpenseRow, calculate, round_half_up
from src.engine.goalseek import available_labor, goal_seek


def _excel_expenses():
    """엑셀 현재 상태 경비 (합계 2,560,000)."""
    return [
        ExpenseRow("여비", unit_price=60000, qty=2, extra1=3),
        ExpenseRow("전문가 활용비", unit_price=300000, qty=4),
        ExpenseRow("문헌구입비", unit_price=1000000),
    ]


class TestLog20MCase:
    """엑셀 Claude Log 2026-06-02: 목표 20,000,000 → 균등 참여율 0.10355655593652548."""

    def test_available_labor_matches_log(self):
        # 로그: 목표인건비 13,181,833.92
        L = available_labor(20000000, 2560000, profit_on=True)
        assert L == pytest.approx(13181833.9236521, abs=0.01)

    def test_uniform_rate_matches_log(self):
        # 로그: 기준합계 127,291,158 → 필요 참여율 0.10355655593652548
        L = available_labor(20000000, 2560000, profit_on=True)
        assert L / 127291158 == pytest.approx(0.10355655593652548, rel=1e-12)

    def test_goal_seek_uniform_final_equals_target(self):
        """균등 모드: 만원미만 절삭으로 표시 견적금액 == 목표, 절삭 < 만원."""
        # 기준합계 127,291,158이 되는 합성 구성 (21,215,193 × 1명 × 6개월)
        labor = [LaborRow("책임연구원", 21215193, count=1, rate=0.0, months=6)]
        res = goal_seek(20000000, labor, _excel_expenses(),
                        profit_on=True, mode="uniform")
        assert res.ok
        # 참여율은 정밀 역산값에 근접(격자 올림)
        assert res.rates[0] == pytest.approx(0.10355655593652548, abs=1e-4)
        assert 0 <= res.trim < 10000
        q = calculate(labor, _excel_expenses(), profit_on=True, trim=res.trim)
        assert round_half_up(q.final) == 20000000


class TestManwonTrimMode:
    """전 모드 공통: 만원미만 자동 절삭 → 목표금액 정확 일치 (1% 반올림 폐지)."""

    def _labor(self):
        return [
            LaborRow("책임연구원", 3783728, count=1, rate=0.0, months=6),
            LaborRow("연구원", 2901312, count=2, rate=0.0, months=6),
            LaborRow("연구보조원", 1939429, count=4, rate=0.0, months=6),
            LaborRow("보조원", 1454621, count=2, rate=0.0, months=6),
        ]

    @pytest.mark.parametrize("target", [42000000, 20000000, 33000000, 55000000])
    def test_final_equals_target_exactly(self, target):
        labor = self._labor()
        expenses = _excel_expenses()
        res = goal_seek(target, labor, expenses, profit_on=True, mode="uniform")
        assert res.ok, res.error
        # 만원 미만만 절삭, 최종견적 표시값 == 목표
        assert 0 <= res.trim < 10000
        q = calculate(labor, expenses, profit_on=True, trim=res.trim)
        assert round_half_up(q.final) == target

    def test_no_profit_variant(self):
        labor = self._labor()
        res = goal_seek(30000000, labor, _excel_expenses(), profit_on=False,
                        mode="uniform")
        assert res.ok
        assert 0 <= res.trim < 10000
        q = calculate(labor, _excel_expenses(), profit_on=False, trim=res.trim)
        assert round_half_up(q.final) == 30000000
        assert q.profit == 0.0

    def test_ratio_mode_preserves_proportion(self):
        """비율유지 모드: 기존 참여율 비율(0.15:0.15:0.20:0.10) 보존(격자 오차 내)."""
        labor = self._labor()
        for row, r0 in zip(labor, [0.15, 0.15, 0.20, 0.10]):
            row.rate = r0
        res = goal_seek(42000000, labor, _excel_expenses(), profit_on=True,
                        mode="ratio")
        assert res.ok
        r = res.rates
        # 격자 올림(≤0.0001) 오차 범위 내에서 비율 보존
        assert r[0] == pytest.approx(r[1], abs=2e-4)            # 0.15 : 0.15
        assert r[2] / r[0] == pytest.approx(0.20 / 0.15, abs=5e-3)
        assert r[3] / r[0] == pytest.approx(0.10 / 0.15, abs=5e-3)


class TestEdgeCases:
    def test_expense_exceeds_budget(self):
        labor = [LaborRow("책임연구원", 3783728, count=1, rate=0.0, months=6)]
        big_expense = [ExpenseRow("문헌구입비", unit_price=50000000)]
        res = goal_seek(10000000, labor, big_expense, profit_on=True)
        assert not res.ok
        assert "경비" in res.error

    def test_no_personnel(self):
        res = goal_seek(10000000, [], [], profit_on=True)
        assert not res.ok

    def test_overload_warning(self):
        """전 직급 100%로도 목표 미달 → 경고."""
        labor = [LaborRow("보조원", 1454621, count=1, rate=0.0, months=1)]
        res = goal_seek(100000000, labor, [], profit_on=True)
        assert res.ok
        assert any("미달" in w or "100%" in w for w in res.warnings)
