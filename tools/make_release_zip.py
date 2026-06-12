#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""배포용 ZIP 생성 헬퍼.

빌드 후 dist\\내비온 견적서 생성기\\ 폴더에서 배포 ZIP을 만든다.
kordoc-runtime\\node_modules 는 기본적으로 제외(~750 MB 절감).
kordoc 의존성이 바뀐 릴리스에서만 --full 옵션으로 포함할 것.

사용:
  py tools/make_release_zip.py            # kordoc 제외 (권장, ~70 MB)
  py tools/make_release_zip.py --full     # 전체 포함 (~1 GB)
"""

import argparse
import os
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.version import __version__

DIST_NAME = "내비온 견적서 생성기"
DIST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dist", DIST_NAME)
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dist")

# kordoc-runtime 하위 제외 항목 (full 아닐 때)
EXCLUDE_PREFIXES_PARTIAL = ["kordoc-runtime" + os.sep + "node_modules"]


def should_exclude(rel_path: str, full: bool) -> bool:
    if full:
        return False
    for prefix in EXCLUDE_PREFIXES_PARTIAL:
        if rel_path.startswith(prefix):
            return True
    return False


def make_zip(full: bool):
    suffix = "-full" if full else ""
    zip_name = f"내비온 견적서-회의록 생성기 v{__version__}{suffix}.zip"
    zip_path = os.path.join(OUT_DIR, zip_name)

    if not os.path.isdir(DIST_DIR):
        print(f"[오류] dist 폴더 없음: {DIST_DIR}")
        print("  먼저 빌드를 실행하세요: py -3.12 -m PyInstaller navion_quote.spec --noconfirm")
        sys.exit(1)

    print(f"ZIP 생성 중: {zip_path}")
    excluded = 0
    included = 0

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(DIST_DIR):
            # config.json, token.json, app-log.txt 는 사용자 데이터 → 배포에서 제외
            dirs[:] = [d for d in dirs if d not in {"__pycache__"}]
            for fname in files:
                if fname in {"config.json", "token.json", "app-log.txt"}:
                    continue
                full_path = os.path.join(root, fname)
                rel = os.path.relpath(full_path, os.path.dirname(DIST_DIR))
                if should_exclude(os.path.relpath(full_path, DIST_DIR), full):
                    excluded += 1
                    continue
                zf.write(full_path, rel)
                included += 1

    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print(f"  포함: {included}개 파일, 제외: {excluded}개 파일")
    print(f"  크기: {size_mb:.1f} MB")
    print(f"  완료: {zip_path}")
    return zip_path


def main():
    parser = argparse.ArgumentParser(description="배포 ZIP 생성")
    parser.add_argument("--full", action="store_true",
                        help="kordoc-runtime/node_modules 포함 (전체 빌드)")
    args = parser.parse_args()
    make_zip(full=args.full)


if __name__ == "__main__":
    main()
