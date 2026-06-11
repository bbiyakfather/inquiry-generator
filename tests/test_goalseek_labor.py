# -*- coding: utf-8 -*-
"""인건비 자동조정(goal_seek_labor) — 결정론적 검증 (한글 COM 무의존)."""
from src.engine.calc import LaborRow, ExpenseRow, calculate, round_half_up
from src.engine.goalseek import goal_seek_labor

PRICES = {"책임연구원": 7567456, "연구원": 5802624,
          "연구보조원": 3878858, "보조원": 2909242}


def _labor(counts, months=5.0):
    return [LaborRow(g, PRICES[g], count=counts.get(g, 0), rate=0.1, months=months)
            for g in ["책임연구원", "연구원", "연구보조원", "보조원"]]


def _final(labor, expenses, profit_on, res):
    for r, rate, cnt in zip(labor, res.rates, res.counts):
        r.rate, r.count = rate, cnt
    return round_half_up(calculate(labor, expenses, profit_on, trim=res.trim).final)


class TestLaborSeek:
    def test_final_equals_target_exactly(self):
        labor = _labor({"책임연구원": 1, "연구원": 2, "연구보조원": 3, "보조원": 2})
        exp = [ExpenseRow("회의비", unit_price=1000000, qty=1)]
        target = 50000000
        res = goal_seek_labor(target, labor, exp, profit_on=True)
        assert res.ok, res.error
        assert _final(labor, exp, True, res) == target

    def test_trim_is_under_10000(self):
        labor = _labor({"책임연구원": 1, "연구원": 2, "연구보조원": 3, "보조원": 2})
        exp = [ExpenseRow("회의비", unit_price=1000000, qty=1)]
        res = goal_seek_labor(50000000, labor, exp, profit_on=True)
        assert res.ok and 0 <= res.trim < 10000

    def test_lead_fixed_one_person_ten_percent(self):
        labor = _labor({"책임연구원": 3, "연구원": 2, "보조원": 2})  # 책임 3명 입력해도
        exp = []
        res = goal_seek_labor(40000000, labor, exp, profit_on=True)
        assert res.ok
        assert res.counts[0] == 1            # 책임연구원 → 1명 강제
        assert abs(res.rates[0] - 0.10) < 1e-9   # 10% 고정

    def test_lead_has_lowest_rate(self):
        labor = _labor({"책임연구원": 1, "연구원": 2, "연구보조원": 2, "보조원": 2})
        res = goal_seek_labor(50000000, labor, [], profit_on=True)
        assert res.ok
        active = [res.rates[i] for i in range(4) if res.counts[i] > 0]
        assert res.rates[0] == min(active)   # 책임이 제일 적음

    def test_buffer_count_grows_on_overflow(self):
        # 인력이 적어 참여율이 100%를 넘으면 보조원 명수가 늘어야 함
        labor = _labor({"책임연구원": 1, "보조원": 1}, months=1.0)
        res = goal_seek_labor(50000000, labor, [], profit_on=True,
                              max_counts={"보조원": 10})
        assert res.ok
        assert res.counts[3] > 1             # 보조원 명수 증가

    def test_buffer_capped_at_max(self):
        labor = _labor({"책임연구원": 1, "보조원": 1}, months=1.0)
        res = goal_seek_labor(80000000, labor, [], profit_on=True,
                              max_counts={"보조원": 3})
        assert res.ok
        assert res.counts[3] <= 3            # 한도 초과 안 함

    def test_target_too_low_errors(self):
        labor = _labor({"책임연구원": 1, "연구원": 2})
        exp = [ExpenseRow("고가경비", unit_price=100000000, qty=1)]
        res = goal_seek_labor(10000000, labor, exp, profit_on=True)
        assert not res.ok and res.error

    def test_no_profit_variant_matches_target(self):
        labor = _labor({"책임연구원": 1, "연구원": 2, "보조원": 2})
        res = goal_seek_labor(30000000, labor, [], profit_on=False)
        assert res.ok
        assert _final(labor, [], False, res) == 30000000

    def test_original_rows_restored(self):
        labor = _labor({"책임연구원": 1, "연구원": 2, "보조원": 2})
        before = [(r.count, r.rate) for r in labor]
        goal_seek_labor(40000000, labor, [], profit_on=True)
        after = [(r.count, r.rate) for r in labor]
        assert before == after              # 함수가 원본을 원복


class TestLockedRows:
    def test_locked_row_value_unchanged(self):
        # 연구원(idx 1)을 고정 → 명수·참여율 그대로, 나머지만 조정
        labor = _labor({"책임연구원": 1, "연구원": 2, "연구보조원": 3, "보조원": 2})
        labor[1].rate = 0.37          # 사용자가 직접 넣은 예외값
        res = goal_seek_labor(50000000, labor, [], profit_on=True, locked=[1])
        assert res.ok, res.error
        assert res.counts[1] == 2                 # 명수 유지
        assert abs(res.rates[1] - 0.37) < 1e-9    # 참여율 유지

    def test_locked_final_still_equals_target(self):
        labor = _labor({"책임연구원": 1, "연구원": 2, "연구보조원": 3, "보조원": 2})
        labor[1].rate = 0.30
        exp = [ExpenseRow("회의비", unit_price=1000000, qty=1)]
        target = 60000000
        res = goal_seek_labor(target, labor, exp, profit_on=True, locked=[1])
        assert res.ok, res.error
        assert _final(labor, exp, True, res) == target

    def test_locked_lead_keeps_user_value(self):
        # 책임연구원을 고정하면 1명·10% 규칙 대신 입력값 유지
        labor = _labor({"책임연구원": 2, "연구원": 2, "보조원": 2})
        labor[0].rate = 0.25
        res = goal_seek_labor(60000000, labor, [], profit_on=True, locked=[0])
        assert res.ok, res.error
        assert res.counts[0] == 2                 # 1명 강제 안 함
        assert abs(res.rates[0] - 0.25) < 1e-9    # 10% 강제 안 함

    def test_all_adjustable_locked_errors(self):
        # 책임 외 전 직급을 고정하면 조정 대상이 없음 → 오류
        labor = _labor({"책임연구원": 1, "연구원": 2, "연구보조원": 2, "보조원": 2})
        res = goal_seek_labor(50000000, labor, [], profit_on=True, locked=[1, 2, 3])
        assert not res.ok and res.error

    def test_locked_buffer_count_not_grown(self):
        # 보조원을 고정하면 100% 초과해도 명수를 늘리지 않음
        labor = _labor({"책임연구원": 1, "연구원": 1, "보조원": 1}, months=1.0)
        res = goal_seek_labor(60000000, labor, [], profit_on=True,
                              locked=[3], max_counts={"보조원": 10})
        assert res.ok, res.error
        assert res.counts[3] == 1                 # 보조원 명수 그대로
