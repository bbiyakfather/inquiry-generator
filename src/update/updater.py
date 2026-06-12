# -*- coding: utf-8 -*-
"""GitHub Releases 기반 자동 업데이트 엔진.

흐름:
  1) check_latest()   — GitHub API로 최신 릴리스 확인
  2) start(url, size) — 백그라운드 스레드: 다운로드 → 압축해제 → phase=ready
  3) status()         — JS 폴링용 상태 스냅샷
  4) apply(pid, dir, exe) — updater 배치 작성·실행(detached), 호출측이 창 종료

개발 모드(is_frozen()==False)에서 apply()는 동작하지 않는다.
"""

import os
import sys
import tempfile
import threading
import zipfile

import requests

from src.version import GITHUB_REPO, __version__, is_newer

# ── 전역 상태 (스레드 세이프) ──────────────────────────────────────────────────
_lock = threading.Lock()
_state: dict = {"phase": "idle", "pct": 0, "msg": "", "error": ""}
# 마지막 check_latest 결과를 캐시 (start/apply 시 재사용)
_last_check: dict = {}


def _set(**kw):
    with _lock:
        _state.update(kw)


def _reset():
    _set(phase="idle", pct=0, msg="", error="")


# ── 1) 최신 버전 확인 ─────────────────────────────────────────────────────────

def check_latest(timeout: int = 15) -> dict:
    """GitHub Releases latest 엔드포인트를 조회한다.

    반환 dict:
      ok, latest_tag, has_update, notes, asset_url, asset_name, asset_size
    """
    global _last_check

    repo = GITHUB_REPO.strip()
    if not repo:
        return {"ok": False, "error": "GITHUB_REPO가 설정되지 않았습니다 (src/version.py 참조)."}

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        resp = requests.get(
            url,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": f"navion-inquiry-generator/{__version__}"},
            timeout=timeout,
        )
    except requests.Timeout:
        return {"ok": False, "error": f"응답 시간 초과({timeout}초). 네트워크를 확인하세요."}
    except requests.ConnectionError:
        return {"ok": False, "error": "네트워크에 연결할 수 없습니다."}
    except Exception as e:
        return {"ok": False, "error": f"네트워크 오류: {e}"}

    if resp.status_code == 404:
        return {"ok": False, "error": "GitHub 저장소 또는 릴리스를 찾을 수 없습니다."}
    if resp.status_code in (403, 429):
        return {"ok": False, "error": "GitHub API 요청 한도 초과. 잠시 후 다시 시도하세요."}
    if resp.status_code != 200:
        return {"ok": False, "error": f"GitHub API 오류 (HTTP {resp.status_code})."}

    data = resp.json()
    tag = data.get("tag_name", "")
    notes = data.get("body", "") or ""

    # .zip 에셋만 선택 (draft/prerelease는 latest 엔드포인트가 이미 제외)
    asset_url = asset_name = asset_size = None
    for asset in (data.get("assets") or []):
        if asset.get("name", "").lower().endswith(".zip"):
            asset_url = asset.get("browser_download_url", "")
            asset_name = asset.get("name", "")
            asset_size = asset.get("size", 0)
            break

    has_upd = bool(tag and is_newer(tag))
    result = {
        "ok": True,
        "latest_tag": tag,
        "has_update": has_upd,
        "notes": notes[:800],        # UI 표시용 — 너무 길면 자름
        "asset_url": asset_url or "",
        "asset_name": asset_name or "",
        "asset_size": asset_size or 0,
    }
    _last_check = result
    return result


# ── 2) 백그라운드 다운로드 ────────────────────────────────────────────────────

def start(asset_url: str, asset_size: int = 0) -> None:
    """다운로드·압축해제를 백그라운드 스레드에서 시작한다."""
    _set(phase="downloading", pct=0, msg="다운로드 준비 중…", error="")
    t = threading.Thread(target=_worker, args=(asset_url, asset_size), daemon=True)
    t.start()


def _work_dir() -> str:
    return os.path.join(tempfile.gettempdir(), "navion_update")


