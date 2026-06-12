# -*- coding: utf-8 -*-
"""견적서 HWP 템플릿 필드 재스캔 → fieldmap.json 갱신.

빌드 전 1회 실행해 fieldmap.json을 최신화한다.
생성된 fieldmap.json은 PyInstaller가 번들에 포함시킨다.

실행:
    cd (프로젝트 루트)
    python tools/rescan_template.py
    python tools/rescan_template.py --template templates\견적서_템플릿.hwp
"""
import argparse
import os
import sys

# 프로젝트 루트를 sys.path에 추가 (tools/ 한 단계 위)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    parser = argparse.ArgumentParser(description="견적서 HWP 템플릿 필드 재스캔")
    parser.add_argument(
        "--template", "-t",
        default=None,
        help="스캔할 HWP 파일 경로 (생략 시 templates/견적서_템플릿.hwp 사용)",
    )
    args = parser.parse_args()

    from src.hwp.hwp_writer import HwpWorker, TEMPLATE_DEFAULT
    from src.ai.template_mapper import save_fieldmap

    tpl = args.template or TEMPLATE_DEFAULT
    tpl = os.path.abspath(tpl)

    if not os.path.isfile(tpl):
        print(f"[오류] 템플릿 파일을 찾을 수 없습니다: {tpl}")
        sys.exit(1)

    print(f"스캔 대상: {tpl}")
    print("한글(HWP)을 시작합니다... (최초 실행은 수십 초 소요)")

    worker = HwpWorker(tpl)
    try:
        result = worker.scan_fields(tpl, timeout=120)
    finally:
        worker.shutdown(timeout=15)

    if not result.get("ok"):
        print(f"[오류] 스캔 실패: {result.get('error', '알 수 없음')}")
        sys.exit(1)

    print(f"  발견 필드 수  : {len(result['fields'])}개")
    print(f"  인건비 최대 행: {result['max_labor']}행")
    print(f"  경비 최대 행  : {result['max_exp']}행")
    print(f"  표준 템플릿   : {'예 (AI 매핑 불필요)' if result['is_standard'] else '아니오'}")

    if result.get("unknown"):
        print(f"  비표준 필드   : {result['unknown']}")
    if result.get("missing"):
        print(f"  누락 필드     : {result['missing']}")

    unknown = result.get("unknown", [])
    missing = result.get("missing", [])

    # unknown: 템플릿에만 있는 비표준 필드명 → AI 매핑 필요
    # missing: 최대 표준(4행/8행) 대비 누락된 행 → 템플릿이 적은 행 수 사용 (정상)
    if unknown:
        print(f"\n[주의] 비표준 필드명이 있습니다 ({len(unknown)}개). "
              "앱 UI '분석·적용' 버튼으로 AI 매핑 후 저장하세요.")
        print("  비표준 필드:", unknown)
        print("fieldmap을 저장하지 않습니다.")
        sys.exit(1)

    if missing:
        print(f"\n[정보] 표준 최대 행(인건비 4/경비 8) 대비 일부 행이 없습니다 ({len(missing)}개).")
        print("  → 이 템플릿은 인건비 {ml}행 / 경비 {me}행 구성으로 동작합니다.".format(
            ml=result["max_labor"], me=result["max_exp"]))
        print("  → 비표준 필드명은 없으므로 fieldmap을 저장합니다.")

    path = save_fieldmap(tpl, result, {"field_map": {}, "unmapped": []})
    print(f"\n[완료] fieldmap 저장: {path}")
    print("이제 PyInstaller 빌드를 실행하세요:")
    print("  py -3.12 -m PyInstaller navion_quote.spec --noconfirm")


if __name__ == "__main__":
    main()
