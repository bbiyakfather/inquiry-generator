# -*- coding: utf-8 -*-
"""HWP 생성기 — 템플릿 사본에 필드 기입 + 미사용 행 삭제 + HWP/PDF 저장.

COM 규칙:
  - 모든 한글 COM 호출은 전용 워커 스레드(HwpWorker) 안에서만 수행 (STA 직렬화)
  - 숨김 실행, 세션 재사용, 작업당 watchdog
  - 원본/템플릿은 읽기 전용 취급: 출력 경로에 사본을 만들고 그 사본을 연다
"""
import glob
import os
import queue
import shutil
import subprocess
import threading
import time
import traceback

from src.paths import resource_path, data_path
from src.logutil import log

# exe 옆 templates/ 폴더가 있으면 우선 사용 (재빌드 없이 템플릿 교체 가능)
# 없으면 번들 기본본(_MEIPASS) 사용
def _resolve_template_default():
    ext = data_path("templates", "견적서_템플릿.hwp")
    return ext if os.path.exists(ext) else resource_path("templates", "견적서_템플릿.hwp")

TEMPLATE_DEFAULT = _resolve_template_default()

MAX_LABOR = 4
MAX_EXP = 8

# COM 자동화 서버 실행 실패 계열 오류 (CO_E_SERVER_EXEC_FAILURE 등) —
# 새 사용자 프로필에서 한글이 한 번도 초기화되지 않았을 때 발생.
_SERVER_EXEC_HRESULTS = (-2146959355, -2147221021, -2147221164, -2147467259)


def _hwp_exe_path():
    """레지스트리(LocalServer32) 또는 알려진 설치 경로에서 Hwp.exe 경로를 찾는다."""
    try:
        import winreg
    except Exception:
        winreg = None

    def _read(root, sub):
        try:
            with winreg.OpenKey(root, sub) as k:
                return winreg.QueryValueEx(k, None)[0]
        except OSError:
            return None

    if winreg is not None:
        clsid = None
        for progid in ("HWPFrame.HwpObject", "HWPFrame.HwpObject.1",
                       "HWPFrame.HwpObject.2"):
            clsid = _read(winreg.HKEY_CLASSES_ROOT, progid + r"\CLSID")
            if clsid:
                break
        subs = []
        if clsid:
            # 64비트 파이썬 + 32비트 한글이면 LocalServer32가 WOW6432Node 아래에 있음
            subs = [rf"WOW6432Node\CLSID\{clsid}\LocalServer32",
                    rf"CLSID\{clsid}\LocalServer32"]
        for sub in subs:
            val = _read(winreg.HKEY_CLASSES_ROOT, sub)
            if not val:
                continue
            # 값 예: "C:\...\Hwp.exe" -Automation
            path = val.split('"')[1] if '"' in val else val.split(" -")[0].strip()
            if os.path.exists(path):
                return path

    # 폴백: 표준 설치 경로 패턴 탐색
    for pat in (r"C:\Program Files (x86)\HNC\*\HOffice*\Bin\Hwp.exe",
                r"C:\Program Files\HNC\*\HOffice*\Bin\Hwp.exe",
                r"C:\Program Files (x86)\Hnc\*\*\Bin\Hwp.exe",
                r"C:\Program Files\Hnc\*\*\Bin\Hwp.exe"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def _prelaunch_automation(wait: float = 14.0) -> bool:
    """한글 자동화 서버(Hwp.exe -Automation)를 직접 선기동하고 COM 등록을 기다린다.

    새 프로필 첫 실행 시 한글이 백그라운드에서 자기 자신을 띄우지 못해
    CO_E_SERVER_EXEC_FAILURE가 나는 문제를 우회한다(수동 1회 기동과 동일 효과)."""
    exe = _hwp_exe_path()
    if not exe:
        log("자가복구: Hwp.exe 경로를 찾지 못했습니다 (한글 미설치 가능).")
        return False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen([exe, "-Automation"], creationflags=flags)
    except Exception as e:
        log(f"자가복구: 자동화 서버 기동 실패: {e}")
        return False
    deadline = time.time() + wait
    while time.time() < deadline:
        time.sleep(1.0)
        try:
            import win32com.client
            win32com.client.Dispatch("HWPFrame.HwpObject")
            log("자가복구: 자동화 서버 준비 완료.")
            return True
        except Exception:
            continue
    log("자가복구: 자동화 서버 응답 대기 시간 초과 — 그래도 재시도합니다.")
    return True


def _clear_gen_py_cache():
    """손상되거나 파이썬 버전 불일치인 win32com gen_py 캐시를 제거한다."""
    try:
        import win32com
        gen = getattr(win32com, "__gen_path__", "")
        if not gen:
            gen = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp", "gen_py")
        if gen and os.path.isdir(gen):
            shutil.rmtree(gen, ignore_errors=True)
            log(f"자가복구: win32com gen_py 캐시 정리 ({gen}).")
    except Exception as e:
        log(f"자가복구: gen_py 캐시 정리 실패: {e}")


def make_hwp():
    """한글 COM 인스턴스 생성. 첫 기동 실패 시 자가복구(서버 선기동/캐시 정리) 후 재시도."""
    from pyhwpx import Hwp
    try:
        return Hwp(new=True, visible=False, register_module=True)
    except Exception as e:
        hres = getattr(e, "hresult", None) or (e.args[0] if getattr(e, "args", None) else None)
        log(f"HWP 1차 기동 실패(hresult={hres}) → 자가복구 시도: {e}")
        # 1단계: 자동화 서버 직접 선기동 후 재시도
        _prelaunch_automation()
        last = e
        for _ in range(3):
            try:
                return Hwp(new=True, visible=False, register_module=True)
            except Exception as e2:
                last = e2
                time.sleep(2.0)
        # 2단계: gen_py 캐시 손상 가능성 → 정리 후 마지막 재시도
        _clear_gen_py_cache()
        _prelaunch_automation()
        try:
            return Hwp(new=True, visible=False, register_module=True)
        except Exception as e3:
            last = e3
        log(f"HWP 자가복구 실패 — 한글 구동 불가: {last}")
        raise last


def _hwp_pids():
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Hwp.exe", "/FO", "CSV"],
            capture_output=True, text=True, timeout=10).stdout
        pids = set()
        for line in out.splitlines()[1:]:
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) >= 2 and parts[1].isdigit():
                pids.add(int(parts[1]))
        return pids
    except Exception:
        return set()


