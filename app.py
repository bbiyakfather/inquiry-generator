# -*- coding: utf-8 -*-
"""내비온 견적서 생성기 — 진입점.

실행: python app.py   (디버그: python app.py --debug)
시작/종료 과정은 app-log.txt에 기록된다 (창이 안 뜨는 문제 진단용).
"""
import os
import sys
import traceback

# frozen exe에서 requests/certifi가 bundled cacert.pem을 찾지 못하는 문제 해결.
# PyInstaller가 certifi 데이터를 _MEIPASS/certifi/cacert.pem에 번들하므로
# SSL_CERT_FILE 환경변수로 그 경로를 명시해줘야 한다.
if getattr(sys, "frozen", False):
    _cert = os.path.join(sys._MEIPASS, "certifi", "cacert.pem")
    if os.path.isfile(_cert):
        os.environ.setdefault("SSL_CERT_FILE", _cert)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", _cert)

# MOTW(다운로드 차단) 자가치유 — 카카오톡/브라우저로 받은 ZIP을 풀면 모든 파일에
# Zone.Identifier(인터넷 존) 스트림이 붙고, .NET이 Python.Runtime.dll 로드를 거부해
# pywebview(import clr) 시점에 즉사한다(0x80131515). webview import 전에 DLL의
# ADS를 제거한다. 실패해도 부팅은 계속(.exe.config의 loadFromRemoteSources가 2차 방어).
if getattr(sys, "frozen", False):
    try:
        import ctypes
        _internal = os.path.join(os.path.dirname(sys.executable), "_internal")
        for _root, _, _files in os.walk(_internal):
            for _f in _files:
                if _f.lower().endswith(".dll"):
                    ctypes.windll.kernel32.DeleteFileW(
                        os.path.join(_root, _f) + ":Zone.Identifier"
                    )
    except Exception:
        pass

from src.paths import resource_path
from src.logutil import log as _log

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    _log(f"=== 시작: python {sys.version.split()[0]} | exe={sys.executable} | cwd={os.getcwd()}")
    import webview
    try:
        from importlib.metadata import version
        _log(f"pywebview {version('pywebview')} 로드됨")
    except Exception:
        pass

    from src.api import Api
    api = Api()
    _log("Api 초기화 완료 (config 로드)")

    window = webview.create_window(
        "내비온 견적서 생성기",
        resource_path("ui", "index.html"),
        js_api=api,
        width=1440, height=920, min_size=(1120, 720),
        background_color="#F6F7FB",
    )
    api.attach_window(window)
    _log("창 객체 생성 — GUI 루프 진입")
    try:
        webview.start(gui="edgechromium", debug="--debug" in sys.argv)
        _log("GUI 루프 종료 (모든 창 닫힘)")
    finally:
        api.shutdown()
        _log("종료 정리 완료")


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        _log("치명적 오류:\n" + traceback.format_exc())
        raise
