# 회의록 HWPX 양식 강화 — 개발 태스크 목록

> 근거 PRD: `docs/PRD_minutes_hwpx_enhancement.md` (v1.2, codex 적대 리뷰 반영본)
> 대상 제품: 내비온 견적서·회의록 생성기 (Python + pywebview, COM-free·오프라인 보장)
> 작성 원칙: 최소 변경·재사용 우선, 새 무거운 의존성 금지, 엔진/스키마/저장 로직은 **TDD(테스트 먼저)**.

## 0. 개요 및 실행 전략

이 목록은 여러 구현 에이전트에게 **웨이브 단위**로 할당된다. PRD 10장이 못박은 구현 순서를 그대로 따른다:

> **A-6(셀 쓰기 엔진 견고화) P0 선결 → A-2/A-3/A-4(UI·스키마 백엔드) → B(preset 저장소) → C(통합)**

핵심 충돌 회피 규칙:
- **같은 파일을 수정하는 태스크는 같은 웨이브에서 병렬 금지.** 특히 `src/api.py`·`ui/app.js`는 공유 핫스팟이라 각 웨이브 내 단일 직렬 태스크로 묶었다.
- 각 태스크는 **수정/생성 파일 목록**을 정확히 명시한다. 이 목록이 겹치면 직렬화한다.
- 의존성은 **선행 태스크 ID**로 표기한다.

### 채택한 Open Questions 기본값 (PRD 9장 권고)

| OQ | 결정 | 영향 태스크 |
|----|------|------------|
| 9-a | **(i)+(ii) 채택**: 7슬롯 재배치 + 정적 텍스트 커스텀 슬롯. 단 (ii)는 무료가 아니므로 ① 저장(fieldmap custom_slots) ② 생성 경로(`data.custom_fields → 지정 셀 쓰기`) ③ 정규화 화이트리스트 확장을 한 묶음으로 구현. (iii) AI 동적 필드는 후속. | T-A3-1, T-A3-2, T-A1-3 |
| 9-c | **앱 데이터 폴더 복사** (원본 이동·삭제에 견고, `data_path` 활용) | T-B1-1, T-B2-2 |
| 9-d | **갤러리 자동 표시 기본 ON** (`gallery_autoshow=true`, `tutorial.seen` 패턴) | T-B1-2, T-B3-1 |
| 9-e | **1셀=1핀** (슬롯 지정 또는 커스텀 라벨 1개, 다중 주석 후속) | T-A4-1, T-A4-2 |
| 9-b / 9-f | **이번 범위 제외** (견적서 .hwp / 누름틀 경로는 별도 PRD) | 전 태스크 공통 가드 |

각 태스크의 "OQ 의존" 항목에 위 결정 의존 여부를 표시했다.

---

## Wave 0 — 엔진 견고화 (P0 선결·단독)

> PRD A-6. A-2/A-3/A-4를 "완료"로 보려면 이 웨이브의 회귀 테스트가 모두 그린이어야 한다.
> **TDD 필수**: 세 시나리오의 실패 재현 테스트를 먼저 작성한 뒤 엔진을 보정한다.
> 파일 핫스팟: `src/minutes/hwpx_minutes.py`, `src/scan/hwpx_scan.py`. 두 파일을 만지는 태스크가 분리돼 있으므로 **T-A6-1/2 (hwpx_minutes)** 와 **T-A6-3 (hwpx_scan)** 는 병렬 가능, 단 T-A6-3의 좌표 계약은 `_find_cell`(hwpx_minutes) 동작에 의존하므로 인터페이스 합의 후 진행.

| 태스크 ID | 제목 | PRD 근거 | 수정/생성 파일 | 의존성 | TDD | OQ 의존 |
|-----------|------|----------|----------------|--------|-----|---------|
| T-A6-1 | 단순 셀 쓰기 구조 내성 보정 | A-6-1 | `src/minutes/hwpx_minutes.py`, `tests/test_minutes.py` | 없음 | ✅ | - |
| T-A6-2 | content·사진표 보존 경계 정책 | A-6-2 | `src/minutes/hwpx_minutes.py`, `tests/test_minutes.py` | T-A6-1 (동일 파일) | ✅ | - |
| T-A6-3 | cellSpan 추출 + 좌표 라운드트립 일관성 | A-6-3, A-4 ① | `src/scan/hwpx_scan.py`, `tests/test_hwpx_scan.py` | 없음(병렬) | ✅ | - |

