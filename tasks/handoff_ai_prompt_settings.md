# 핸드오프: AI 초안 기초 프롬프트 설정 편집 (M16)

**작성일**: 2026-06-12
**상태**: ✅ 구현·검증·커밋 완료 (`b1ccab8`)
**테스트**: pytest 206건 green (신규 23건 포함)

---

## 한 줄 요약

설정의 **견적서 탭 / 회의록 탭**에 "AI 초안 프롬프트" 카드를 추가해, AI의 역할·작성 규칙(기초 지침)을
사용자가 직접 편집·저장·기본값 복원할 수 있게 했다. 과업 내용·금액·단가표 등 **데이터는 항상 시스템이
자동 첨부**하므로 지침을 어떻게 고쳐도 초안 기능은 깨지지 않는다.

---

## 왜 했나 (배경)

AI 초안(견적서·회의록)의 방향 프롬프트가 `gemini.py PROMPT_TMPL` / `minutes.py _PROMPT_TMPL`에
하드코딩돼 있어, 사용자가 AI의 역할·작성 규칙을 조정할 수 없었다. 사용자가 "기초 방향 프롬프트를
설정에서 편집·저장하고 싶다"고 요청 → 유형별 편집 기능으로 구현.

**사용자 확정 사양**: ① 편집 범위는 기초 지침(디렉티브)만 ② 견적서·회의록 둘 다.

---

## 설계 핵심 — 3대 불변식 (이걸 깨면 안 됨)

프롬프트를 **[기초 지침: 편집 가능] + [데이터 블록: 시스템 고정·항상 자동 첨부]** 두 조각으로 분리했다.

```
[디렉티브: 사용자 편집]   ← QUOTE_DIRECTIVE_DEFAULT / MINUTES_DIRECTIVE_DEFAULT (config로 오버라이드)
        +  "\n\n"
[데이터 블록: 시스템 고정]  ← _QUOTE_DATA_TMPL / _MINUTES_DATA_TMPL (.format으로 과업·금액·단가 주입)
```

1. **사용자 텍스트는 `str.format()`을 절대 통과하지 않는다.**
   - 과거 `build_prompt`는 템플릿 전체를 `.format`에 넣었음 → 사용자가 지침에 `{`/`}`(JSON 예시 등)를
     쓰면 `KeyError` 크래시. 새 조립은 `디렉티브원문 + "\n\n" + 데이터템플릿.format(...)`.
   - 그래서 **기본 디렉티브 텍스트에는 자리표시자(`{...}`)가 0개**여야 한다(test_ai_prompts가 검증).
2. **데이터 블록은 디렉티브와 무관하게 항상 첨부된다.** → 지침이 엉망이어도 과업·금액·단가표는 전달됨.
   추가로 출력 형태는 `RESPONSE_SCHEMA`/`MINUTES_SCHEMA`(구조화 출력) + `_normalize` 클램프가 보장.
3. **기본값과 동일하거나 빈 텍스트 저장 → `""`(오버라이드 해제)로 정규화.**
   - 사용자가 안 고치고 저장 버튼만 눌러도 향후 기본 지침 개선이 계속 반영되게 하는 장치.
   - `api.set_ai_prompt`가 `\r\n→\n` 정규화 + strip 후 `DIRECTIVE_DEFAULTS[t].strip()`와 비교.

---

## 파일 맵 (무엇이 어디서 바뀌었나)

### 백엔드
| 파일 | 변경 |
|---|---|
| `src/ai/gemini.py` | `PROMPT_TMPL` 제거 → `QUOTE_DIRECTIVE_DEFAULT`(공개) + `_QUOTE_DATA_TMPL`(프라이빗). `build_prompt(..., directive=None)`, `draft_quote(..., directive=None)`. 규칙3의 경비 가이드는 조건 블록으로 이동. |
| `src/ai/minutes.py` | `_PROMPT_TMPL` → `MINUTES_DIRECTIVE_DEFAULT` + `_MINUTES_DATA_TMPL`. `build_minutes_prompt(description, directive=None)`, `_draft_gemini(..., directive)`, `draft_minutes(..., directive=None)`. |
| `src/ai/engine.py` | `DIRECTIVE_DEFAULTS = {"quote":…, "minutes":…}` 상수. 두 디스패처에 `directive=None` 추가, 전 경로(gemini 직접/openai·anthropic 공통) 통과. |
| `src/store/config_store.py` | `DEFAULT_CONFIG["ai_prompts"] = {"quote":"", "minutes":""}`. `AI_PROMPT_DOC_TYPES`, `get_ai_prompt(cfg, t)`, `set_ai_prompt(cfg, t, text)`. `_merge`가 구버전 config 자동 승급 → 마이그레이션 불필요. |
| `src/api.py` | `get_config()`에 `ai_prompts`(저장값) + `ai_prompt_defaults`(기본값) 노출. 새 메서드 `set_ai_prompt(doc_type, text)`(8000자 상한 `_AI_PROMPT_MAX`, 에코백 `{ok, doc_type, custom, text}`). `ai_draft`/`minutes_draft`에서 `directive=cs.get_ai_prompt(cfg, t) or None` 전달. |

