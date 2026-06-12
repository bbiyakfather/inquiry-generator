# -*- coding: utf-8 -*-
"""config.json 관리 + Gemini API 키 DPAPI 암호화 저장."""
import base64
import copy
import json
import os
import tempfile
import threading
import time

from src.paths import data_path

_config_lock = threading.RLock()

# config.json은 쓰기 가능한 데이터 → EXE에서는 exe 옆 폴더 (번들 임시폴더 아님)
CONFIG_PATH = data_path("config.json")

# 견적 구성 제안에 적합한 Gemini 텍스트 Flash 모델 (2026-06 기준).
# id는 generativelanguage API의 모델명. label은 설정 드롭다운 표기.
# gemini-flash-latest는 항상 최신 Flash로 자동 갱신되는 별칭(구형 종료에 안전).
# 드롭다운 선택지는 api._DEPRECATED_MODELS와 절대 겹치면 안 됨
# (겹치면 사용자가 고른 모델이 재시작 시 자동 치환돼 되돌아감). test_ai에서 불변식 검증.
GEMINI_MODELS = [
    {"id": "gemini-flash-latest", "label": "Gemini Flash (항상 최신 · 권장)"},
    {"id": "gemini-3.5-flash", "label": "Gemini 3.5 Flash (최고 성능)"},
    {"id": "gemini-3-flash-preview", "label": "Gemini 3 Flash"},
    {"id": "gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash-Lite (최저가)"},
]

DEFAULT_CONFIG = {
    "company": {
        "name": "주식회사 내비온",
        "reg_no": "319-86-00553",
        "ceo": "조 성 한",
        "address": "(06175) 서울시 강남구 테헤란로 108길 11, 삼호빌딩 4층",
        "biz_type": "전문, 과학 및 기술서비스업",
        "biz_item": "학술연구용역/ 기술 거래 중개 및 알선업",
        "manager": "",
        "tel": "",
        "email": "",
        "fax": "02-6407-7739",
    },
    # 학술연구용역 인건비 기준단가 (월). 연도별 편집 가능.
    "unit_prices": {
        "2026": {
            "책임연구원": 7567456,
            "연구원": 5802624,
            "연구보조원": 3878858,
            "보조원": 2909242,
        }
    },
    "default_price_year": "2026",
    # 인건비 자동조정 — 직급별 최대 인원(전역 기본값, 견적별 조정 가능).
    # 책임연구원은 규칙상 항상 1명이라 조정 대상 아님.
    "labor": {
        "max_counts": {"연구원": 5, "연구보조원": 5, "보조원": 10},
        # 인건비 목표 비율 (목표금액 대비, 0.1~0.9). 경비 목표 = 직접비 − 인건비 목표.
        "labor_ratio": 0.5,
    },
    "gemini": {"api_key_enc": "", "model": "gemini-flash-latest"},
    # 멀티 AI 프로바이더: gemini 키는 위 "gemini"에 유지(하위호환),
    # openai·anthropic는 아래에 저장. provider가 현재 선택된 프로바이더.
    "ai": {
        "provider": "gemini",
        "openai": {"api_key_enc": "", "model": "gpt-5.1"},
        "anthropic": {"api_key_enc": "", "model": "claude-opus-4-8"},
    },
    # AI 초안 기초 지침 오버라이드 — 빈 문자열이면 내장 기본 지침(engine.DIRECTIVE_DEFAULTS) 사용.
    # 과업 내용·단가표·경비 가이드 등 데이터 블록은 지침과 무관하게 항상 시스템이 자동 첨부.
    "ai_prompts": {"quote": "", "minutes": ""},
    "quote_no_seq": {},          # {"2026": 2} → 다음 번호 제 2026-002호
    "last_folder": "",           # (하위호환) 견적서 폴더 구버전 키 — doc_types.quote.folder가 우선
    # 문서 유형별 네임스페이스 — 새 유형 추가 시 여기에 키 추가 (ui DOC_TYPES와 짝)
    "doc_types": {
        "quote":   {"folder": ""},
        "minutes": {"folder": "", "template_path": ""},
    },
    "hwp": {"visible_debug": False},
    "money": {"keep_il": True},
    "drive": {"folder": "내비온 견적서", "auto": False},
    # 최초 실행 튜토리얼 — 완료/건너뛰기 시 True (설정에서 다시 보기 가능)
    "tutorial": {"seen": False},
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    # 읽기도 같은 락으로 보호 — Windows에서 os.replace와 읽기 핸들 경합 방지
    with _config_lock:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as fp:
                    return _merge(DEFAULT_CONFIG, json.load(fp))
            except Exception:
                pass
        return copy.deepcopy(DEFAULT_CONFIG)


def save_config(cfg: dict):
    """동시 저장 보호 + 원자적 쓰기 (임시파일 → os.replace)로 손상 방지."""
    with _config_lock:
        dir_path = os.path.dirname(CONFIG_PATH) or "."
        fd, tmp = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                json.dump(cfg, fp, ensure_ascii=False, indent=2)
            # 외부 프로세스(백신·탐색기 등)의 일시적 잠금에 대비한 짧은 재시도
            for attempt in range(5):
                try:
                    os.replace(tmp, CONFIG_PATH)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.05)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


# ---- DPAPI 키 암호화 (현재 Windows 사용자 계정에 바인딩) ----

def encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    try:
        import win32crypt
        blob = win32crypt.CryptProtectData(
            plain.encode("utf-8"), None, None, None, None, 0)
        return base64.b64encode(blob).decode("ascii")
    except Exception as e:
        raise ValueError(f"DPAPI 암호화 실패(Windows 계정 권한 확인 필요): {e}") from e


