# 회의록 HWPX 양식 강화 PRD (양식 매핑 편집기 · Preset 갤러리)

## 1. 개요 및 배경

### 문서 정보
- 문서명: 회의록 HWPX 양식 강화 제품 요구사항 정의서(PRD)
- 버전: v1.2 (codex 적대 리뷰 반영 — 10장 참조)
- 대상 제품: 내비온 견적서·회의록 생성기 (Python + pywebview 데스크톱 앱)
- 범위 구분: **신규 프로젝트가 아니라 기존 코드베이스 위에 얹는 강화 작업**

### 배경
이 문서는 이미 운영 중인 데스크톱 앱에 회의록 관련 3개 기능(A·B·C)을 추가하기 위한 요구사항을 정의한다. 핵심 메시지는 다음과 같다.

> **엔진의 "좌표 배선"은 이미 깔려 있다(`build_minutes(cell_map=…)`). 빠진 것은 (0) 임의 양식에서도 안전하게 쓰는 셀 쓰기 엔진 견고화[P0 선결], (1) 매핑을 사람이 고치는 편집 UI, (2) 여러 양식을 보관·선택하는 다중 preset 저장소, (3) 표준 7슬롯을 넘어서는 커스텀 슬롯 스키마다.**

> ⚠️ **정정(적대 리뷰 반영)**: 초기 표현 "엔진은 이미 준비되어 있다"는 **과장**이었다. `cell_map`을 인자로 받는 배선은 존재하지만, `_set_simple_cell_text`가 대상 셀의 `subList>p>run>t` 구조를 무방비로 가정하는 등(아래 A-6) **임의 양식에 안전하게 쓰려면 엔진 보강이 선결**이다. 따라서 본 작업은 "UI/저장소만 남았다"가 아니라 **A-6(셀 쓰기 견고화)을 P0 선결로 둔 뒤** 그 위에 UI/저장소/스키마를 얹는다.

이 판단의 근거는 현재 코드가 이미 상당히 성숙하다는 점이다.
- `src/minutes/hwpx_minutes.py`의 `build_minutes(data, template_hwpx, out_path, cell_map)`는 **이미 `cell_map`(슬롯→[row,col] 오버라이드)을 인자로 받아** 커스텀 양식 좌표로 셀을 채운다. `_norm_cells()`가 부분 오버라이드를 `DEFAULT_CELLS` 위에 병합한다.
- `src/scan/hwpx_scan.py`의 `scan_hwpx_grid(path)`는 **이미 표 전체 셀을 `{row, col, text}` 그리드로 반환**한다(AI 입력·UI 표시용으로 그대로 재사용 가능).
- `src/ai/minutes_template_mapper.py`는 **이미 AI 매핑(`map_minutes_cells`)과 `.minutes.fieldmap.json` 캐시(`save_minutes_fieldmap`/`load_minutes_fieldmap`)**를 갖췄다.
- `src/api.py`의 `generate_minutes`는 **이미 fieldmap을 로드해 비표준 양식이면 `cell_map`을 `build_minutes`에 전달**한다.

즉, 데이터가 양식의 올바른 칸으로 들어가는 "마지막 1마일"의 엔진 **배선(좌표 인자 수용)**은 끝나 있다. 다만 그 배선이 **표준 내장 양식 기준으로 검증됐을 뿐**, 사용자가 임의 셀로 재매핑할 때의 구조 내성(A-6)은 아직 확보되지 않았다. 부족한 것은 ① 그 매핑을 안전하게 쓰는 엔진 보강, ② 매핑을 **눈으로 보고 손으로 고치는 수단**, ③ 선호 양식을 **여러 개 보관·전환하는 수단**이다.

### 현재의 한계(개선 대상)
- 회의록 "양식 관리" 패널(`ui/app.js` 약 1424~1506행, `scanMinutesTemplate`)은 커스텀 양식 1개를 선택해 `scan_minutes_template`로 AI 자동 매핑한 뒤, `cell_map`/`unmapped`를 **읽기 전용 표로 보여주기만** 한다. 사용자가 매핑을 수정하거나, AI가 못 맞춘 칸을 직접 지정·추가할 방법이 없다.
- 회의록 양식은 `doc_types.minutes.template_path`라는 **단일 문자열 하나만** 저장한다(`src/store/config_store.py`의 `get_minutes_tpl`/`set_minutes_tpl`). 여러 양식을 보관하거나 빠르게 전환할 수 없다.

### 설계 철학(반드시 준수)
- 최소 변경. 이미 있는 것은 **재사용**, 없는 것만 **신규**로 명확히 구분한다.
- 새 무거운 의존성 추가 지양. 오프라인·한글(COM) 미설치 환경에서도 동작하는 현재 보장을 유지한다(HWPX는 `zipfile` + `ElementTree`로만 처리).
- 계산·로직은 Python 엔진에서. UI(JS)는 표시·입력만 담당(JS 산수 금지 원칙).

## 2. 목표 및 비목표

### 비즈니스 목표 (Business Goals)
- B1. 비개발 내부 직원이 자기 부서·발주처 양식(임의의 HWPX 표)을 가져와도 **AI 매핑이 틀린 칸을 직접 바로잡아** 정확한 회의록을 생성하게 한다. 양식 불일치로 인한 재작업·수기 보정을 줄인다.
- B2. 자주 쓰는 양식을 **여러 개 보관·즉시 전환**(Word 시작 창 같은 preset 갤러리)하게 하여, 회의 성격(내부/외부/발주처)별 양식 전환 비용을 0에 가깝게 만든다.
- B3. AI 초안 → 양식 매핑 → HWPX 생성으로 이어지는 **일관된 회의록 워크플로**를 완성해 회의록 작성 시간을 단축한다.
- B4. 기존 견적서/회의록 데이터·설정과의 **후방호환을 100% 유지**하여 업데이트 후에도 기존 사용자가 재설정 없이 그대로 쓰게 한다.

### 비목표 (Non-Goals)
- N1. 한글(HWP/HWPX) 표 자체의 행·열 추가/병합 등 **양식 구조 편집**은 하지 않는다. 우리는 "양식의 어느 셀에 어떤 값을 넣을지"만 매핑한다(양식 자체는 사용자가 한글에서 만든다).
- N2. **픽셀 단위 WYSIWYG 한글 미리보기 렌더링은 하지 않는다**(A-4 타당성 결론 참조). 미리보기는 셀 그리드를 HTML 표로 재구성한 수준 + 선택적 Markdown 내용 미리보기로 충분하다.
- N3. 견적서(.hwp, COM 워커 경로)에 대한 대대적 개편은 이번 범위가 아니다. 견적서 적용 여부·범위는 Open Questions(9-b, 9-f)에서 다룬다.
- N4. 클라우드 동기화·다중 사용자 공유 양식 저장소는 이번 범위가 아니다(로컬 단일 사용자 데스크톱 앱 전제 유지).
- N5. 새 외부 런타임·무거운 패키지 도입은 하지 않는다(썸네일·미리보기도 추가 의존성 없이 처리하거나 생략).

