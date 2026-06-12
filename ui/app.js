/* ===== 내비온 견적서 생성기 — 프론트엔드 로직 ===== */
'use strict';

const GRADES = ['책임연구원', '연구원', '연구보조원', '보조원'];
const COMPANY_FIELDS = [
  ['name', '상호'], ['reg_no', '등록번호'], ['ceo', '대표자'], ['address', '주소'],
  ['biz_type', '업태'], ['biz_item', '종목'], ['manager', '담당자'],
  ['tel', '전화번호'], ['email', '이메일'], ['fax', '팩스번호'],
];

const state = {
  view: 'quote',                                    // 'quote' | 'minutes' | 'settings'
  sub: { quote: 'dashboard', minutes: 'dashboard' }, // 허브별 현재 서브탭
  config: null,
  folder: '',          // 견적서 작업 폴더 (doc_types.quote)
  minutesFolder: '',   // 회의록 작업 폴더 (doc_types.minutes)
  quotes: [],
  minutes: [],         // 회의록 대시보드 스캔 결과
  filter: 'all',
  search: '',
  mnSearch: '',        // 회의록 대시보드 검색어
  quote: null,        // 현재 편집 중 견적 (정규 payload 형태)
  lastDisplay: null,
};

/* ---------- 문서 유형 레지스트리 ----------
   새 문서 유형 추가 절차 (4곳):
   ① 여기 DOC_TYPES에 항목  ② index.html 사이드바 버튼 + #hub-<type> 섹션
   ③ src/store/config_store.py DEFAULT_CONFIG["doc_types"]에 키
   ④ 백엔드 scan/store 모듈 (scan_folder류 API)                       */
const DOC_TYPES = {
  quote: {
    label: '견적서', hub: 'hub-quote', defaultSub: 'dashboard',
    subs: {
      dashboard: { panel: 'view-dashboard', label: '대시보드', init: () => refreshDashboard() },
      editor:    { panel: 'view-editor',    label: '편집기',   init: () => ensureEditorQuote() },
    },
  },
  minutes: {
    label: '회의록', hub: 'hub-minutes', defaultSub: 'dashboard',
    subs: {
      dashboard: { panel: 'view-minutes-dashboard', label: '대시보드', init: () => refreshMinutesDashboard() },
      compose:   { panel: 'view-minutes',           label: '작성',     init: () => initMinutesComposeLazy() },
    },
  },
};
// 구 뷰 토큰 호환 — 투어·기존 switchView 호출부의 이중 안전망
const VIEW_ALIASES = { dashboard: ['quote', 'dashboard'], editor: ['quote', 'editor'] };

/* ---------- 유틸 ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const el = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
};
const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');
const onlyDigits = (s) => String(s == null ? '' : s).replace(/[^0-9.]/g, '');
const parseMoney = (s) => {
  const v = parseFloat(onlyDigits(s));
  return isNaN(v) ? null : v;
};
const commafy = (n) => {
  if (n == null || n === '' || isNaN(n)) return '';
  return Number(n).toLocaleString('en-US');
};

let _overlayCount = 0;
function overlay(on, msg) {
  if (on) { _overlayCount++; $('#overlay-msg').textContent = msg || '처리 중...'; $('#overlay').classList.remove('hidden'); }
  else { _overlayCount = Math.max(0, _overlayCount - 1); if (_overlayCount === 0) $('#overlay').classList.add('hidden'); }
}
function toast(msg, kind = 'info', ms = 3200) {
  const t = el('div', `toast ${kind}`, esc(msg));
  $('#toast-wrap').appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .3s'; setTimeout(() => t.remove(), 300); }, ms);
}

/* pywebview api 래퍼 — 항상 {ok,...} 반환, 예외도 흡수 */
async function call(method, ...args) {
  try {
    const api = window.pywebview && window.pywebview.api;
    if (!api || typeof api[method] !== 'function') {
      return { ok: false, error: `백엔드 메서드 없음: ${method}` };
    }
    const res = await api[method](...args);
    return res == null ? { ok: false, error: '빈 응답' } : res;
  } catch (e) {
    return { ok: false, error: String(e && e.message ? e.message : e) };
  }
}

