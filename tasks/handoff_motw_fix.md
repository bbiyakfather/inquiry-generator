# 핸드오프: MOTW(다운로드 차단) 버그 수정

**작성일**: 2026-06-11  
**상태**: 분석 완료 / 수정 미적용  
**우선순위**: 높음 (클라이언트 납품 시 재현 가능)

---

## 문제 요약

내비온 견적서 생성기 V1.1을 카카오톡으로 전달받아 실행한 클라이언트 PC에서
앱이 즉시 종료되는 문제.

**에러 메시지** (팝업):
```
Failed to execute script 'app' due to unhandled exception:
Failed to resolve Python.Runtime.Loader.Initialize from
C:\Users\com\Downloads\내비온 견적서 생성기 V 1.1\_internal\pythonnet\runtime\Python.Runtime.dll
```

---

## 원인 (100% 확정)

**Windows Mark-of-the-Web (MOTW) — 다운로드 파일 인터넷 존 차단**

### 근거

클라이언트 `app-log.txt` 분석:

```
[10:05:28] === 시작: python 3.13.13 | exe=C:\Users\com\Downloads\내비온 견적서 생성기 V 1.1\...
[10:05:28] pywebview 6.2.1 로드됨
[10:05:28] Api 초기화 완료 (config 로드)
[10:05:28] 창 객체 생성 — GUI 루프 진입
[10:05:29] 종료 정리 완료                   ← 비정상 종료
[10:05:29] 치명적 오류: RuntimeError: Failed to resolve Python.Runtime.Loader.Initialize
```

빌드 PC(AIDEN-DESKTOP) 로그 — 동일 바이너리, 정상 동작:
```
[01:17:35] 창 객체 생성 — GUI 루프 진입
[01:17:49] GUI 루프 종료 (모든 창 닫힘)   ← 정상
```

| 실행 위치 | 경로 패턴 | 결과 |
|---|---|---|
| 빌드 PC (AIDEN-DESKTOP) | 로컬 dist\ | ✅ 정상 |
| 김형일 PC | 로컬 dist\ | ✅ 정상 |
| **클라이언트 (com)** | **Downloads\ (다운로드)** | ❌ 실패 |

### 메커니즘

1. 카카오톡/브라우저로 ZIP 수신 → 탐색기로 압축 해제
2. 탐색기가 내부 모든 파일에 `Zone.Identifier`(인터넷 존=3) NTFS 스트림 부착
3. pythonnet이 `Assembly.LoadFrom`으로 `Python.Runtime.dll` 적재 시도
4. .NET Framework가 인터넷 존 어셈블리 **기본 거부** (HRESULT 0x80131515)
5. `clr_loader/netfx.py:47` → `"Failed to resolve ..."` 발생
6. pywebview가 winforms 백엔드를 import하는 순간(= `import clr`) 죽음

PyInstaller 부트로더·`python313.dll`은 Win32 `LoadLibrary`로 로드돼 MOTW 무시
→ 그래서 pywebview 로드/Api 초기화까지는 멀쩡히 진행됨.

---

## 즉시 해결 (클라이언트, 재빌드 불필요)

클라이언트 PC에서 PowerShell 실행:

```powershell
Get-ChildItem -Path "C:\Users\com\Downloads\내비온 견적서 생성기 V 1.1" -Recurse | Unblock-File
```

또는 배포 전: ZIP 파일 우클릭 → 속성 → **[차단 해제]** 체크 → 적용 → 그 다음 압축 해제.

---

## 근본 해결 (다음 배포부터 면역)

### 방법 A — `.exe.config` 동봉 (권장, 가장 표준)

`dist/내비온 견적서 생성기/내비온 견적서 생성기.exe.config` 파일을 추가:

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <runtime>
    <loadFromRemoteSources enabled="true"/>
  </runtime>
  <startup>
    <supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.7.2"/>
  </startup>
</configuration>
```

**위치**: EXE와 **같은 최상위 폴더** (= `_internal` 안이 아님)

`navion_quote.spec`의 `COLLECT` 블록에 자동 복사 추가:

```python
# spec 파일 최하단, coll = COLLECT(...) 다음에 추가
import shutil, os
_dist_dir = os.path.join("dist", "내비온 견적서 생성기")
shutil.copy("내비온 견적서 생성기.exe.config", _dist_dir)
```

또는 `datas`에 포함:
```python
datas = [
    ...
    ("내비온 견적서 생성기.exe.config", "."),  # EXE 옆에 배치
]
```

### 방법 B — app.py 자가치유 코드 (재빌드만 하면 끝)

`app.py` 상단 (SSL_CERT_FILE 처리 블록 바로 다음)에 삽입:

```python
# 다운로드 배포 시 MOTW(Zone.Identifier)로 DLL 차단 방지
if getattr(sys, "frozen", False):
    import ctypes
    _internal = os.path.join(os.path.dirname(sys.executable), "_internal")
    for root, _, files in os.walk(_internal):
        for f in files:
            if f.endswith(".dll"):
                ctypes.windll.kernel32.DeleteFileW(
                    os.path.join(root, f) + ":Zone.Identifier"
                )
```

### 방법 C — Inno Setup 설치기 (배포 품질 최대)

설치 파일(`.exe`)로 배포하면 MOTW 자체가 붙지 않음.
SmartScreen 경고도 서명 추가 시 제거 가능.

---

## 부수 발견: 빌드 환경 드리프트

- 배포된 V1.1: **Python 3.13.13**으로 빌드됨 (AIDEN-DESKTOP)
- 현재 김형일 PC: Python **3.12** / **3.14** 만 설치 (3.13 없음)
- `navion_quote.spec` 주석은 `py -3.12`로 표기되어 있어 실제 배포본과 불일치

**→ 다음 빌드 전, 어느 Python 버전으로 통일할지 결정 필요.**  
  AIDEN-DESKTOP에서 빌드하거나, 김형일 PC에 3.13 추가 설치.

---

## 다음 세션에서 할 일

- [ ] **즉시**: 클라이언트에게 `Unblock-File` PowerShell 명령 전달 → 테스트 확인
- [ ] **방법 A 적용**: `.exe.config` 파일 생성 + spec에 datas 추가
- [ ] **재빌드 테스트**: 수정 후 V1.2 빌드 → 다운로드 ZIP 시뮬레이션 (`Unblock-File` 없이 실행) 검증
- [ ] **빌드 Python 버전 통일**: 3.13 또는 3.12 중 택일하여 spec 주석 및 README 업데이트
- [ ] (선택) `tasks/lessons.md`에 MOTW 함정 기록

---

## 참고 파일

- 클라이언트 로그: `카카오톡 받은 파일/app-log.txt`
- 빌드 명세: `navion_quote.spec`
- 앱 진입점: `app.py` (SSL_CERT_FILE 패턴 참고)
- 에러 발생 소스: `clr_loader/netfx.py:47`, `pythonnet/__init__.py:143`