### T-A6-1 — `_set_simple_cell_text` 구조 보정
- **요구**: `_set_simple_cell_text`(`hwpx_minutes.py:90-103`)는 `tc is None`만 막고 이후 `subList→p→run→t`를 None 체크 없이 연쇄한다. 빈 셀·병합 잔여 셀·구조가 다른 셀에 단순 슬롯을 매핑하면 `AttributeError`로 `build_minutes` 전체가 `{ok:false}`가 된다.
- **구현**: 누락된 `subList/p/run`을 방어적으로 `SubElement` 생성·보정한다. 보정 불가한 구조(예: subList 자체가 없는 비텍스트 셀)면 **전체 실패 대신 해당 슬롯만 명확한 오류**로 수집해 결과의 `slot_errors`(또는 동등 필드)에 담는다.
- **수용 기준 (pytest)**: `tests/test_minutes.py`에 신규 — 단순 슬롯(`business_name` 등)을 `subList/p/run` 없는 셀에 매핑한 cell_map으로 `build_minutes` 호출 시 `AttributeError` 없이 (a) 구조 보정 후 텍스트가 들어가거나 (b) 해당 슬롯만 오류로 보고되고 나머지 슬롯은 정상 생성됨을 검증. **테스트 먼저 작성(현재 실패 → 보정 후 그린).**
- **OQ 의존**: 없음 (단, T-A3-2 커스텀 필드 쓰기가 이 보정 위에 얹힌다 — 9-a (ii)의 전제).

### T-A6-2 — content 재매핑 시 사진표 보존 정책
- **요구**: content 슬롯은 대상 셀 문단을 전부 삭제·재구성하고, 사진표는 매핑된 content 셀 **내부**의 `paraPrIDRef=='28'`/내부 `tbl` 첫 문단만 `deepcopy`로 보존한다(`hwpx_minutes.py:289-339`). content를 사진표 없는 셀로 매핑하면 사진표가 **사일런트 소실**, 사진표 있는 셀을 content로 찍으면 나머지 구조 삭제.
- **구현**: content 재매핑 시 보존 정책을 명시(원래 셀의 사진표 **유지** 기본)하고, 사진표가 없는 셀로 매핑되면 경고 플래그를 결과에 담아 사일런트 소실을 막는다.
- **수용 기준 (pytest)**: `tests/test_minutes.py` — content를 사진표 없는 셀로 재매핑했을 때 보존 정책(유지/이동/생략)이 의도대로 동작하고 사일런트 소실이 없음을 검증. **TDD.**
- **OQ 의존**: 없음.

### T-A6-3 — `scan_hwpx_grid` cellSpan 추출 + 좌표 계약
- **요구**: `scan_hwpx_grid`(`hwpx_scan.py:144-186`)는 첫 표만·`cellAddr` 평면만 읽고 `cellSpan`(colSpan/rowSpan)을 무시한다. UI가 병합 영역을 평면 격자로 그리면 존재하지 않는 (row,col) 클릭이 가능해 `_find_cell`이 조용히 `None`을 반환한다.
- **구현**: 각 셀에 `cellSpan`(colSpan/rowSpan)을 추가 추출해 반환 cell에 `colspan/rowspan` 부여. **그리드가 반환하는 좌표 집합 ⊆ `_find_cell` 인식 좌표(병합 영역은 대표 좌표 1개로 정규화)** 를 엔진 계약으로 보장. 응답 스키마 후방호환 유지(기존 `{row,col,text}` 키 보존, `colspan/rowspan` 추가).
- **수용 기준 (pytest)**: `tests/test_hwpx_scan.py` — (a) `회의록_양식.hwpx`의 병합셀에 대해 `colspan`(=2 5개·=3 1개)을 정확히 반환, (b) 그리드 반환 좌표 전체가 `_find_cell`로 실셀에 라운드트립됨을 검증. **TDD.**
- **OQ 의존**: 없음.