## 3. 사용자 페르소나

### 핵심 사용자 유형
- 내부 직원(견적·회의록 작성자). 비개발자. 한글(HWP)·엑셀 사용에는 익숙하나 좌표·JSON·매핑 개념에는 익숙하지 않다.

### 페르소나 상세
- **김주임 (회의록 작성자)**: 회의가 끝나면 메모/녹취를 정리해 회의록 HWPX를 만든다. 부서 표준 양식과 발주처 제출용 양식 두세 가지를 번갈아 쓴다. AI 초안 기능은 즐겨 쓰지만, 발주처 양식은 표 구조가 달라 값이 엉뚱한 칸에 들어가는 일을 겪었다. "양식 그림을 보고 내가 직접 칸을 클릭해서 어디에 뭐가 들어갈지 고정하고 싶다"가 핵심 니즈.
- **이과장 (검수·관리자)**: 여러 직원이 같은 양식을 쓰도록 표준 양식을 배포·관리하고 싶어 한다. preset로 한 번 세팅해두고 팀이 같은 걸 고르길 원한다.

### 역할 기반 접근(RBAC) 관점
- 이 앱은 **로컬 단일 사용자 데스크톱 앱**으로, 로그인·다중 역할 권한 체계가 없다. 따라서 전통적 인증/인가는 적용되지 않는다.
- 다만 **보안 경계는 존재**한다: AI API 키는 `config_store.encrypt_secret`(Windows DPAPI, 현재 사용자 계정 바인딩)로 암호화 저장된다. AI 매핑 기능은 이 키에 의존하며, 키가 없으면 자동 매핑은 건너뛰고 수동 매핑으로 폴백한다(US-013 참조).

## 4. 기능 요구사항

각 요구사항에 `[재사용]`(기존 코드 그대로/소폭 노출) 또는 `[신규]`(새로 구현) 태그와 근거 파일·함수를 명시한다. 우선순위는 P0(필수)·P1(중요)·P2(여유).

### 기능 A — HWPX 양식 인식 강화: 칸 배치 선택 + 수제작/가변 입력
회의록 HWPX를 우선 대상으로 한다(견적서 HWP 적용 범위는 9-b·9-f 참조).

- **A-1. 표 구조·Markdown 미리보기 표시 [재사용+노출] · P0**
  - 근거: `scan_hwpx_grid(path)`(`src/scan/hwpx_scan.py`)가 이미 `{ok, row_cnt, col_cnt, cells:[{row,col,text}]}`를 반환한다. kordoc 변환(`Api.convert_files`, `src/convert/kordoc.py`)은 HWPX→Markdown을 이미 제공한다.
  - 요구: `scan_minutes_template` 응답(또는 신규 보강)에 그리드를 포함해, UI가 **표를 행×열 격자로 시각화**하고 각 셀의 텍스트(라벨/샘플값)를 보여준다. Markdown 미리보기는 선택적(P2)으로, 변환 엔진이 준비된 경우에만 노출.
  - 근거 보강: `scan_minutes_template`는 현재 그리드를 응답에 담지 않으므로, **그리드를 응답에 추가**하는 소폭 변경이 필요(엔진은 이미 있음 → 노출만).

- **A-2. 인터랙티브 셀 매핑 편집기 (드롭다운식) [신규] · P0**
  - 표준 7개 슬롯(`MINUTES_SLOTS`: business_name, meeting_date, meeting_place, meeting_topic, participants, total_count, content) 각각을, 그리드의 어느 셀(row,col)에 배치할지 사용자가 **드롭다운 선택 또는 셀 클릭으로 직접 지정·수정**한다.
  - AI 매핑(`map_minutes_cells`) 결과는 **초기 제안값**으로만 채워지고, 사용자가 언제든 덮어쓸 수 있다.
  - 저장 시 사용자 편집본을 `.minutes.fieldmap.json`에 기록한다. 신규 엔드포인트: **`save_minutes_cellmap(template_path, cell_map, custom_slots=None, annotations=None)`**.
    - 근거: 저장 포맷·경로 규약은 `save_minutes_fieldmap`/`_fieldmap_path`(`src/ai/minutes_template_mapper.py`)를 재사용·확장한다. `is_standard_map`으로 `is_standard` 재계산. `build_minutes`는 `cell_map`을 인자로 받지만, **임의 셀 재매핑의 쓰기 안전성은 A-6 선결**(이 항목만으로 "엔진 변경 없음"이라 단정하지 않는다).
  - 검증: 잘못된 좌표(범위 밖·중복)는 저장 시 경고. 단 `_norm_cells`는 좌표 **형식**(정수쌍)만 검증할 뿐 **그 좌표가 가리키는 셀이 텍스트 쓰기에 적합한 구조인지**는 보지 못한다 → 구조 적합성 검증·보정은 A-6에서 처리.

- **A-3. 수제작/가변 입력항목(커스텀 슬롯) [신규] · P1**
  - 양식의 칸이 표준 7슬롯에 안 맞을 때, 사용자가 (a) 특정 셀을 수동 지정하거나 (b) **새 커스텀 슬롯(라벨 + 대상 셀 [row,col])을 추가**해 입력 항목을 동적으로 늘린다.
  - 데이터 스키마 영향(후방호환 필수):
    - `.minutes.fieldmap.json`을 **version 2**로 확장하고 선택적 `custom_slots: [{id, label, cell:[r,c]}]` 배열을 추가한다. version 1 파일은 `custom_slots` 없이도 그대로 로드(기존 로더가 키 부재를 견딤).
    - `build_minutes`/`_norm_cells`는 현재 `DEFAULT_CELLS`에 없는 슬롯을 **무시**한다. 커스텀 슬롯 텍스트를 실제로 쓰려면, 커스텀 슬롯 값을 단순 셀 텍스트로 채우는 경로를 추가해야 한다(예: `data.custom_fields = {slot_id: text}` → 해당 cell 좌표에 `_set_simple_cell_text`). 이 확장 범위(새 데이터 필드 도입 여부)는 9-a Open Question.
    - `minutes_store`(`src/store/minutes_store.py`)는 `data`를 그대로 직렬화하므로 커스텀 필드가 들어와도 **스키마 변경 없이 보존**된다(후방호환 자동 충족).
  - 견적서 HWP 경로 적용 여부: 동일 "수동 재매핑/커스텀 필드" 원칙을 견적서(`scan_template`, `src/ai/template_mapper.py`)에도 적용할지는 9-b에서 결정. 기본 권고는 **이번 범위는 회의록 HWPX 한정**, 견적서는 후속.

