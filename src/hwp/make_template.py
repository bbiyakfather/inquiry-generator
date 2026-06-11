# -*- coding: utf-8 -*-
"""1회성 템플릿화: 원본 견적서 → 필드 삽입된 templates/견적서_템플릿.hwp

원본은 절대 수정하지 않고 사본에 작업한다.
처리 순서(문서 순서대로 — 중복 텍스트는 순방향 찾기로 자연 해소):
  1. 수신처 셀: 가변 텍스트를 누름틀로 치환 (recv, quote_no, ref_name, ref_tel, quote_date)
  2. 용역명/용역기간/견적금액 셀 필드
  3. 인건비 3행 필드 + 보조원(4행) 행 추가
  4. 인건비 계: %fmu 계산식 필드 제거 후 필드 부여
  5. 경비 4행 필드 + 4행 추가 확장(총 8행)
  6. 경비 계 / 소계 / 일반관리비 / 이윤 / 총계 / 부가세 필드
  7. 절삭 행 추가 (부가세 아래)
  8. 최종견적 필드
  9. GetFieldList 검증 → 저장 → 검증용 PDF 출력
"""
import json
import os
import shutil
import sys
import traceback

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ORIGINAL = os.path.join(BASE, "내비온_견적서_저가의 고효율 라이다 센서 사업 타당성 분석 용역.hwp")
TEMPLATE = os.path.join(BASE, "templates", "견적서_템플릿.hwp")
CHECK_PDF = os.path.join(BASE, "templates", "_template_check.pdf")

LOG = []


def log(msg):
    LOG.append(str(msg))
    print(f"[tpl] {msg}", flush=True)


def find_text(hwp, text):
    pset = hwp.HParameterSet.HFindReplace
    hwp.HAction.GetDefault("RepeatFind", pset.HSet)
    pset.FindString = text
    pset.IgnoreMessage = 1
    pset.FindType = 1
    try:
        pset.Direction = hwp.FindDir("Forward")
    except Exception:
        pset.Direction = 0
    ok = bool(hwp.HAction.Execute("RepeatFind", pset.HSet))
    if not ok:
        raise RuntimeError(f"찾기 실패: {text!r}")
    return ok


def set_cell_field(hwp, name):
    """현재 캐럿 셀에 셀 필드 부여."""
    hwp.SetCurFieldName(name, option=1, direction="", memo="")


def step(hwp, action, n=1):
    for _ in range(n):
        hwp.Run(action)


def addr(hwp):
    try:
        ki = hwp.KeyIndicator()
        return ki[-1] if ki else "?"
    except Exception:
        return "?"


def field_row(hwp, names, first_at_caret=True):
    """캐럿 셀부터 오른쪽으로 이동하며 필드 연속 부여."""
    for i, name in enumerate(names):
        if i > 0 or not first_at_caret:
            step(hwp, "TableRightCell")
        set_cell_field(hwp, name)
        log(f"  field {name} @ {addr(hwp)}")


def insert_row_below(hwp):
    """현재 행 아래에 행 삽입 후 캐럿을 새 행(같은 열)으로 이동.

    실측: TableInsertLowerRow는 캐럿을 원래 셀에 남겨둔다 → TableLowerCell로 진입.
    """
    a0 = addr(hwp)
    step(hwp, "TableInsertLowerRow")
    step(hwp, "TableLowerCell")
    a1 = addr(hwp)
    log(f"  row insert+enter: {a0} → {a1}")
    if a0 == a1:
        raise RuntimeError(f"새 행 진입 실패: {a0}")