def _scan_fields_com(hwp, hwp_path: str) -> dict:
    """한글 COM으로 템플릿 필드 목록 + max_labor/max_exp 감지."""
    import re
    hwp.open(hwp_path, arg="forceopen:true")
    fields = set()
    for opt in (0, 1, 2, 3):
        try:
            fl = hwp.GetFieldList(0, opt)
            for f in fl.split("\x02"):
                n = f.split("{{")[0].strip()
                if n:
                    fields.add(n)
        except Exception:
            pass

    # 연번 최대값 감지
    max_labor = 0
    max_exp = 0
    for f in fields:
        m = re.match(r"labor(\d+)_", f)
        if m:
            max_labor = max(max_labor, int(m.group(1)))
        m = re.match(r"exp(\d+)_", f)
        if m:
            max_exp = max(max_exp, int(m.group(1)))

    # 표준 필드셋과 대조
    std = _standard_field_set(max(max_labor, MAX_LABOR), max(max_exp, MAX_EXP))
    unknown = sorted(fields - std)
    missing = sorted(std - fields)
    is_standard = not unknown and not missing

    hwp.Run("FileClose")
    return {"fields": sorted(fields), "max_labor": max_labor or MAX_LABOR,
            "max_exp": max_exp or MAX_EXP, "is_standard": is_standard,
            "unknown": unknown, "missing": missing}