- **A-4. 시각적 클릭-핀 매핑 편집기 [신규] · P1**
  - 사용자 요구 원문: "한글 양식 미리보기에서 특정 위치를 클릭하여 핀포인트 생성 및 댓글(입력 위치)을 입력하여 유저가 직접 보완."
  - **타당성 결론(두 방식 구분 — 반드시 명시)**:
    - **(불채택) 픽셀 이미지 핀포인트**: 실제 한글 페이지를 이미지/PDF로 렌더해 임의 픽셀 좌표에 핀을 찍는 방식. 회의록 엔진의 **COM-free 설계 목표**(한글 미설치로 동작)와 충돌하고, HWPX를 충실히 렌더하는 순수 파이썬 렌더러가 없으며, 픽셀→셀 역매핑이 불안정하다. → **비권장.**
    - **(채택·권장) HTML 재구성 표 미리보기 + 셀 클릭 핀**: `scan_hwpx_grid`가 이미 표 전체 셀(row,col,text)을 주므로, 이를 HTML `<table>`로 시각 재구성하고, 사용자가 셀을 클릭하면 해당 (row,col)에 **핀 + 댓글(입력 위치 설명)**을 달아 표준 슬롯을 지정하거나 커스텀 라벨을 입력한다. 핀은 **알려진 (row,col)으로 정확히 라운드트립**되어 `.minutes.fieldmap.json`에 저장된다.
  - 본질: A-4는 A-2(드롭다운식 매핑 편집기)·A-3(커스텀 슬롯)의 **시각·공간형 UX 변형**으로, **동일한 데이터 모델(cell_map + custom_slots/annotations)을 공유**한다. 좌표를 숫자가 아니라 격자 위 위치로 인지시키는, 비개발자 페르소나 친화 표면이다.
  - 구현 델타(아래 6장 기술 고려사항 "A-4 구현 델타"에 상세):
    1. `scan_hwpx_grid`가 현재 `cellAddr`만 읽음(코드 확인) → **`cellSpan`(colSpan/rowSpan) 추가 추출 필요**. 실측: `templates/회의록_양식.hwpx` 표에 colSpan=2 5개·colSpan=3 1개의 병합셀이 존재 → HTML 표가 실제 병합 모양과 일치해야 핀이 올바른 셀에 떨어진다.
    2. **중첩표(회의내용 셀 내부 사진표) 처리**: 파일에 tbl이 2개(본 표 + 사진표)다. `build_minutes`도 content 셀 안 사진표를 `deepcopy`로 보존한다. 내부 셀 클릭은 content 슬롯으로 귀속하거나 비활성/플래그 처리해, 별도 매핑 대상으로 오인하지 않게 한다.
    3. **fieldmap 스키마 확장**: `cell_map`(slot→[row,col])은 유지하고, 핀/댓글을 위해 optional `annotations: [{row,col,label,comment,slot?}]`를 추가(A-3 `custom_slots`와 동일 저장소·동일 후방호환 원칙).
  - **A-4 결론: 엔진(`build_minutes`)은 cell_map을 이미 수용함 → 신규 작업은 ① `cellSpan` 추출 ② 클릭형 HTML 표 미리보기 UI ③ 핀·댓글 주석 스키마(annotations) 세 가지로 좁혀진다.**
  - 부가(P2): kordoc Markdown 변환 결과는 **"내용 미리보기(읽기전용)"로만** 부가 노출한다. md는 `cellAddr` 정밀도를 잃으므로, 인터랙티브 핀 레이어는 반드시 `section0.xml` 그리드(`scan_hwpx_grid`)를 사용한다.

- **A-5. 미매핑(unmapped) 처리 정책 [신규] · P0**
  - 셀이 지정되지 않은 슬롯은 **경고로 노출**하되 생성을 차단하지 않는다("빈 칸으로 진행" 정책). 근거: `build_minutes`는 `_find_cell`이 `None`이면 조용히 건너뛰므로 빈 칸 생성이 이미 안전하다.
  - 생성 직전 미매핑 슬롯이 있으면 **확인 단계**를 한 번 노출(US-007).

- **A-6. HWPX 셀 쓰기 엔진 견고화 [신규] · P0 선결(A-2/A-3/A-4의 전제)**
  - 배경(적대 리뷰 Critical/High): 현재 엔진은 **표준 내장 양식 구조를 암묵 가정**한다. 임의 양식·임의 셀 재매핑에서 다음이 깨진다.
    - **A-6-1 단순 셀 쓰기 내성**: `_set_simple_cell_text`(`hwpx_minutes.py:90-103`)는 `tc is None`만 막고, 이후 `subList→p→run→t`를 None 체크 없이 연쇄한다. 사용자가 `business_name` 등 단순 슬롯을 **빈 셀·병합 잔여 셀·구조가 다른 셀**에 매핑하면 `AttributeError` → `build_minutes`가 `{ok:false}` 반환(생성 실패). 요구: 누락된 `subList/p/run/t`를 **방어적으로 생성·보정**하거나, 쓰기 불가 구조면 **명확한 슬롯별 오류**로 안내(전체 실패가 아니라).
    - **A-6-2 content·사진표 보존 경계**: content 슬롯은 대상 셀 문단을 전부 삭제 후 재구성하고, 사진표는 **매핑된 content 셀 내부**의 `paraPrIDRef=='28'`/내부 `tbl` 첫 문단만 `deepcopy`로 보존한다(`hwpx_minutes.py:289-339`). content를 **사진표 없는 셀로 매핑하면 사진표가 소실**되고, 사진표 있는 셀을 content로 찍으면 나머지 구조가 삭제된다. 요구: content 재매핑 시 사진표 보존 정책(원래 셀의 사진표를 유지/이동/생략 중 택)을 명시하고 경고.
    - **A-6-3 좌표 라운드트립 일관성**: `scan_hwpx_grid`는 첫 표만·`cellAddr` 평면만 읽고 `cellSpan`을 무시한다(`hwpx_scan.py:158-186`). UI가 병합 영역을 평면 격자로 그리면 **존재하지 않는 (row,col) 클릭**이 가능해 `_find_cell`이 `None`을 반환(조용한 누락). 요구: `cellSpan` 추출(A-4 ①)에 더해, **그리드가 반환하는 좌표 집합과 `_find_cell`이 인식하는 좌표 집합이 1:1 일치**함을 엔진 계약으로 보장(병합 영역은 대표 좌표 1개로 정규화).
  - 수용: 위 3개 시나리오에 대한 회귀 테스트가 그린이어야 A-2/A-3/A-4를 "완료"로 본다.

### 기능 B — 회의록 Preset 양식 갤러리 (Word 시작 창 방식)

