/**
 * Lynx Portfolio — lightweight mobile-friendly dashboard.
 *
 * Talks to the Flask API at the same origin as this page. The bearer
 * token is entered once at login and stored in sessionStorage; it
 * never leaves the browser.
 *
 * No build step, no framework. Plain ES2020 + fetch.
 */

'use strict';

// ─────────────────────────── Config ───────────────────────────

const API = window.location.origin;
const TOKEN_KEY = 'lynx-portfolio-token';

// ─────────────────────────── DOM helpers ───────────────────────────

const $  = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class')      e.className = v;
    else if (k === 'html')  e.innerHTML = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else                    e.setAttribute(k, v);
  }
  for (const c of children) {
    if (c === null || c === undefined) continue;
    e.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return e;
}

function fmtEur(n) {
  if (n === null || n === undefined) return '—';
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(n) + ' €';
}
function fmtPct(n) {
  if (n === null || n === undefined) return '—';
  const sign = n > 0 ? '+' : '';
  return sign + n.toFixed(2) + '%';
}
function pnlClass(n) {
  if (n === null || n === undefined) return '';
  return n > 0 ? 'pos' : n < 0 ? 'neg' : '';
}

// ─────────────────────────── Auth ───────────────────────────

function token()       { return sessionStorage.getItem(TOKEN_KEY); }
function setToken(t)   { sessionStorage.setItem(TOKEN_KEY, t); }
function clearToken()  { sessionStorage.removeItem(TOKEN_KEY); }

