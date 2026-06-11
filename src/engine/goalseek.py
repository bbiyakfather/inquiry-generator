# -*- coding: utf-8 -*-
"""목표 견적금액 → 인건비 참여율 역산 (goal-seek).

원리 (엑셀 Claude Log 2026-06-02 케이스로 검증):
  가용 인건비 L* = T / 1.1(부가세) [/ 1.1(이윤, 이윤 버전만)] / 1.05(일반관리비) − 경비합
  균등 모드:   r = L* / Σ(단가×명수×개월)
  비율유지 모드: 기존 참여율 비율을 보존한 채 스케일

만원미만 자동 절삭(전 모드 공통): 참여율을 고운 격자(0.01%→0.001%→0.0001%)로
올려 총계 ≥ 목표를 보장하고, '만원 미만' 잔액만 절삭으로 흡수 →
최종 견적금액 = 목표 정확히 일치. (구 1% 반올림 방식은 폐지)
"""
import math
from dataclasses import dataclass, field

from .calc import (LaborRow, ExpenseRow, calculate, round_half_up,
                   MGMT_RATE, PROFIT_RATE, VAT_RATE)


@dataclass
class GoalSeekResult:
    ok: bool
    rates: list = field(default_factory=list)   # 직급별 참여율 (labor_rows 순서)
    trim: int = 0                               # 절삭(원, 정수)
    available_labor: float = 0.0                # L*
    warnings: list = field(default_factory=list)
    error: str = ""


@dataclass
class LaborSeekResult:
    """인건비 자동조정 결과 — 참여율과 명수를 함께 돌려준다."""
    ok: bool
    rates: list = field(default_factory=list)    # 직급별 참여율 (labor_rows 순서)
    counts: list = field(default_factory=list)   # 직급별 명수 (책임=1, 보조원 탄력)
    trim: int = 0
    warnings: list = field(default_factory=list)
    error: str = ""


# 인건비 자동조정 규칙 상수
_LEAD_GRADE = "책임연구원"     # 무조건 1명, 참여율 최저(고정 10%)
_BUFFER_GRADE = "보조원"       # 명수 탄력 운영 버퍼
_LEAD_RATE = 0.10              # 책임연구원 고정 참여율 (최소 10%·제일 적음)
_TRIM_UNIT = 10000            # 만원 — 절삭 단위
_DEFAULT_MAX_BUFFER = 10      # 보조원 최대 인원 기본값


def available_labor(target: float, expense_total: float, profit_on: bool) -> float:
    """목표 견적금액(VAT 포함)에서 역산한 가용 인건비."""
    v = target / (1 + VAT_RATE)          # 공급가액
    if profit_on:
        v = v / (1 + PROFIT_RATE)        # 이윤 제거 → 인건비+경비+일반관리비
    v = v / (1 + MGMT_RATE)              # 일반관리비 제거 → 인건비+경비
    return v - expense_total