- **B-1. 다중 양식 preset 저장소 [신규] · P0**
  - 현재 한계: `doc_types.minutes.template_path` 단일 문자열만 저장 → 여러 양식 보관 불가.
  - 요구: 각 preset = `{id, name, template_path, is_builtin, fieldmap_path(파생), created}`. 저장 위치는 `config.json`의 `doc_types.minutes.presets` 배열로 두되, **활성 선택은 기존 `template_path`에 계속 반영**(후방호환: 기존 `generate_minutes`/`get_minutes_template`가 그대로 동작).
  - 내장 기본 양식(`templates/회의록_양식.hwpx`, `TEMPLATE_MINUTES`)은 **항상 첫 preset이며 삭제 불가**.
  - 사용자가 가져온 양식 파일의 보관 정책(원본 경로 참조 vs 앱 데이터 폴더로 복사)은 9-c Open Question. 권고: **앱 데이터 폴더로 복사**(원본 이동·삭제에 견고; `data_path` 활용).

- **B-2. Preset 갤러리 모달 [신규] · P0**
  - 회의록 메뉴 진입 시(또는 새 회의록 시작 시) **카드형 갤러리 모달**을 띄운다. 각 카드 = 양식 이름 + 미리보기(셀 그리드 요약/썸네일) + 매핑 상태 배지(표준/AI 매핑됨/미매핑 N개).
  - 카드 선택 즉시 활성 양식 적용(`select_minutes_preset` → 내부적으로 `set_minutes_tpl`).
  - "내 양식 추가" 액션: HWPX import(`pick_minutes_template_file` 재사용) → 기능 A의 매핑 편집기(A-2/A-4)로 자연 연결.
  - preset 삭제(`delete_minutes_preset`)·이름변경(`rename_minutes_preset`). 내장 양식은 삭제·이름변경 불가.

- **B-3. 갤러리 표시 정책 [신규] · P1**
  - "다음부터 표시 안 함" 체크박스로 자동 표시를 끌 수 있다. 근거: 기존 `tutorial.seen` 패턴(`set_tutorial_seen`, `config_store`의 `tutorial`)을 미러해 `doc_types.minutes.gallery_autoshow`(기본 true) 같은 플래그로 저장.
  - 마지막 선택 preset을 기억하고(활성 `template_path`로 충분), 갤러리를 끈 사용자는 회의록 메뉴 내 버튼으로 언제든 다시 연다.

- **신규 엔드포인트 후보(이름 제안)**: `list_minutes_presets`, `add_minutes_preset`, `select_minutes_preset`, `delete_minutes_preset`, `rename_minutes_preset`, `set_minutes_gallery_autoshow`.

### 기능 C — 회의록 워크플로 통합 강화 (A·B를 포괄)

- **C-1. 일관 흐름 [신규 통합] · P0**
  - preset 선택 → (필요 시 매핑 편집) → AI 초안(`minutes_draft`) → 검토 → 생성(`generate_minutes`)이 끊김 없이 이어진다. 생성 시 **활성 preset의 cell_map을 자동 적용**한다(이미 `generate_minutes`가 fieldmap을 로드·적용하므로 재사용).

- **C-2. 미매핑 가드 [신규] · P0**
  - 생성 직전, 활성 양식의 fieldmap에 미매핑 슬롯이 있으면 경고를 노출하되 진행은 허용(A-5와 동일 정책, 한 곳에서 일관 처리).

- **C-3. preset별 cell_map 캐시 재사용 [재사용] · P0**
  - 각 preset 양식 옆 `.minutes.fieldmap.json`이 매핑의 단일 출처다. 한 번 편집·저장하면 이후 같은 preset 선택 시 재분석 없이 즉시 적용(`load_minutes_fieldmap` 재사용). AI 호출은 "처음 양식을 추가할 때 1회" 또는 "사용자가 재분석을 누를 때"만 발생 → 비용·오프라인 친화.

- **범위 가드**: 위 외의 신기능(예: 회의록 협업, 버전 관리, 템플릿 마켓)은 추가하지 않는다. 요청에 없는 기능 남발 금지.

## 5. 사용자 경험 플로우

### 진입점 (Entry Points)
- 좌측 문서 유형 내비게이션에서 "회의록" 선택 시.
- 회의록 대시보드의 "새 회의록" 시작 시(갤러리 자동 표시 정책에 따름).
- 설정/양식 관리 패널에서 "양식 관리" 진입 시(직접 매핑 편집).

### 핵심 경험 (Core Experience)
1. 사용자가 회의록 메뉴에 들어오면 **Preset 갤러리 모달**이 뜬다(자동 표시가 켜진 경우). 카드들 중 하나를 고르거나 "내 양식 추가"를 누른다.
2. "내 양식 추가"를 누르면 HWPX 파일을 고르고, 앱이 표 구조를 스캔해 **HTML 격자로 시각화**한다(병합셀 포함). AI가 7슬롯의 초기 셀 위치를 제안한다(키가 있을 때).
3. 사용자는 매핑을 두 방식 중 편한 쪽으로 보완한다 — **(A-2) 슬롯별 드롭다운**으로 셀을 고르거나, **(A-4) 격자 미리보기에서 셀을 클릭해 핀을 찍고 댓글로 "여기에 사업명"처럼 입력 위치를 적는다**. 표준에 안 맞는 칸은 커스텀 슬롯/주석으로 추가한다. 저장하면 preset과 `.minutes.fieldmap.json`(cell_map + annotations)이 만들어진다.
4. 활성 preset이 정해진 상태에서 사용자는 회의 메모/녹취를 입력하고 **AI 초안**을 받는다(`minutes_draft`).
5. 초안을 검토·수정한 뒤 **생성**을 누르면, 활성 preset의 cell_map으로 값이 정확한 칸에 들어간 **HWPX가 생성**된다(`generate_minutes`). 미매핑 슬롯이 있으면 생성 직전 한 번 경고한다.

### 고급 기능 (Advanced Features)
- 클릭-핀 + 댓글 주석으로 시각적 보완(A-4).
- 커스텀 슬롯 추가/삭제(가변 입력항목, A-3).
- preset 이름변경·삭제, 갤러리 자동 표시 토글.
- 양식 재분석(AI 매핑 다시 받기) — 사용자가 명시적으로 누를 때만.

### UI/UX 하이라이트
- 매핑 편집기는 **읽기 전용 표(현재)** 를 **편집 가능한 격자(드롭다운 + 클릭 핀)**로 대체한다.
- 좌표(row,col)는 사용자에게 숫자보다 **시각적 격자 위치**로 인지되게 한다(셀 클릭 = 매핑/핀).
- 병합셀은 HTML `<table>`의 `colspan/rowspan`으로 실제 양식 모양과 일치시켜, 핀이 의도한 칸에 떨어지게 한다.
- 모든 안내·경고는 한국어. 기존 토스트(`toast`)·상태 텍스트 패턴 재사용.
- 위험·비가역 동작(preset 삭제, 양식 파일 삭제)은 확인을 받는다.

## 6. 기술 고려사항

