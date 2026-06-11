# -*- coding: utf-8 -*-
"""공용 로깅 — app-log.txt에 타임스탬프와 함께 기록.

시작/종료뿐 아니라 HWP/PDF 생성 실패 등 진단에 필요한 사건을 한곳에 남긴다.
워커 스레드와 GUI 스레드가 동시에 쓸 수 있으므로 락으로 직렬화한다.
"""
import threading
from datetime import datetime

from src.paths import data_path

LOG_PATH = data_path("app-log.txt")
_lock = threading.Lock()


def log(msg: str) -> None:
    try:
        with _lock, open(LOG_PATH, "a", encoding="utf-8") as fp:
            fp.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except OSError:
        pass
