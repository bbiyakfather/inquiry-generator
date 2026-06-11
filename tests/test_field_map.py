# -*- coding: utf-8 -*-
"""RenderPlan(필드 매핑) 순수 로직 테스트."""
from src.engine.calc import LaborRow, ExpenseRow, calculate
from src.hwp.field_map import build_render_plan

DOC = {
    "recipient": "한국과학기술연구원",
    "quote_no": "제 2026-001호",
    "ref_name": "", "ref_tel": "",
    "date": "2026-06-10",
    "service_name": "테스트 용역",
    "service_period": "계약일로부터 3주일",
}


def _quote_22m():
    labor = [
        LaborRow("책임연구원", 6993408, count=1, rate=0.4, months=0.75),
        LaborRow("연구원", 5362452, count=2, rate=0.4, months=0.75),
        LaborRow("연구보조원", 3584618, count=4, rate=0.4, months=0.75),
    ]
    expenses = [
        ExpenseRow("전문가 활용비", details=["- 시장참여자 검증/자문"],
                   qty_text="5명", unit_price=600000, qty=5),
        ExpenseRow("문헌구입비", details=["- 산업동향 유료 보고서 구매"],
                   qty_text="1식", unit_price=4000000, qty=1),
        ExpenseRow("국내여비", details=["- 교통비, 식사비 등"],
                   qty_text="-", unit_price=308982),
        ExpenseRow("회의비", details=["- 3~4인 * 4회"],
                   qty_text="13명", unit_price=30000, qty=13),
    ]
    return calculate(labor, expenses, profit_on=True, trim=0.0)


class TestRenderPlan:
    def test_golden_22m_fields(self):
        plan = build_render_plan(DOC, _quote_22m())
        f = plan.fields
        assert plan.labor_used == 3
        assert plan.exp_used == 4
        assert plan.show_trim is False
        assert f["labor1_amt"] == "2,098,022"
        assert f["labor1_months"] == "0.75개월"
        assert f["labor1_rate"] == "40%"
        assert f["labor3_amt"] == "4,301,542"
        assert f["labor_sum_amt"] == "9,617,035"
        assert f["labor_sum_ratio"] == "43.7%"
        assert f["exp_sum_amt"] == "7,698,982"
        assert f["subtotal_amt"] == "17,316,017"
        assert f["mgmt_amt"] == "865,801"
        assert f["profit_amt"] == "1,818,182"
        assert f["supply_amt"] == "20,000,000"
        assert f["vat_amt"] == "2,000,000"
        assert f["final_amt"] == "22,000,000"
        assert f["final_ratio"] == "100.0%"
        assert f["amount_kor"] == "금이천이백만원정 (₩ 22,000,000), 부가세 포함"
        assert f["quote_date"] == "2026년 6월 10일"
        # 빈 참조/전화는 안내문 노출 방지용 공백
        assert f["ref_name"] == " "
        # 절삭 행 없음 → trim 필드 미포함
        assert "trim_amt" not in f

    def test_no_profit_display(self):
        labor = [LaborRow("책임연구원", 3783728, count=1, rate=0.5, months=6)]
        q = calculate(labor, [], profit_on=False, trim=0.0)
        plan = build_render_plan(DOC, q)
        assert plan.fields["profit_basis"] == "이윤 미계상"
        assert plan.fields["profit_amt"] == "-"

    def test_trim_row(self):
        labor = [LaborRow("책임연구원", 3783728, count=1, rate=0.5, months=6)]
        q = calculate(labor, [], profit_on=True, trim=71487)
        plan = build_render_plan(DOC, q)
        assert plan.show_trim is True
        assert plan.fields["trim_amt"] == "-71,487"

    def test_multiline_detail_joined_crlf(self):
        q = _quote_22m()
        q.expense_rows[0].details = ["- 줄1", "- 줄2", "- 줄3"]
        plan = build_render_plan(DOC, q)
        assert plan.fields["exp1_detail"] == "- 줄1\r\n- 줄2\r\n- 줄3"