def decrypt_secret(enc: str) -> str:
    if not enc:
        return ""
    try:
        import win32crypt
        raw = base64.b64decode(enc.encode("ascii"))
        out = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
        return out[1].decode("utf-8")
    except Exception:
        return ""


def set_gemini_key(cfg: dict, plain_key: str) -> dict:
    cfg.setdefault("gemini", {})["api_key_enc"] = encrypt_secret(plain_key.strip())
    save_config(cfg)
    return cfg


def get_gemini_key(cfg: dict) -> str:
    return decrypt_secret(cfg.get("gemini", {}).get("api_key_enc", ""))


# ---- 멀티 프로바이더 (gemini / openai / anthropic) ----

AI_PROVIDERS = ("gemini", "openai", "anthropic")
_AI_DEFAULT_MODELS = {
    "gemini": "gemini-flash-latest",
    "openai": "gpt-5.1",
    "anthropic": "claude-opus-4-8",
}


def _provider_store(cfg: dict, provider: str) -> dict:
    """프로바이더별 {api_key_enc, model} 저장 dict 반환.
    gemini는 하위호환을 위해 최상위 cfg['gemini']에 유지."""
    if provider == "gemini":
        return cfg.setdefault("gemini", {"api_key_enc": "",
                                         "model": _AI_DEFAULT_MODELS["gemini"]})
    ai = cfg.setdefault("ai", {})
    return ai.setdefault(provider, {"api_key_enc": "",
                                    "model": _AI_DEFAULT_MODELS.get(provider, "")})


def get_provider(cfg: dict) -> str:
    p = cfg.get("ai", {}).get("provider", "gemini")
    return p if p in AI_PROVIDERS else "gemini"


def set_provider(cfg: dict, provider: str) -> dict:
    if provider not in AI_PROVIDERS:
        raise ValueError(f"알 수 없는 AI 프로바이더: {provider}")
    cfg.setdefault("ai", {})["provider"] = provider
    save_config(cfg)
    return cfg


def get_ai_key(cfg: dict, provider: str) -> str:
    return decrypt_secret(_provider_store(cfg, provider).get("api_key_enc", ""))


def set_ai_key(cfg: dict, provider: str, plain_key: str) -> dict:
    _provider_store(cfg, provider)["api_key_enc"] = encrypt_secret((plain_key or "").strip())
    save_config(cfg)
    return cfg


def get_ai_model(cfg: dict, provider: str) -> str:
    return (_provider_store(cfg, provider).get("model")
            or _AI_DEFAULT_MODELS.get(provider, ""))


def set_ai_model(cfg: dict, provider: str, model: str) -> dict:
    _provider_store(cfg, provider)["model"] = str(model or "").strip()
    save_config(cfg)
    return cfg


# ---- AI 초안 기초 지침 (문서 유형별 오버라이드) ----

AI_PROMPT_DOC_TYPES = ("quote", "minutes")


def get_ai_prompt(cfg: dict, doc_type: str) -> str:
    """저장된 기초 지침 오버라이드. 빈 문자열 = 내장 기본 지침 사용."""
    v = (cfg.get("ai_prompts") or {}).get(doc_type, "")
    return v if isinstance(v, str) else ""


def set_ai_prompt(cfg: dict, doc_type: str, text: str) -> dict:
    if doc_type not in AI_PROMPT_DOC_TYPES:
        raise ValueError(f"알 수 없는 문서 유형: {doc_type}")
    cfg.setdefault("ai_prompts", {})[doc_type] = str(text or "")
    save_config(cfg)
    return cfg


def get_labor_ratio(cfg: dict) -> float:
    """인건비 목표 비율 (목표금액 대비). 기본 0.5 (50%)."""
    v = (cfg.get("labor") or {}).get("labor_ratio", 0.5)
    try:
        return max(0.1, min(0.9, float(v)))
    except (TypeError, ValueError):
        return 0.5


def set_labor_ratio(cfg: dict, ratio: float) -> None:
    cfg.setdefault("labor", {})["labor_ratio"] = max(0.1, min(0.9, float(ratio)))
    save_config(cfg)


def get_minutes_tpl(cfg: dict) -> str:
    """저장된 회의록 커스텀 템플릿 경로. 빈 문자열 = 내장 기본 사용."""
    v = (cfg.get("doc_types") or {}).get("minutes", {}).get("template_path", "")
    return v if isinstance(v, str) else ""


def set_minutes_tpl(cfg: dict, path: str) -> None:
    cfg.setdefault("doc_types", {}).setdefault("minutes", {})["template_path"] = str(path or "")
    save_config(cfg)


def migrate_doc_type_folders(cfg: dict) -> bool:
    """구버전 last_folder → doc_types.quote.folder 1회 복사.
    이미 quote.folder가 설정돼 있으면 덮어쓰지 않는다. 변경 시 True 반환
    (저장은 호출자 책임 — Api.__init__의 기존 마이그레이션 패턴과 동일)."""
    dt = cfg.setdefault("doc_types", {}).setdefault("quote", {})
    if not dt.get("folder") and cfg.get("last_folder"):
        dt["folder"] = cfg["last_folder"]
        return True
    return False


def next_quote_no(cfg: dict, year: str, peek: bool = False) -> str:
    """'제 2026-001호' 형식 자동 번호. peek=False면 시퀀스 증가 후 저장."""
    seqs = cfg.setdefault("quote_no_seq", {})
    seq = int(seqs.get(year, 0)) + 1
    if not peek:
        seqs[year] = seq
        save_config(cfg)
    return f"제 {year}-{seq:03d}호"