def _worker(asset_url: str, asset_size: int):
    work = _work_dir()
    zip_path = os.path.join(work, "download.zip")
    staging = os.path.join(work, "staging")

    try:
        os.makedirs(work, exist_ok=True)

        # ── 다운로드 ──────────────────────────────────────────────────────────
        _set(phase="downloading", pct=0, msg="다운로드 시작…")
        resp = requests.get(asset_url, stream=True, timeout=120,
                            headers={"User-Agent": f"navion-inquiry-generator/{__version__}"})
        resp.raise_for_status()

        total = asset_size or int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024  # 1 MB

        with open(zip_path, "wb") as fp:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    fp.write(chunk)
                    downloaded += len(chunk)
                    pct = int(downloaded * 100 / total) if total else 0
                    mb = downloaded / 1024 / 1024
                    _set(pct=pct, msg=f"다운로드 중… {mb:.1f} MB")

        _set(phase="extracting", pct=0, msg="압축 해제 중…")

        # ── 압축 해제 ─────────────────────────────────────────────────────────
        if os.path.isdir(staging):
            import shutil
            shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.namelist()
            for i, member in enumerate(members):
                zf.extract(member, staging)
                _set(pct=int((i + 1) * 100 / len(members)))

        # ── 최상위 폴더 탐지 (한글 폴더명 하드코딩 회피) ─────────────────────
        top_dirs = [d for d in os.listdir(staging)
                    if os.path.isdir(os.path.join(staging, d))]
        if len(top_dirs) == 1:
            staging_app = os.path.join(staging, top_dirs[0])
        else:
            # 단일 폴더가 없으면 staging 자체를 앱 루트로 간주
            staging_app = staging

        _set(phase="ready", pct=100,
             msg=f"준비 완료 — {staging_app}",
             error="")

    except Exception as e:
        _set(phase="error", error=str(e), msg="")


# ── 3) 상태 조회 ──────────────────────────────────────────────────────────────

def status() -> dict:
    with _lock:
        return dict(_state)


# ── 4) 업데이트 적용 (배치 작성 + detached 실행) ───────────────────────────────

def apply(pid: int, install_dir: str, app_exe_name: str) -> dict:
    """updater 배치를 %TEMP%\\navion_update 에 쓰고 detached 실행한다.

    호출 측이 이 함수 반환 직후 창을 종료해야 한다.
    frozen 아닐 때는 오류를 반환한다(배치 교체는 EXE 환경에서만 의미있음).
    """
    from src.paths import is_frozen
    if not is_frozen():
        return {"ok": False, "error": "개발 모드에서는 업데이트 적용이 지원되지 않습니다."}

    with _lock:
        if _state.get("phase") != "ready":
            return {"ok": False, "error": "아직 다운로드가 완료되지 않았습니다."}
        staging_app = _state.get("msg", "").replace("준비 완료 — ", "").strip()

    if not staging_app or not os.path.isdir(staging_app):
        return {"ok": False, "error": "압축 해제 폴더를 찾을 수 없습니다."}

    staging_root = _work_dir()
    bat_path = os.path.join(staging_root, "apply_update.bat")
    app_exe = os.path.join(install_dir, app_exe_name)

    # 경로에 따옴표가 필요한 경우를 위해 인용
    def q(p):
        return f'"{p}"'

    bat_lines = [
        "@echo off",
        "chcp 65001 >nul",
        f"set PID={pid}",
        ":wait",
        f"tasklist /fi \"PID eq %PID%\" 2>nul | find \"{pid}\" >nul",
        "if not errorlevel 1 ( timeout /t 1 /nobreak >nul & goto wait )",
        f"robocopy {q(staging_app)} {q(install_dir)} /E /IS /IT /R:2 /W:1 >nul",
        f"start \"\" {q(app_exe)}",
        f"rmdir /s /q {q(staging_root)}",
        "(goto) 2>nul & del \"%~f0\"",
    ]

    try:
        with open(bat_path, "w", encoding="utf-8") as fp:
            fp.write("\r\n".join(bat_lines) + "\r\n")
    except Exception as e:
        return {"ok": False, "error": f"배치 파일 작성 실패: {e}"}

    try:
        import subprocess
        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
            close_fds=True,
        )
    except Exception as e:
        return {"ok": False, "error": f"업데이트 프로세스 실행 실패: {e}"}

    _set(phase="applying")
    return {"ok": True}