/* ---------- 네비게이션 (허브 + 서브탭) ---------- */
function switchView(view, sub) {
  if (VIEW_ALIASES[view]) {
    const [v, s] = VIEW_ALIASES[view];
    sub = sub || s;
    view = v;
  }
  state.view = view;
  const dt = DOC_TYPES[view];
  if (dt) {
    sub = sub || state.sub[view] || dt.defaultSub;
    state.sub[view] = sub;
  }
  $$('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  const activeId = dt ? dt.hub : `view-${view}`;   // settings = view-settings
  $$('.view').forEach(v => v.classList.toggle('active', v.id === activeId));
  if (dt) {
    $$(`#${dt.hub} .sub-tab`).forEach(t => t.classList.toggle('active', t.dataset.sub === sub));
    $$(`#${dt.hub} .subview`).forEach(p => p.classList.toggle('active', p.id === dt.subs[sub].panel));
    dt.subs[sub].init();
  }
  if (view === 'settings') renderSettings();
}

/* 편집기 직행 시 견적이 없으면 새 견적 생성 (사이드바→편집기 크래시 방지) */
function ensureEditorQuote() {
  if (!state.quote) newQuote(false);
}

/* 회의록 작성: 최초 1회만 리셋 — 이후 탭 왕복 시 위저드 상태 보존(재편집 전제).
   명시적 리셋은 "＋ 새 회의록" 버튼이 담당. */
let _minutesComposeInited = false;
function initMinutesComposeLazy() {
  if (_minutesComposeInited) return;
  _minutesComposeInited = true;
  initMinutesView();
}

/* ===================================================================
   대시보드
=================================================================== */
async function refreshDashboard() {
  const r = await call('scan_folder', state.folder || null);
  if (!r.ok) { toast(r.error || '폴더 스캔 실패', 'err'); return; }
  state.folder = r.folder || '';
  state.quotes = r.quotes || [];
  $('#folder-path').textContent = state.folder || '폴더를 선택하세요';
  $('#folder-path').title = state.folder || '';
  renderStats(r.stats);
  renderGrid();
}

function renderStats(s) {
  s = s || {};
  $('#st-total').textContent = s.total ?? 0;
  $('#st-month').textContent = s.this_month ?? 0;
  $('#st-amount').textContent = s.sum_amount ?? '0';
  $('#st-editable').textContent = s.editable ?? 0;
}

function filteredQuotes() {
  let list = state.quotes;
  if (state.filter === 'editable') list = list.filter(q => q.editable);
  else if (state.filter === 'external') list = list.filter(q => !q.editable && q.source === 'hwp');
  const kw = state.search.trim().toLowerCase();
  if (kw) {
    list = list.filter(q =>
      (q.service_name || '').toLowerCase().includes(kw) ||
      (q.recipient || '').toLowerCase().includes(kw) ||
      (q.quote_no || '').toLowerCase().includes(kw));
  }
  return list;
}

function renderGrid() {
  const grid = $('#quote-grid');
  const list = filteredQuotes();
  grid.innerHTML = '';
  $('#empty-state').classList.toggle('hidden', list.length > 0);
  for (const q of list) grid.appendChild(quoteCard(q));
}

function quoteCard(q) {
  const c = el('div', 'qcard');
  let badge = '';
  if (q.editable) badge = `<span class="badge editable">재편집 가능</span>`;
  else if (q.source === 'hwp') badge = `<span class="badge external">외부 HWP</span>`;
  else badge = `<span class="badge json">임시저장</span>`;

  const amount = q.amount ? `${commafy(q.amount)}<span class="won">원</span>` : '<span class="pv-muted">금액 미확인</span>';
  c.innerHTML = `
    <div class="qcard-top">
      <div>
        <div class="qcard-no">${esc(q.quote_no || '견적번호 미상')}</div>
        <div class="qcard-title" title="${esc(q.service_name)}">${esc(q.service_name || '(용역명 없음)')}</div>
      </div>
      ${badge}
    </div>
    <div class="qcard-meta">
      <div class="qcard-row"><span class="k">수신처</span><span class="v" title="${esc(q.recipient)}">${esc(q.recipient || '-')}</span></div>
      <div class="qcard-row"><span class="k">견적일자</span><span class="v">${esc(q.date || '-')}</span></div>
      <div class="qcard-row"><span class="k">파일</span><span class="v" title="${esc(q.filename)}">${esc(q.filename)}</span></div>
    </div>
    <div class="qcard-amount">${amount}</div>
    <div class="qcard-actions"></div>`;

  const actions = $('.qcard-actions', c);
  if (q.source === 'hwp') {
    const open = el('button', 'btn btn-ghost', 'HWP 열기');
    open.onclick = () => call('open_file', q.path).then(r => { if (!r.ok) toast(r.error, 'err'); });
    actions.appendChild(open);
    const pdf = el('button', 'btn btn-ghost', 'PDF');
    pdf.onclick = () => call('open_sibling_pdf', q.path).then(r => { if (!r.ok) toast(r.error, 'warn'); });
    actions.appendChild(pdf);
  }
  if (q.editable) {
    const edit = el('button', 'btn btn-outline', '재편집');
    edit.onclick = () => loadAndEdit(q.json_path || q.path);
    actions.appendChild(edit);
  }
  const del = el('button', 'qcard-del', '×');
  del.title = '삭제';
  del.setAttribute('aria-label', '견적서 삭제');
  del.onclick = (ev) => { ev.stopPropagation(); openDeleteModal(q); };
  c.appendChild(del);
  return c;
}

async function loadAndEdit(jsonPath) {
  overlay(true, '불러오는 중...');
  const r = await call('load_quote', jsonPath);
  overlay(false);
  if (!r.ok) { toast(r.error || '불러오기 실패', 'err'); return; }
  openEditor(r.quote);
}

/* ===================================================================
   편집기
=================================================================== */
async function newQuote(viaAI) {
  const r = await call('new_quote');
  if (!r.ok) { toast(r.error || '생성 실패', 'err'); return; }
  openEditor(r.quote);
  if (viaAI) openAIModal();
}

function openEditor(quote) {
  // 정규화: 누락 필드 보강
  quote = quote || {};
  quote.doc = quote.doc || {};
  quote.options = quote.options || { profit: true };
  quote.goal = quote.goal || { mode: 'uniform' };
  quote.labor = (quote.labor && quote.labor.length) ? quote.labor : defaultLabor();
  // 경비 정규화: details는 항상 배열 (손상/구버전 JSON 방어)
  quote.expenses = (quote.expenses || []).map(e => ({
    ...e,
    details: Array.isArray(e.details) ? e.details
      : (typeof e.details === 'string' ? e.details.split('\n').map(s => s.trim()).filter(Boolean) : []),
  }));
  quote.trim = quote.trim || 0;
  state.quote = quote;

  // 문서 정보 채우기
  const d = quote.doc;
  $('#f-recipient').value = d.recipient || '';
  $('#f-quote-no').value = d.quote_no || '';
  $('#f-date').value = d.date || new Date().toISOString().slice(0, 10);
  $('#f-period').value = d.service_period || '';
  $('#f-svc-name').value = d.service_name || '';
  $('#f-ref-name').value = d.ref_name || '';
  $('#f-ref-tel').value = d.ref_tel || '';
  $('#editor-title').textContent = d.service_name || '새 견적서';

  // 이윤 토글
  setProfitSeg(quote.options.profit !== false);
  // 목표/모드
  $('#f-target').value = quote.goal.target ? commafy(quote.goal.target) : '';
  $('#f-gs-mode').value = quote.goal.mode || 'labor_first';
  $('#gs-result').classList.add('hidden');

  const year = (quote.options && quote.options.price_year) || (state.config && state.config.default_price_year) || '2026';
  $('#price-year-label').textContent = `${year}년 학술용역단가 기준`;

  renderLaborRows();
  renderExpenseRows();
  switchView('editor');
  refreshCalc();
}

function defaultLabor() {
  const prices = (state.config && state.config.unit_prices && state.config.unit_prices[state.config.default_price_year]) || {};
  return GRADES.map(g => ({ grade: g, unit_price: prices[g] || 0, count: 0, rate: 0, months: 0, locked: false }));
}

function setProfitSeg(on) {
  $$('#profit-seg button').forEach(b => b.classList.toggle('active', (b.dataset.v === '1') === on));
}
function profitOn() { return $('#profit-seg button.active').dataset.v === '1'; }

/* 인건비 행 렌더 (rate는 % 표기) */
function renderLaborRows() {
  const tb = $('#labor-table tbody');
  tb.innerHTML = '';
  state.quote.labor.forEach((row, i) => {
    const tr = el('tr');
    if (row.locked) tr.classList.add('row-locked');
    tr.innerHTML = `
      <td><input class="grade-name" data-i="${i}" data-k="grade" value="${esc(row.grade)}"></td>
      <td><input data-i="${i}" data-k="count" value="${row.count || ''}" placeholder="0"></td>
      <td><input data-i="${i}" data-k="unit_price" value="${commafy(row.unit_price)}"></td>
      <td><input data-i="${i}" data-k="rate" value="${row.rate ? +(row.rate * 100).toFixed(4) : ''}" placeholder="0"></td>
      <td><input data-i="${i}" data-k="months" value="${row.months || ''}" placeholder="0"></td>
      <td class="cell-amt" data-amt="${i}">-</td>
      <td class="cell-lock"><input type="checkbox" class="lock-chk" data-i="${i}" data-k="locked" ${row.locked ? 'checked' : ''} title="자동조정 제외(값 고정)"></td>`;
    tb.appendChild(tr);
  });
  $$('#labor-table input').forEach(inp => {
    inp.addEventListener(inp.type === 'checkbox' ? 'change' : 'input', onLaborInput);
    if (inp.dataset.k === 'unit_price') inp.addEventListener('blur', e => { e.target.value = commafy(parseMoney(e.target.value)); });
  });
}

function onLaborInput(e) {
  const i = +e.target.dataset.i, k = e.target.dataset.k;
  const row = state.quote.labor[i];
  if (k === 'grade') row.grade = e.target.value;
  else if (k === 'locked') {
    row.locked = e.target.checked;
    e.target.closest('tr').classList.toggle('row-locked', row.locked);
    return;
  }
  else if (k === 'unit_price') row.unit_price = parseMoney(e.target.value) || 0;
  else if (k === 'rate') row.rate = (parseFloat(onlyDigits(e.target.value)) || 0) / 100;
  else row[k] = parseFloat(onlyDigits(e.target.value)) || 0;
  refreshCalc();
}

/* 수량 표기에서 숫자 자동 추출: "5명"→5, "1식"→1, "-"→null */
function parseLeadingNum(s) {
  const m = String(s == null ? '' : s).match(/[\d,]+(\.\d+)?/);
  if (!m) return null;
  const v = parseFloat(m[0].replace(/,/g, ''));
  return isNaN(v) ? null : v;
}

/* 경비 표 렌더 (엑셀형: 구분 | 내역 | 수량 | 단가 | 금액 | 삭제) */
function renderExpenseRows() {
  const wrap = $('#exp-list');
  if (!state.quote.expenses.length) {
    wrap.innerHTML = `<div class="exp-empty">경비 항목이 없습니다. ＋ 항목 추가를 눌러 입력하세요.</div>`;
    return;
  }
  const rows = state.quote.expenses.map((e, i) => `
    <tr>
      <td><input class="x-name" data-i="${i}" data-k="name" value="${esc(e.name)}" placeholder="전문가 활용비"></td>
      <td><textarea class="x-detail" data-i="${i}" data-k="details" rows="2" placeholder="- 시장참여자 검증/자문&#10;- 인허가 계획 자문">${esc((Array.isArray(e.details) ? e.details : []).join('\n'))}</textarea></td>
      <td><input class="x-qty" data-i="${i}" data-k="qty_text" value="${esc(e.qty_text)}" placeholder="5명/1식/-"></td>
      <td><input data-i="${i}" data-k="unit_price" value="${commafy(e.unit_price)}" placeholder="0"></td>
      <td class="x-amt" data-expamt="${i}">-</td>
      <td class="x-del"><button class="x-del-btn" data-del="${i}" title="이 경비 삭제" aria-label="경비 삭제">×</button></td>
    </tr>`).join('');
  wrap.innerHTML = `
    <table class="exp-table">
      <colgroup><col style="width:17%"><col><col style="width:11%"><col style="width:16%"><col style="width:15%"><col style="width:40px"></colgroup>
      <thead><tr><th>구분</th><th>내역 (한 줄에 하나씩, '- ' 시작)</th><th class="c">수량</th><th class="r">단가(원)</th><th class="r">금액(원)</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  $$('#exp-list input, #exp-list textarea').forEach(inp => inp.addEventListener('input', onExpenseInput));
  $$('#exp-list input[data-k="unit_price"]').forEach(inp =>
    inp.addEventListener('blur', ev => { ev.target.value = commafy(parseMoney(ev.target.value)); }));
  $$('#exp-list [data-del]').forEach(b =>
    b.addEventListener('click', () => { state.quote.expenses.splice(+b.dataset.del, 1); renderExpenseRows(); refreshCalc(); }));
}

function onExpenseInput(e) {
  const i = +e.target.dataset.i, k = e.target.dataset.k;
  const row = state.quote.expenses[i];
  if (k === 'name') row.name = e.target.value;
  else if (k === 'qty_text') { row.qty_text = e.target.value; row.qty = parseLeadingNum(e.target.value); }
  else if (k === 'unit_price') row.unit_price = parseMoney(e.target.value);
  else if (k === 'details') row.details = e.target.value.split('\n').map(s => s.trim()).filter(Boolean);
  refreshCalc();
}

/* 폼 → payload 동기화 */
function syncDocFromForm() {
  const d = state.quote.doc;
  d.recipient = $('#f-recipient').value.trim();
  d.quote_no = $('#f-quote-no').value.trim();
  d.date = $('#f-date').value;
  d.service_period = $('#f-period').value.trim();
  d.service_name = $('#f-svc-name').value.trim();
  d.ref_name = $('#f-ref-name').value.trim();
  d.ref_tel = $('#f-ref-tel').value.trim();
  state.quote.options.profit = profitOn();
  state.quote.goal = state.quote.goal || {};
  state.quote.goal.target = parseMoney($('#f-target').value);
  state.quote.goal.mode = $('#f-gs-mode').value;
  $('#editor-title').textContent = d.service_name || '새 견적서';
}

function payload() {
  syncDocFromForm();
  return JSON.parse(JSON.stringify(state.quote));
}

/* 실시간 계산 (디바운스) */
let _calcTimer = null;
function refreshCalc() {
  clearTimeout(_calcTimer);
  _calcTimer = setTimeout(doCalc, 180);
}
async function doCalc() {
  const p = payload();
  const r = await call('calc', p);
  if (!r.ok) { return; }
  state.lastDisplay = r.display;
  paintAmounts(r.display);
  paintGuide(r.guide);
  paintPreview(r.display);
}

function paintAmounts(disp) {
  if (!disp || !disp.labor || !disp.expenses) return;
  disp.labor.forEach((l, i) => { const c = $(`[data-amt="${i}"]`); if (c && l) c.textContent = l.amt || '-'; });
  state.quote.expenses.forEach((e, i) => { const c = $(`[data-expamt="${i}"]`); if (c) c.textContent = (disp.expenses[i] && disp.expenses[i].amt) ? disp.expenses[i].amt : '-'; });
  $('#preview-final').textContent = disp.final ? `${disp.final.won}원` : '-';
}

function paintGuide(guide) {
  const body = $('#guide-body');
  if (!guide) { body.className = 'guide-body dim'; body.textContent = '목표금액을 입력하면 인건비·경비 적정 범위가 표시됩니다.'; return; }
  body.className = 'guide-body';
  const gapCls = (raw) => raw == null ? '' : (Math.abs(raw) < 1 ? 'gap-ok' : (raw > 0 ? 'gap-over' : 'gap-under'));
  const gapTxt = (raw, txt) => raw == null ? '' : (Math.abs(raw) < 1 ? '일치' : (raw > 0 ? `+${txt} 초과` : `-${txt} 부족`));
  body.innerHTML = `
    <div class="guide-line"><span class="gk">목표 견적금액</span><span class="gv">${guide.budget}원</span></div>
    <div class="guide-line"><span class="gk">→ 적정 인건비</span><span class="gv">${guide.labor_target}원</span></div>
    <div class="guide-line"><span class="gk">→ 적정 경비</span><span class="gv">${guide.expense_target}원</span></div>
    <div class="guide-line"><span class="gk">현재 인건비 차이</span><span class="gv ${gapCls(guide.labor_gap_raw)}">${gapTxt(guide.labor_gap_raw, guide.labor_gap)}</span></div>
    <div class="guide-line"><span class="gk">현재 경비 차이</span><span class="gv ${gapCls(guide.exp_gap_raw)}">${gapTxt(guide.exp_gap_raw, guide.exp_gap)}</span></div>
    <div class="guide-line"><span class="gk">현재 견적금액 차이</span><span class="gv ${gapCls(guide.final_gap_raw)}">${gapTxt(guide.final_gap_raw, guide.final_gap)}</span></div>`;
}

function paintPreview(d) {
  const rows = [];
  rows.push(`<tr class="pv-sec"><td class="l" colspan="2">인건비</td><td>금액</td><td>구성비</td></tr>`);
  d.labor.filter(l => l.active).forEach(l => {
    rows.push(`<tr><td class="l">${esc(l.grade)}</td><td class="pv-muted">${esc(l.cnt)}·${esc(l.rate)}·${esc(l.months)}</td><td class="num">${l.amt}</td><td>${l.pct}</td></tr>`);
  });
  rows.push(`<tr class="pv-sum"><td class="l" colspan="2">인건비 계</td><td class="num">${d.labor_sum.won}</td><td>${d.labor_sum.pct}</td></tr>`);
  rows.push(`<tr class="pv-sec"><td class="l" colspan="2">경비</td><td></td><td></td></tr>`);
  d.expenses.filter(e => e.active).forEach(e => {
    rows.push(`<tr><td class="l">${esc(e.name)}</td><td class="pv-muted">${esc(e.qty_text)}</td><td class="num">${e.amt}</td><td>${e.pct}</td></tr>`);
  });
  rows.push(`<tr class="pv-sum"><td class="l" colspan="2">경비 계</td><td class="num">${d.exp_sum.won}</td><td>${d.exp_sum.pct}</td></tr>`);
  rows.push(`<tr class="pv-sum"><td class="l" colspan="2">소계(인건비+경비)</td><td class="num">${d.subtotal.won}</td><td>${d.subtotal.pct}</td></tr>`);
  rows.push(`<tr><td class="l" colspan="2">일반관리비 (5%)</td><td class="num">${d.mgmt.won}</td><td>${d.mgmt.pct}</td></tr>`);
  rows.push(`<tr><td class="l" colspan="2">이윤 ${d.profit_on ? '(10%)' : '(미계상)'}</td><td class="num">${d.profit.won}</td><td>${d.profit.pct}</td></tr>`);
  rows.push(`<tr class="pv-sum"><td class="l" colspan="2">총계(공급가액)</td><td class="num">${d.supply.won}</td><td>${d.supply.pct}</td></tr>`);
  rows.push(`<tr><td class="l" colspan="2">부가세 (10%)</td><td class="num">${d.vat.won}</td><td>${d.vat.pct}</td></tr>`);
  if (d.trim && d.trim.raw > 0.5) {
    rows.push(`<tr><td class="l" colspan="2">절삭</td><td class="num">-${d.trim.won}</td><td>-${d.trim.pct}</td></tr>`);
  }
  rows.push(`<tr class="pv-final"><td class="l" colspan="2">최종견적</td><td class="num">${d.final.won}</td><td>${d.final.pct}</td></tr>`);
  $('#preview-body').innerHTML = `<table class="pv-table">${rows.join('')}</table>
    <div class="hint" style="padding:8px 7px 0">${esc(d.amount_kor)}</div>`;
}

/* goal-seek */
async function runGoalSeek() {
  const p = payload();
  if (!p.goal || !p.goal.target) { toast('목표 금액을 입력하세요.', 'warn'); return; }
  const laborFirst = (p.goal.mode === 'labor_first');
  overlay(true, laborFirst ? '인건비 자동조정 중...' : '참여율 역산 중...');
  const r = await call('goal_seek', p);
  overlay(false);
  const box = $('#gs-result');
  box.classList.remove('hidden');
  if (!r.ok) {
    box.className = 'gs-result err';
    box.innerHTML = `⚠ ${esc(r.error)}` + ((r.warnings || []).map(w => `<br>· ${esc(w)}`).join(''));
    return;
  }
  // 결과 적용 (rate는 소수 → 입력은 %). 인건비 자동조정 모드는 명수도 변경.
  r.rates.forEach((rate, i) => { if (state.quote.labor[i]) state.quote.labor[i].rate = rate; });
  if (r.counts) r.counts.forEach((c, i) => { if (state.quote.labor[i]) state.quote.labor[i].count = c; });
  state.quote.trim = r.trim;
  renderLaborRows();
  const warnHtml = (r.warnings || []).map(w => `<br>· ${esc(w)}`).join('');
  box.className = r.warnings && r.warnings.length ? 'gs-result warn' : 'gs-result';
  const rateTxt = r.rates.map((rt, i) => state.quote.labor[i].count > 0
    ? `${state.quote.labor[i].grade} ${state.quote.labor[i].count}명·${+(rt * 100).toFixed(2)}%` : null).filter(Boolean).join(', ');
  box.innerHTML = `✓ ${laborFirst ? '인건비 자동조정' : '참여율 역산'} 완료 — ${esc(rateTxt)}${r.trim ? ` · 만원미만 절삭 ${commafy(r.trim)}원` : ''}${warnHtml}`;
  refreshCalc();
}

/* 저장 / 생성 */
async function saveQuote() {
  const p = payload();
  if (!state.folder) { toast('먼저 대시보드에서 작업 폴더를 선택하세요.', 'warn'); return; }
  if (!p.doc.service_name) { toast('용역명을 입력하세요.', 'warn'); return; }
  overlay(true, '저장 중...');
  const r = await call('save_quote', p);
  overlay(false);
  if (r.ok) toast('임시 저장 완료', 'ok'); else toast(r.error || '저장 실패', 'err');
}

async function generate(makePdf) {
  const p = payload();
  if (!state.folder) { toast('먼저 대시보드에서 작업 폴더를 선택하세요.', 'warn'); return; }
  if (!p.doc.service_name) { toast('용역명을 입력하세요.', 'warn'); switchInput('#f-svc-name'); return; }
  if (!p.labor.some(l => (l.count || 0) > 0)) { toast('최소 1개 직급에 인원을 입력하세요.', 'warn'); return; }
  overlay(true, makePdf ? '한글에서 HWP·PDF 생성 중... (최초 실행은 한글 구동에 시간이 걸립니다)' : 'HWP 생성 중...');
  const r = await call('generate', p, !!makePdf);
  overlay(false);
  if (!r.ok) { toast(r.error || '생성 실패', 'err', 6000); return; }
  (r.warnings || []).forEach(w => toast(w, 'warn', 5000));
  if (r.pdf_error) toast(r.pdf_error, 'warn', 5000);
  if (r.drive) {
    if (r.drive.ok) toast(`Google Drive 업로드 완료 (${(r.drive.links || []).length}개 파일)`, 'ok', 4000);
    else toast('Drive 업로드 실패: ' + (r.drive.error || ''), 'warn', 5000);
  }
  toast(`생성 완료 (${r.final}원). 파일을 엽니다.`, 'ok', 4000);
  call('open_file', r.pdf || r.hwp);
}

function switchInput(sel) { const e = $(sel); if (e) e.focus(); }

/* ===================================================================
   AI 모달
=================================================================== */
let aiState = null;        // { desc, target, profit, draft, rationale, warnings }
let _aiCalcTimer = null;
let aiAttachments = [];    // [{ name, markdown, chars }]
let _convertStatusReady = false;   // true = node+kordoc 모두 사용 가능

/* ===== 변환 엔진 상태 + 드롭존 ===== */
async function refreshConvertStatus() {
  const r = await call('convert_status');
  _convertStatusReady = !!(r && r.ready);
  const dz = $('#ai-dropzone');
  const banner = $('#ai-node-banner');
  if (!dz) return;
  if (r && r.state === 'node_missing') {
    dz.classList.add('dz-disabled');
    if (banner) banner.classList.remove('hidden');
  } else {
    dz.classList.remove('dz-disabled');
    if (banner) banner.classList.add('hidden');
  }
}

/* JS-side dragover/enter/leave/drop handlers (M4 배선).
   dragover preventDefault 없이는 drop 이벤트가 발생하지 않는다. */
function wireDropzoneJS() {
  const dz = $('#ai-dropzone');
  if (!dz) return;

  // 전역 drop 차단 — 드롭존 밖 드롭이 브라우저 파일 열기로 넘어가는 것 방지
  document.addEventListener('dragover', e => e.preventDefault());
  document.addEventListener('drop', e => e.preventDefault());

  dz.addEventListener('dragenter', e => {
    e.preventDefault();
    if (!dz.classList.contains('dz-disabled')) dz.classList.add('drag-over');
  });
  dz.addEventListener('dragover', e => {
    e.preventDefault();
    if (!dz.classList.contains('dz-disabled')) dz.classList.add('drag-over');
  });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
  dz.addEventListener('drop', e => {
    e.preventDefault();
    dz.classList.remove('drag-over');
    // 순수 JS 드롭(브라우저 내): 파일 경로는 얻을 수 없으므로
    // 이름만 수집 후 파일선택 안내. 실제 경로는 pywebview 핸들러가 통지.
    const files = Array.from(e.dataTransfer?.files || []);
    if (files.length) {
      // pywebview DnD라면 onNativeFilesDropped가 이미 불렸을 것.
      // 여기선 이름만으로 칩 표시 → 경로 없으면 사용자에게 안내
      toast('파일 경로를 확인할 수 없습니다. [파일 선택…] 버튼을 이용해 주세요.', 'warn', 4000);
    }
  });
}

/* Python → JS 드롭 통지 (api.py _on_drop → evaluate_js) */
window.onNativeFilesDropped = function(data) {
  if (data.unmatched && data.unmatched.length) {
    toast(`경로를 가져오지 못한 파일: ${data.unmatched.join(', ')}. [파일 선택…] 버튼을 이용하세요.`, 'warn', 5000);
  }
  if (!data.paths || !data.paths.length) return;
  if (data.zone === 'minutes') handleMinutesDroppedPaths(data.paths);
  else handleDroppedPaths(data.paths);
};

/* 설치/변환 진행 overlay 업데이트 */
window.__convertProgress = function(info) {
  if (info.phase === 'install') {
    overlay(true, `kordoc 설치 중... (${info.msg || ''})`);
  } else if (info.phase === 'convert') {
    overlay(true, `변환 중 (${info.i}/${info.total}) — ${info.name || ''}`);
  } else if (info.phase === 'done') {
    overlay(false);
  }
};

async function handleDroppedPaths(paths) {
  if (!paths || !paths.length) return;
  overlay(true, '변환 준비 중...');
  await convertPaths(paths);
  overlay(false);
}

async function convertPaths(paths) {
  const r = await call('convert_files', paths);
  overlay(false);
  if (!r.ok) {
    const code = r.error_code || '';
    if (code === 'node_missing') {
      toast('Node.js가 설치되지 않아 변환할 수 없습니다.', 'err', 5000);
    } else {
      toast(r.error || '변환 실패', 'err', 5000);
    }
    return;
  }
  if (r.installed_now) toast('변환 도구 준비 완료. HWP·PDF·DOCX 변환을 사용할 수 있습니다.', 'ok', 4000);
  for (const res of r.results || []) {
    if (res.ok) {
      const existing = aiAttachments.findIndex(a => a.name === res.name);
      if (existing >= 0) aiAttachments[existing] = { name: res.name, markdown: res.markdown, chars: res.chars };
      else aiAttachments.push({ name: res.name, markdown: res.markdown, chars: res.chars });
    } else {
      toast(`변환 실패: ${res.name} — ${res.error || res.error_code || ''}`, 'err', 5000);
    }
  }
  renderAIChips();
}

function renderAIChips() {
  const wrap = $('#ai-chips');
  const preview = $('#ai-md-preview');
  if (!wrap) return;
  if (!aiAttachments.length) {
    wrap.classList.add('hidden');
    wrap.innerHTML = '';
    if (preview) { preview.classList.add('hidden'); preview.textContent = ''; }
    return;
  }
  wrap.classList.remove('hidden');
  wrap.innerHTML = aiAttachments.map((a, i) => `
    <span class="ai-chip chip-ok" data-idx="${i}">
      <span class="chip-name" title="${esc(a.name)}">📄 ${esc(a.name)}</span>
      <span class="chip-sub">${(a.chars || 0).toLocaleString()}자</span>
      <button class="chip-preview-btn" data-idx="${i}" type="button" title="미리보기">👁</button>
      <button class="chip-rm" data-idx="${i}" type="button" title="제거">✕</button>
    </span>`).join('');

  wrap.querySelectorAll('.chip-rm').forEach(btn => {
    btn.addEventListener('click', e => {
      const idx = +e.currentTarget.dataset.idx;
      aiAttachments.splice(idx, 1);
      renderAIChips();
    });
  });
  wrap.querySelectorAll('.chip-preview-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      const idx = +e.currentTarget.dataset.idx;
      const a = aiAttachments[idx];
      if (!preview || !a) return;
      if (preview.dataset.idx === String(idx) && !preview.classList.contains('hidden')) {
        preview.classList.add('hidden');
        preview.dataset.idx = '';
      } else {
        preview.textContent = a.markdown.slice(0, 2000) + (a.markdown.length > 2000 ? '\n...' : '');
        preview.dataset.idx = String(idx);
        preview.classList.remove('hidden');
      }
    });
  });
}

function openAIModal() {
  const prov = (state.config && state.config.ai_provider) || 'gemini';
  const keySet = state.config && (state.config.ai_keys_set || {})[prov];
  if (!state.config || !keySet) {
    toast('AI 기능은 설정에서 API 키를 먼저 등록해야 합니다.', 'warn', 4500);
    switchView('settings');
    setTimeout(() => $('#s-ai-key').focus(), 200);
    return;
  }
  $('#ai-desc').value = (aiState && aiState.desc)
    || (state.quote && state.quote.doc && state.quote.doc.service_name) || '';
  $('#ai-target').value = (state.quote && state.quote.goal && state.quote.goal.target) ? commafy(state.quote.goal.target) : '';
  $('#ai-profit').checked = state.quote ? state.quote.options.profit !== false : true;
  // 첨부 상태 초기화 (재열기 시 이전 첨부 유지는 불필요)
  aiAttachments = [];
  renderAIChips();
  setAIStatus('');
  showAIStep(1);
  $('#ai-modal').classList.remove('hidden');
  refreshConvertStatus();
}
function closeAIModal() { clearTimeout(_aiCalcTimer); $('#ai-modal').classList.add('hidden'); }

function showAIStep(n) {
  $('#ai-step1').classList.toggle('hidden', n !== 1);
  $('#ai-step2').classList.toggle('hidden', n !== 2);
  $('#ai-modal-card').classList.toggle('modal-wide', n === 2);
}

/* 상태/에러 박스 (눈에 띄게 표출). modelError면 [설정 열기] 링크 노출 */
function setAIStatus(msg, kind, modelError) {
  const box = $('#ai-status');
  if (!msg) { box.className = 'ai-status'; box.innerHTML = ''; return; }
  box.className = 'ai-status show' + (kind ? ' ' + kind : '');
  let html = esc(msg);
  if (modelError) html += '<div class="ai-status-link"><button type="button" id="ai-goto-settings">설정 열기 →</button></div>';
  box.innerHTML = html;
  const go = $('#ai-goto-settings');
  if (go) go.addEventListener('click', () => { closeAIModal(); switchView('settings'); });
}

/* 백엔드 초안 구조 방어 정규화 */
function normalizeAIDraft(q) {
  q = q || {};
  q.doc = q.doc || {};
  q.options = q.options || { profit: true };
  q.goal = q.goal || { mode: 'ratio' };
  q.labor = (q.labor && q.labor.length) ? q.labor : [];
  q.expenses = (q.expenses || []).map(e => ({
    name: e.name || '',
    details: Array.isArray(e.details) ? e.details
      : (typeof e.details === 'string' ? e.details.split('\n').map(s => s.trim()).filter(Boolean) : []),
    qty_text: e.qty_text || '', unit_price: e.unit_price, qty: e.qty,
  }));
  q.trim = q.trim || 0;
  return q;
}

async function runAI() {
  const desc = $('#ai-desc').value.trim();
  const target = parseMoney($('#ai-target').value);
  const profit = $('#ai-profit').checked;
  if (desc.length < 10 && !aiAttachments.length) {
    setAIStatus('용역 설명을 10자 이상 입력하거나 과업지시서 파일을 첨부하세요.', 'warn'); return;
  }
  if (!target) { setAIStatus('목표 금액을 입력하세요.', 'warn'); return; }
  setAIStatus('');
  overlay(true, 'AI가 견적 구성을 제안하는 중...');
  const r = await call('ai_draft', {
    description: desc, target, profit,
    attachments: aiAttachments.map(a => ({ name: a.name, markdown: a.markdown })),
  });
  overlay(false);
  if (!r.ok) { setAIStatus(r.error || 'AI 호출 실패', 'err', !!r.model_error); return; }
  aiState = { desc, target, profit, draft: normalizeAIDraft(r.quote),
              rationale: r.rationale || '', warnings: r.warnings || [], _seq: 0 };
  renderAIReview();
  showAIStep(2);
}

/* 다시 생성: 1단계로 (입력 보존) */
function aiBack() { setAIStatus(''); showAIStep(1); }

function renderAIReview() {
  const d = aiState.draft;
  const dd = d.doc || {};
  const qd = (state.quote && state.quote.doc) || {};
  $('#ai-svc-name').value = dd.service_name || qd.service_name || '';
  $('#ai-period').value = dd.service_period || '';
  // 문서정보: AI 제안값 → 없으면 기존 견적값 → 일자는 기본 오늘
  $('#ai-recipient').value = dd.recipient || qd.recipient || '';
  $('#ai-quote-no').value = dd.quote_no || qd.quote_no || '';
  $('#ai-date').value = dd.date || qd.date || new Date().toISOString().slice(0, 10);
  $('#ai-ref-name').value = dd.ref_name || qd.ref_name || '';
  $('#ai-ref-tel').value = dd.ref_tel || qd.ref_tel || '';
  const note = $('#ai-rationale');
  const parts = [];
  if (aiState.rationale) parts.push('<b>구성 근거</b> · ' + esc(aiState.rationale));
  (aiState.warnings || []).forEach(w => parts.push('⚠ ' + esc(w)));
  if (parts.length) { note.innerHTML = parts.join('<br>'); note.classList.remove('hidden'); }
  else { note.innerHTML = ''; note.classList.add('hidden'); }
  renderAILabor();
  renderAIExp();
  aiRecalc();
}

/* 인건비 검토표 (명수·참여율·개월 수정 가능, 단가 읽기전용) */
function renderAILabor() {
  const tb = $('#ai-labor tbody');
  tb.innerHTML = aiState.draft.labor.map((row, i) => `
    <tr>
      <td class="l ai-grade">${esc(row.grade)}</td>
      <td><input data-i="${i}" data-k="count" value="${row.count || ''}" placeholder="0"></td>
      <td class="ro">${commafy(row.unit_price)}</td>
      <td><input data-i="${i}" data-k="rate" value="${row.rate ? +(row.rate * 100).toFixed(4) : ''}" placeholder="0"></td>
      <td><input data-i="${i}" data-k="months" value="${row.months || ''}" placeholder="0"></td>
      <td class="amt" data-ailaboramt="${i}">-</td>
    </tr>`).join('');
  $$('#ai-labor input').forEach(inp => inp.addEventListener('input', onAILaborInput));
}
function onAILaborInput(e) {
  const i = +e.target.dataset.i, k = e.target.dataset.k;
  const row = aiState.draft.labor[i];
  if (!row) return;
  if (k === 'rate') row.rate = (parseFloat(onlyDigits(e.target.value)) || 0) / 100;
  else row[k] = parseFloat(onlyDigits(e.target.value)) || 0;
  aiRecalc();
}

/* 경비 검토표 (.exp-table 재사용) */
function renderAIExp() {
  const wrap = $('#ai-exp');
  const exps = aiState.draft.expenses;
  if (!exps.length) {
    wrap.innerHTML = `<div class="exp-empty">경비 항목이 없습니다. ＋ 항목 추가를 눌러 입력하세요.</div>`;
    return;
  }
  const rows = exps.map((e, i) => `
    <tr>
      <td><input class="x-name" data-i="${i}" data-k="name" value="${esc(e.name)}" placeholder="전문가 활용비"></td>
      <td><textarea class="x-detail" data-i="${i}" data-k="details" rows="2" placeholder="- 시장참여자 검증/자문">${esc((Array.isArray(e.details) ? e.details : []).join('\n'))}</textarea></td>
      <td><input class="x-qty" data-i="${i}" data-k="qty_text" value="${esc(e.qty_text)}" placeholder="5명/1식/-"></td>
      <td><input data-i="${i}" data-k="unit_price" value="${commafy(e.unit_price)}" placeholder="0"></td>
      <td class="x-amt" data-aiexpamt="${i}">-</td>
      <td class="x-del"><button class="x-del-btn" data-aidel="${i}" type="button" title="이 경비 삭제" aria-label="경비 삭제">×</button></td>
    </tr>`).join('');
  wrap.innerHTML = `
    <table class="exp-table">
      <colgroup><col style="width:17%"><col><col style="width:11%"><col style="width:16%"><col style="width:15%"><col style="width:40px"></colgroup>
      <thead><tr><th>구분</th><th>내역 (한 줄에 하나씩, '- ' 시작)</th><th class="c">수량</th><th class="r">단가(원)</th><th class="r">금액(원)</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  $$('#ai-exp input, #ai-exp textarea').forEach(inp => inp.addEventListener('input', onAIExpInput));
  $$('#ai-exp input[data-k="unit_price"]').forEach(inp =>
    inp.addEventListener('blur', ev => { ev.target.value = commafy(parseMoney(ev.target.value)); }));
  $$('#ai-exp [data-aidel]').forEach(b =>
    b.addEventListener('click', () => { aiState.draft.expenses.splice(+b.dataset.aidel, 1); renderAIExp(); aiRecalc(); }));
}
function onAIExpInput(e) {
  const i = +e.target.dataset.i, k = e.target.dataset.k;
  const row = aiState.draft.expenses[i];
  if (!row) return;
  if (k === 'name') row.name = e.target.value;
  else if (k === 'qty_text') { row.qty_text = e.target.value; row.qty = parseLeadingNum(e.target.value); }
  else if (k === 'unit_price') row.unit_price = parseMoney(e.target.value);
  else if (k === 'details') row.details = e.target.value.split('\n').map(s => s.trim()).filter(Boolean);
  aiRecalc();
}

/* 합계 미리보기 — 모든 금액은 Python calc 엔진으로 (JS 산수 금지) */
function aiRecalc() { clearTimeout(_aiCalcTimer); _aiCalcTimer = setTimeout(doAIRecalc, 200); }
function aiPayload(trim) {
  const d = aiState.draft;
  return {
    doc: d.doc || {},
    options: { profit: !!(d.options && d.options.profit !== false),
               price_year: d.options && d.options.price_year },
    labor: d.labor, expenses: d.expenses,
    goal: { target: aiState.target, mode: (d.goal && d.goal.mode) || 'ratio',
          },
    trim: trim != null ? trim : (d.trim || 0),
  };
}
async function doAIRecalc() {
  if (!aiState) return;
  const seq = ++aiState._seq;
  const r = await call('calc', aiPayload());
  if (!aiState || seq !== aiState._seq) return;          // 늦게 온 stale 응답 폐기
  if (!r.ok || !r.display) {                              // 계산 실패 → stale 값 제거 + 경고 표출
    $$('#ai-labor [data-ailaboramt], #ai-exp [data-aiexpamt]').forEach(c => c.textContent = '-');
    $('#ai-sum').innerHTML = `<div class="si"><span class="v gap-over">${esc(r.error || '합계 계산 실패 — 입력값을 확인하세요')}</span></div>`;
    return;
  }
  (r.display.labor || []).forEach((l, i) => { const c = $(`[data-ailaboramt="${i}"]`); if (c) c.textContent = l.amt; });
  (r.display.expenses || []).forEach((e, i) => { const c = $(`[data-aiexpamt="${i}"]`); if (c) c.textContent = e.amt; });
  renderAISummary(r.display, r.guide);
}
function renderAISummary(disp, guide) {
  const box = $('#ai-sum');
  let gapHtml = '', reseek = '';
  if (guide) {
    const gr = guide.final_gap_raw;                       // 계산 견적금액 − 목표 (백엔드 산출)
    const cls = Math.abs(gr) < 1 ? 'gap-ok' : (gr > 0 ? 'gap-over' : 'gap-under');
    const label = Math.abs(gr) < 1 ? '일치' : (gr > 0 ? '초과' : '부족');
    const sign = gr > 0 ? '+' : (gr < 0 ? '−' : '');
    gapHtml = `<div class="si"><span class="k">차액</span><span class="v ${cls}">${sign}${guide.final_gap}원 (${label})</span></div>`;
    if (Math.abs(gr) >= 1) reseek = `<button class="btn btn-mini ai-reseek" id="ai-reseek" type="button">⚖ 목표금액 재역산</button>`;
  }
  box.innerHTML = `
    <div class="si"><span class="k">목표금액</span><span class="v">${commafy(aiState.target)}원</span></div>
    <div class="si"><span class="k">계산 견적금액</span><span class="v">${disp.final.won}원</span></div>
    ${gapHtml}${reseek}`;
  const rs = $('#ai-reseek');
  if (rs) rs.addEventListener('click', aiReseek);
}

/* 목표금액에 맞춰 참여율 재역산 (사용자 수정 후 정합) */
async function aiReseek() {
  if (!aiState) return;
  const seq = ++aiState._seq;
  overlay(true, '목표금액에 맞춰 참여율 재계산 중...');
  const r = await call('goal_seek', aiPayload(0));
  overlay(false);
  if (!aiState || seq !== aiState._seq) return;          // 다른 작업이 시작됨 → stale
  if (!r.ok) { (r.warnings || []).forEach(w => toast(w, 'warn', 4000)); toast(r.error || '재역산 실패', 'err'); return; }
  const d = aiState.draft;
  r.rates.forEach((rate, i) => { if (d.labor[i]) d.labor[i].rate = rate; });
  d.trim = r.trim;
  (r.warnings || []).forEach(w => toast(w, 'warn', 4000));
  renderAILabor();
  aiRecalc();
}

function aiAddExp() {
  if (!aiState) return;
  aiState.draft.expenses.push({ name: '', details: [], qty_text: '', unit_price: null, qty: null });
  renderAIExp(); aiRecalc();
}

/* 확정 → 편집기 폼(문서정보 포함)에 반영. 수신처/견적번호/일자/참조는 보존 */
function confirmAIDraft() {
  if (!aiState) return;
  clearTimeout(_aiCalcTimer);
  const d = aiState.draft;
  const q = state.quote || {};
  q.doc = q.doc || {};
  const sn = $('#ai-svc-name').value.trim();
  if (sn) q.doc.service_name = sn;                  // 비우면 기존 용역명 보존
  q.doc.service_period = $('#ai-period').value.trim();
  // 문서정보 반영: 수신처·견적번호·일자는 입력 시에만 덮어쓰고, 참조/전화는 그대로 반영
  const rcp = $('#ai-recipient').value.trim();
  if (rcp) q.doc.recipient = rcp;
  const qno = $('#ai-quote-no').value.trim();
  if (qno) q.doc.quote_no = qno;
  const dt = $('#ai-date').value;
  if (dt) q.doc.date = dt;
  q.doc.ref_name = $('#ai-ref-name').value.trim();
  q.doc.ref_tel = $('#ai-ref-tel').value.trim();
  q.options = q.options || {};
  q.options.profit = !!(d.options && d.options.profit !== false);
  q.labor = d.labor;
  q.expenses = d.expenses;
  q.goal = d.goal || { mode: 'ratio' };
  q.goal.target = aiState.target;
  q.trim = d.trim || 0;
  state.quote = q;
  closeAIModal();
  openEditor(q);
  toast('AI 초안을 견적서에 반영했습니다. 내용을 확인하고 생성하세요.', 'ok', 5000);
}

/* ===================================================================
   설정 (탭: 공통 | 견적서 | 회의록)
=================================================================== */
let _settingsTab = 'common';

function showSettingsTab(tab) {
  _settingsTab = tab;
  $$('#settings-tabs .tab').forEach(t => t.classList.toggle('active', t.dataset.stab === tab));
  ['common', 'quote', 'minutes'].forEach(k =>
    $(`#stab-${k}`).classList.toggle('hidden', k !== tab));
}

function renderSettings() {
  const cfg = state.config;
  if (!cfg) return;
  showSettingsTab(_settingsTab);
  // 단가표 연도
  const ySel = $('#s-price-year');
  const years = Object.keys(cfg.unit_prices || {}).sort();
  ySel.innerHTML = years.map(y => `<option value="${y}" ${y === cfg.default_price_year ? 'selected' : ''}>${y}년</option>`).join('');
  renderPriceTable(ySel.value || cfg.default_price_year);
  renderMaxCounts();
  renderLaborRatio();
  // AI 제공사·모델
  $('#s-ai-provider').value = cfg.ai_provider || 'gemini';
  renderAIProvider();
  renderAiPrompts();
  // 공급자
  const grid = $('#company-grid');
  grid.innerHTML = COMPANY_FIELDS.map(([k, label]) =>
    `<label${k === 'address' ? ' class="span2"' : ''}>${label}<input data-ck="${k}" value="${esc((cfg.company || {})[k] || '')}"></label>`).join('');
  // Google Drive 상태
  loadDriveStatus();
  // 유형별 작업 폴더
  $('#s-quote-folder-path').textContent = state.folder || '폴더 미지정';
  $('#s-quote-folder-path').title = state.folder || '';
  $('#s-minutes-folder-path').textContent = state.minutesFolder || '폴더 미지정 (견적서 폴더 공용)';
  $('#s-minutes-folder-path').title = state.minutesFolder || '';
  // 회의록 양식 정보
  call('get_minutes_template').then(r => {
    const name = $('#mn-tpl-name'), st = $('#mn-tpl-status');
    if (!name) return;
    if (r.ok) {
      name.textContent = r.name;
      name.title = r.path || '';
      st.textContent = r.exists ? '✓ 내장' : '⚠ 파일 없음';
    } else {
      name.textContent = '확인 실패';
      st.textContent = '';
    }
  });
  // 현재 버전 표기 (설정 탭 진입 시마다 갱신)
  call('get_app_version').then(r => {
    const el = $('#app-version');
    if (el) el.textContent = r.ok ? `v${r.version}` : '–';
  });
}

function renderPriceTable(year) {
  const prices = (state.config.unit_prices && state.config.unit_prices[year]) || {};
  const tb = $('#price-table tbody');
  tb.innerHTML = GRADES.map(g =>
    `<tr><td class="l" style="text-align:left;font-weight:600">${g}</td>
      <td><input data-pg="${g}" value="${commafy(prices[g] || 0)}"></td></tr>`).join('');
  $$('#price-table input').forEach(inp => inp.addEventListener('blur', e => { e.target.value = commafy(parseMoney(e.target.value)); }));
}

const MAXCNT_GRADES = ['연구원', '연구보조원', '보조원'];   // 책임연구원은 항상 1명

function renderMaxCounts() {
  const mc = (state.config && state.config.max_counts) || {};
  const def = { '연구원': 5, '연구보조원': 5, '보조원': 10 };
  $('#maxcnt-grid').innerHTML = MAXCNT_GRADES.map(g =>
    `<label>${g} 최대<input data-mc="${g}" type="number" min="1" value="${mc[g] || def[g]}"></label>`).join('');
}

async function saveMaxCounts() {
  const counts = {};
  $$('#maxcnt-grid input[data-mc]').forEach(inp => {
    const v = parseInt(inp.value, 10);
    if (v >= 1) counts[inp.dataset.mc] = v;
  });
  const r = await call('set_max_counts', counts);
  if (r.ok) { state.config.max_counts = r.max_counts; toast('최대 인원 저장 완료', 'ok'); }
  else toast(r.error || '저장 실패', 'err');
}

function renderLaborRatio() {
  const ratio = Math.round(((state.config && state.config.labor_ratio) || 0.5) * 100);
  $('#s-labor-ratio').value = ratio;
}

async function saveLaborRatio() {
  const pct = parseInt($('#s-labor-ratio').value, 10);
  if (isNaN(pct) || pct < 10 || pct > 90) { toast('비율은 10~90% 사이로 입력하세요', 'warn'); return; }
  const r = await call('set_labor_ratio', pct / 100);
  if (r.ok) {
    state.config.labor_ratio = r.labor_ratio;
    toast(`인건비 비율 ${pct}% 저장 완료`, 'ok');
  } else toast(r.error || '저장 실패', 'err');
}

async function savePrices() {
  const year = $('#s-price-year').value;
  const prices = {};
  $$('#price-table input').forEach(inp => { prices[inp.dataset.pg] = parseMoney(inp.value) || 0; });
  state.config.unit_prices[year] = prices;
  const r = await call('set_config', { unit_prices: state.config.unit_prices, default_price_year: year });
  if (r.ok) toast(`${year}년 단가표 저장 완료`, 'ok'); else toast(r.error, 'err');
}

async function addYear() {
  const y = prompt('추가할 연도를 입력하세요 (예: 2027)');
  if (!y || !/^\d{4}$/.test(y.trim())) { if (y) toast('4자리 연도를 입력하세요.', 'warn'); return; }
  const year = y.trim();
  const base = state.config.unit_prices[state.config.default_price_year] || {};
  state.config.unit_prices[year] = { ...base };
  state.config.default_price_year = year;
  renderSettings();
  toast(`${year}년 추가됨 (기존 단가 복사). 값을 수정 후 저장하세요.`, 'info');
}

async function saveCompany() {
  const company = { ...(state.config.company || {}) };
  $$('#company-grid input').forEach(inp => { company[inp.dataset.ck] = inp.value; });
  state.config.company = company;
  const r = await call('set_config', { company });
  if (r.ok) toast('공급자 정보 저장 완료', 'ok'); else toast(r.error, 'err');
}

// ── AI 초안 기초 프롬프트 (문서 유형별 편집·저장·기본값 복원) ──
const AI_PROMPT_TYPES = ['quote', 'minutes'];

function renderAiPrompts() {
  const cfg = state.config;
  if (!cfg) return;
  AI_PROMPT_TYPES.forEach(t => {
    const ta = $(`#s-ai-prompt-${t}`);
    if (!ta) return;
    const ov = ((cfg.ai_prompts || {})[t] || '').trim();
    ta.value = ov || ((cfg.ai_prompt_defaults || {})[t] || '');
    $(`#ai-prompt-status-${t}`).textContent = ov ? '사용자 지정 지침 사용 중' : '기본 지침 사용 중';
  });
}

async function saveAiPrompt(t) {
  const r = await call('set_ai_prompt', t, $(`#s-ai-prompt-${t}`).value);
  if (!r.ok) { toast(r.error || '저장 실패', 'err'); return; }
  state.config.ai_prompts = state.config.ai_prompts || {};
  state.config.ai_prompts[t] = r.text;          // 백엔드 정규화 결과(에코백) 반영
  renderAiPrompts();
  toast(r.custom ? 'AI 프롬프트 저장 완료' : '기본 지침과 동일 — 기본값 사용으로 저장됨', 'ok');
}

async function resetAiPrompt(t) {
  const r = await call('set_ai_prompt', t, '');
  if (!r.ok) { toast(r.error || '복원 실패', 'err'); return; }
  state.config.ai_prompts = state.config.ai_prompts || {};
  state.config.ai_prompts[t] = '';
  renderAiPrompts();
  toast('기본 지침으로 복원됨', 'ok');
}

const CUSTOM_MODEL = '__custom__';

/* 제공사별 키 발급 안내 + 입력 힌트 */
const AI_GUIDE = {
  gemini: {
    placeholder: 'AIza...',
    steps: [
      '<a class="ext-link" data-url="https://aistudio.google.com/apikey">Google AI Studio 키 발급 ↗</a> (구글 로그인)',
      '<b>API 키 만들기 / Create API key</b> → 키(<code>AIza…</code>) 복사',
      '아래 <b>API 키</b>에 붙여넣고 <b>모델</b> 선택 후 <b>키·모델 저장</b>',
    ],
    foot: '무료 등급으로 충분합니다. · <a class="ext-link" data-url="https://ai.google.dev/gemini-api/docs/pricing">요금 안내 ↗</a>',
  },
  openai: {
    placeholder: 'sk-...',
    steps: [
      '<a class="ext-link" data-url="https://platform.openai.com/api-keys">OpenAI API keys ↗</a> 로그인',
      '<b>Create new secret key</b> → 키(<code>sk-…</code>) 복사 (1회만 표시)',
      '결제 수단 등록 필요 · 아래에 붙여넣고 모델 선택 후 저장',
    ],
    foot: '유료 종량제(상위 모델 = 더 좋은 품질). · <a class="ext-link" data-url="https://openai.com/api/pricing/">요금 ↗</a>',
  },
  anthropic: {
    placeholder: 'sk-ant-...',
    steps: [
      '<a class="ext-link" data-url="https://console.anthropic.com/settings/keys">Anthropic Console → API Keys ↗</a> 로그인',
      '<b>Create Key</b> → 키(<code>sk-ant-…</code>) 복사',
      '크레딧 충전 필요 · 아래에 붙여넣고 모델 선택 후 저장',
    ],
    foot: '유료 종량제(Claude Opus = 최고 품질). · <a class="ext-link" data-url="https://www.anthropic.com/pricing">요금 ↗</a>',
  },
};

function currentProvider() { return $('#s-ai-provider').value || 'gemini'; }

function renderAIProvider() {
  const cfg = state.config;
  if (!cfg) return;
  const p = currentProvider();
  const g = AI_GUIDE[p] || AI_GUIDE.gemini;
  $('#ai-guide-steps').innerHTML = g.steps.map(s => `<li>${s}</li>`).join('');
  $('#ai-guide-foot').innerHTML = g.foot;
  const keyInput = $('#s-ai-key');
  keyInput.placeholder = g.placeholder;
  keyInput.value = '';
  // gemini는 큐레이트 [{id,label}], 그 외는 기본 모델 ID 문자열 배열
  const models = p === 'gemini'
    ? (cfg.gemini_models || [])
    : ((cfg.ai_default_models || {})[p] || []);
  buildModelSelect(models, (cfg.ai_models || {})[p] || '');
  $('#key-status').textContent = (cfg.ai_keys_set || {})[p] ? '✓ 키 등록됨' : '키 미등록';
}

function buildModelSelect(models, current) {
  const sel = $('#s-ai-model');
  // 문자열 배열도 허용 (openai/anthropic 모델 ID 목록)
  const norm = (models || []).map(m => (typeof m === 'string' ? { id: m, label: m } : m));
  const seen = new Set();
  const opts = [];
  norm.forEach(m => {
    if (!m || seen.has(m.id)) return;
    seen.add(m.id);
    opts.push(`<option value="${esc(m.id)}">${esc(m.label || m.id)}</option>`);
  });
  // 저장된 모델이 큐레이트 목록에 없으면 옵션으로 추가
  if (current && !seen.has(current)) {
    seen.add(current);
    opts.push(`<option value="${esc(current)}">${esc(current)} (저장됨)</option>`);
  }
  opts.push(`<option value="${CUSTOM_MODEL}">(직접 입력…)</option>`);
  sel.innerHTML = opts.join('');
  sel.value = current && seen.has(current) ? current : (norm[0] ? norm[0].id : CUSTOM_MODEL);
  toggleCustomModel();
}

function mergeLiveModels(ids) {
  const sel = $('#s-ai-model');
  const existing = new Set(Array.from(sel.options).map(o => o.value));
  let added = 0;
  // (직접 입력…) 옵션 앞에 실시간 모델 삽입
  const customOpt = Array.from(sel.options).find(o => o.value === CUSTOM_MODEL);
  ids.forEach(id => {
    if (existing.has(id)) return;
    const o = document.createElement('option');
    o.value = id; o.textContent = `${id} (실시간)`;
    sel.insertBefore(o, customOpt);
    added++;
  });
  return added;
}

function toggleCustomModel() {
  const isCustom = $('#s-ai-model').value === CUSTOM_MODEL;
  $('#custom-model-wrap').classList.toggle('hidden', !isCustom);
}

function selectedModel() {
  const sel = $('#s-ai-model');
  if (sel.value === CUSTOM_MODEL) return $('#s-ai-model-custom').value.trim();
  return sel.value;
}

async function refreshModels() {
  const p = currentProvider();
  $('#key-status').textContent = '모델 목록 조회 중...';
  const r = await call('list_ai_models', p);
  if (!r.ok) { $('#key-status').textContent = '⚠ ' + (r.error || '조회 실패'); return; }
  const n = mergeLiveModels(r.models || []);
  $('#key-status').textContent = `✓ 사용 가능 모델 ${(r.models || []).length}개${n ? ` (신규 ${n}개 추가)` : ''}`;
}

async function saveKey() {
  const p = currentProvider();
  const key = $('#s-ai-key').value.trim();
  const model = selectedModel();
  if (model) {
    await call('set_ai_model', p, model);
    state.config.ai_models = state.config.ai_models || {};
    state.config.ai_models[p] = model;
  }
  // 키 입력이 비어 있으면 모델만 저장 (기존 키 유지)
  if (key) {
    const r = await call('set_ai_key', p, key);
    if (!r.ok) { toast(r.error, 'err'); return; }
    state.config.ai_keys_set = state.config.ai_keys_set || {};
    state.config.ai_keys_set[p] = true;
    $('#s-ai-key').value = '';
  }
  $('#key-status').textContent = (state.config.ai_keys_set || {})[p]
    ? `✓ 저장됨 · 모델 ${model}` : '키 미등록 (모델만 저장됨)';
  toast('AI 설정 저장 완료', 'ok');
}

async function testKey() {
  const p = currentProvider();
  $('#key-status').textContent = '확인 중...';
  const r = await call('validate_ai_key', p);
  if (r.ok) $('#key-status').textContent = `✓ 정상 (사용 가능 모델: ${(r.models || []).slice(0, 3).join(', ') || '확인됨'})`;
  else $('#key-status').textContent = '⚠ ' + (r.error || '확인 실패');
}

function diagLine(label, ok, val) {
  const cls = ok === true ? 'ok' : ok === 'warn' ? 'warn' : 'no';
  return `<div class="diag-line"><span class="diag-dot ${cls}"></span><span class="diag-k">${esc(label)}</span><span class="diag-v">${esc(val)}</span></div>`;
}
function openDiag(title, html) {
  $('#diag-modal-title').textContent = title;
  $('#diag-modal-body').innerHTML = html;
  $('#diag-modal').classList.remove('hidden');
}
function closeDiag() { $('#diag-modal').classList.add('hidden'); }

async function runDiagnose() {
  openDiag('환경 점검', '<div class="hint">점검 중...</div>');
  const r = await call('diagnose');
  openDiag('환경 점검',
    diagLine('한글(HWP) COM 등록', r.hwp_com, r.hwp_com ? '사용 가능' : '미등록') +
    diagLine('보안 모듈(FilePathChecker)', r.security_module, r.security_module ? '등록됨' : '미등록 — 첫 생성 시 자동 등록') +
    diagLine('견적서 템플릿', r.template, r.template ? '존재' : '없음 — make_template 실행 필요') +
    diagLine('Gemini API 키', r.gemini_key ? true : 'warn', r.gemini_key ? '등록됨' : '미등록 (AI 비활성)') +
    diagLine('Google Drive', r.drive_connected ? true : 'warn', r.drive_connected ? '연결됨' : '미연결') +
    diagLine('작업 폴더', r.folder_ok ? true : 'warn', r.folder || '미선택') +
    diagLine('Node.js (문서 변환)', r.node ? true : 'warn', r.node ? `${r.node_bundled ? '내장됨' : '설치됨'} (${r.node})` : '런타임 없음') +
    diagLine('kordoc (변환 도구)', r.kordoc ? true : 'warn', r.kordoc ? `내장됨 (v${r.kordoc})` : '준비 안 됨'));
}

async function runHwpTest() {
  openDiag('한글 구동 테스트', '<div class="hint">한글을 실행하는 중입니다... (최초 실행은 시간이 걸립니다)</div>');
  const r = await call('diagnose_hwp_session');
  openDiag('한글 구동 테스트', r.ok
    ? diagLine('한글 COM 구동', true, `정상 (버전 ${r.version || '확인됨'})`)
    : diagLine('한글 COM 구동', false, r.error || '실패'));
}

/* ===================================================================
   문서 삭제 — 견적서·회의록 공용 모달 (kind로 분기, 파일 삭제는 별도 확인)
=================================================================== */
let _delTarget = null;   // { kind: 'quote' | 'minutes', item }
function openDeleteModal(item, kind = 'quote') {
  _delTarget = { kind, item };
  $('#del-files').checked = false;
  const note = $('#del-files-note');
  if (kind === 'minutes') {
    $('#del-title').textContent = '회의록 삭제';
    $('#del-target').textContent = `"${item.topic || item.filename}" 회의록을 삭제합니다.`;
    $('#del-files-label').textContent = '폴더에 있는 실제 파일(.hwpx)도 함께 삭제';
    note.textContent = item.editable
      ? '체크하지 않으면 목록에서만 제거되고(재편집 데이터 .minutes.json만 삭제) 실제 회의록 파일은 폴더에 남습니다.'
      : '외부 HWPX라 재편집 데이터가 없습니다. 폴더의 파일을 지우려면 위 항목을 체크하세요(체크 안 하면 변화 없음).';
  } else {
    $('#del-title').textContent = '견적서 삭제';
    $('#del-target').textContent = `"${item.service_name || item.filename}" 견적서를 삭제합니다.`;
    $('#del-files-label').textContent = '폴더에 있는 실제 파일(.hwp/.pdf)도 함께 삭제';
    note.textContent = (item.source === 'hwp' && !item.editable)
      ? '외부 HWP라 재편집 데이터가 없습니다. 폴더의 파일을 지우려면 위 항목을 체크하세요(체크 안 하면 변화 없음).'
      : '체크하지 않으면 목록에서만 제거되고(.quote.json만 삭제) 실제 한글/PDF 파일은 폴더에 남습니다.';
  }
  $('#del-modal').classList.remove('hidden');
}
function closeDeleteModal() { $('#del-modal').classList.add('hidden'); _delTarget = null; }
async function confirmDelete() {
  if (!_delTarget) return;
  const { kind, item } = _delTarget;
  const alsoFiles = $('#del-files').checked;
  $('#del-modal').classList.add('hidden');
  _delTarget = null;
  overlay(true, '삭제 중...');
  const r = await call(kind === 'minutes' ? 'delete_minutes' : 'delete_quote', {
    path: item.path, json_path: item.json_path, source: item.source, also_files: alsoFiles,
  });
  overlay(false);
  if (r.ok) {
    toast(`삭제 완료 (${(r.removed || []).join(', ') || '항목'})`, 'ok');
    if (kind === 'minutes') refreshMinutesDashboard(); else refreshDashboard();
  } else toast(r.error || '삭제 실패', 'err', 5000);
}

/* ===================================================================
   Google Drive
=================================================================== */
async function loadDriveStatus() {
  const box = $('#drive-status');
  if (!box) return;
  const r = await call('drive_status');
  const set = (cls, k, v) => { box.innerHTML = `<span class="diag-dot ${cls}"></span><span class="diag-k">${esc(k)}</span><span class="diag-v">${esc(v)}</span>`; };
  if (!r.ok) { set('no', '오류', r.error || '상태 확인 실패'); return; }
  if (r.connected) set('ok', '연결됨', r.email || 'Drive 사용 가능');
  else if (!r.lib) set('no', '미설치', 'google-api-python-client 필요 (pip install)');
  else if (!r.client_secret) set('warn', '미연결', 'client_secret.json 파일 필요');
  else set('warn', '미연결', 'Drive 연결 버튼을 누르세요');
  if (typeof r.folder === 'string' && r.folder) $('#s-drive-folder').value = r.folder;
  $('#s-drive-auto').checked = !!r.auto;
}
async function driveConnect() {
  await saveDriveOptions();
  overlay(true, '브라우저에서 구글 로그인·허용을 진행하세요...');
  const r = await call('drive_connect');
  overlay(false);
  if (r.ok) { toast('Google Drive 연결 완료', 'ok'); loadDriveStatus(); }
  else toast(r.error || 'Drive 연결 실패', 'err', 6000);
}
async function driveDisconnect() {
  const r = await call('drive_disconnect');
  if (r.ok) { toast('Drive 연결 해제됨', 'ok'); loadDriveStatus(); }
  else toast(r.error || '실패', 'err');
}
async function saveDriveOptions() {
  const r = await call('set_drive_options', {
    folder: $('#s-drive-folder').value.trim(),
    auto: $('#s-drive-auto').checked,
  });
  if (!r.ok) toast(r.error || 'Drive 설정 저장 실패', 'warn');
}

/* ===================================================================
   템플릿 관리
=================================================================== */
let _tplPendingPath = null;   // 파일 선택 후 아직 분석 안 한 경로

async function initTemplateStatus() {
  const r = await call('get_active_template');
  if (!r.ok) return;
  const name = r.template_name || '기본 템플릿 (내장)';
  $('#tpl-name').textContent = name;
  if (r.has_fieldmap && !r.is_standard) {
    $('#tpl-status').textContent = `커스텀 템플릿 적용됨 (인건비 ${r.max_labor}행 / 경비 ${r.max_exp}행)`;
  } else if (r.is_standard || !r.has_fieldmap) {
    $('#tpl-status').textContent = r.has_fieldmap ? '표준 필드 구조 확인됨' : '';
  }
}

async function pickTemplate() {
  const r = await call('pick_template_file');
  if (!r.ok || r.cancelled) return;
  _tplPendingPath = r.path;
  $('#tpl-name').textContent = r.path.split(/[/\\]/).pop();
  $('#tpl-status').textContent = '파일 선택됨 — [분석·적용] 버튼으로 필드 구조를 분석하세요.';
  $('#btn-scan-tpl').disabled = false;
  $('#tpl-scan-result').classList.add('hidden');
}

async function scanTemplate() {
  if (!_tplPendingPath) return;
  $('#btn-scan-tpl').disabled = true;
  $('#tpl-status').textContent = '분석 중… (한글 COM으로 필드 스캔)';
  $('#tpl-scan-result').classList.add('hidden');

  const r = await call('scan_template', _tplPendingPath);
  if (!r.ok) {
    $('#tpl-status').textContent = `오류: ${r.error}`;
    $('#btn-scan-tpl').disabled = false;
    return;
  }

  // 결과 요약 표시
  if (r.is_standard) {
    $('#tpl-status').textContent =
      `표준 필드 구조 확인 ✓ (인건비 ${r.max_labor}행 / 경비 ${r.max_exp}행) — 즉시 사용 가능합니다.`;
    $('#tpl-scan-result').classList.add('hidden');
  } else {
    const mapped = Object.keys(r.field_map || {}).length;
    const unmapped = (r.unmapped || []).length;
    let msg = `비표준 필드 감지 (인건비 ${r.max_labor}행 / 경비 ${r.max_exp}행)`;
    if (r.ai_used) msg += ` — AI 매핑 ${mapped}개 완료`;
    if (r.ai_error) msg += ` (AI 오류: ${r.ai_error})`;
    if (unmapped) msg += `, 미매핑 ${unmapped}개`;
    $('#tpl-status').textContent = msg;

    // 매핑 표
    const tbody = $('#tpl-map-body');
    tbody.innerHTML = '';
    for (const [tplField, stdSlot] of Object.entries(r.field_map || {})) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td><code>${esc(tplField)}</code></td><td><code>${esc(stdSlot)}</code></td>`;
      tbody.appendChild(tr);
    }
    if ((r.unmapped || []).length) {
      $('#tpl-unmapped').textContent = `매핑 불가 필드: ${r.unmapped.join(', ')}`;
    } else {
      $('#tpl-unmapped').textContent = '';
    }
    $('#tpl-scan-result').classList.toggle('hidden', !Object.keys(r.field_map || {}).length && !unmapped);
  }
  $('#btn-scan-tpl').disabled = false;
  toast('템플릿 분석·적용 완료', 'ok');
}

/* ===================================================================
   회의록 양식 관리
=================================================================== */
async function initMinutesTemplateStatus() {
  const r = await call('get_minutes_template');
  if (!r.ok) return;
  $('#mn-tpl-name').textContent = r.name || '기본 양식 (내장)';
  $('#mn-tpl-status').textContent = r.is_custom ? '커스텀 양식 적용 중' : '기본 내장 양식 사용 중';
}

async function pickMinutesTemplate() {
  const r = await call('pick_minutes_template_file');
  if (!r.ok || r.cancelled) return;
  const r2 = await call('set_minutes_template', r.path);
  if (!r2.ok) { toast(r2.error || '양식 저장 실패', 'err'); return; }
  $('#mn-tpl-name').textContent = r.path.split(/[/\\]/).pop();
  $('#mn-tpl-status').textContent = '커스텀 양식 적용 중';
  toast('회의록 양식이 변경됐습니다', 'ok');
}

async function resetMinutesTemplate() {
  const r = await call('set_minutes_template', '');
  if (!r.ok) { toast(r.error || '복원 실패', 'err'); return; }
  initMinutesTemplateStatus();
  toast('기본 내장 양식으로 복원됐습니다', 'ok');
}

/* ===================================================================
   튜토리얼 (코치마크 투어)
=================================================================== */
const TOUR_STEPS = [
  { view: 'quote', sub: 'dashboard', target: null, placement: 'center',
    title: '환영합니다! 👋',
    body: '내비온 업무 문서 생성기의 핵심 기능을 1분 만에 안내해 드립니다.<br>좌측 아이콘이 문서 유형(견적서·회의록)입니다. ESC 키를 누르면 언제든 종료할 수 있습니다.' },
  { view: 'quote', sub: 'dashboard', target: '#btn-pick-folder', placement: 'bottom',
    title: '① 작업 폴더 선택',
    body: '견적서를 저장하고 불러올 폴더를 먼저 선택하세요. 폴더 안의 기존 견적 파일도 자동으로 목록에 표시됩니다. (회의록 폴더는 회의록 대시보드에서 따로 지정)' },
  { view: 'quote', sub: 'dashboard', target: '.split-btn', placement: 'bottom',
    title: '② 새 견적서 만들기',
    body: '직접 작성하거나, ▾를 눌러 <b>✦ AI 초안</b>으로 시작할 수 있습니다. 과업지시서를 붙여넣으면 AI가 인력·경비 구성을 제안합니다.' },
  { view: 'quote', sub: 'editor', target: '#btn-ai-open', placement: 'bottom',
    title: '③ AI 초안',
    body: '편집 중에도 언제든 AI 초안을 불러와 인건비·경비 구성을 다시 제안받을 수 있습니다. (설정에서 AI API 키 필요)' },
  { view: 'quote', sub: 'editor', target: '.goal-row', placement: 'bottom',
    title: '④ 목표금액 자동 맞춤',
    body: '목표금액(부가세 포함)을 입력하고 <b>⚖ 인건비 자동조정</b>을 누르면 참여율·명수를 자동 계산해 최종 견적이 목표금액과 정확히 일치합니다. 만원 미만 잔액은 "만원미만 절삭"으로 처리됩니다.' },
  { view: 'quote', sub: 'editor', target: '#labor-table', placement: 'bottom',
    title: '⑤ 🔒 값 고정',
    body: '특정 직급의 명수·참여율을 그대로 유지하고 싶으면 맨 오른쪽 <b>🔒고정</b>을 체크하세요. 자동조정 시 그 행은 건드리지 않습니다.' },
  { view: 'quote', sub: 'editor', target: '#view-editor .topbar-right', placement: 'bottom',
    title: '⑥ HWP 생성',
    body: '작성이 끝나면 <b>HWP 생성</b> 또는 <b>HWP + PDF</b>를 누르세요. 한글(HWP)이 자동 실행되어 회사 양식 그대로 견적서가 완성됩니다.' },
  { view: 'minutes', sub: 'dashboard', target: '#btn-new-minutes', placement: 'bottom',
    title: '⑦ 회의록',
    body: '회의 메모·녹음 전사본으로 AI가 회의록 초안을 만들고 HWPX로 생성합니다. 생성된 회의록은 이 대시보드에서 관리·재편집할 수 있습니다.' },
  { view: 'settings', settingsTab: 'common', target: '#card-ai-engine', placement: 'left',
    title: '⑧ AI API 키 설정',
    body: 'AI 초안 기능을 쓰려면 여기서 제공사를 선택하고 API 키를 저장하세요.<br>이 안내는 <b>설정 → 튜토리얼 다시 보기</b>로 언제든 다시 볼 수 있습니다.' },
];
let _tour = { active: false, idx: 0 };
let _tourResizeT = null;

function startTour() {
  if (_tour.active) return;
  _tour.active = true;
  $('#tour').classList.remove('hidden');
  document.addEventListener('keydown', tourKeydown);
  window.addEventListener('resize', tourResize);
  tourShow(0, 1);
}

function endTour(markSeen = true) {
  if (!_tour.active) return;
  _tour.active = false;
  $('#tour').classList.add('hidden');
  document.removeEventListener('keydown', tourKeydown);
  window.removeEventListener('resize', tourResize);
  switchView('quote', 'dashboard');
  if (markSeen) {
    if (state.config) state.config.tutorial_seen = true;
    call('set_tutorial_seen', true);     // 저장 실패해도 투어는 닫힘(다음 실행 때 재노출)
  }
}

function tourKeydown(e) { if (e.key === 'Escape') endTour(true); }
function tourResize() {
  clearTimeout(_tourResizeT);
  _tourResizeT = setTimeout(() => { if (_tour.active) tourShow(_tour.idx, 1); }, 100);
}

function tourShow(idx, dir = 1) {
  if (idx >= TOUR_STEPS.length) { endTour(true); return; }
  if (idx < 0) idx = 0;
  _tour.idx = idx;
  const step = TOUR_STEPS[idx];
  if (state.view !== step.view || (step.sub && state.sub[step.view] !== step.sub)) {
    switchView(step.view, step.sub);
  }
  // 설정 탭 뒤에 숨은 타깃 방지 — 사용자가 다른 탭을 보던 상태여도 강제 전환
  if (step.settingsTab) showSettingsTab(step.settingsTab);
  setTimeout(() => tourPaint(idx, dir), 80);   // 뷰 전환 페인트 대기
}

function tourPaint(idx, dir) {
  if (!_tour.active || _tour.idx !== idx) return;   // 종료·추월된 호출 무시
  const step = TOUR_STEPS[idx];
  let rect;
  if (step.target) {
    const t = $(step.target);
    if (!t) { tourShow(idx + dir, dir); return; }   // 타깃 소실 → 진행 방향으로 건너뜀
    t.scrollIntoView({ block: 'center' });
    const r = t.getBoundingClientRect();
    if (!r.width && !r.height) { tourShow(idx + dir, dir); return; }
    rect = { left: r.left - 8, top: r.top - 8, width: r.width + 16, height: r.height + 16 };
  } else {
    rect = { left: innerWidth / 2, top: innerHeight / 2, width: 0, height: 0 };  // 전체 디밍
  }
  const hole = $('#tour-hole');
  hole.style.left = rect.left + 'px';
  hole.style.top = rect.top + 'px';
  hole.style.width = rect.width + 'px';
  hole.style.height = rect.height + 'px';

  $('#tour-title').textContent = step.title;
  $('#tour-body').innerHTML = step.body;
  $('#tour-count').textContent = `${idx + 1} / ${TOUR_STEPS.length}`;
  $('#tour-prev').classList.toggle('hidden', idx === 0);
  $('#tour-next').textContent = idx === TOUR_STEPS.length - 1 ? '완료' : '다음';
  tourPlaceCard(rect, step.placement);
}

function tourPlaceCard(rect, placement) {
  const card = $('#tour-card');
  const cw = card.offsetWidth, ch = card.offsetHeight, gap = 12;
  let left, top;
  if (!rect.width && !rect.height) {                       // 중앙 카드
    left = (innerWidth - cw) / 2; top = (innerHeight - ch) / 2;
  } else if (placement === 'left' || placement === 'right') {
    top = rect.top + rect.height / 2 - ch / 2;
    left = placement === 'left' ? rect.left - cw - gap : rect.left + rect.width + gap;
    if (left < gap) left = rect.left + rect.width + gap;             // 화면 밖 → 반전
    if (left + cw > innerWidth - gap) left = rect.left - cw - gap;
  } else {                                                  // top / bottom
    left = rect.left + rect.width / 2 - cw / 2;
    top = placement === 'top' ? rect.top - ch - gap : rect.top + rect.height + gap;
    if (top < gap) top = rect.top + rect.height + gap;
    if (top + ch > innerHeight - gap) top = rect.top - ch - gap;
  }
  card.style.left = Math.max(gap, Math.min(left, innerWidth - cw - gap)) + 'px';
  card.style.top = Math.max(gap, Math.min(top, innerHeight - ch - gap)) + 'px';
}

/* ===================================================================
   회의록 대시보드
=================================================================== */
async function refreshMinutesDashboard() {
  const r = await call('scan_minutes_folder', state.minutesFolder || null);
  if (!r.ok) { toast(r.error || '회의록 폴더 스캔 실패', 'err'); return; }
  state.minutesFolder = r.folder || '';
  state.minutes = r.minutes || [];
  $('#mnd-folder-path').textContent = state.minutesFolder || '폴더를 선택하세요';
  $('#mnd-folder-path').title = state.minutesFolder || '';
  renderMinutesStats(r.stats);
  renderMinutesGrid();
}

function renderMinutesStats(s) {
  s = s || {};
  $('#mst-total').textContent = s.total ?? 0;
  $('#mst-month').textContent = s.this_month ?? 0;
  $('#mst-editable').textContent = s.editable ?? 0;
}

function filteredMinutes() {
  let list = state.minutes;
  const kw = state.mnSearch.trim().toLowerCase();
  if (kw) {
    list = list.filter(m =>
      (m.topic || '').toLowerCase().includes(kw) ||
      (m.business_name || '').toLowerCase().includes(kw) ||
      (m.place || '').toLowerCase().includes(kw));
  }
  return list;
}

function renderMinutesGrid() {
  const grid = $('#minutes-grid');
  const list = filteredMinutes();
  grid.innerHTML = '';
  $('#mnd-empty').classList.toggle('hidden', list.length > 0);
  for (const m of list) grid.appendChild(minutesCard(m));
}

function minutesCard(m) {
  const c = el('div', 'qcard');
  let badge;
  if (m.source === 'json') badge = `<span class="badge json">재편집 데이터</span>`;
  else if (m.editable) badge = `<span class="badge editable">재편집 가능</span>`;
  else badge = `<span class="badge external">외부 HWPX</span>`;

  c.innerHTML = `
    <div class="qcard-top">
      <div>
        <div class="qcard-no" title="${esc(m.business_name)}">${esc(m.business_name || '사업명 미상')}</div>
        <div class="qcard-title" title="${esc(m.topic)}">${esc(m.topic || '(주제 없음)')}</div>
      </div>
      ${badge}
    </div>
    <div class="qcard-meta">
      <div class="qcard-row"><span class="k">일시</span><span class="v" title="${esc(m.date)}">${esc(m.date || '-')}</span></div>
      <div class="qcard-row"><span class="k">장소</span><span class="v" title="${esc(m.place)}">${esc(m.place || '-')}</span></div>
      <div class="qcard-row"><span class="k">참석</span><span class="v">${m.total_count ? esc(String(m.total_count)) + '명' : '-'}</span></div>
      <div class="qcard-row"><span class="k">파일</span><span class="v" title="${esc(m.filename)}">${esc(m.filename)}</span></div>
    </div>
    <div class="qcard-actions"></div>`;

  const actions = $('.qcard-actions', c);
  if (m.source !== 'json') {
    const open = el('button', 'btn btn-ghost', 'HWPX 열기');
    open.onclick = () => call('open_file', m.path).then(r => { if (!r.ok) toast(r.error, 'err'); });
    actions.appendChild(open);
  }
  if (m.editable && m.json_path) {
    const edit = el('button', 'btn btn-outline', '재편집');
    edit.onclick = () => reEditMinutes(m.json_path);
    actions.appendChild(edit);
  }
  const del = el('button', 'qcard-del', '×');
  del.title = '삭제';
  del.setAttribute('aria-label', '회의록 삭제');
  del.onclick = (ev) => { ev.stopPropagation(); openDeleteModal(m, 'minutes'); };
  c.appendChild(del);
  return c;
}

/* 사이드카 → 위저드 2단계 복원 (재편집) */
async function reEditMinutes(jsonPath) {
  overlay(true, '불러오는 중...');
  const r = await call('load_minutes', jsonPath);
  overlay(false);
  if (!r.ok) { toast(r.error || '불러오기 실패', 'err'); return; }
  _minutesComposeInited = true;   // lazy-init이 위저드를 리셋하지 않도록 선세트
  minutesDraft = r.data;
  renderMinutesReview(minutesDraft);
  showMinutesStep(2);
  switchView('minutes', 'compose');
}

/* ===================================================================
   회의록 뷰
=================================================================== */
let minutesAttachments = [];  // [{ name, markdown, chars }]
let minutesDraft = null;      // 검토 중인 MINUTES_SCHEMA 초안

/* 회의록 드롭존 상태 (ai 드롭존과 동일 패턴) */
async function refreshMinutesConvertStatus() {
  const r = await call('convert_status');
  const dz = $('#minutes-dropzone');
  const banner = $('#mn-node-banner');
  if (!dz) return;
  if (r && r.state === 'node_missing') {
    dz.classList.add('dz-disabled');
    if (banner) banner.classList.remove('hidden');
  } else {
    dz.classList.remove('dz-disabled');
    if (banner) banner.classList.add('hidden');
  }
}

function wireMinutesDropzone() {
  const dz = $('#minutes-dropzone');
  if (!dz) return;
  dz.addEventListener('dragenter', e => { e.preventDefault(); if (!dz.classList.contains('dz-disabled')) dz.classList.add('drag-over'); });
  dz.addEventListener('dragover',  e => { e.preventDefault(); if (!dz.classList.contains('dz-disabled')) dz.classList.add('drag-over'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
  dz.addEventListener('drop', e => {
    e.preventDefault(); dz.classList.remove('drag-over');
    if (e.dataTransfer?.files?.length) toast('파일 경로를 확인할 수 없습니다. [파일 선택…] 버튼을 이용해 주세요.', 'warn', 4000);
  });
}

async function handleMinutesDroppedPaths(paths) {
  if (!paths || !paths.length) return;
  overlay(true, '변환 준비 중...');
  await convertPathsForMinutes(paths);
  overlay(false);
}

async function convertPathsForMinutes(paths) {
  const r = await call('convert_files', paths);
  overlay(false);
  if (!r.ok) {
    toast(r.error || '변환 실패', 'err', 5000);
    return;
  }
  if (r.installed_now) toast('변환 도구 준비 완료. HWP·PDF·DOCX 변환을 사용할 수 있습니다.', 'ok', 4000);
  for (const res of r.results || []) {
    if (res.ok) {
      const ex = minutesAttachments.findIndex(a => a.name === res.name);
      if (ex >= 0) minutesAttachments[ex] = { name: res.name, markdown: res.markdown, chars: res.chars };
      else minutesAttachments.push({ name: res.name, markdown: res.markdown, chars: res.chars });
    } else {
      toast(`변환 실패: ${res.name} — ${res.error || ''}`, 'err', 5000);
    }
  }
  renderMinutesChips();
}

function renderMinutesChips() {
  const wrap = $('#mn-chips');
  if (!wrap) return;
  if (!minutesAttachments.length) { wrap.classList.add('hidden'); wrap.innerHTML = ''; return; }
  wrap.classList.remove('hidden');
  wrap.innerHTML = minutesAttachments.map((a, i) => `
    <span class="ai-chip chip-ok" data-idx="${i}">
      <span class="chip-name" title="${esc(a.name)}">📄 ${esc(a.name)}</span>
      <span class="chip-sub">${(a.chars || 0).toLocaleString()}자</span>
      <button class="chip-rm" data-idx="${i}" type="button" title="제거">✕</button>
    </span>`).join('');
  wrap.querySelectorAll('.chip-rm').forEach(btn => btn.addEventListener('click', e => {
    minutesAttachments.splice(+e.currentTarget.dataset.idx, 1); renderMinutesChips();
  }));
}

function setMnStatus(msg, kind) {
  const box = $('#mn-status');
  if (!box) return;
  if (!msg) { box.textContent = ''; box.className = 'ai-status'; return; }
  box.textContent = msg;
  box.className = 'ai-status ' + (kind || 'info');
}

function showMinutesStep(n) {
  $('#minutes-step1').classList.toggle('hidden', n !== 1);
  $('#minutes-step2').classList.toggle('hidden', n !== 2);
  const ind = $('#mn-step-indicator');
  if (ind) ind.textContent = n === 1 ? '1단계: 회의 내용 입력' : '2단계: 초안 검토·수정';
}

async function runMinutesDraft() {
  const desc = ($('#mn-memo').value || '').trim();
  if (desc.length < 5 && !minutesAttachments.length) {
    setMnStatus('회의 메모를 5자 이상 입력하거나 파일을 첨부하세요.', 'warn'); return;
  }
  const prov = state.config && state.config.ai_provider;
  const keySet = state.config && (state.config.ai_keys_set || {})[prov];
  if (!keySet) {
    toast('AI 기능은 설정에서 API 키를 먼저 등록해야 합니다.', 'warn', 4500);
    switchView('settings'); return;
  }
  setMnStatus('AI가 회의록 초안을 작성하는 중입니다...', 'info');
  overlay(true, 'AI 회의록 초안 생성 중...');
  const r = await call('minutes_draft', {
    description: desc,
    attachments: minutesAttachments.map(a => ({ name: a.name, markdown: a.markdown })),
    hints: { date: $('#mn-date').value.trim(), place: $('#mn-place').value.trim() },
  });
  overlay(false);
  if (!r.ok) { setMnStatus(r.error || 'AI 호출 실패', 'err'); return; }
  if (r.warnings && r.warnings.length) toast(r.warnings.join(' / '), 'warn', 5000);
  setMnStatus('');
  minutesDraft = r.draft;
  renderMinutesReview(minutesDraft);
  showMinutesStep(2);
}

function renderMinutesReview(draft) {
  $('#mn-r-business').value = draft.business_name || '';
  $('#mn-r-date').value    = draft.meeting_date   || '';
  $('#mn-r-place').value   = draft.meeting_place  || '';
  $('#mn-r-topic').value   = draft.meeting_topic  || '';
  $('#mn-r-total').value   = draft.total_count    || '';

  // 참석자
  const pWrap = $('#mn-r-participants');
  pWrap.innerHTML = '';
  const parts = (draft.participants || []).length ? draft.participants : [''];
  parts.forEach(line => addParticipantRow(line));

  // 섹션
  const sWrap = $('#mn-r-sections');
  sWrap.innerHTML = '';
  (draft.sections || []).forEach(s => addSectionRow(s.type, s.text));

  const rStatus = $('#mn-r-status');
  if (rStatus) { rStatus.textContent = ''; rStatus.className = 'ai-status'; }
}

function addParticipantRow(value) {
  const row = el('div', 'mn-part-row');
  const inp = el('input');
  inp.type = 'text'; inp.value = value || ''; inp.placeholder = '기관명 + 참석자명';
  const rm = el('button', 'btn btn-mini');
  rm.type = 'button'; rm.textContent = '삭제';
  rm.addEventListener('click', () => row.remove());
  row.appendChild(inp); row.appendChild(rm);
  $('#mn-r-participants').appendChild(row);
}

const SECTION_TYPE_LABELS = { header: '■ 제목', bullet: '• 항목', sub: '  └ 하위', empty: '빈 줄' };
function addSectionRow(type, text) {
  const row = el('div', 'mn-sec-row');
  const sel = el('select');
  ['header','bullet','sub','empty'].forEach(t => {
    const opt = document.createElement('option');
    opt.value = t; opt.textContent = SECTION_TYPE_LABELS[t] || t;
    if (t === (type || 'bullet')) opt.selected = true;
    sel.appendChild(opt);
  });
  const inp = el('input');
  inp.type = 'text'; inp.value = text || ''; inp.placeholder = '내용 입력';
  const rm = el('button', 'btn btn-mini');
  rm.type = 'button'; rm.textContent = '삭제';
  rm.addEventListener('click', () => row.remove());
  row.appendChild(sel); row.appendChild(inp); row.appendChild(rm);
  $('#mn-r-sections').appendChild(row);
}

function collectMinutesPayload() {
  const participants = Array.from($('#mn-r-participants').querySelectorAll('.mn-part-row input'))
    .map(i => i.value.trim()).filter(Boolean);
  const sections = Array.from($('#mn-r-sections').querySelectorAll('.mn-sec-row'))
    .map(row => ({
      type: row.querySelector('select').value,
      text: row.querySelector('input[type=text]').value.trim(),
    }));
  return {
    business_name: $('#mn-r-business').value.trim(),
    meeting_date:  $('#mn-r-date').value.trim(),
    meeting_place: $('#mn-r-place').value.trim(),
    meeting_topic: $('#mn-r-topic').value.trim(),
    participants,
    total_count:   parseInt($('#mn-r-total').value || '0', 10) || 0,
    sections,
  };
}

async function generateMinutes() {
  const data = collectMinutesPayload();
  if (!data.meeting_topic) {
    const box = $('#mn-r-status');
    if (box) { box.textContent = '회의주제를 입력하세요.'; box.className = 'ai-status warn'; }
    return;
  }
  overlay(true, 'HWPX 생성 중...');
  const r = await call('generate_minutes', {
    data,
    out_folder: state.minutesFolder || '',   // 회의록 전용 폴더 (비면 백엔드 폴백)
  });
  overlay(false);
  if (!r.ok) {
    const box = $('#mn-r-status');
    if (box) { box.textContent = r.error || 'HWPX 생성 실패'; box.className = 'ai-status err'; }
    return;
  }
  if (r.warning) toast(r.warning, 'warn', 5000);
  toast('회의록 HWPX 생성 완료! 파일을 엽니다.', 'ok', 4000);
  call('open_file', r.path);
  refreshMinutesDashboard();   // 대시보드 목록 즉시 갱신
}

function initMinutesView() {
  minutesAttachments = [];
  renderMinutesChips();
  setMnStatus('');
  showMinutesStep(1);
  refreshMinutesConvertStatus();
}

/* ===================================================================
   자동 업데이트
=================================================================== */
// 마지막 check 결과 캐시 (start_update 시 재사용)
let _updateInfo = null;
// "나중에" 클릭 시 이번 세션 동안 배너 재표시 억제
let _updateBannerDismissed = false;
// 폴링 인터벌 ID
let _updatePollId = null;

function _setUpdateStatus(msg, opts = {}) {
  const el = $('#update-status-msg');
  if (el) el.textContent = msg;
  const bannerText = $('#update-banner-text');
  if (bannerText && opts.banner) bannerText.textContent = opts.banner;
}

function _hideUpdateBanner() {
  const banner = $('#update-banner');
  if (banner) banner.setAttribute('hidden', '');
}

function _showUpdateBanner(info) {
  if (_updateBannerDismissed) return;
  const banner = $('#update-banner');
  if (!banner) return;
  // 새 버전이 아니면 배너를 띄우지 않는다 (이미 최신인데 잔류 방지)
  if (!info || !info.has_update) { _hideUpdateBanner(); return; }
  const tag = info.latest_tag || '';
  $('#update-banner-text').textContent = `새 버전 ${tag}이(가) 있습니다.`;
  banner.removeAttribute('hidden');
  _updateInfo = info;
}

async function startUpdateFlow(info) {
  if (!info) info = _updateInfo;
  // 동일/구버전 가드 — 이미 최신이면 진행하지 않음
  if (!info || !info.has_update) {
    toast('이미 최신 버전입니다.', 'info');
    _hideUpdateBanner();
    const btnDo = $('#btn-do-update');
    if (btnDo) btnDo.setAttribute('hidden', '');
    return;
  }
  if (!info.asset_url) {
    toast('다운로드 링크를 찾을 수 없습니다.', 'err');
    return;
  }
  // 버튼 비활성화
  ['#btn-do-update', '#update-banner-go'].forEach(sel => {
    const b = $(sel);
    if (b) { b.disabled = true; b.textContent = '준비 중…'; }
  });

  const r = await call('start_update', info.asset_url, info.asset_size || 0);
  if (!r.ok) {
    toast(r.error || '업데이트 시작 실패', 'err');
    ['#btn-do-update', '#update-banner-go'].forEach(sel => {
      const b = $(sel);
      if (b) { b.disabled = false; b.textContent = '지금 업데이트'; }
    });
    return;
  }

  // 폴링 시작
  if (_updatePollId) clearInterval(_updatePollId);
  _updatePollId = setInterval(async () => {
    const s = await call('update_status');
    if (!s.ok) return;
    const phase = s.phase || '';
    const pct = s.pct || 0;

    let label = '';
    if (phase === 'downloading') label = `다운로드 중… ${pct}%`;
    else if (phase === 'extracting') label = `압축 해제 중… ${pct}%`;
    else if (phase === 'ready') label = '준비 완료. 적용 중…';
    else if (phase === 'applying') label = '파일 교체 중…';
    else if (phase === 'error') label = `오류: ${s.error || ''}`;

    _setUpdateStatus(label, { banner: label });

    if (phase === 'ready') {
      clearInterval(_updatePollId);
      _updatePollId = null;
      _setUpdateStatus('재시작 중…', { banner: '재시작합니다…' });
      const ar = await call('apply_update');
      if (!ar.ok) {
        toast(`업데이트 적용 실패: ${ar.error || ''}`, 'err');
        _setUpdateStatus(`적용 실패: ${ar.error || ''}`, { banner: `적용 실패: ${ar.error || ''}` });
        ['#btn-do-update', '#update-banner-go'].forEach(sel => {
          const b = $(sel);
          if (b) { b.disabled = false; b.textContent = '지금 업데이트'; }
        });
      }
      // 성공 시 앱이 곧 종료/재실행되므로 추가 처리 없음
    } else if (phase === 'error') {
      clearInterval(_updatePollId);
      _updatePollId = null;
      toast(`업데이트 실패: ${s.error || ''}`, 'err');
      ['#btn-do-update', '#update-banner-go'].forEach(sel => {
        const b = $(sel);
        if (b) { b.disabled = false; b.textContent = '지금 업데이트'; }
      });
    }
  }, 800);
}

async function checkUpdateManual() {
  const btnCheck = $('#btn-check-update');
  const btnDo = $('#btn-do-update');
  const statusMsg = $('#update-status-msg');
  const notes = $('#update-notes');
  if (btnCheck) { btnCheck.disabled = true; btnCheck.textContent = '확인 중…'; }
  if (statusMsg) statusMsg.textContent = '';
  if (notes) notes.setAttribute('hidden', '');

  const r = await call('check_update');
  if (btnCheck) { btnCheck.disabled = false; btnCheck.textContent = '업데이트 확인'; }
  if (!r.ok) {
    if (statusMsg) statusMsg.textContent = r.error || '확인 실패';
    return;
  }
  _updateInfo = r;
  if (r.has_update) {
    if (statusMsg) statusMsg.textContent = `새 버전 ${r.latest_tag}이(가) 있습니다.`;
    if (notes && r.notes) { notes.textContent = r.notes; notes.removeAttribute('hidden'); }
    if (btnDo) { btnDo.removeAttribute('hidden'); btnDo.disabled = false; btnDo.textContent = '지금 업데이트'; }
    _showUpdateBanner(r);
  } else {
    if (statusMsg) statusMsg.textContent = '최신 버전입니다.';
    if (btnDo) btnDo.setAttribute('hidden', '');
    _hideUpdateBanner();
  }
}

async function checkUpdateSilently() {
  try {
    const r = await call('check_update');
    if (r && r.ok && r.has_update) {
      _updateInfo = r;
      _showUpdateBanner(r);
    }
  } catch (_) { /* 네트워크 오류 시 조용히 무시 */ }
}

/* ===================================================================
   초기화 / 이벤트 바인딩
=================================================================== */
async function init() {
  const r = await call('get_config');
  if (r.ok) state.config = r.config;

  // 네비 (사이드바 = 문서 유형 허브)
  $$('.nav-btn').forEach(b => b.addEventListener('click', () => switchView(b.dataset.view)));
  // 허브 서브탭
  $$('.sub-nav .sub-tab').forEach(t => t.addEventListener('click', () => {
    const hub = t.closest('.view');
    if (hub) switchView(hub.id.replace('hub-', ''), t.dataset.sub);
  }));
  // 견적 필터 탭 — 반드시 #view-dashboard로 스코프 한정 (설정 탭·서브탭과 충돌 방지)
  $$('#view-dashboard .tab').forEach(t => t.addEventListener('click', () => {
    $$('#view-dashboard .tab').forEach(x => x.classList.toggle('active', x === t));
    state.filter = t.dataset.tab; renderGrid();
  }));
  // 검색
  $('#search-input').addEventListener('input', e => { state.search = e.target.value; renderGrid(); });
  // 폴더
  $('#btn-pick-folder').addEventListener('click', async () => {
    const r = await call('pick_folder');
    if (r.ok) { state.folder = r.folder; refreshDashboard(); }
    else if (!r.cancelled) toast(r.error || '폴더 선택 실패', 'err');
  });
  $('#btn-rescan').addEventListener('click', refreshDashboard);
  // 회의록 대시보드
  $('#mnd-search').addEventListener('input', e => { state.mnSearch = e.target.value; renderMinutesGrid(); });
  $('#btn-mnd-pick-folder').addEventListener('click', async () => {
    const r = await call('pick_doc_folder', 'minutes');
    if (r.ok) { state.minutesFolder = r.folder; refreshMinutesDashboard(); }
    else if (!r.cancelled) toast(r.error || '폴더 선택 실패', 'err');
  });
  $('#btn-mnd-rescan').addEventListener('click', refreshMinutesDashboard);
  $('#btn-new-minutes').addEventListener('click', () => {
    _minutesComposeInited = true;   // 명시적 리셋이므로 lazy-init 중복 방지
    initMinutesView();
    switchView('minutes', 'compose');
  });
  // 설정 탭 (data-stab — 견적 필터 탭과 별도 바인딩)
  $$('#settings-tabs .tab').forEach(t =>
    t.addEventListener('click', () => showSettingsTab(t.dataset.stab)));
  // 설정 내 유형별 폴더 변경
  $('#btn-s-quote-folder').addEventListener('click', async () => {
    const r = await call('pick_doc_folder', 'quote');
    if (r.ok) { state.folder = r.folder; renderSettings(); }
    else if (!r.cancelled) toast(r.error || '폴더 선택 실패', 'err');
  });
  $('#btn-s-minutes-folder').addEventListener('click', async () => {
    const r = await call('pick_doc_folder', 'minutes');
    if (r.ok) { state.minutesFolder = r.folder; renderSettings(); }
    else if (!r.cancelled) toast(r.error || '폴더 선택 실패', 'err');
  });
  // 새 견적 (분할 버튼)
  $('#btn-new-quote').addEventListener('click', () => newQuote(false));
  $('#btn-new-dropdown').addEventListener('click', e => { e.stopPropagation(); $('#new-menu').classList.toggle('hidden'); });
  $$('#new-menu button').forEach(b => b.addEventListener('click', () => {
    $('#new-menu').classList.add('hidden');
    newQuote(b.dataset.act === 'ai');
  }));
  document.addEventListener('click', () => $('#new-menu').classList.add('hidden'));

  // 편집기 — 문서 입력 변경 시 재계산
  ['f-recipient', 'f-quote-no', 'f-date', 'f-period', 'f-svc-name', 'f-ref-name', 'f-ref-tel', 'f-target']
    .forEach(id => $('#' + id).addEventListener('input', refreshCalc));
  $('#f-target').addEventListener('blur', e => { const v = parseMoney(e.target.value); e.target.value = v ? commafy(v) : ''; });
  $$('#profit-seg button').forEach(b => b.addEventListener('click', () => { setProfitSeg(b.dataset.v === '1'); refreshCalc(); }));
  $('#btn-auto-no').addEventListener('click', async () => {
    const y = ($('#f-date').value || '').slice(0, 4);
    const r = await call('suggest_quote_no', y);
    if (r.ok) { $('#f-quote-no').value = r.quote_no; refreshCalc(); }
  });
  $('#btn-goalseek').addEventListener('click', runGoalSeek);
  $('#btn-add-exp').addEventListener('click', () => {
    state.quote.expenses.push({ name: '', details: [], qty_text: '', unit_price: null, qty: null });
    renderExpenseRows(); refreshCalc();
  });
  $('#btn-save-json').addEventListener('click', saveQuote);
  $('#btn-gen-hwp').addEventListener('click', () => generate(false));
  $('#btn-gen-both').addEventListener('click', () => generate(true));
  $('#btn-ai-open').addEventListener('click', openAIModal);

  // AI 모달 (2단계 위저드)
  $('#ai-cancel').addEventListener('click', closeAIModal);
  $('#ai-cancel2').addEventListener('click', closeAIModal);
  $('#ai-run').addEventListener('click', runAI);
  $('#ai-back').addEventListener('click', aiBack);
  $('#ai-pick-files').addEventListener('click', async () => {
    const r = await call('pick_convert_files');
    if (r && r.ok && r.paths && r.paths.length) await handleDroppedPaths(r.paths);
  });
  wireDropzoneJS();
  wireMinutesDropzone();
  $('#ai-confirm').addEventListener('click', confirmAIDraft);
  $('#ai-add-exp').addEventListener('click', aiAddExp);
  $('#ai-auto-no').addEventListener('click', async () => {
    const y = ($('#ai-date').value || '').slice(0, 4);
    const r = await call('suggest_quote_no', y);
    if (r.ok) $('#ai-quote-no').value = r.quote_no;
  });
  $('#ai-target').addEventListener('blur', e => { const v = parseMoney(e.target.value); e.target.value = v ? commafy(v) : ''; });
  $('#ai-modal').addEventListener('click', e => { if (e.target.id === 'ai-modal') closeAIModal(); });

  // 회의록
  $('#mn-run').addEventListener('click', runMinutesDraft);
  $('#mn-pick-files').addEventListener('click', async () => {
    const r = await call('pick_convert_files');
    if (r && r.ok && r.paths && r.paths.length) await handleMinutesDroppedPaths(r.paths);
  });
  $('#mn-r-back').addEventListener('click', () => showMinutesStep(1));
  $('#mn-r-add-participant').addEventListener('click', () => addParticipantRow(''));
  $('#mn-r-add-section').addEventListener('click', () => addSectionRow('bullet', ''));
  $('#mn-r-gen').addEventListener('click', generateMinutes);

  // 설정
  $('#s-price-year').addEventListener('change', e => renderPriceTable(e.target.value));
  $('#btn-add-year').addEventListener('click', addYear);
  $('#btn-save-prices').addEventListener('click', savePrices);
  $('#btn-save-maxcnt').addEventListener('click', saveMaxCounts);
  $('#btn-save-labor-ratio').addEventListener('click', saveLaborRatio);
  $('#btn-save-company').addEventListener('click', saveCompany);
  $('#s-ai-provider').addEventListener('change', async () => {
    const p = currentProvider();
    await call('set_ai_provider', p);
    state.config.ai_provider = p;
    renderAIProvider();
  });
  $('#s-ai-model').addEventListener('change', toggleCustomModel);
  $('#btn-refresh-models').addEventListener('click', refreshModels);
  $('#btn-save-key').addEventListener('click', saveKey);
  $('#btn-test-key').addEventListener('click', testKey);
  AI_PROMPT_TYPES.forEach(t => {
    $(`#btn-save-ai-prompt-${t}`).addEventListener('click', () => saveAiPrompt(t));
    $(`#btn-reset-ai-prompt-${t}`).addEventListener('click', () => resetAiPrompt(t));
  });
  // 견적서 템플릿 관리
  $('#btn-pick-tpl').addEventListener('click', pickTemplate);
  $('#btn-scan-tpl').addEventListener('click', scanTemplate);
  initTemplateStatus();
  // 회의록 양식 관리
  $('#btn-pick-mn-tpl').addEventListener('click', pickMinutesTemplate);
  $('#btn-reset-mn-tpl').addEventListener('click', resetMinutesTemplate);
  initMinutesTemplateStatus();

  $('#btn-diag').addEventListener('click', runDiagnose);
  $('#btn-diag-hwp').addEventListener('click', runHwpTest);
  $('#diag-close').addEventListener('click', closeDiag);
  $('#diag-modal').addEventListener('click', e => { if (e.target.id === 'diag-modal') closeDiag(); });

  // 삭제 모달
  $('#del-cancel').addEventListener('click', closeDeleteModal);
  $('#del-confirm').addEventListener('click', confirmDelete);
  $('#del-modal').addEventListener('click', e => { if (e.target.id === 'del-modal') closeDeleteModal(); });

  // Google Drive
  $('#btn-drive-connect').addEventListener('click', driveConnect);
  $('#btn-drive-disconnect').addEventListener('click', driveDisconnect);
  $('#s-drive-folder').addEventListener('blur', saveDriveOptions);
  $('#s-drive-auto').addEventListener('change', saveDriveOptions);

  // 외부 링크 (이벤트 위임 — 기본 브라우저로 열기)
  document.addEventListener('click', e => {
    const a = e.target.closest('.ext-link');
    if (a && a.dataset.url) { e.preventDefault(); call('open_external', a.dataset.url).then(r => { if (r && !r.ok) toast(r.error || '링크 열기 실패', 'warn'); }); }
  });

  // 튜토리얼
  $('#tour-next').addEventListener('click', () => tourShow(_tour.idx + 1, 1));
  $('#tour-prev').addEventListener('click', () => tourShow(_tour.idx - 1, -1));
  $('#tour-skip').addEventListener('click', () => endTour(true));
  $('#btn-tutorial-replay').addEventListener('click', startTour);

  // 초기 화면 — 유형별 폴더 시딩 (doc_folders는 백엔드가 폴백 적용한 실효값)
  const df = (state.config && state.config.doc_folders) || {};
  state.folder = df.quote || (state.config && state.config.last_folder) || '';
  state.minutesFolder = df.minutes || '';
  refreshDashboard();

  // 최초 실행 시 튜토리얼 자동 시작 (=== false: config 미로딩 폴백에선 미작동)
  if (state.config && state.config.tutorial_seen === false) setTimeout(startTour, 400);

  // 업데이트 — 설정 탭 버튼
  $('#btn-check-update').addEventListener('click', checkUpdateManual);
  $('#btn-do-update').addEventListener('click', () => startUpdateFlow(_updateInfo));

  // 업데이트 — 상단 배너
  $('#update-banner-go').addEventListener('click', () => startUpdateFlow(_updateInfo));
  $('#update-banner-later').addEventListener('click', () => {
    _updateBannerDismissed = true;
    const b = $('#update-banner');
    if (b) b.setAttribute('hidden', '');
  });

  // 시작 시 자동 업데이트 확인 (1.5초 지연 — init 완료 후 조용히 실행)
  setTimeout(checkUpdateSilently, 1500);
}

/* pywebview 준비 대기 */
if (window.pywebview && window.pywebview.api) {
  init();
} else {
  window.addEventListener('pywebviewready', init);
  // 폴백: 2초 내 미준비 시 강제 시도
  setTimeout(() => { if (!state.config) init(); }, 2000);
}