---

## Wave 1 — 매핑 백엔드 (A-2/A-3/A-4)

> PRD A-2(드롭다운 매핑 저장), A-3(커스텀 슬롯), A-4(클릭-핀 annotations). 셋은 **하나의 저장 경로(`save_minutes_cellmap`)와 fieldmap v2 스키마를 공유**한다.
> 파일 핫스팟: `src/ai/minutes_template_mapper.py`(스키마·저장), `src/api.py`(엔드포인트), `src/minutes/hwpx_minutes.py`(커스텀 필드 쓰기).
> 직렬화 규칙: `api.py`를 만지는 T-A2-2/T-A1-2는 **단일 태스크로 통합 직렬**(아래 T-A2-2가 두 엔드포인트를 함께 추가). mapper를 만지는 T-A2-1/T-A3-1은 동일 파일이므로 직렬.

| 태스크 ID | 제목 | PRD 근거 | 수정/생성 파일 | 의존성 | TDD | OQ 의존 |
|-----------|------|----------|----------------|--------|-----|---------|
| T-A2-1 | fieldmap v2 스키마 + `save_minutes_cellmap` 저장 로직 | A-2, A-4 ③④, 6장 데이터스키마 | `src/ai/minutes_template_mapper.py`, `tests/test_minutes_template_mapper.py`(신규) | Wave 0 완료 | ✅ | 9-a, 9-e |
| T-A3-1 | custom_slots·annotations 스키마 확장 + 로더 후방호환 | A-3, A-4 ③ | `src/ai/minutes_template_mapper.py`, `tests/test_minutes_template_mapper.py` | T-A2-1 (동일 파일) | ✅ | 9-a, 9-e |
| T-A3-2 | 커스텀 필드 생성 경로(`data.custom_fields → 셀 쓰기`) + 정규화 화이트리스트 | A-3, 9-a 데이터계약 | `src/minutes/hwpx_minutes.py`, `src/ai/minutes.py`, `tests/test_minutes.py` | T-A6-1, T-A2-1 | ✅ | **9-a (ii) 채택 의존** |
| T-A2-2 | API 엔드포인트: `save_minutes_cellmap` + `scan_minutes_grid` + `scan_minutes_template` grid 추가 | A-2, A-5, 6장 엔드포인트, 적대리뷰 #6 | `src/api.py`, `tests/test_minutes_api.py` | T-A2-1, T-A3-1, T-A6-3 | ✅(저장 라운드트립) | 9-a |

### T-A2-1 — fieldmap v2 + `save_minutes_cellmap`
- **요구**: 사용자 편집본(cell_map)을 `.minutes.fieldmap.json` **version 2**로 기록하는 저장 함수 추가. 기존 `save_minutes_fieldmap`/`_fieldmap_path`(`minutes_template_mapper.py:111-141`) 규약을 재사용·확장. `is_standard_map`으로 `is_standard` 재계산.
- **구현**: `save_minutes_cellmap(template_path, cell_map, custom_slots=None, annotations=None) -> dict`. version 2 구조: `{version:2, template, is_standard, cell_map, unmapped, custom_slots, annotations}`. `load_minutes_fieldmap`은 version 1 파일에서 `custom_slots`/`annotations` 부재를 견디게 유지(기존 로더는 이미 임의 키에 견고 — 회귀만 보장).
- **수용 기준 (pytest)**: `tests/test_minutes_template_mapper.py`(신규) — (a) 저장→`load_minutes_fieldmap` 라운드트립으로 cell_map·custom_slots·annotations 동일 복원, (b) `is_standard` 재계산, (c) version 1 fieldmap 로드 후 v2 저장해도 기존 7슬롯 동작 불변(후방호환). **TDD.**
- **OQ 의존**: 9-a(custom_slots 형상), 9-e(annotations 1셀=1핀 키 유일성).

