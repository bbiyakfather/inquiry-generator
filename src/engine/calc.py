# -*- coding: utf-8 -*-
"""견적 계산 엔진 — 엑셀 '용역비용 계산(이윤없는 버전).xlsx' Sheet1을 1:1 재현.

원칙:
  - 내부 계산은 raw float 체인 (엑셀과 동일한 연산 순서, 중간 반올림 없음)
  - 표시 단계에서만 half-up 반올림 (금액: 원 단위 정수, 구성비: 소수 1자리 %)
  - Python round()는 은행가 반올림이므로 사용 금지
  - 엑셀 PRODUCT는 빈 셀을 무시 (모두 비면 0)

용어 매핑 (엑셀 ↔ HWP 견적서):
  C25 인건비+경비   ↔ 소계(인건비+경비)
  C26 일반관리비    ↔ 일반관리비 (5%)
  C27 이윤          ↔ 이윤 (10%, 무이윤 버전은 0)
  C28 원가          ↔ '총계' (공급가액)
  C29 부가세        ↔ 부가세
  C30 총계          ↔ (HWP에 없음, 원가+부가세)
  C31 절삭          ↔ (옵션 행)
  C32 견적금액      ↔ 최종견적
"""
import math
from dataclasses import dataclass, field
from typing import Optional

ROLES = ["책임연구원", "연구원", "연구보조원", "보조원"]

# 2026년 학술연구용역 인건비 기준단가 (월 단위). 참조용 — 실제 소스는 config_store.
UNIT_PRICES = {
    "2026": {
        "책임연구원": 7567456,
        "연구원": 5802624,
        "연구보조원": 3878858,
        "보조원": 2909242,
    }
}

MGMT_RATE = 0.05    # 일반관리비율 (인건비+경비의 5%)
PROFIT_RATE = 0.1   # 이윤율 ((인건비+경비+일반관리비)의 10%)
VAT_RATE = 0.1      # 부가가치세율