### 프론트 (`ui/`)
| 파일 | 변경 |
|---|---|
| `index.html` | 견적서 탭(인건비 자동조정 카드 직후)·회의록 탭(작업 폴더 카드 직후)에 카드 추가. textarea id `s-ai-prompt-{quote,minutes}`, 버튼 `btn-save-ai-prompt-*`/`btn-reset-ai-prompt-*`, 상태 `ai-prompt-status-*`. |
| `app.js` | `renderSettings()`에 `renderAiPrompts()` 호출. 함수 3개: `renderAiPrompts`(override\|\|default 채움 + 상태 라벨), `saveAiPrompt(t)`, `resetAiPrompt(t)`. `init()` 설정 바인딩에 save/reset 핸들러(`AI_PROMPT_TYPES.forEach`). |
| `app.css` | `.settings-layout textarea` 스타일 **신규 추가**(이전엔 input/select만 있어 textarea가 브라우저 기본 테두리로 렌더됐음). |

### 문서·테스트
- `tests/test_ai_prompts.py` — 신규 23건 (디렉티브 주입·중괄호 안전·데이터 불변식·engine 통과·config 라운드트립·api 저장 규칙·ai_draft/minutes_draft 배선).
- `사용설명서.md` — 설정 탭 설명·AI 설정 절·테스트 건수(206) 갱신.

---

## 검증 방법 (재현)

```powershell
# 1. 전체 테스트 (hwp/node 마커 자동 제외)
py -3.12 -m pytest -q                       # → 206 passed, 4 deselected

# 2. 이 기능 집중
py -3.12 -m pytest tests/test_ai_prompts.py -q   # → 23 passed
```

**UI 정적 검증** (`.claude/launch.json`의 "ui" = `python -m http.server 8765 --directory ui`):
- pywebview 백엔드 없이도 `renderSettings`는 `state.config` null이면 조기 반환 → JS 에러 0.
- preview_eval로 가짜 `state.config`(`ai_prompts`/`ai_prompt_defaults` 포함) 주입 후 `switchView('settings')`
  → textarea 값·상태 라벨 확인. 저장/복원은 `window.pywebview.api.set_ai_prompt` 스텁으로 클릭 검증 가능.
- ⚠️ **이 환경에서 `preview_screenshot`은 30초 타임아웃**(렌더러 이슈). 검증은 eval/inspect/fill/click으로.

**라이브 스모크**(선택): `py -3.12 app.py` → 설정에서 저장/복원 → exe 옆 `config.json`의 `ai_prompts` 확인.
키 보유 시 AI 초안 1회 실행해 커스텀 지침이 실제 반영되는지 확인.

---

## 알려진 한계 / 다음에 할 수 있는 것

- **미리보기 없음**: 사용자가 편집한 지침 + 자동 데이터 블록이 합쳐진 "최종 프롬프트"를 미리 볼 수단이 없다.
  필요하면 카드에 "최종 프롬프트 미리보기" 버튼(샘플 과업으로 `build_prompt` 호출 결과 표시) 추가 가능.
- **OpenAI/Anthropic 경로**: directive는 `complete_json`의 prompt 맨 앞에 들어간다(검증됨). 단, OpenAI는
  system 메시지가 따로 있어("너는 오직 JSON만…") 사용자 지침과 약하게 경합할 수 있음 — 현재 문제는 없음.
- **새 문서 유형 추가 시**: `AI_PROMPT_DOC_TYPES`(config_store) + `DIRECTIVE_DEFAULTS`(engine) + UI 카드 +
  `AI_PROMPT_TYPES`(app.js) 4곳에 키를 더하면 자동 확장된다. (기존 `DOC_TYPES` 레지스트리 확장과 짝)
- **배포(.exe)**: 코드 변경만이라 `navion_quote.spec` 수정 불필요. 재빌드 시 MOTW는 `handoff_motw_fix.md` 참조.

---

## 참고 파일

- 핵심 로직: `src/ai/gemini.py`, `src/ai/minutes.py`, `src/ai/engine.py`
- 저장·노출: `src/store/config_store.py`, `src/api.py`
- UI: `ui/index.html`(설정 섹션), `ui/app.js`(`renderAiPrompts`/`saveAiPrompt`/`resetAiPrompt`)
- 테스트: `tests/test_ai_prompts.py`
- 커밋: `b1ccab8` (main)
