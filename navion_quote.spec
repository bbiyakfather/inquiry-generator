# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 빌드 명세 — 내비온 견적서 생성기.

빌드:  py -3.12 -m PyInstaller navion_quote.spec --noconfirm
산출:  dist/내비온 견적서 생성기/내비온 견적서 생성기.exe  (onedir)

- ui/, templates/ 는 데이터로 번들(읽기 전용). 코드에서 src.paths.resource_path로 접근.
- config.json/token.json/app-log.txt 는 EXE 옆(쓰기 가능 위치)에 생성됨.
- pywebview(EdgeChromium)는 자체 PyInstaller 훅이 WebView2 DLL을 자동 수집.
"""
from PyInstaller.utils.hooks import collect_all, collect_data_files

# templates 폴더 전체가 아니라 실제 사용하는 템플릿 1개만 번들.
# (직인 포함 백업본 '견적서_템플릿_직인포함.hwp'가 배포물에 들어가지 않도록)
datas = [
    ("ui", "ui"),
    ("templates/견적서_템플릿.hwp", "templates"),
    ("templates/회의록_양식.hwpx", "templates"),
    *collect_data_files('certifi'),   # cacert.pem — HTTPS 요청용 TLS 인증서 번들
]
binaries = []
hiddenimports = [
    # pywin32 (pyhwpx COM + DPAPI 키 암호화)
    "win32com", "win32com.client", "win32timezone", "win32crypt",
    "pythoncom", "pywintypes",
    # pythonnet (pywebview EdgeChromium 백엔드)
    "clr",
]

# 데이터/바이너리/서브모듈을 통째로 수집해야 안전한 패키지들
for pkg in ("webview", "clr_loader", "pythonnet", "pyhwpx",
            "googleapiclient", "google_auth_oauthlib",
            "google.auth", "google.oauth2", "google_auth_httplib2"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "_pytest", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="내비온 견적서 생성기",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI 앱: 콘솔 없음 (오류는 app-log.txt에 기록됨)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",   # 견적서 모티프 아이콘 (tools/make_icon.py로 재생성)
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="내비온 견적서 생성기",
)

# MOTW(다운로드 차단) 대응 — .exe.config는 EXE와 같은 최상위 폴더에 있어야
# .NET Framework가 인식한다. PyInstaller 6.x는 datas를 전부 _internal/ 아래로
# 넣으므로 datas로는 불가능 → COLLECT 후 직접 복사한다.
# (다운로드 ZIP 해제 시 Zone.Identifier가 붙은 Python.Runtime.dll 로드 거부 방지)
import shutil as _shutil
import os as _os
_dist_dir = _os.path.join(DISTPATH, "내비온 견적서 생성기")
_shutil.copy(
    _os.path.join(SPECPATH, "내비온 견적서 생성기.exe.config"),
    _os.path.join(_dist_dir, "내비온 견적서 생성기.exe.config"),
)

# kordoc-runtime 내장 — Node.js 별도 설치 불필요
# PyInstaller 6.x는 datas를 _internal/ 아래로 복사하므로 data_path()가 찾지 못한다.
# COLLECT 후 exe 옆에 직접 복사하고, 빌드 머신의 node.exe도 동봉한다.
_kordoc_src = _os.path.join(SPECPATH, "kordoc-runtime")
_kordoc_dst = _os.path.join(_dist_dir, "kordoc-runtime")
if _os.path.isdir(_kordoc_src):
    if _os.path.isdir(_kordoc_dst):
        _shutil.rmtree(_kordoc_dst)
    _shutil.copytree(_kordoc_src, _kordoc_dst)
    # 빌드 머신의 node.exe를 동봉 (사용자가 Node.js를 별도 설치할 필요 없음)
    _node_dst = _os.path.join(_kordoc_dst, "node.exe")
    if not _os.path.isfile(_node_dst):
        _node_src = _shutil.which("node")
        if _node_src and _os.path.isfile(_node_src):
            _shutil.copy2(_node_src, _node_dst)
            print(f"[spec] node.exe 동봉 완료: {_node_src} → {_node_dst}")
        else:
            print("[spec] 경고: 빌드 머신에 node.exe를 찾지 못했습니다. "
                  "Node.js를 설치한 뒤 다시 빌드하세요.")