def _standard_field_set(max_labor=MAX_LABOR, max_exp=MAX_EXP) -> set:
    """표준 필드명 전체 집합."""
    s = {"recv", "quote_no", "ref_name", "ref_tel", "quote_date",
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
    for i in range(1, max_labor + 1):
        s |= {f"labor{i}_{x}" for x in
              ("grade", "cnt", "price", "months", "rate", "amt", "ratio")}
    for i in range(1, max_exp + 1):
        s |= {f"exp{i}_{x}" for x in
              ("name", "detail", "qty", "price", "amt", "ratio")}
    return s


def _load_fieldmap_for(template_path: str) -> dict:
    """템플릿 옆 .fieldmap.json 로드 (포맷 작성자: src/ai/template_mapper.py).
    없거나 손상이면 빈 dict → 표준 템플릿으로 동작."""
    import json
    path = os.path.splitext(template_path)[0] + ".fieldmap.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _fill_document(hwp, plan: dict, out_hwp: str, out_pdf: str = None,
                   template: str = TEMPLATE_DEFAULT,
                   fieldmap: dict = None) -> dict:
    """열린 한글 인스턴스로 1건 생성. plan: RenderPlan을 dict화한 것.

    fieldmap: template_mapper가 저장한 .fieldmap.json 전체 dict (없으면 표준 템플릿).
      - field_map: {템플릿 필드명 → 표준 슬롯명}. 여기서 역방향(표준→템플릿)으로
        뒤집어 필드 기입·행 삭제 시 템플릿 실제 필드명을 쓴다.
      - max_labor/max_exp: 템플릿의 행 수 (기본 4/8과 다를 수 있음).
    """
    report = {"hwp": None, "pdf": None, "pdf_error": "", "deleted_rows": []}

    fieldmap = fieldmap or {}
    max_labor_tpl = int(fieldmap.get("max_labor") or MAX_LABOR)
    max_exp_tpl = int(fieldmap.get("max_exp") or MAX_EXP)
    std_to_tpl = {std: tpl for tpl, std in (fieldmap.get("field_map") or {}).items()}

    def tpl_name(std_name):
        return std_to_tpl.get(std_name, std_name)

    os.makedirs(os.path.dirname(os.path.abspath(out_hwp)), exist_ok=True)
    shutil.copy2(template, out_hwp)
    hwp.open(out_hwp, arg="forceopen:true")

    def delete_row_at_field(name):
        if hwp.MoveToField(tpl_name(name), True, True, False):
            hwp.Run("TableDeleteRow")
            report["deleted_rows"].append(name)

    # 미사용 행 삭제 (아래쪽부터)
    labor_used = max(1, min(max_labor_tpl, int(plan["labor_used"])))
    exp_used = max(1, min(max_exp_tpl, int(plan["exp_used"])))
    for i in range(max_labor_tpl, labor_used, -1):
        delete_row_at_field(f"labor{i}_grade")
    for i in range(max_exp_tpl, exp_used, -1):
        delete_row_at_field(f"exp{i}_name")
    if not plan["show_trim"]:
        delete_row_at_field("trim_label")

    # 필드 기입 (표준 슬롯명 → 템플릿 필드명 번역)
    for name, value in plan["fields"].items():
        hwp.PutFieldText(tpl_name(name), value if value is not None else "")

    # 저장
    hwp.save_as(out_hwp, format="HWP")
    report["hwp"] = out_hwp
    if out_pdf:
        try:
            hwp.save_as(out_pdf, format="PDF")
            if os.path.exists(out_pdf) and os.path.getsize(out_pdf) > 0:
                report["pdf"] = out_pdf
            else:
                report["pdf_error"] = "PDF 파일이 생성되지 않았습니다."
        except Exception as e:
            report["pdf_error"] = f"PDF 변환 실패: {e}"
    return report


def generate_once(plan: dict, out_hwp: str, out_pdf: str = None,
                  template: str = TEMPLATE_DEFAULT) -> dict:
    """단발 생성 (자체 한글 인스턴스 생성/종료). 테스트·CLI용."""
    hwp = make_hwp()
    try:
        return _fill_document(hwp, plan, out_hwp, out_pdf, template,
                              fieldmap=_load_fieldmap_for(template))
    finally:
        try:
            hwp.quit()
        except Exception:
            pass