### 기술 스택/제약 (현재 유지)
- Python + pywebview 데스크톱 앱. UI는 `ui/index.html` + `ui/app.js`(바닐라 JS) + `ui/app.css`.
- Python↔JS 단일 계약 지점은 `src/api.py`의 `class Api`. 모든 메서드는 JSON dict 입출력, 계산은 Python에서.
- 설정 저장: `src/store/config_store.py`(config.json, DPAPI 키 암호화, 원자적 쓰기 `os.replace`).
- HWPX 처리는 **한글(COM) 없이** `zipfile` + `ElementTree`로만(`hwpx_minutes.py`, `hwpx_scan.py`). 이 보장을 깨지 않는다. → A-4의 **픽셀 렌더 방식이 불채택인 1차 근거**.
- 문서→Markdown 변환은 kordoc(Node.js CLI) subprocess(`src/convert/kordoc.py`), 첫 사용 시 npm 자동 설치, 오프라인/노드없음 상태머신 보유. A-1/A-4 부가의 Markdown 미리보기는 이 상태에 의존하므로 **변환 불가 상태에서도 셀 그리드 시각화·핀 매핑은 동작**해야 한다(그리드·핀은 kordoc 불필요).

### 통합 지점 (Integration Points)
- `build_minutes(data, template_hwpx, out_path, cell_map)` — **변경 최소**. 커스텀 슬롯/주석을 실제 채우려면 커스텀 필드→셀 텍스트 경로만 소폭 추가(9-a 결정에 따름).
- `scan_hwpx_grid` — 그리드 공급원(재사용). **A-4를 위해 `cellSpan` 추출 추가**(아래 구현 델타).
- `map_minutes_cells` / `save_minutes_fieldmap` / `load_minutes_fieldmap` / `is_standard_map` — AI 초기 제안 + 캐시(재사용·확장).
- `generate_minutes`(api) — 활성 양식 fieldmap 로드·적용(재사용).
- 견적서 경로(`scan_template`, `src/ai/template_mapper.py`, `<이름>.fieldmap.json`)는 **별도 규약**임을 유지. "공통 hwpx 인식"은 회의록 HWPX 경로에 적용되며, 견적서 .hwp(COM 스캔) 경로와 매핑 캐시 파일은 분리된 채로 둔다(혼동 방지).

### A-4 구현 델타 (클릭-핀 미리보기)
1. **`cellSpan` 추출 [신규·소폭]**: `scan_hwpx_grid`(`src/scan/hwpx_scan.py`)는 현재 `cellAddr`(rowAddr/colAddr)만 읽는다(코드 확인). HWPX 셀의 `cellSpan`(colSpan/rowSpan)을 추가로 읽어 각 셀에 `colspan/rowspan`을 부여한다. 실측 근거: `templates/회의록_양식.hwpx`에 colSpan=2 5개·colSpan=3 1개 병합셀 존재. 이 정보가 없으면 HTML 표가 실제 양식과 어긋나 핀이 잘못된 칸에 떨어진다.
2. **중첩표 처리 [신규]**: 본 표 외에 회의내용 셀 안 사진표(중첩 `tbl`)가 있다(`build_minutes`가 `paraPrIDRef=='28'` 또는 내부 `tbl`을 `deepcopy`로 보존). `scan_hwpx_grid`는 첫 번째 표만 보지만, 중첩 셀이 평탄화돼 별도 매핑 대상으로 노출되지 않도록 content 귀속/플래그 처리한다.
3. **fieldmap 스키마 확장 [신규]**: `.minutes.fieldmap.json` version 2에 optional `annotations: [{row, col, label, comment, slot?}]` 추가. `slot`이 표준 7슬롯이면 cell_map과 동일 의미(시각식 입력), 아니면 A-3 `custom_slots`와 동일 취급. version 1 파일은 `annotations` 부재로 안전 로드.
4. **저장 엔드포인트 [신규]**: `save_minutes_cellmap(template_path, cell_map, custom_slots=None, annotations=None)` — A-2/A-3/A-4가 **하나의 저장 경로**를 공유. `build_minutes`는 cell_map을 이미 받으므로 엔진 변경 최소.
5. **미리보기 레이어 분리 [정책]**: 인터랙티브 핀 레이어는 항상 `section0.xml` 그리드(`scan_hwpx_grid`)를 사용한다(셀 좌표 정밀). kordoc Markdown은 정밀도를 잃으므로 읽기전용 "내용 미리보기"로만 부가 노출(P2).

### 신규/변경 엔드포인트 목록 (이름 제안)
- A: `save_minutes_cellmap(template_path, cell_map, custom_slots=None, annotations=None)` [신규]
- A: `scan_minutes_grid(template_path)` — **AI 호출 없이** `scan_hwpx_grid`(cellSpan 포함)만 반환하는 **오프라인 전용 경로** [신규]. (정정·적대 리뷰 Medium: 현재 `scan_minutes_template`는 스캔 직후 AI 매핑을 강제 호출(`api.py:1196-1218`)하고 grid를 응답에 담지 않으므로, "시각 격자만 보기"가 AI 실패/지연에 묶이지 않게 **그리드 조회를 AI에서 분리**한다.)
- A: `scan_minutes_template` 응답에 `grid`(셀 그리드, `cellSpan` 포함) 추가 [변경·소폭] — AI 매핑 제안과 함께 쓰는 경로(키 있을 때).
- B: `list_minutes_presets()`, `add_minutes_preset(path, name=None)`, `select_minutes_preset(id)`, `delete_minutes_preset(id)`, `rename_minutes_preset(id, name)` [신규]
- B: `set_minutes_gallery_autoshow(on)` [신규]

### 데이터 스키마 변경 (후방호환)
- `.minutes.fieldmap.json`: `version` 1→2, 선택적 `custom_slots: [{id,label,cell:[r,c]}]` 및 `annotations: [{row,col,label,comment,slot?}]` 추가. version 1 로드 시 두 키 부재를 허용(기존 `load_minutes_fieldmap`은 임의 키에 견고).
- `config.json`: `doc_types.minutes.presets: [...]`, `doc_types.minutes.gallery_autoshow: bool` 추가.
  - ⚠️ **정정(적대 리뷰 High)**: `_merge`(`config_store.py:86-93`)는 **양쪽이 dict일 때만** 재귀 병합하고 **리스트는 override가 통째로 덮는다**. 따라서 "_merge가 알아서 안전 시딩"은 **키 부재 시에만 참**이고, 사용자 config에 `presets: [...]`가 이미 있으면 **기본 내장 preset이 시딩되지 않는다**. → preset 시딩은 `_merge`에 의존하지 말고 **전용 마이그레이션 함수**(`migrate_minutes_presets(cfg)`, 기존 `migrate_doc_type_folders` 패턴)로 처리: (a) `presets` 부재/비배열이면 내장 preset 1개로 초기화, (b) 항상 내장 preset이 첫 항목으로 존재함을 보장, (c) 타입 검증.
  - **이중 진실 원천 방지**: `presets[]`(보관 목록)와 `template_path`(활성 선택)가 어긋나면 갤러리 선택과 실제 출력이 불일치한다. **활성 preset id ↔ `template_path` 동기화 규칙**을 한 곳(`select_minutes_preset`)에서 강제하고, `generate_minutes`/`get_minutes_template`는 계속 `template_path`를 단일 활성 출처로 읽는다(후방호환).