def goal_seek(target: float, labor_rows: list, expense_rows: list,
              profit_on: bool = True, mode: str = "uniform",
              locked: list = None) -> GoalSeekResult:
    """labor_rows의 count/months는 유지하고 rate만 역산.

    mode: "uniform" 균등 참여율 / "ratio" 기존 rate 비율 유지
    locked: 참여율을 그대로 둘(값 고정) 직급 인덱스. 고정 행 인건비는 예산에서
            먼저 차감하고, 나머지 직급만 역산한다.

    참여율은 고운 격자로 올림 → 총계 ≥ 목표, '만원 미만' 잔액만 자동 절삭하여
    최종견적 = 목표금액에 정확히 일치시킨다. (1% 반올림 방식은 폐지)
    """
    res = GoalSeekResult(ok=False)
    locked_ids = {id(labor_rows[i]) for i in (locked or []) if 0 <= i < len(labor_rows)}
    locked_amt = sum(labor_rows[i].amount for i in (locked or []) if 0 <= i < len(labor_rows))
    # 고정 직급은 역산 대상(active)에서 제외 — 명수·참여율을 그대로 유지
    active = [r for r in labor_rows
              if r.count > 0 and r.months > 0 and id(r) not in locked_ids]
    if not active:
        res.error = ("역산할 직급이 없습니다. 명수·기간을 입력하거나 "
                     "고정한 직급을 일부 해제하세요.")
        return res

    expense_total = sum(e.amount for e in expense_rows)
    L = available_labor(target, expense_total, profit_on) - locked_amt
    res.available_labor = L
    if L <= 0:
        res.error = (f"경비·고정 인건비 합계가 목표 금액 대비 너무 큽니다. "
                     f"가용 인건비가 {L:,.0f}원으로 0 이하입니다.")
        return res

    bases = {id(r): r.base for r in active}
    total_base = sum(bases.values())

    if mode == "ratio" and any(r.rate > 0 for r in active):
        weighted = sum(r.base * r.rate for r in active)
        if weighted <= 0:
            mode = "uniform"
        else:
            scale = L / weighted
            raw_rates = {id(r): r.rate * scale for r in active}
    if mode != "ratio" or not any(r.rate > 0 for r in active):
        r_uni = L / total_base
        raw_rates = {id(r): r_uni for r in active}

    def total_with(rates_map):
        for r in active:
            r.rate = rates_map[id(r)]
        return calculate(labor_rows, expense_rows, profit_on, trim=0.0).total

    # ── 만원 미만 절삭: 참여율을 점점 고운 격자로 올림 → 총계 ≥ 목표, 잔액 < 만원
    rates = dict(raw_rates)
    for q in (0.0001, 0.00001, 0.000001):       # 0.01% → 0.001% → 0.0001%
        q_rates = {k: math.ceil(v / q) * q for k, v in raw_rates.items()}
        if total_with(q_rates) - target < _TRIM_UNIT:
            rates = q_rates
            break
        rates = q_rates

    total = total_with(rates)
    trim = round_half_up(total - target)
    if trim < 0:
        trim = 0
        res.warnings.append(
            "전 직급 참여율 100%로도 목표 금액에 미달합니다. "
            "명수 또는 기간(월)을 늘리세요.")

    # 검증: 절삭 반영 시 최종견적 표시값 == 목표
    final_check = round_half_up(total_with(rates) - trim)
    if abs(final_check - round_half_up(target)) > 1:
        res.warnings.append(
            f"최종견적({final_check:,}원)이 목표({round_half_up(target):,}원)와 "
            f"{final_check - round_half_up(target):+,}원 차이납니다.")

    for r in active:
        if rates[id(r)] > 1.0 + 1e-9:
            res.warnings.append(
                f"{r.grade} 참여율이 {rates[id(r)]*100:.1f}%로 100%를 초과합니다. "
                f"명수 또는 기간을 늘리세요.")

    res.ok = True
    res.trim = max(0, trim)
    res.rates = [rates.get(id(r), r.rate) for r in labor_rows]
    return res


