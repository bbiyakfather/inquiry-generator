# -*- coding: utf-8 -*-
"""회의록 사이드카(.minutes.json) 저장/로드 — quote_store 미러 검증."""
import os

from src.store import minutes_store as ms

SAMPLE = {
    "business_name": "AI 음장 센싱 기반 스마트 홈 보안 모니터링 시스템",
    "meeting_date": "2026. 04. 09.(목) 09:17~09:52",
    "meeting_place": "온라인 화상회의",
    "meeting_topic": "창업 활동 현황 논의",
    "participants": ["KIST 김종민 박사", "내비온 장윤화 이사, 김형일"],
    "total_count": 4,
    "sections": [{"type": "header", "text": " ■ 주요 회의 내용"},
                 {"type": "bullet", "text": "사업 선정 완료"}],
}


def test_sidecar_path():
    assert ms.sidecar_path(r"C:\w\회의록_주제_260409.hwpx") == \
        r"C:\w\회의록_주제_260409.minutes.json"


def test_save_load_roundtrip(tmp_path):
    hwpx = str(tmp_path / "회의록_테스트_260611.hwpx")
    path = ms.save_minutes(hwpx, SAMPLE)
    assert path == str(tmp_path / "회의록_테스트_260611.minutes.json")
    assert os.path.exists(path)

    store = ms.load_minutes(path)
    assert store["schema_version"] == ms.SCHEMA_VERSION
    assert store["data"] == SAMPLE
    assert store["meta"]["created"]
    assert store["meta"]["modified"]


def test_resave_preserves_created(tmp_path):
    hwpx = str(tmp_path / "a.hwpx")
    p1 = ms.save_minutes(hwpx, SAMPLE)
    created = ms.load_minutes(p1)["meta"]["created"]

    data2 = dict(SAMPLE, meeting_topic="수정된 주제")
    ms.save_minutes(hwpx, data2)
    store = ms.load_minutes(p1)
    assert store["meta"]["created"] == created
    assert store["data"]["meeting_topic"] == "수정된 주제"