### T-A3-1 — custom_slots·annotations 스키마
- **요구**: `custom_slots: [{id, label, cell:[r,c]}]`, `annotations: [{row, col, label, comment, slot?}]` 선택적 배열 추가. `slot`이 표준 7슬롯이면 cell_map과 동일 의미, 아니면 custom_slots와 동일 취급.
- **구현**: 스키마 검증 헬퍼(정수쌍·라벨 타입·**1셀=1핀 유일성** 검증, 9-e). 잘못된 항목은 무시·경고. `save_minutes_cellmap`(T-A2-1)이 이 검증을 호출.
- **수용 기준 (pytest)**: `tests/test_minutes_template_mapper.py` — custom_slots/annotations 라운드트립, 동일 (row,col)에 핀 2개 거부(1셀=1핀), `custom_slots` 없는 v1 안전 로드. **TDD.**
- **OQ 의존**: 9-a, 9-e.

### T-A3-2 — 커스텀 필드 생성 경로 + 정규화 화이트리스트
- **요구 (9-a (ii) 데이터 계약 공백 메우기)**: 현재 `_norm_cells`는 `DEFAULT_CELLS`에 없는 슬롯을 무시(`hwpx_minutes.py:185-199`), AI 매퍼는 7슬롯만 허용, `MINUTES_SCHEMA` 정규화도 unknown 필드를 버린다. 따라서 정적 텍스트 커스텀 슬롯을 **실제로 출력**하려면 생성 경로와 정규화를 함께 확장해야 한다.
- **구현**: `build_minutes`에 `data.custom_fields = {slot_id: text}` 경로 추가 — 각 custom_slot의 cell 좌표에 `_set_simple_cell_text`(T-A6-1 보정본) 호출. `src/ai/minutes.py`의 MINUTES_SCHEMA 정규화에서 `custom_fields`를 화이트리스트로 보존(unknown 폐기 방지). **범위 가드: 정적 텍스트만, AI 동적 필드(iii) 미포함.**
- **수용 기준 (pytest)**: `tests/test_minutes.py` — 커스텀 슬롯 텍스트가 `build_minutes`에서 지정 셀에 들어감, 미지정 커스텀 슬롯은 빈 칸 안전 생성, `custom_fields` 미존재 시 기존 동작 불변. **TDD.**
- **OQ 의존**: **9-a (ii) 채택에 직접 의존.** 만약 (ii) 미채택으로 변경되면 이 태스크는 드롭되고 UI(Wave 3)에서 "저장·표시만, 생성 미반영"을 명시해야 함.