def goal_seek_labor(target: float, labor_rows: list, expense_rows: list,
                    profit_on: bool = True, max_counts: dict = None,
                    locked: list = None) -> LaborSeekResult:
    """목표 견적금액 → 인건비 자동조정 (목표값-찾기 방식).

    규칙(사용자 확정):
      - 책임연구원: 무조건 1명, 참여율 10% 고정 (가장 적음).
      - 책임 외 전원(연구원·연구보조원·보조원): 참여율을 동시에 비례/균등 스케일.
      - 보조원: 참여율이 100%를 넘으면 명수를 max_counts까지 늘려 흡수(탄력 운영).
      - 단가·기간은 고정. 1% 반올림 없음.
      - 참여율을 고운 격자로 올림 → 총계 ≥ 목표, '만원 미만' 잔액만 절삭.
      - 최종견적 = 목표금액과 정확히 일치.

    locked: 자동조정에서 제외할 직급 인덱스(값 고정). 고정 행의 명수·참여율은
            현재 값 그대로 유지되며 예산에서 먼저 차감되고, 나머지 직급만 스케일된다.
            책임연구원을 고정하면 1명·10% 규칙 대신 사용자가 입력한 값을 그대로 쓴다.

    경비는 건드리지 않는다(수동 조작 원칙).
    """
    res = LaborSeekResult(ok=False)
    max_counts = max_counts or {}
    locked = set(locked or [])
    n = len(labor_rows)
    orig = [(r.count, r.rate) for r in labor_rows]   # 끝에 원복

    def restore():
        for i, (c, rt) in enumerate(orig):
            labor_rows[i].count, labor_rows[i].rate = c, rt

    expense_total = sum(e.amount for e in expense_rows)
    L = available_labor(target, expense_total, profit_on)
    if L <= 0:
        res.error = (f"경비 합계({expense_total:,.0f}원)가 목표 대비 너무 큽니다. "
                     f"가용 인건비가 {L:,.0f}원으로 0 이하입니다.")
        return res

    lead_idx = next((i for i, r in enumerate(labor_rows)
                     if r.grade == _LEAD_GRADE), None)
    buf_idx = next((i for i, r in enumerate(labor_rows)
                    if r.grade == _BUFFER_GRADE), None)

    # ── 책임연구원 고정 (1명·10%) — 단, 사용자가 직접 '값 고정'하면 입력값 유지
    if lead_idx is not None and lead_idx not in locked:
        labor_rows[lead_idx].count = 1
        labor_rows[lead_idx].rate = _LEAD_RATE
        if labor_rows[lead_idx].months <= 0:
            res.warnings.append("책임연구원 기간(월)이 0입니다. 기간을 입력하세요.")

    # ── 고정 직급(책임 + 사용자 고정) 인건비를 먼저 예산에서 차감
    fixed_idxs = set(locked)
    if lead_idx is not None:
        fixed_idxs.add(lead_idx)
    fixed_amt = sum(labor_rows[i].amount for i in fixed_idxs)

    L_other = L - fixed_amt
    if L_other <= 0:
        restore()
        res.error = ("목표금액이 너무 낮아 고정된 직급(책임연구원·값 고정 직급)의 "
                     "인건비 합계도 초과합니다. 고정을 해제하거나 목표금액을 높이세요.")
        return res

    def adj_idxs():
        """고정 외, 명수·기간 유효한 조정 대상 인덱스."""
        return [i for i, r in enumerate(labor_rows)
                if i not in fixed_idxs and r.count > 0 and r.months > 0]

    def solve(idxs):
        """idxs 직급 참여율을 L_other에 맞게 스케일. 비례(기존 rate) 또는 균등."""
        bases = {i: labor_rows[i].unit_price * labor_rows[i].count * labor_rows[i].months
                 for i in idxs}
        idxs = [i for i in idxs if bases[i] > 0]
        if not idxs:
            return None
        weighted = sum(bases[i] * orig[i][1] for i in idxs)
        if weighted > 0:                       # 비례 유지
            scale = L_other / weighted
            return {i: orig[i][1] * scale for i in idxs}
        total_base = sum(bases[i] for i in idxs)   # 균등
        r_uni = L_other / total_base
        return {i: r_uni for i in idxs}

    buf_free = buf_idx is not None and buf_idx not in fixed_idxs   # 보조원 탄력 가능?
    idxs = adj_idxs()
    # 조정 대상이 전무하면 보조원을 버퍼로 활성화 (단, 고정되지 않은 경우)
    if not idxs and buf_free and labor_rows[buf_idx].months > 0:
        labor_rows[buf_idx].count = max(1, labor_rows[buf_idx].count)
        idxs = adj_idxs()
    if not idxs:
        restore()
        res.error = ("조정할 인건비 직급이 없습니다. 연구원·보조원 명수와 기간(월)을 "
                     "입력하거나, 고정한 직급을 일부 해제하세요.")
        return res

    # ── 보조원 명수 탄력: 참여율 100% 초과 시 보조원 +1 (max까지)
    max_buf = int(max_counts.get(_BUFFER_GRADE, _DEFAULT_MAX_BUFFER) or _DEFAULT_MAX_BUFFER)
    rates = solve(idxs)
    guard = 0
    while (rates and max(rates.values()) > 1.0 and buf_free
           and labor_rows[buf_idx].months > 0
           and labor_rows[buf_idx].count < max_buf and guard < 100):
        labor_rows[buf_idx].count += 1
        idxs = adj_idxs()
        rates = solve(idxs)
        guard += 1

    if rates is None:
        restore()
        res.error = "참여율 계산에 필요한 단가·명수·기간이 부족합니다."
        return res
    if max(rates.values()) > 1.0 + 1e-9:
        res.warnings.append(
            "일부 직급 참여율이 100%를 초과합니다(보조원 최대 인원 도달). "
            "명수 또는 기간(월)을 늘리세요.")

    def total_with(rmap):
        for i in idxs:
            labor_rows[i].rate = rmap[i]
        return calculate(labor_rows, expense_rows, profit_on, trim=0.0).total

    # ── 만원 미만 절삭: 참여율을 점점 고운 격자로 올림 → 잔액 < 만원
    chosen = rates
    for q in (0.0001, 0.00001, 0.000001):       # 0.01% → 0.001% → 0.0001%
        q_rates = {i: math.ceil(v / q) * q for i, v in rates.items()}
        if total_with(q_rates) - target < _TRIM_UNIT:
            chosen = q_rates
            break
        chosen = q_rates
    total = total_with(chosen)
    trim = round_half_up(total - target)
    if trim < 0:
        trim = 0
        res.warnings.append("참여율 100%로도 목표 금액에 미달합니다. 명수 또는 기간을 늘리세요.")

    res.ok = True
    res.trim = max(0, trim)
    res.rates = [labor_rows[i].rate for i in range(n)]
    res.counts = [int(labor_rows[i].count) for i in range(n)]
    restore()
    return res