- `minutes.json` 사이드카: 커스텀 필드가 `data`에 추가돼도 `minutes_store`가 그대로 보존(스키마 변경 불필요).

### 확장성·성능
- 양식 스캔/매핑/핀 편집은 파일 1개 단위의 가벼운 연산. preset 수는 수십 개 규모를 가정 → 배열 순회로 충분, 인덱스/DB 불필요.
- AI 호출은 양식 추가/재분석 시에만. 생성 시점에는 캐시(`load_minutes_fieldmap`)만 읽어 **추가 비용·지연 없음**.

### 잠재적 도전 과제
- 좌표 기반 매핑을 비개발자가 직관적으로 이해하도록 하는 UI 설계(시각 격자·클릭 핀 = 핵심).
- 병합셀·중첩표를 가진 임의 발주처 양식에서 HTML 표 재구성이 실제 모양과 어긋날 위험 → `cellSpan` 추출과 중첩표 평탄화 정책으로 대응, 그 외는 미매핑 경고로 흡수.
- 커스텀 슬롯/주석이 "새 데이터 필드"까지 도입하면 AI 초안 스키마(MINUTES_SCHEMA)와의 정합이 필요 → 9-a에서 범위를 좁게 결정(우선은 "기존 7슬롯 재배치 + 정적 텍스트 커스텀 슬롯/주석"까지).

### 테스트 요구 (pytest, 기존 스타일)
- 기존 `tests/test_minutes.py`, `test_minutes_api.py`, `test_minutes_store.py`, `test_hwpx_scan.py` 스타일을 따른다.
- 신규 단위 테스트(필수):
  - `scan_hwpx_grid`가 `회의록_양식.hwpx`의 병합셀에 대해 `colspan`(=2 5개·=3 1개)을 정확히 반환하는지(A-4 ① 회귀 방지).
  - 중첩 사진표 셀이 별도 매핑 대상으로 새지 않고 content로 귀속/플래그되는지(A-4 ②).
  - `save_minutes_cellmap` 라운드트립(저장→`load_minutes_fieldmap`로 cell_map·custom_slots·annotations 동일 복원), `is_standard` 재계산 검증.
  - version 1 fieldmap 로드 후 version 2로 저장해도 기존 7슬롯 동작 불변(후방호환).
  - preset CRUD(추가/선택/이름변경/삭제), 내장 preset 삭제 거부, 선택 시 `template_path` 반영.
  - 커스텀 슬롯/주석이 `build_minutes`에서 지정 셀에 텍스트로 들어가는지(9-a 채택 시).
  - 미매핑 슬롯이 있어도 `build_minutes`가 빈 칸으로 안전 생성(`_find_cell` None 경로).
  - **A-6-1**: 단순 슬롯을 `subList/p/run`가 없는 셀(빈 셀·병합 잔여)에 매핑해도 `AttributeError`로 전체 실패하지 않고, 구조를 보정해 쓰거나 해당 슬롯만 명확한 오류로 보고하는지.
  - **A-6-2**: content를 사진표 없는 셀로 재매핑했을 때 사진표 보존 정책(유지/이동/생략)이 의도대로 동작하고 사일런트 소실이 없는지.
  - **A-6-3**: `scan_hwpx_grid`가 반환하는 좌표 집합 ⊆ `_find_cell` 인식 좌표(병합 영역 대표 좌표 1:1) — 그리드 클릭이 항상 실셀로 라운드트립되는지.
  - `scan_minutes_grid`가 AI 키 없이도 그리드를 반환(오프라인 경로 분리).

## 7. 성공 지표

### 사용자 중심 지표
- 커스텀 양식 첫 생성 성공률: 양식 추가 후 첫 HWPX 생성에서 값이 올바른 칸에 들어간 비율 ≥ 90%.
- 매핑 수정 가능성 충족: AI가 틀린 칸을 사용자가 UI(드롭다운 또는 클릭 핀)에서 바로잡아 재생성한 케이스가 "수기 보정 없이" 해결되는 비율 ≥ 95%.
- 클릭 핀 정확도: 병합셀·중첩표가 포함된 양식에서 사용자가 클릭한 위치가 의도한 (row,col)으로 매핑된 비율 ≥ 98%.
- preset 전환 시간: 양식 변경에 드는 클릭/시간이 기존(파일 재선택+재분석) 대비 체감 단축.

### 비즈니스 지표
- 회의록 작성 평균 소요시간 감소.
- 커스텀 양식 사용 직원 비율 증가(내장 양식만 쓰던 사용자가 자기 양식을 등록).

### 기술 지표
- 회귀 0: 기존 회의록/견적서 생성·재편집 동작 불변(기존 테스트 전부 통과).
- 후방호환: 기존 config.json·fieldmap·minutes.json을 가진 사용자가 업데이트 후 재설정 없이 동작(마이그레이션 테스트 통과).
- 오프라인·COM-free 유지: 한글 미설치·네트워크 없음 상태에서도 그리드 시각화·클릭 핀 매핑·생성이 동작(AI 매핑만 비활성).

## 8. 사용자 스토리

### A. 양식 인식·매핑 편집

- **US-001 — 표 구조 격자 시각화**
  - 설명: 작성자로서, 커스텀 회의록 양식을 선택하면 표가 행×열 격자로 보이고 각 셀의 라벨/샘플 텍스트를 확인하고 싶다.
  - 수용 기준:
    - 양식을 선택하면 `scan_hwpx_grid` 결과(행·열 수, 셀별 텍스트)가 격자로 표시된다.
    - 병합셀이 `colspan/rowspan`으로 실제 양식 모양과 일치하게 표시된다.
    - 한글(COM) 미설치·오프라인 상태에서도 격자 시각화가 동작한다.
    - 표를 찾을 수 없는 파일은 오류 메시지를 표시하고 매핑 편집을 비활성화한다.

- **US-002 — AI 초기 매핑 제안**
  - 설명: 작성자로서, 양식 추가 시 AI가 7개 슬롯의 셀 위치를 자동 제안해 시작점을 주길 원한다.
  - 수용 기준:
    - AI 키가 있으면 `map_minutes_cells`로 `cell_map`/`unmapped`가 채워져 편집기에 초기값으로 표시된다.
    - AI 키가 없거나 호출 실패면 모든 슬롯이 미지정 상태로 시작하고, 그 사실을 안내한다(생성 차단 아님).