class HwpWorker:
    """한글 COM 전용 워커 스레드. submit()은 어느 스레드에서든 호출 가능."""

    def __init__(self, template: str = TEMPLATE_DEFAULT):
        self.template = template
        self._jobs = queue.Queue()
        self._session_pids = set()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="hwp-worker")
        self._thread.start()

    # ---------- 외부 API ----------
    def generate(self, plan: dict, out_hwp: str, out_pdf: str = None,
                 timeout: int = 180) -> dict:
        return self._submit({"op": "generate", "plan": plan,
                             "out_hwp": out_hwp, "out_pdf": out_pdf}, timeout)

    def diagnose(self, timeout: int = 60) -> dict:
        return self._submit({"op": "diagnose"}, timeout)

    def scan_fields(self, hwp_path: str, timeout: int = 60) -> dict:
        """템플릿 HWP의 필드 목록·max_labor·max_exp 스캔 (COM STA 스레드에서 실행)."""
        return self._submit({"op": "scan_fields", "hwp_path": hwp_path}, timeout)

    def shutdown(self, timeout: int = 8):
        """quit 작업 완료까지 대기 — 데몬 스레드가 죽기 전에 hwp.quit() 보장."""
        try:
            rq = queue.Queue()
            self._jobs.put({"op": "quit", "_result": rq})
            rq.get(timeout=timeout)
        except queue.Empty:
            # 응답 지연 시 좀비 방지를 위해 세션 강제 종료
            self._kill_session()
        except Exception:
            pass

    # ---------- 내부 ----------
    def _submit(self, job: dict, timeout: int) -> dict:
        rq = queue.Queue()
        job["_result"] = rq
        self._jobs.put(job)
        try:
            return rq.get(timeout=timeout)
        except queue.Empty:
            # watchdog: 멈춘 한글 프로세스 강제 종료 → 워커는 예외로 탈출
            self._kill_session()
            return {"ok": False, "error": f"한글 작업이 {timeout}초 안에 끝나지 않아 중단했습니다. "
                                          f"한글 창이 열려 있다면 닫고 다시 시도하세요."}

    def _kill_session(self):
        with self._lock:
            pids = set(self._session_pids)
        for pid in pids:
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=10)
            except Exception:
                pass

    def _loop(self):
        import pythoncom
        pythoncom.CoInitialize()
        hwp = None

        def ensure_hwp():
            nonlocal hwp
            if hwp is None:
                before = _hwp_pids()
                hwp = make_hwp()
                with self._lock:
                    self._session_pids = _hwp_pids() - before
            return hwp

        def drop_session():
            nonlocal hwp
            try:
                if hwp is not None:
                    hwp.quit()
            except Exception:
                pass
            hwp = None
            with self._lock:
                self._session_pids = set()

        while True:
            job = self._jobs.get()
            op = job.get("op")
            rq = job.get("_result")
            if op == "quit":
                drop_session()
                if rq:
                    rq.put({"ok": True})
                break
            try:
                if op == "generate":
                    h = ensure_hwp()
                    rep = _fill_document(h, job["plan"], job["out_hwp"],
                                         job.get("out_pdf"), self.template,
                                         fieldmap=_load_fieldmap_for(self.template))
                    rq.put({"ok": True, **rep})
                elif op == "diagnose":
                    info = {"template_exists": os.path.exists(self.template)}
                    try:
                        h = ensure_hwp()
                        info["com_ok"] = True
                        info["version"] = str(h.Version)
                    except Exception as e:
                        info["com_ok"] = False
                        info["error"] = str(e)
                    rq.put({"ok": info.get("com_ok", False), **info})
                elif op == "scan_fields":
                    h = ensure_hwp()
                    result = _scan_fields_com(h, job["hwp_path"])
                    rq.put({"ok": True, **result})
                else:
                    rq.put({"ok": False, "error": f"알 수 없는 작업: {op}"})
            except Exception as e:
                # 세션이 오염됐을 수 있으므로 재생성 대상으로 표시
                drop_session()
                tb = traceback.format_exc()
                log(f"HWP 작업 실패(op={op}): {e}\n{tb}")
                rq.put({"ok": False, "error": str(e), "traceback": tb})