async function api(path, opts = {}) {
  const t = token();
  if (!t) throw new Error('not authenticated');
  const headers = { 'Authorization': 'Bearer ' + t, ...(opts.headers || {}) };
  if (opts.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const response = await fetch(API + path, {
    method: opts.method || 'GET',
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (response.status === 401) {
    clearToken(); showLogin();
    throw new Error('unauthorized');
  }
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.status === 204 ? null : response.json();
}

function showLogin() {
  $('#login-overlay').classList.remove('hidden');
  $('#token-input').focus();
}
function hideLogin() {
  $('#login-overlay').classList.add('hidden');
}

$('#login-btn').addEventListener('click', async () => {
  const t = $('#token-input').value.trim();
  if (!t) return;
  setToken(t);
  try {
    await api('/api/version');
    hideLogin();
    refreshAll();
  } catch (exc) {
    alert('Token rejected. Check that the server is running and the token is correct.');
    clearToken();
  }
});
$('#token-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') $('#login-btn').click();
});

$('#logout-btn').addEventListener('click', () => {
  clearToken();
  showLogin();
});

// ─────────────────────────── Tab switching ───────────────────────────

$$('.tab').forEach((btn) => {
  btn.addEventListener('click', () => {
    const name = btn.dataset.tab;
    $$('.tab').forEach(b => b.classList.toggle('active', b === btn));
    $$('.panel').forEach(p => p.classList.toggle('active', p.id === `panel-${name}`));
  });
});

$('#refresh-btn').addEventListener('click', refreshAll);

// Theme cycling — rotate through a built-in set of CSS variables.
const WEB_THEMES = [
  { // Lynx Theme (default — financial-first: vivid green/red, neutral chrome)
    '--bg':'#0f1419','--bg-alt':'#171c23','--surface':'#171c23','--panel':'#252b33',
    '--text':'#e6eaf0','--subtle':'#9aa5b5','--primary':'#3daee9','--accent':'#facc15',
    '--success':'#22c55e','--warning':'#f59e0b','--error':'#ef4444',
  },
  { // Lynx Theme Light (daytime — cream bg, vivid gain/loss)
    '--bg':'#fafaf9','--bg-alt':'#f5f5f4','--surface':'#f5f5f4','--panel':'#e7e5e4',
    '--text':'#1c1917','--subtle':'#78716c','--primary':'#0369a1','--accent':'#ca8a04',
    '--success':'#16a34a','--warning':'#d97706','--error':'#b91c1c',
  },
  { // Catppuccin Mocha
    '--bg':'#1e1e2e','--bg-alt':'#181825','--surface':'#313244','--panel':'#45475a',
    '--text':'#cdd6f4','--subtle':'#a6adc8','--primary':'#89b4fa','--accent':'#f5c2e7',
    '--success':'#a6e3a1','--warning':'#f9e2af','--error':'#f38ba8',
  },
  { // Dracula
    '--bg':'#282a36','--bg-alt':'#21222c','--surface':'#44475a','--panel':'#6272a4',
    '--text':'#f8f8f2','--subtle':'#a4a6b8','--primary':'#bd93f9','--accent':'#ff79c6',
    '--success':'#50fa7b','--warning':'#f1fa8c','--error':'#ff5555',
  },
  { // Tokyo Night
    '--bg':'#1a1b26','--bg-alt':'#16161e','--surface':'#292e42','--panel':'#3b3f5a',
    '--text':'#c0caf5','--subtle':'#9aa5ce','--primary':'#7aa2f7','--accent':'#bb9af7',
    '--success':'#9ece6a','--warning':'#e0af68','--error':'#f7768e',
  },
  { // Nord
    '--bg':'#2e3440','--bg-alt':'#272b35','--surface':'#3b4252','--panel':'#434c5e',
    '--text':'#eceff4','--subtle':'#d8dee9','--primary':'#88c0d0','--accent':'#b48ead',
    '--success':'#a3be8c','--warning':'#ebcb8b','--error':'#bf616a',
  },
  { // Gruvbox Dark
    '--bg':'#282828','--bg-alt':'#1d2021','--surface':'#3c3836','--panel':'#504945',
    '--text':'#ebdbb2','--subtle':'#bdae93','--primary':'#83a598','--accent':'#d3869b',
    '--success':'#b8bb26','--warning':'#fabd2f','--error':'#fb4934',
  },
  { // Solarized Light
    '--bg':'#fdf6e3','--bg-alt':'#eee8d5','--surface':'#eee8d5','--panel':'#93a1a1',
    '--text':'#657b83','--subtle':'#93a1a1','--primary':'#268bd2','--accent':'#d33682',
    '--success':'#859900','--warning':'#b58900','--error':'#dc322f',
  },
];
let _themeIdx = 0;
$('#theme-btn').addEventListener('click', () => {
  _themeIdx = (_themeIdx + 1) % WEB_THEMES.length;
  const t = WEB_THEMES[_themeIdx];
  const root = document.documentElement;
  for (const [k, v] of Object.entries(t)) root.style.setProperty(k, v);
  sessionStorage.setItem('lynx-theme-idx', String(_themeIdx));
});
const savedIdx = Number(sessionStorage.getItem('lynx-theme-idx') || 0);
if (savedIdx > 0) {
  _themeIdx = savedIdx - 1;
  $('#theme-btn').click();
}

// ─────────────────────────── Refresh logic ───────────────────────────

async function refreshAll() {
  const now = new Date();
  $('#last-sync').textContent = 'Syncing…';
  try {
    const [dash, positions, watch, alerts] = await Promise.all([
      api('/api/dashboard'),
      api('/api/portfolio'),
      api('/api/watchlists'),
      api('/api/price-alerts'),
    ]);
    renderStats(dash.stats);
    renderPositions(positions);
    renderSectors(dash.sectors);
    renderMovers(dash.movers);
    renderAlerts([...dash.alerts, ...formatPriceAlerts(alerts)]);
    renderWatchlist(watch);
    $('#last-sync').textContent = 'Synced ' + now.toLocaleTimeString();
  } catch (exc) {
    $('#last-sync').textContent = 'Error: ' + exc.message;
  }
}

// ─────────────────────────── Renderers ───────────────────────────

function renderStats(stats) {
  if (!stats) return;
  const cards = [
    ['Positions', stats.positions, ''],
    ['Market value', fmtEur(stats.total_value_eur), ''],
    ['Invested', fmtEur(stats.total_invested_eur), ''],
    ['Total PnL', fmtEur(stats.total_pnl_eur), pnlClass(stats.total_pnl_eur),
      fmtPct(stats.total_pnl_pct)],
    ['Day change', fmtEur(stats.day_change_eur), pnlClass(stats.day_change_eur),
      fmtPct(stats.day_change_pct)],
  ];
  const container = $('#stats-cards');
  container.innerHTML = '';
  for (const [label, value, cls, sub] of cards) {
    container.append(el('div', { class: 'card' },
      el('span', { class: 'label' }, label),
      el('span', { class: `value ${cls}` }, value),
      sub ? el('span', { class: `sub ${cls}` }, sub) : null,
    ));
  }

  // Sparkline placeholder — shows text representation since we don't
  // fetch price history for the whole portfolio yet.
  const spark = $('#spark-strip');
  spark.textContent = `▂▃▄▅▆▇█▇▆▆▅▄▅▆▇█   ${fmtPct(stats.total_pnl_pct)} since entry`;
}

function renderPositions(rows) {
  const body = $('#positions-table tbody');
  body.innerHTML = '';
  for (const r of rows || []) {
    body.append(el('tr', {},
      el('td', { class: 'ticker' }, r.ticker),
      el('td', {}, (r.name || '').slice(0, 40)),
      el('td', { class: 'num' }, r.shares),
      el('td', { class: 'num' }, (r.current_price ?? '—').toLocaleString()),
      el('td', { class: 'num' }, fmtEur(r.market_value_eur)),
      el('td', { class: `num ${pnlClass(r.pnl_eur)}` }, fmtEur(r.pnl_eur)),
      el('td', { class: `num ${pnlClass(r.pnl_pct)}` }, fmtPct(r.pnl_pct)),
    ));
  }
  if (!rows || !rows.length) {
    body.append(el('tr', {}, el('td', { colspan: 7, class: 'subtle' }, 'No positions yet.')));
  }
}

function renderSectors(rows) {
  const body = $('#sectors-table tbody');
  body.innerHTML = '';
  for (const r of rows || []) {
    body.append(el('tr', {},
      el('td', {}, r.sector),
      el('td', { class: 'num' }, r.positions),
      el('td', { class: 'num' }, fmtEur(r.value_eur)),
      el('td', { class: 'num' }, fmtPct(r.pct_of_portfolio)),
      el('td', {},
        el('div', { class: 'bar', style: `width:${Math.min(100, r.pct_of_portfolio)}%` }),
      ),
    ));
  }
  if (!rows || !rows.length) {
    body.append(el('tr', {}, el('td', { colspan: 5, class: 'subtle' }, 'No data.')));
  }
}

function renderMovers(movers) {
  for (const [key, tbody] of [['gainers', '#gainers-table tbody'],
                              ['losers',  '#losers-table tbody']]) {
    const body = $(tbody);
    body.innerHTML = '';
    const rows = (movers && movers[key]) || [];
    if (!rows.length) {
      body.append(el('tr', {}, el('td', { colspan: 3, class: 'subtle' }, '—')));
      continue;
    }
    for (const r of rows) {
      body.append(el('tr', {},
        el('td', { class: 'ticker' }, r.ticker),
        el('td', {}, (r.name || '').slice(0, 30)),
        el('td', { class: `num ${pnlClass(r.day_change_pct)}` }, fmtPct(r.day_change_pct)),
      ));
    }
  }
}

function renderAlerts(alerts) {
  const body = $('#alerts-table tbody');
  body.innerHTML = '';
  if (!alerts || !alerts.length) {
    body.append(el('tr', {},
      el('td', { colspan: 4, class: 'subtle' }, 'No alerts. Portfolio looks healthy.'),
    ));
    return;
  }
  for (const a of alerts) {
    body.append(el('tr', {},
      el('td', {}, el('span', { class: `sev sev-${a.severity}` }, a.severity)),
      el('td', {}, a.kind),
      el('td', { class: 'ticker' }, a.ticker || '—'),
      el('td', {}, a.message),
    ));
  }
}

function formatPriceAlerts(priceAlerts) {
  // Surface triggered price-threshold alerts as dashboard-style alerts.
  return (priceAlerts || [])
    .filter(a => a.triggered_at)
    .map(a => ({
      severity: 'warn',
      kind: 'price-alert',
      ticker: a.ticker,
      message: `${a.ticker} ${a.condition} ${a.threshold} — triggered ${a.triggered_at.slice(0,19)}`,
    }));
}

function renderWatchlist(items) {
  const body = $('#watch-table tbody');
  body.innerHTML = '';
  if (!items || !items.length) {
    body.append(el('tr', {},
      el('td', { colspan: 4, class: 'subtle' }, 'Watchlist is empty.'),
    ));
    return;
  }
  for (const w of items) {
    const rm = el('button', { class: 'remove-btn' }, '✕');
    rm.addEventListener('click', async () => {
      if (!confirm(`Remove ${w.ticker}?`)) return;
      await api(`/api/watchlists/${w.ticker}?name=${encodeURIComponent(w.name)}`, {
        method: 'DELETE',
      });
      refreshAll();
    });
    body.append(el('tr', {},
      el('td', {}, w.name),
      el('td', { class: 'ticker' }, w.ticker),
      el('td', {}, w.note || ''),
      el('td', {}, rm),
    ));
  }
}

$('#watch-add-btn').addEventListener('click', async () => {
  const input = $('#watch-input');
  const ticker = input.value.trim().toUpperCase();
  if (!ticker) return;
  try {
    await api('/api/watchlists', { method: 'POST', body: { ticker } });
    input.value = '';
    refreshAll();
  } catch (exc) {
    alert('Failed: ' + exc.message);
  }
});

// ─────────────────────────── Boot ───────────────────────────

if (!token()) {
  showLogin();
} else {
  refreshAll();
}

// Auto-refresh every 60 seconds when the tab is visible.
setInterval(() => {
  if (document.visibilityState === 'visible' && token()) refreshAll();
}, 60_000);
