# -*- coding: utf-8 -*-
"""한글 금액 표기 변환.

22000000 → "금이천이백만원정 (₩ 22,000,000), 부가세 포함"
재무 문서 관행에 따라 천/백/십 선두의 1은 '일'을 표기한다 (일천삼백만 등).
keep_il=False 시 '천삼백만' 스타일.
"""

_DIGITS = "일이삼사오육칠팔구"          # 1~9
_SMALL = [(1000, "천"), (100, "백"), (10, "십"), (1, "")]
_BIG = ["", "만", "억", "조", "경"]


def _group_to_kor(n: int, keep_il: bool) -> str:
    """0 < n <= 9999 그룹을 한글로."""
    out = []
    for unit, name in _SMALL:
        d = (n // unit) % 10
        if d == 0:
            continue
        if d == 1 and name and not keep_il:
            out.append(name)
        else:
            out.append(_DIGITS[d - 1] + name)
    return "".join(out)


def num_to_kor(n: int, keep_il: bool = True) -> str:
    """정수 → 한글 숫자 표기 (만 단위 그룹핑)."""
    n = int(n)
    if n == 0:
        return "영"
    if n < 0:
        return "마이너스" + num_to_kor(-n, keep_il)
    groups = []   # (한글, 큰단위) 낮은 자리부터
    big_idx = 0
    while n > 0:
        g = n % 10000
        if g:
            groups.append(_group_to_kor(g, keep_il) + _BIG[big_idx])
        n //= 10000
        big_idx += 1
    return "".join(reversed(groups))


def amount_kor(amount: int, keep_il: bool = True, vat_included: bool = True) -> str:
    """견적서 견적금액 셀 표기."""
    kor = num_to_kor(int(amount), keep_il)
    suffix = ", 부가세 포함" if vat_included else ", 부가세 별도"
    return f"금{kor}원정 (₩ {int(amount):,}){suffix}"