- **US-003 — 슬롯-셀 매핑 수동 편집 (드롭다운)**
  - 설명: 작성자로서, 각 표준 슬롯이 들어갈 셀을 드롭다운/클릭으로 직접 지정·수정하고 싶다.
  - 수용 기준:
    - 7개 슬롯 각각에 대해 셀(row,col)을 선택/변경할 수 있다.
    - AI 제안값을 덮어써도 즉시 반영된다.
    - 범위 밖·중복 좌표는 저장 시 경고하고, 명백히 잘못된 항목은 무시(기본값 유지)한다.

- **US-004 — 편집한 매핑 저장**
  - 설명: 작성자로서, 편집한 매핑을 저장해 다음에 같은 양식을 쓸 때 재사용하고 싶다.
  - 수용 기준:
    - `save_minutes_cellmap`이 `.minutes.fieldmap.json`(version 2)에 사용자 편집본(cell_map·custom_slots·annotations)을 기록한다.
    - 저장 후 `load_minutes_fieldmap`로 동일하게 복원된다(라운드트립).
    - `is_standard`가 매핑 내용에 맞게 재계산된다.

- **US-005 — 커스텀 슬롯 추가(가변 입력항목)**
  - 설명: 작성자로서, 표준 7슬롯에 없는 칸을 위해 라벨과 대상 셀을 가진 커스텀 슬롯을 추가하고 싶다.
  - 수용 기준:
    - 라벨 + 대상 셀(row,col)을 입력해 커스텀 슬롯을 추가/삭제할 수 있다.
    - 커스텀 슬롯은 `.minutes.fieldmap.json`의 `custom_slots`에 저장된다.
    - 채택 범위(9-a)에 따라, 커스텀 슬롯에 입력한 텍스트가 생성 시 지정 셀에 들어간다.

- **US-006 — 후방호환 로드**
  - 설명: 기존 사용자로서, 예전 version 1 fieldmap을 가진 양식도 그대로 열리고 동작해야 한다.
  - 수용 기준:
    - version 1 fieldmap을 로드해 편집·재저장(version 2)해도 기존 7슬롯 매핑 동작이 불변이다.
    - `custom_slots`·`annotations`가 없는 파일도 오류 없이 로드된다.

- **US-007 — 미매핑 경고(빈 칸 진행)**
  - 설명: 작성자로서, 일부 슬롯이 매핑되지 않아도 생성을 막지 말고 경고만 받고 싶다.
  - 수용 기준:
    - 생성 직전 미매핑 슬롯이 있으면 어떤 슬롯이 비는지 경고를 표시한다(A-5 정책).
    - 사용자가 진행을 선택하면 해당 칸을 빈 채로 둔 HWPX가 정상 생성된다.

- **US-015 — 클릭-핀 + 댓글 시각 매핑**
  - 설명: 작성자로서, 양식 미리보기 격자에서 셀을 클릭해 핀을 찍고 댓글(입력 위치 설명)을 달아, 표준 슬롯 지정이나 커스텀 라벨을 시각적으로 보완하고 싶다.
  - 수용 기준:
    - HTML 재구성 표(병합셀 반영)에서 셀을 클릭하면 해당 (row,col)에 핀이 생성되고, 라벨/슬롯 지정과 댓글을 입력할 수 있다.
    - 핀이 정확히 그 (row,col)으로 `annotations`에 라운드트립 저장되고, 표준 슬롯에 연결한 핀은 `cell_map`에도 반영된다.
    - 중첩 사진표 내부 셀 클릭은 별도 매핑 대상으로 만들어지지 않는다(content 귀속/비활성).
    - 픽셀 이미지 렌더 없이(COM-free) 동작하며, 오프라인·한글 미설치 상태에서도 핀 편집이 가능하다.
    - 드롭다운식 편집(US-003)과 동일한 fieldmap 데이터에 일관되게 저장된다.

### B. Preset 갤러리

- **US-008 — 갤러리에서 양식 선택**
  - 설명: 작성자로서, 회의록 시작 시 Word 시작 창처럼 카드형 갤러리에서 양식을 고르고 싶다.
  - 수용 기준:
    - `list_minutes_presets`가 내장 양식을 첫 카드로, 사용자 양식을 이어서 반환한다.
    - 카드 선택 시 `select_minutes_preset`이 활성 양식(`template_path`)을 즉시 적용한다.
    - 각 카드에 매핑 상태 배지(표준/AI 매핑됨/미매핑 N개)가 표시된다.

- **US-009 — 내 양식 추가**
  - 설명: 작성자로서, 갤러리에서 "내 양식 추가"로 HWPX를 가져와 매핑 편집으로 이어가고 싶다.
  - 수용 기준:
    - `pick_minutes_template_file`로 파일을 고르면 `add_minutes_preset`이 preset를 만든다.
    - 추가 직후 매핑 편집기(US-001~US-005, US-015)로 자연스럽게 연결된다.
    - 보관 정책(9-c 결정)에 따라 원본 참조 또는 앱 폴더 복사가 일관되게 적용된다.

- **US-010 — preset 이름변경·삭제**
  - 설명: 작성자로서, preset의 이름을 바꾸거나 더 이상 안 쓰는 것을 삭제하고 싶다.
  - 수용 기준:
    - `rename_minutes_preset`/`delete_minutes_preset`이 동작한다.
    - 내장 기본 양식은 이름변경·삭제가 불가(버튼 비활성 + 서버측 거부)하다.
    - 삭제는 확인 단계를 거친다.

- **US-011 — 갤러리 자동 표시 토글**
  - 설명: 작성자로서, 갤러리를 매번 띄울지 말지 선택하고, 껐어도 필요할 때 다시 열고 싶다.
  - 수용 기준:
    - "다음부터 표시 안 함" 체크 시 `set_minutes_gallery_autoshow(false)`로 저장되고, 이후 자동 표시가 꺼진다.
    - 자동 표시를 꺼도 회의록 메뉴 버튼으로 언제든 갤러리를 다시 연다.
    - 마지막 선택 preset이 다음 실행에도 활성으로 유지된다.

### C. 통합 워크플로

- **US-012 — 끊김 없는 생성 흐름**
  - 설명: 작성자로서, preset 선택 → AI 초안 → 검토 → 생성이 한 흐름으로 이어지길 원한다.
  - 수용 기준:
    - 활성 preset 상태에서 `minutes_draft` 초안을 받아 검토 후 `generate_minutes`로 생성하면, 활성 preset의 cell_map이 자동 적용된다.
    - 생성된 HWPX에서 값이 매핑된 셀에 정확히 들어간다.
    - 재분석을 누르지 않는 한 캐시된 fieldmap만 사용해 추가 AI 호출이 없다.

### 보안·환경