def parse_leading_num(s):
    """수량 표기에서 앞 숫자 추출: '5명'→5.0, '1식'→1.0, '-'→None."""
    import re
    m = re.match(r"[\d,]+(\.\d+)?", str(s) if s is not None else "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def round_half_up(x: float) -> int:
    """원 단위 half-up 반올림 (음수는 절댓값 기준)."""
    if x >= 0:
        return int(math.floor(x + 0.5))
    return -int(math.floor(-x + 0.5))


def pct1(ratio: float) -> float:
    """비율(0~1) → 퍼센트 소수 1자리 half-up (예: 0.19552 → 19.6)."""
    return math.floor(ratio * 1000 + 0.5) / 10


def fmt_won(x: float) -> str:
    return f"{round_half_up(x):,}"


def fmt_pct(ratio: float) -> str:
    return f"{pct1(ratio):.1f}%"


def fmt_num(x: float, max_dec: int = 6) -> str:
    """소수점 이하 불필요한 0 제거 (6 → '6', 0.75 → '0.75')."""
    s = f"{x:.{max_dec}f}".rstrip("0").rstrip(".")
    return s if s else "0"


def fmt_rate(rate: float) -> str:
    """참여율(0~1) → '40%' / '10.36%' 스타일."""
    p = rate * 100
    if abs(p - round(p)) < 1e-9:
        return f"{int(round(p))}%"
    return f"{fmt_num(p, 4)}%"


@dataclass
class LaborRow:
    grade: str                  # 직급
    unit_price: float           # 단가(원/월)
    count: float = 0            # 명수
    rate: float = 0.0           # 참여율 (0~1)
    months: float = 0           # 기간(월)

    @property
    def amount(self) -> float:
        # 엑셀 M = PRODUCT(단가, 명수, 참여율, 기간) — 순서 고정
        return self.unit_price * self.count * self.rate * self.months

    @property
    def base(self) -> float:
        """참여율 1.0 기준 금액 (goal-seek 분모)."""
        return self.unit_price * self.count * self.months


@dataclass
class ExpenseRow:
    name: str                       # 구분 (전문가 활용비 등)
    details: list = field(default_factory=list)  # 내역 불릿 ["- ...", ...]
    qty_text: str = ""              # 표시용 수량 ("5명", "1식", "-")
    unit_price: Optional[float] = None   # 단가
    qty: Optional[float] = None          # 수량(숫자)
    extra1: Optional[float] = None       # 기타값1
    extra2: Optional[float] = None       # 기타값2

    @property
    def amount(self) -> float:
        # 단가 없으면 금액 0 (수량만 있고 단가 없는 행이 수량값으로 잘못 계산되는 것 방지)
        if self.unit_price is None:
            return 0.0
        # 단가 × (있는 수량/기타값들). 엑셀 PRODUCT 의미: None 인자는 무시
        v = float(self.unit_price)
        for f in (self.qty, self.extra1, self.extra2):
            if f is not None:
                v *= f
        return v


@dataclass
class QuoteResult:
    """raw float 체인 계산 결과."""
    labor_rows: list
    expense_rows: list
    labor_total: float      # M15
    expense_total: float    # M26
    direct: float           # C25 인건비+경비
    mgmt: float             # C26 일반관리비
    profit: float           # C27 이윤
    supply: float           # C28 원가(공급가액) = HWP '총계'
    vat: float              # C29 부가세
    total: float            # C30 총계(원가+부가세)
    trim: float             # C31 절삭
    final: float            # C32 견적금액 = HWP '최종견적'
    profit_on: bool

    def ratio(self, x: float) -> float:
        return x / self.final if self.final else 0.0


def calculate(labor_rows: list, expense_rows: list,
              profit_on: bool = True, trim: float = 0.0) -> QuoteResult:
    """엑셀 섹션 ②·③ 재현."""
    labor_total = 0.0
    for r in labor_rows:
        labor_total += r.amount          # M15 = SUM(M11:M14)
    expense_total = 0.0
    for e in expense_rows:
        expense_total += e.amount        # M26 = SUM(M18:M25)

    direct = labor_total + expense_total             # C25
    mgmt = direct * MGMT_RATE                        # C26
    profit = (direct + mgmt) * PROFIT_RATE if profit_on else 0.0   # C27
    supply = direct + mgmt + profit                  # C28
    vat = supply * VAT_RATE                          # C29
    total = supply + vat                             # C30
    final = total - trim                             # C32

    return QuoteResult(
        labor_rows=labor_rows, expense_rows=expense_rows,
        labor_total=labor_total, expense_total=expense_total,
        direct=direct, mgmt=mgmt, profit=profit,
        supply=supply, vat=vat, total=total, trim=trim, final=final,
        profit_on=profit_on,
    )


@dataclass
class BudgetGuide:
    """엑셀 섹션 ① 예산금액 기준 견적 범위 (고객 예산 → 역산 가이드)."""
    budget: float          # C12 총계 (고객 제시 예산, VAT 포함)
    vat: float             # C13
    cost: float            # C14 원가
    profit: float          # C15 이윤
    mgmt: float            # C16 일반관리비
    direct: float          # C17 인건비+경비
    labor_target: float    # C18 인건비 목표 (총계 × labor_ratio)
    expense_target: float  # C19 경비 목표 (직접비 − 인건비 목표, 음수 시 0 클램프)


def budget_guide(budget: float, profit_on: bool = True,
                 labor_ratio: float = 0.5) -> BudgetGuide:
    vat = budget - budget / (1 + VAT_RATE)                 # C13
    cost = budget - vat                                    # C14
    profit = (cost - cost / (1 + PROFIT_RATE)) if profit_on else 0.0   # C15
    mgmt = (cost - profit) - (cost - profit) / (1 + MGMT_RATE)         # C16
    direct = cost - profit - mgmt                          # C17
    ratio = max(0.0, min(1.0, float(labor_ratio)))
    labor_target = budget * ratio                          # C18
    expense_target = max(0.0, direct - labor_target)       # C19
    return BudgetGuide(budget, vat, cost, profit, mgmt, direct,
                       labor_target, expense_target)
