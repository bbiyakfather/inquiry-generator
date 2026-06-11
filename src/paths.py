# -*- coding: utf-8 -*-
"""실행 경로 해석 — 개발 실행과 PyInstaller EXE를 동일 코드로 지원.

두 종류의 경로를 구분한다:
  - resource_*  : 읽기 전용 번들 리소스 (ui/, templates/). EXE에서는 _MEIPASS.
  - data_*      : 쓰기 가능한 사용자 데이터 (config.json, token.json, 로그).
                  EXE에서는 exe가 놓인 폴더 (임시 _MEIPASS가 아니라 영구 위치).

개발 모드(비 frozen)에서는 둘 다 프로젝트 루트로 동일 → 기존 동작·테스트 불변.
"""
import os
import sys

# 이 파일은 <루트>/src/paths.py → 루트 = 두 단계 상위
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> str:
    """읽기 전용 번들 리소스의 기준 폴더."""
    if is_frozen():
        # onefile: 임시 추출 폴더, onedir: _internal 폴더
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return _PROJECT_ROOT


def data_root() -> str:
    """쓰기 가능한 데이터의 기준 폴더 (EXE 옆, 영구)."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return _PROJECT_ROOT


def resource_path(*parts) -> str:
    return os.path.join(resource_root(), *parts)


def data_path(*parts) -> str:
    return os.path.join(data_root(), *parts)
