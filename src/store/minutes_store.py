# -*- coding: utf-8 -*-
"""회의록 JSON 사이드카 저장/로드 — 재편집 데이터.

quote_store 패턴 미러. 견적서와 달리 파일명 계산은 하지 않는다
(api.generate_minutes가 out_path를 확정하므로 경로 기반이 단순·정확).
사이드카: <회의록.hwpx와 같은 베이스명>.minutes.json
"""
import json
import os
from datetime import datetime

SCHEMA_VERSION = 1


def sidecar_path(hwpx_path: str) -> str:
    """회의록 hwpx 경로 → 사이드카 .minutes.json 경로."""
    base, _ = os.path.splitext(hwpx_path)
    return base + ".minutes.json"


def save_minutes(hwpx_path: str, data: dict) -> str:
    """MINUTES_SCHEMA data → 사이드카 저장, 경로 반환."""
    path = sidecar_path(hwpx_path)
    now = datetime.now().isoformat(timespec="seconds")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "meta": {"created": now, "modified": now},
        "data": data,
    }
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fp:
                old = json.load(fp)
            created = old.get("meta", {}).get("created")
            if created:
                payload["meta"]["created"] = created
        except Exception:
            pass
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
    return path


def load_minutes(path: str) -> dict:
    """사이드카 전체 dict 반환 ({schema_version, meta, data})."""
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)