def main():
    os.makedirs(os.path.dirname(TEMPLATE), exist_ok=True)
    work = TEMPLATE  # 사본에 직접 작업
    shutil.copy2(ORIGINAL, work)
    orig_size = os.path.getsize(ORIGINAL)
    log(f"copy → {work}")

    from pyhwpx import Hwp
    hwp = Hwp(new=True, visible=False, register_module=True)
    try:
        hwp.open(work, arg="forceopen:true")
        log("open ok")

        # 초기 필드 목록 (계산식 %fmu 포함 여부 확인)
        for opt in (0, 1, 2, 3):
            try:
                fl = hwp.GetFieldList(0, opt)
                log(f"GetFieldList(opt={opt}): {fl!r}")
            except Exception as e:
                log(f"GetFieldList(opt={opt}) err: {e}")

        # ---- 1. 수신처 셀 누름틀 ----
        hwp.Run("MoveDocBegin")
        # 수신기관명: 찾기 → (선택됨) → 삭제 → 누름틀
        find_text(hwp, "한국과학기술연구원")
        hwp.Run("Delete")
        r = hwp.CreateField("recv", "수신기관명", "")
        log(f"누름틀 recv: create={r}, exist={hwp.FieldExist('recv')}")

        find_text(hwp, "제 2023-152호")
        hwp.Run("Delete")
        r = hwp.CreateField("quote_no", "견적번호", "")
        log(f"누름틀 quote_no: create={r}, exist={hwp.FieldExist('quote_no')}")

        find_text(hwp, "참    조 :")
        step(hwp, "MoveRight")  # 선택 해제(블록 끝으로)
        r = hwp.CreateField("ref_name", "참조자", "")
        log(f"누름틀 ref_name: create={r}, exist={hwp.FieldExist('ref_name')}")

        find_text(hwp, "전화번호 :")  # 수신처 셀의 전화번호(공급자 블록보다 앞)
        step(hwp, "MoveRight")
        r = hwp.CreateField("ref_tel", "연락처", "")
        log(f"누름틀 ref_tel: create={r}, exist={hwp.FieldExist('ref_tel')}")

        find_text(hwp, "2023년 11월 23일")
        hwp.Run("Delete")
        r = hwp.CreateField("quote_date", "견적일자", "")
        log(f"누름틀 quote_date: create={r}, exist={hwp.FieldExist('quote_date')}")

        # ---- 2. 용역명/기간/금액 ----
        find_text(hwp, "저가의 고효율 라이다 센서 사업 타당성 분석 용역")
        set_cell_field(hwp, "svc_name")
        log(f"svc_name @ {addr(hwp)}")
        find_text(hwp, "계약일로부터 3주일")
        set_cell_field(hwp, "svc_period")
        log(f"svc_period @ {addr(hwp)}")
        find_text(hwp, "금이천이백만원정")
        set_cell_field(hwp, "amount_kor")
        log(f"amount_kor @ {addr(hwp)}")

        # ---- 3. 인건비 3행 ----
        labor_anchor = {1: "6,993,408", 2: "5,362,452", 3: "3,584,618"}
        for i in (1, 2, 3):
            find_text(hwp, labor_anchor[i])
            set_cell_field(hwp, f"labor{i}_price")
            log(f"labor{i}_price @ {addr(hwp)}")
            step(hwp, "TableLeftCell")
            set_cell_field(hwp, f"labor{i}_cnt")
            step(hwp, "TableLeftCell")
            set_cell_field(hwp, f"labor{i}_grade")
            step(hwp, "TableRightCell", 3)  # cnt, price 지나 참여기간으로
            field_row(hwp, [f"labor{i}_months", f"labor{i}_rate",
                            f"labor{i}_amt", f"labor{i}_ratio"])

        # ---- 보조원(labor4) 행 추가: labor3 행 아래 ----
        hwp.MoveToField("labor3_grade", True, True, False)
        insert_row_below(hwp)
        field_row(hwp, ["labor4_grade", "labor4_cnt", "labor4_price",
                        "labor4_months", "labor4_rate", "labor4_amt",
                        "labor4_ratio"])

        # ---- 4. 인건비 계 (%fmu 계산식 처리) ----
        find_text(hwp, "9,617,035")
        log(f"인건비 계 셀 진입: {addr(hwp)}")
        # 계산식 필드 제거 시도 1: DeleteField (캐럿이 필드 안일 때)
        try:
            r = hwp.DeleteField()
            log(f"DeleteField → {r}, 상태: {addr(hwp)}")
        except Exception as e:
            log(f"DeleteField 예외: {e}")
        # 시도 2: 셀 내용 전체 삭제
        step(hwp, "TableCellBlock")
        step(hwp, "Delete")
        log(f"셀 내용 삭제 후 상태: {addr(hwp)}")
        set_cell_field(hwp, "labor_sum_amt")
        # 검증: PutFieldText 왕복
        hwp.PutFieldText("labor_sum_amt", "999")
        got = hwp.GetFieldText("labor_sum_amt")
        log(f"labor_sum_amt 왕복: {got!r}, 상태: {addr(hwp)}")
        hwp.PutFieldText("labor_sum_amt", "")
        step(hwp, "TableRightCell")
        set_cell_field(hwp, "labor_sum_ratio")
        log(f"labor_sum_ratio @ {addr(hwp)}")

        # ---- 5. 경비 4행 ----
        exp_anchor = {1: "전문가 활용비", 2: "문헌구입비", 3: "국내여비", 4: "회의비"}
        for i in (1, 2, 3, 4):
            find_text(hwp, exp_anchor[i])
            set_cell_field(hwp, f"exp{i}_name")
            log(f"exp{i}_name @ {addr(hwp)}")
            field_row(hwp, [f"exp{i}_detail", f"exp{i}_qty", f"exp{i}_price",
                            f"exp{i}_amt", f"exp{i}_ratio"], first_at_caret=False)

        # ---- 경비 4행 추가 (exp5~exp8) ----
        for i in (5, 6, 7, 8):
            hwp.MoveToField(f"exp{i-1}_name", True, True, False)
            insert_row_below(hwp)
            field_row(hwp, [f"exp{i}_name", f"exp{i}_detail", f"exp{i}_qty",
                            f"exp{i}_price", f"exp{i}_amt", f"exp{i}_ratio"])

        # ---- 6. 경비 계 / 소계 ----
        find_text(hwp, "7,698,982")
        set_cell_field(hwp, "exp_sum_amt")
        step(hwp, "TableRightCell")
        set_cell_field(hwp, "exp_sum_ratio")
        log(f"exp_sum @ {addr(hwp)}")

        find_text(hwp, "17,316,017")
        set_cell_field(hwp, "subtotal_amt")
        step(hwp, "TableRightCell")
        set_cell_field(hwp, "subtotal_ratio")
        log(f"subtotal @ {addr(hwp)}")

        # ---- 일반관리비 / 이윤 ----
        find_text(hwp, "인건비+경비의 6% 이내")
        set_cell_field(hwp, "mgmt_basis")
        field_row(hwp, ["mgmt_amt", "mgmt_ratio"], first_at_caret=False)

        find_text(hwp, "인건비+경비+일반관리비의 10% 이내")
        set_cell_field(hwp, "profit_basis")
        field_row(hwp, ["profit_amt", "profit_ratio"], first_at_caret=False)

        # ---- 총계(공급가액) ----
        find_text(hwp, "20,000,000")
        set_cell_field(hwp, "supply_amt")
        step(hwp, "TableRightCell")
        set_cell_field(hwp, "supply_ratio")
        log(f"supply @ {addr(hwp)}")

        # ---- 부가세 ----
        find_text(hwp, "공급가액의 10%")
        set_cell_field(hwp, "vat_basis")
        field_row(hwp, ["vat_amt", "vat_ratio"], first_at_caret=False)

        # ---- 7. 절삭 행 (부가세 행 아래) ----
        insert_row_below(hwp)  # vat_ratio 셀에서 아래로
        # 캐럿은 새 행의 같은 열(구성비 열) → 왼쪽으로 이동하며 부여
        set_cell_field(hwp, "trim_ratio")
        step(hwp, "TableLeftCell")
        set_cell_field(hwp, "trim_amt")
        step(hwp, "TableLeftCell")
        set_cell_field(hwp, "trim_basis")
        step(hwp, "TableLeftCell")
        set_cell_field(hwp, "trim_label")
        log(f"trim_label @ {addr(hwp)}")

        # ---- 8. 최종견적 ----
        find_text(hwp, "22,000,000")
        set_cell_field(hwp, "final_amt")
        step(hwp, "TableRightCell")
        set_cell_field(hwp, "final_ratio")
        log(f"final @ {addr(hwp)}")

        # 절삭 라벨 텍스트 기입 (필드라서 PutFieldText로)
        hwp.PutFieldText("trim_label", "절    삭")
        hwp.PutFieldText("trim_basis", "총계+부가세-최종견적")

        # ---- 9. 검증 ----
        fields = set()
        for opt in (0, 1, 2, 3):
            try:
                fl = hwp.GetFieldList(0, opt)
                names = [f.split("{{")[0] for f in fl.split("\x02") if f]
                log(f"GetFieldList(opt={opt}): {len(names)}개 {sorted(set(names))}")
                fields |= set(names)
            except Exception as e:
                log(f"GetFieldList(opt={opt}) err: {e}")
        fields = set(fields)
        log(f"최종 필드 수(전체 옵션 합집합): {len(fields)}")

        expected = {"recv", "quote_no", "ref_name", "ref_tel", "quote_date",
                    "svc_name", "svc_period", "amount_kor",
                    "labor_sum_amt", "labor_sum_ratio",
                    "exp_sum_amt", "exp_sum_ratio",
                    "subtotal_amt", "subtotal_ratio",
                    "mgmt_basis", "mgmt_amt", "mgmt_ratio",
                    "profit_basis", "profit_amt", "profit_ratio",
                    "supply_amt", "supply_ratio",
                    "vat_basis", "vat_amt", "vat_ratio",
                    "trim_label", "trim_basis", "trim_amt", "trim_ratio",
                    "final_amt", "final_ratio"}
        for i in (1, 2, 3, 4):
            expected |= {f"labor{i}_{s}" for s in
                         ("grade", "cnt", "price", "months", "rate", "amt", "ratio")}
        for i in range(1, 9):
            expected |= {f"exp{i}_{s}" for s in
                         ("name", "detail", "qty", "price", "amt", "ratio")}
        missing = expected - set(fields)
        extra = set(fields) - expected
        log(f"누락 필드: {sorted(missing) if missing else '없음'}")
        log(f"추가 필드(계산식 잔재 등): {sorted(extra) if extra else '없음'}")

        # 저장
        hwp.save_as(work, format="HWP")
        log(f"템플릿 저장: {work} ({os.path.getsize(work):,} bytes)")
        hwp.save_as(CHECK_PDF, format="PDF")
        log(f"검증 PDF: {CHECK_PDF}")

        ok = not missing
        log(f"RESULT: {'OK' if ok else 'MISSING_FIELDS'}")
    finally:
        try:
            hwp.quit()
        except Exception:
            pass

    assert os.path.getsize(ORIGINAL) == orig_size, "원본 크기 변동!"
    log("원본 무결성 확인")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(traceback.format_exc(), file=sys.stderr)
        print("===LOG===")
        print("\n".join(LOG))
        sys.exit(1)

