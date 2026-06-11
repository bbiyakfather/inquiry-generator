# -*- coding: utf-8 -*-
"""첨부 문서(Markdown) ↔ AI 입력 병합 — 순수 함수.

변환된 md를 과업지시서 설명과 합쳐 AI 프롬프트로 보낼 본문을 만든다.
총량 상한을 두어 토큰 폭주를 막고, 잘린 사실은 warnings로 UI에 알린다.
"""

MAX_ATTACH_TOTAL = 30_000   # 첨부 합산 글자수 상한 (한국어 ≈ 30k~45k 토큰, 전 프로바이더 안전권)
_MIN_KEEP = 200             # 이만큼도 못 싣는 문서는 통째로 생략


def merge_attachments(description, attachments, max_total=MAX_ATTACH_TOTAL):
    """(병합된 description, warnings) 반환.

    attachments: [{"name": str, "markdown": str}] — 잘못된 항목은 무시.
    형식:
        {description}

        ===== 첨부 문서 1: 과업지시서.hwp =====
        {markdown}
    """
    desc = (description or "").strip()
    warnings = []
    valid = []
    for a in attachments or []:
        if not isinstance(a, dict):
            continue
        name = str(a.get("name") or "").strip() or "이름없음"
        md = a.get("markdown")
        if isinstance(md, str) and md.strip():
            valid.append((name, md.strip()))

    if not valid:
        return desc, warnings

    parts = [desc] if desc else []
    used = 0
    truncated = 0   # 일부 절단된 문서 수
    skipped = 0     # 통째로 생략된 문서 수
    for i, (name, md) in enumerate(valid, start=1):
        remain = max_total - used
        if remain < _MIN_KEEP:
            skipped += 1
            continue
        body = md
        if len(body) > remain:
            cut = len(body) - remain
            body = body[:remain] + f"\n\n[... 분량 초과로 이하 {cut:,}자 생략 ...]"
            truncated += 1
        used += min(len(md), remain)
        parts.append(f"===== 첨부 문서 {i}: {name} =====\n{body}")

    if truncated or skipped:
        detail = []
        if truncated:
            detail.append(f"{truncated}건 일부 절단")
        if skipped:
            detail.append(f"{skipped}건 제외")
        warnings.append(
            f"첨부 분량이 상한({max_total:,}자)을 초과하여 {', '.join(detail)}되었습니다. "
            "핵심 문서를 먼저 첨부하세요.")

    return "\n\n".join(parts), warnings