- **US-013 — AI 키 부재 시 안전한 폴백**
  - 설명: 작성자로서, AI 키가 없거나 오프라인이어도 양식 매핑·회의록 생성을 수동으로 끝낼 수 있어야 한다.
  - 수용 기준:
    - AI 키가 없으면 자동 매핑은 건너뛰고 수동 매핑 편집기(드롭다운·클릭 핀)로 전체 작업을 완료할 수 있다.
    - AI API 키는 DPAPI로 암호화 저장(`encrypt_secret`)되며 평문으로 노출되지 않는다.
    - 네트워크 없음·한글 미설치 상태에서도 그리드 시각화·매핑 편집·HWPX 생성이 동작한다.

- **US-014 — 비가역 동작 보호**
  - 설명: 작성자로서, 양식 파일이나 preset을 실수로 지우지 않도록 보호받고 싶다.
  - 수용 기준:
    - preset 삭제, 양식 파일 삭제 등 비가역 동작은 명시적 확인을 거친다.
    - preset 삭제는 기본적으로 등록만 해제하고, 실제 양식 파일 삭제는 별도 동의가 있을 때만 수행한다(`delete_minutes`/`delete_quote`의 `also_files` 패턴 미러).

## 9. 미해결 결정사항 (Open Questions)

- **9-a. 커스텀 슬롯/주석의 범위**: 커스텀 슬롯·핀 주석이 (i) 기존 7슬롯의 재배치만 허용할지, (ii) 새로운 데이터 입력 필드(정적 텍스트)까지 추가할지, (iii) AI 초안(MINUTES_SCHEMA)과도 연동되는 동적 필드까지 갈지. 권고: 1차로 (i)+(ii)까지(7슬롯 재배치 + 사용자가 직접 입력하는 정적 텍스트 커스텀 슬롯/주석). (iii)은 후속. 이 결정이 `build_minutes`/MINUTES_SCHEMA 변경 폭을 좌우한다.
  - ⚠️ **데이터 계약 공백 명시(적대 리뷰 Medium)**: 현재 (ii)조차 **무료가 아니다**. `_norm_cells`는 `DEFAULT_CELLS`에 없는 슬롯을 무시하고(`hwpx_minutes.py:185-199`), AI 매퍼는 7슬롯만 허용하며(`minutes_template_mapper.py:51-52`), `MINUTES_SCHEMA` 정규화도 unknown 필드를 버린다(`src/ai/minutes.py`). 따라서 (ii)를 채택하면 **저장(fieldmap `custom_slots`)에 더해 ① 생성 경로(`data.custom_fields → 지정 셀 쓰기`, A-6-1 구조 보정 위에서), ② 정규화 화이트리스트 확장**까지 한 묶음으로 구현해야 한다. (ii) 미채택 시 커스텀 슬롯은 "저장·표시만 하고 생성에는 미반영"임을 UI에서 분명히 한다.

- **9-b. 견적서 HWP 경로 적용 범위**: 동일한 수동 매핑 편집기/커스텀 필드를 견적서(.hwp, COM 스캔, `scan_template`/`src/ai/template_mapper.py`)에도 적용할지. 견적서는 좌표(셀)가 아니라 누름틀 필드명 기반이라 UI 모델이 다르다. 권고: 이번 범위는 회의록 HWPX 한정, 견적서는 별도 PRD.

- **9-c. preset 저장 위치/내장 양식 복사 정책**: 사용자가 가져온 양식을 원본 경로로 참조할지, 앱 데이터 폴더(`data_path`)로 복사해 보관할지. 권고: 복사(원본 이동·삭제에 견고). 복사 시 디스크 사용·중복 관리 정책 필요.

- **9-d. 갤러리 자동 표시 기본값**: 최초 도입 시 자동 표시 기본을 켤지(온보딩 효과) 끌지(방해 최소화). 권고: 기본 켜고 "다음부터 표시 안 함" 제공(`tutorial.seen` 패턴과 일관).

- **9-e. 핀/댓글 모델**: 한 셀에 핀을 1개만(슬롯 1:1 지정) 허용할지, 다중 주석(여러 메모/여러 슬롯 후보)을 허용할지. 권고: 1차는 1셀=1핀(슬롯 지정 또는 커스텀 라벨), 다중 주석은 필요 시 후속. 이 결정이 `annotations` 스키마의 키 유일성·검증 규칙을 좌우한다.

- **9-f. 시각 미리보기의 견적서 적용 여부**: 클릭-핀 미리보기를 견적서 HWP 경로에도 제공할지. 견적서는 HWPX가 아니고 COM 스캔(누름틀 필드명) 기반이라 그리드 좌표 모델이 없다 → 같은 클릭-핀 UX를 적용하려면 별도 스캔/좌표 모델이 필요. 권고: 이번 범위 제외(회의록 HWPX 한정), 견적서는 9-b와 함께 후속 결정.

## 10. 적대 리뷰(codex) 반영 요약

PRD v1.1을 codex로 적대적 기술 검토한 결과, "엔진은 이미 준비됨" 논지가 **과장**으로 판정됐다. 좌표 인자 배선은 존재하나 임의 양식 쓰기 안전성·preset 마이그레이션·데이터 계약이 미비. 아래 6건을 본문에 반영했다.

| # | 심각도 | 지적 | 반영 위치 |
|---|--------|------|-----------|
| 1 | Critical | `_set_simple_cell_text`가 `subList>p>run>t` 무방비 가정 → 임의 셀 재매핑 시 AttributeError·생성 실패. "엔진 변경 없음" 거짓 | 개요 정정, A-2 완화, **A-6-1**, 테스트 |
| 2 | High | content/사진표 보존이 특정 셀에 결합 → 재매핑 시 사진표 사일런트 소실 | **A-6-2**, 테스트 |
| 3 | High | `scan_hwpx_grid`가 첫 표·평면 cellAddr만·cellSpan 무시 → 클릭 좌표 라운드트립 불일치 | A-4 ①, **A-6-3**, 테스트 |
| 4 | High | `_merge`가 리스트를 통째로 덮음 → `presets[]` 안전 시딩 거짓, 내장 preset 소실·이중 진실 원천 | 스키마 정정, 전용 `migrate_minutes_presets` |
| 5 | Medium | `custom_slots`/MINUTES_SCHEMA/AI 매퍼가 unknown 필드 폐기 → "정적 텍스트 생성" 비용 과소평가 | 9-a 데이터 계약 공백 명시 |
| 6 | Medium | `scan_minutes_template`가 AI 호출과 결합 → 오프라인 격자 보기가 AI에 묶임 | `scan_minutes_grid` 분리 엔드포인트 |

**판정 수용**: 구현 순서는 **A-6(셀 쓰기 견고화) P0 선결 → A-2/A-3/A-4(UI·스키마) → B(preset) → C(통합)**. 기각된 가설: "cell_map이 단순 4셀에만 적용된다"(틀림 — participants/total_count/content도 좌표 사용). 즉 문제는 적용 여부가 아니라 **구조 내성·보존 정책**이다.