### T-A2-2 — API 엔드포인트 3종 (api.py 단일 직렬)
- **요구**:
  1. `save_minutes_cellmap(template_path, cell_map, custom_slots=None, annotations=None)` — T-A2-1 저장 함수 노출.
  2. `scan_minutes_grid(template_path)` — **AI 호출 없이** `scan_hwpx_grid`(cellSpan 포함, T-A6-3)만 반환하는 오프라인 전용 경로(적대리뷰 #6: 시각 격자 보기를 AI 실패/지연에서 분리).
  3. `scan_minutes_template` 응답에 `grid`(cellSpan 포함) 추가 — AI 매핑 제안과 함께 쓰는 경로(`api.py:1183-1220` 수정).
- **구현**: 셋 다 `src/api.py` `class Api`에 추가/수정. JSON dict 입출력, 계산은 Python. 미매핑(A-5) 정책은 응답에 `unmapped` 노출만(차단 없음).
- **수용 기준 (pytest)**: `tests/test_minutes_api.py` — (a) `scan_minutes_grid`가 AI 키 없이도 grid(colspan 포함) 반환, (b) `save_minutes_cellmap` API 라운드트립, (c) `scan_minutes_template` 응답에 grid 포함. **저장·계약 부분 TDD.**
- **OQ 의존**: 9-a.

---

## Wave 2 — Preset 저장소 백엔드 (B)

> PRD B-1/B-2/B-3. config.json에 `doc_types.minutes.presets[]`·`gallery_autoshow` 추가. **활성 선택은 기존 `template_path`에 계속 반영**(후방호환).
> 파일 핫스팟: `src/store/config_store.py`(스키마·마이그레이션), `src/api.py`(CRUD 엔드포인트). **Wave 1의 api.py 작업(T-A2-2) 완료 후 진행**(같은 파일 충돌 방지).
> config_store를 만지는 T-B1-1/T-B1-2는 동일 파일이므로 직렬.

| 태스크 ID | 제목 | PRD 근거 | 수정/생성 파일 | 의존성 | TDD | OQ 의존 |
|-----------|------|----------|----------------|--------|-----|---------|
| T-B1-1 | presets 스키마 + `migrate_minutes_presets` + 양식 파일 복사 | B-1, 적대리뷰 #4, 6장 스키마 | `src/store/config_store.py`, `tests/test_config_minutes_presets.py`(신규) | Wave 1 완료 | ✅ | 9-c |
| T-B1-2 | `gallery_autoshow` 플래그 + 활성 preset↔template_path 동기화 | B-3, 6장 이중진실 방지 | `src/store/config_store.py`, `tests/test_config_minutes_presets.py` | T-B1-1 (동일 파일) | ✅ | 9-d |
| T-B2-1 | API: preset CRUD (`list/add/select/delete/rename`) + `set_minutes_gallery_autoshow` | B-1, B-2, B-3, US-008~011, US-014 | `src/api.py`, `tests/test_minutes_api.py` | T-B1-1, T-B1-2, T-A2-2 | ✅ | 9-c, 9-d |

### T-B1-1 — presets 스키마 + 전용 마이그레이션 + 복사
- **요구**: preset = `{id, name, template_path, is_builtin, fieldmap_path(파생), created}`. 저장 위치 `doc_types.minutes.presets[]`. 내장 양식(`TEMPLATE_MINUTES`)은 **항상 첫 preset·삭제 불가**.
- **적대리뷰 #4 (High) 필수 반영**: `_merge`(`config_store.py:86-93`)는 **리스트를 통째로 덮으므로** preset 시딩을 `_merge`에 의존하면 안 된다. 사용자 config에 `presets:[...]`가 이미 있으면 내장 preset이 시딩되지 않는다. → 전용 `migrate_minutes_presets(cfg) -> bool`(기존 `migrate_doc_type_folders` 패턴, `config_store.py:268-276`)로: (a) `presets` 부재/비배열이면 내장 preset 1개로 초기화, (b) 항상 내장 preset이 첫 항목임을 보장, (c) 타입 검증.
- **9-c 채택**: `add_minutes_preset`(Wave 2 API)에서 쓸 **앱 데이터 폴더 복사** 헬퍼 추가(`data_path` 활용, 원본 이동·삭제에 견고).
- **수용 기준 (pytest)**: `tests/test_config_minutes_presets.py`(신규) — (a) presets 부재 config에 내장 preset 시딩, (b) 사용자 presets 있어도 내장 preset 첫 항목 보장, (c) 비배열/손상 타입 복구. **TDD.**
- **OQ 의존**: 9-c(복사 정책).

### T-B1-2 — gallery_autoshow + 활성 동기화
- **요구**: `doc_types.minutes.gallery_autoshow`(기본 **true**, 9-d) 추가 — `tutorial.seen` 패턴(`config_store.py:81-82`) 미러. get/set 헬퍼.
- **이중 진실 원천 방지(6장)**: `presets[]`(보관)와 `template_path`(활성)가 어긋나면 갤러리 선택과 실제 출력 불일치. **활성 preset id ↔ `template_path` 동기화 규칙을 한 곳(`select_minutes_preset` 백엔드 헬퍼)에서 강제**. `generate_minutes`/`get_minutes_template`는 계속 `template_path`를 단일 활성 출처로 읽음(후방호환).
- **수용 기준 (pytest)**: `tests/test_config_minutes_presets.py` — (a) `gallery_autoshow` 기본 true·토글 저장, (b) preset 선택 시 `template_path` 반영, (c) 활성 preset 삭제 시 `template_path`가 내장으로 폴백. **TDD.**
- **OQ 의존**: 9-d.

### T-B2-1 — Preset CRUD API (api.py 단일 직렬)
- **요구**: `list_minutes_presets()`, `add_minutes_preset(path, name=None)`, `select_minutes_preset(id)`, `delete_minutes_preset(id)`, `rename_minutes_preset(id, name)`, `set_minutes_gallery_autoshow(on)`.
- **구현**: `add`는 9-c에 따라 양식 파일을 앱 폴더로 복사(T-B1-1 헬퍼). `select`는 동기화 규칙(T-B1-2). `delete`/`rename`은 내장 preset 거부(서버측). 삭제는 `delete_minutes`/`delete_quote`의 `also_files` 패턴 미러(US-014: 등록 해제 기본, 파일 삭제는 별도 동의).
- **수용 기준 (pytest)**: `tests/test_minutes_api.py` — preset 추가/선택/이름변경/삭제 CRUD, 내장 preset 삭제·이름변경 거부, 선택 시 `template_path` 반영, `set_minutes_gallery_autoshow` 동작. **TDD.**
- **OQ 의존**: 9-c, 9-d.

---

## Wave 3 — 프론트엔드 통합 (A·B UI)

> PRD A-1/A-2/A-4 UI, B-2/B-3 갤러리. 백엔드 엔드포인트 확정(Wave 1·2) 후 **단일 작업으로** 진행(app.js/index.html/app.css는 공유 핫스팟이라 웨이브 내 직렬).
> 파일 핫스팟: `ui/index.html`, `ui/app.js`, `ui/app.css`. 세 태스크가 모두 같은 파일군을 만지므로 **T-F1 → T-F2 → T-F3 직렬**.
> 원칙: JS는 표시·입력만(JS 산수 금지). 모든 안내·경고 한국어. 기존 `toast`·상태 텍스트 패턴 재사용. **COM-free·오프라인에서 그리드·핀 동작**(kordoc Markdown 미리보기는 P2 부가).

| 태스크 ID | 제목 | PRD 근거 | 수정/생성 파일 | 의존성 | TDD | OQ 의존 |
|-----------|------|----------|----------------|--------|-----|---------|
| T-F1 | Preset 갤러리 모달(카드·배지·자동표시 토글·CRUD UI) | B-2, B-3, US-008~011, US-014 | `ui/index.html`, `ui/app.js`, `ui/app.css` | T-B2-1 | ❌(수동 검증) | 9-c, 9-d |
| T-F2 | 매핑 편집기: HTML 격자 + 드롭다운 + 클릭-핀 미리보기 | A-1, A-2, A-4, US-001~005, US-015 | `ui/index.html`, `ui/app.js`, `ui/app.css` | T-A2-2, T-F1 (동일 파일) | ❌(수동 검증) | 9-a, 9-e |
| T-F3 | 미매핑 경고 + 끊김 없는 흐름 와이어링 | A-5, C-1, C-2, US-007, US-012, US-013 | `ui/app.js`, `ui/index.html` | T-F2 (동일 파일) | ❌(수동 검증) | - |

### T-F1 — Preset 갤러리 모달
- **요구**: 회의록 메뉴 진입/새 회의록 시작 시 카드형 갤러리 모달. 각 카드 = 양식 이름 + 미리보기(셀 그리드 요약/썸네일) + 매핑 상태 배지(표준/AI 매핑됨/미매핑 N개). 카드 선택 즉시 `select_minutes_preset`. "내 양식 추가"(`pick_minutes_template_file`→`add_minutes_preset`)→매핑 편집기로 연결. 이름변경·삭제(내장 비활성). "다음부터 표시 안 함" 토글(`set_minutes_gallery_autoshow`).
- **구현**: `list_minutes_presets` 응답으로 렌더. 위험 동작(삭제) 확인 다이얼로그(US-014). 자동 표시 정책(9-d ON)에 따라 진입 시 표시, 껐어도 회의록 메뉴 버튼으로 재오픈.
- **수용 기준**: 백엔드 그린(T-B2-1) 전제. UI는 **실제 렌더러(pywebview)에서 모달 표시→카드 선택→template_path 반영→삭제 확인 흐름을 관찰**해 검증(CLAUDE.md render-grounding 정책). 자동화 pytest 없음.
- **OQ 의존**: 9-c, 9-d.

### T-F2 — 매핑 편집기 (격자 + 드롭다운 + 클릭-핀)
- **요구**: 읽기 전용 표를 **편집 가능한 격자**로 대체.
  - (A-1) `scan_minutes_grid`/`scan_minutes_template` grid를 HTML `<table>`로 재구성, **colspan/rowspan으로 실제 병합 모양 일치**(핀이 의도 셀에 떨어지게).
  - (A-2) 7슬롯 각각 드롭다운/셀 클릭으로 (row,col) 지정·수정. AI 제안은 초기값, 사용자가 덮어쓰기.
  - (A-4/US-015) 셀 클릭 시 핀 + 댓글(입력 위치) 입력. **1셀=1핀**(9-e). 중첩 사진표 내부 셀 클릭은 content 귀속/비활성(별도 매핑 대상 금지).
  - (A-3) 커스텀 슬롯 추가/삭제(라벨 + 대상 셀).
  - 저장은 **단일 경로** `save_minutes_cellmap`(cell_map + custom_slots + annotations). 드롭다운·클릭-핀이 동일 fieldmap에 일관 저장.
- **구현**: 좌표는 시각적 격자 위치로 인지(셀 클릭=매핑). 범위 밖·중복 좌표는 저장 시 경고. AI 키 없으면 수동 매핑으로 전체 완료(US-013). kordoc Markdown은 읽기전용 "내용 미리보기"로만 부가(P2, 변환 불가 상태에서도 격자·핀 동작).
- **수용 기준**: 백엔드 그린(T-A2-2) 전제. **실제 렌더러에서 병합셀 양식(`회의록_양식.hwpx`) 로드→격자 모양 일치→셀 클릭 핀→저장→재로드 복원을 관찰**해 검증. 클릭 핀 정확도(병합·중첩 포함)는 T-A6-3 좌표 계약에 의존.
- **OQ 의존**: 9-a(커스텀 슬롯), 9-e(1셀=1핀).

### T-F3 — 미매핑 경고 + 흐름 와이어링
- **요구**: preset 선택 →(필요시 매핑 편집)→ AI 초안(`minutes_draft`)→ 검토 → 생성(`generate_minutes`)이 끊김 없이 연결(C-1). 생성 직전 미매핑 슬롯 있으면 **경고 1회 노출, 진행 허용**(A-5/C-2 동일 정책 한 곳에서). AI 키 부재·오프라인 폴백 안내(US-013).
- **구현**: 활성 preset의 cell_map은 `generate_minutes`가 이미 fieldmap 로드·적용(재사용). 재분석은 사용자가 명시적으로 누를 때만(C-3, 추가 AI 호출 없음).
- **수용 기준**: **실제 렌더러에서 미매핑 슬롯 있는 양식으로 생성 시 경고→진행→빈 칸 HWPX 정상 생성을 관찰**. C-3 캐시 재사용은 T-C1(Wave 4) 회귀로 검증.
- **OQ 의존**: 없음.

---

## Wave 4 — 통합·회귀 (C)

> PRD C-1/C-2/C-3 통합 검증 + 전체 pytest 회귀. 기능 추가 없이 **끊김 없는 흐름·미매핑 가드·캐시 재사용**을 엔드투엔드로 묶고, 후방호환·오프라인·COM-free를 회귀로 못박는다.

| 태스크 ID | 제목 | PRD 근거 | 수정/생성 파일 | 의존성 | TDD | OQ 의존 |
|-----------|------|----------|----------------|--------|-----|---------|
| T-C1 | 통합 흐름 + 캐시 재사용 엔드투엔드 검증 | C-1, C-3, US-012 | `tests/test_minutes_api.py`, `tests/test_minutes.py` | Wave 3 완료 | ✅ | - |
| T-C2 | 전체 회귀 + 후방호환·오프라인 게이트 | 7장 기술지표, US-006, US-013 | `tests/*`(전체) | T-C1 | ✅(게이트) | - |

### T-C1 — 통합 흐름 + 캐시 재사용
- **요구**: 활성 preset 상태에서 `minutes_draft`→검토→`generate_minutes`로 생성하면 활성 preset의 cell_map이 자동 적용되고, 값이 매핑 셀에 정확히 들어감(US-012). 재분석을 누르지 않는 한 캐시(`load_minutes_fieldmap`)만 사용해 추가 AI 호출 없음(C-3).
- **수용 기준 (pytest)**: `tests/test_minutes_api.py` — preset 선택→생성 시 cell_map 적용 검증, 생성 경로가 AI를 호출하지 않음(캐시 only) 검증. **TDD.**

### T-C2 — 전체 회귀 + 게이트
- **요구 (PRD 7장 기술지표 = 완료 게이트)**:
  - **회귀 0**: 기존 회의록/견적서 생성·재편집 동작 불변 — 기존 `tests/test_minutes*.py`, `test_hwpx_scan.py`, `test_config_*` 전부 통과.
  - **후방호환**: 기존 config.json·fieldmap(v1)·minutes.json 사용자가 업데이트 후 재설정 없이 동작(US-006, 마이그레이션 테스트).
  - **오프라인·COM-free**: 한글 미설치·네트워크 없음에서 그리드 시각화·클릭 핀·HWPX 생성 동작(AI 매핑만 비활성, US-013, `scan_minutes_grid` 분리 경로).
  - **미매핑 안전 생성**: `_find_cell` None 경로로 빈 칸 안전 생성.
- **수용 기준 (pytest)**: `python -m pytest tests/` 전체 그린. 신규/수정 테스트(Wave 0~3) + 기존 테스트 모두 통과. **이 게이트가 그린이어야 프로젝트 "완료".**

---

## 실행 순서 요약 (웨이브별 병렬 vs 직렬)

| 웨이브 | 태스크 | 병렬 가능? | 비고 |
|--------|--------|-----------|------|
| **Wave 0** | T-A6-1 → T-A6-2 (직렬, 동일 hwpx_minutes.py) · T-A6-3 (병렬, hwpx_scan.py) | T-A6-3 ∥ {T-A6-1→T-A6-2} | A6 = P0 선결, 전부 TDD. T-A6-3 좌표 계약은 `_find_cell` 인터페이스 합의 필요 |
| **Wave 1** | T-A2-1 → T-A3-1 (직렬, 동일 mapper) · T-A3-2 (T-A6-1·T-A2-1 후) · T-A2-2 (api.py 단일, 모든 mapper/scan 후) | {T-A2-1→T-A3-1} 후 T-A3-2 ∥ 준비 → T-A2-2 직렬 마감 | save 로직·스키마 TDD 필수 |
| **Wave 2** | T-B1-1 → T-B1-2 (직렬, 동일 config_store) → T-B2-1 (api.py 단일) | 웨이브 내 직렬 | Wave 1의 api.py 완료 후 시작(파일 충돌) |
| **Wave 3** | T-F1 → T-F2 → T-F3 (직렬, 동일 ui 파일군) | 전부 직렬 | 백엔드 엔드포인트 확정 후. 렌더러 실관찰 검증 |
| **Wave 4** | T-C1 → T-C2 (직렬) | 직렬 | T-C2 전체 pytest 게이트 = 완료 조건 |

### 웨이브 간 의존
```
Wave 0 (A-6 선결) ──▶ Wave 1 (A-2/A-3/A-4 백엔드) ──▶ Wave 2 (B 백엔드)
                                                  └──▶ Wave 3 (FE 통합) ──▶ Wave 4 (C 통합·회귀)
```
- Wave 3은 Wave 1·2의 API가 모두 확정돼야 시작(앤드포인트 계약 의존).
- Wave 4는 전 웨이브 완료 후 회귀 게이트.

### 총 태스크 수: **14개**
- Wave 0: 3 (T-A6-1, T-A6-2, T-A6-3)
- Wave 1: 4 (T-A2-1, T-A3-1, T-A3-2, T-A2-2)
- Wave 2: 3 (T-B1-1, T-B1-2, T-B2-1)
- Wave 3: 3 (T-F1, T-F2, T-F3)
- Wave 4: 2 (T-C1, T-C2)

### TDD 필수 태스크 (테스트 먼저)
T-A6-1, T-A6-2, T-A6-3, T-A2-1, T-A3-1, T-A3-2, T-A2-2, T-B1-1, T-B1-2, T-B2-1, T-C1, T-C2 (엔진·스키마·저장·API·마이그레이션). FE 3종(T-F1~T-F3)은 자동 pytest 대신 **실제 렌더러 관찰 검증**(CLAUDE.md render-grounding 정책).
