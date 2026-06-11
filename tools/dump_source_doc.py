# -*- coding: utf-8 -*-
"""새 원본 견적서 분석: 텍스트 전체 + 기존 필드 목록 덤프 (읽기 전용 — 사본에 작업)."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SRC = r"C:\Users\eicic.AIDEN-DESKTOP\Downloads\[내비온] 국가수리과학연구소 용역견적서_예산 증액안_20260610(수정 4차) .hwp"
OUT_TXT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "source_doc_dump.txt")


def main():
    assert os.path.exists(SRC), f"원본 없음: {SRC}"
    orig_size = os.path.getsize(SRC)

    tmp = os.path.join(tempfile.gettempdir(), "_navion_tpl_src_copy.hwp")
    shutil.copy2(SRC, tmp)

    from src.hwp.hwp_writer import make_hwp
    hwp = make_hwp()
    lines = []
    try:
        hwp.open(tmp, arg="forceopen:true")
        lines.append(f"=== 원본: {SRC} ({orig_size:,} bytes) ===")

        # 기존 필드 목록 (계산식 잔재 포함 여부)
        for opt in (0, 1, 2, 3):
            try:
                fl = hwp.GetFieldList(0, opt)
                names = [f.split("{{")[0] for f in fl.split("\x02") if f]
                lines.append(f"GetFieldList(opt={opt}): {len(names)}개 {sorted(set(names))}")
            except Exception as e:
                lines.append(f"GetFieldList(opt={opt}) err: {e}")

        # 전체 텍스트 추출
        txt_path = os.path.join(tempfile.gettempdir(), "_navion_tpl_src_dump.txt")
        hwp.save_as(txt_path, format="TEXT")
        with open(txt_path, "rb") as fp:
            raw = fp.read()
        body = None
        if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            body = raw.decode("utf-16")
        else:
            for enc in ("utf-8", "cp949"):
                try:
                    body = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
        if body is None:
            body = raw.decode("cp949", errors="replace")
        lines.append("=== 본문 텍스트 ===")
        lines.append(body)
        os.remove(txt_path)
    finally:
        try:
            hwp.quit()
        except Exception:
            pass
        try:
            os.remove(tmp)
        except OSError:
            pass

    assert os.path.getsize(SRC) == orig_size, "원본 크기 변동!"
    with open(OUT_TXT, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines))
    print(f"OK → {OUT_TXT} (원본 무결성 확인)")


if __name__ == "__main__":
    main()
