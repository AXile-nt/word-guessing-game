/* 语义猜词 · 前端 (调用 Python 后端, 支持任意词语) */
'use strict';

const API = '';  // 同源, 空。后端在 http://localhost:8000
const NEAR_RANK = 1000;

const $ = id => document.getElementById(id);
const state = {
  total: 0,
  guesses: [],
  round: 1,
  hintsLeft: 3,
  target: null,      // 仅调试
  busy: false,
};

/* ---------- API ---------- */
async function api(path, data) {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data || {}),
  });
  return r.json();
}

/* ---------- 工具 ---------- */
function colorFor(percent) {
  const h = (percent / 100) * 120;   // 0红..120绿
  return `hsl(${h}, 70%, 50%)`;
}
// 百分比格式化: 始终保留 5 位小数(63.7 -> "63.70000"), 精确区分极高分
function fmtPct(p) { return p.toFixed(5); }

/* ---------- 新一轮 ---------- */
async function newRound() {
  state.guesses = [];
  state.hintsLeft = 3;
  $('guessCount').textContent = '0';
  $('roundLabel').textContent = `第 ${state.round} 局`;
  $('guessList').innerHTML = '';
  $('lastFeedback').innerHTML = '<div class="fb-empty">输入你的第一个词开始 ↑</div>';
  $('guessInput').value = '';
  // 显示"生成提示中"
  $('hint1').textContent = '… 字';
  $('hint2').textContent = '生成中…';
  const res = await api('/new', {});
  state.total = res.total;
  state.target = res.target || null;
  // 显示提示
  $('hint1').textContent = `${res.hint1} 字`;
  $('hint2').textContent = res.hint2;
  updateHintBtn();
  $('guessInput').focus();
}

/* ---------- 提交猜测 ---------- */
async function submitGuess(raw) {
  const word = (raw || '').trim();
  if (!word || state.busy) return;
  state.busy = true;
  $('submitBtn').disabled = true;
  const fb = $('lastFeedback');
  fb.innerHTML = '<div class="fb-empty">计算中…</div>';

  // 重复校验 (前端层; 后端不感知历史)
  if (state.guesses.some(g => g.word === word)) {
    fb.innerHTML = `<div class="fb-rank">“${escapeHtml(word)}” 已经猜过了。</div>`;
    state.busy = false; $('submitBtn').disabled = false; return;
  }

  try {
    const res = await api('/guess', { word });
    if (res.error) {
      fb.innerHTML = `<div class="fb-rank">出错了: ${escapeHtml(res.error)}</div>`;
    } else {
      const g = { word: res.word, percent: res.percent, rank: res.rank, sim: res.sim };
      state.guesses.push(g);
      $('guessCount').textContent = state.guesses.length;
      $('guessInput').value = '';
      renderFeedback(g);
      renderList();
      if (res.hit) setTimeout(win, 400);
    }
  } catch (e) {
    fb.innerHTML = `<div class="fb-rank">无法连接后端。请先运行 <code>server.py</code>(或双击 启动游戏.bat)。</div>`;
  }
  state.busy = false;
  $('submitBtn').disabled = false;
  $('guessInput').focus();
}

/* ---------- 渲染 ---------- */
function renderFeedback(g) {
  const color = colorFor(g.percent);
  const fb = $('lastFeedback');
  let rankTxt;
  if (g.rank === 1) rankTxt = '🎯 就是它！';
  else if (g.rank <= 10) rankTxt = `🔥 极其接近！排名第 <b>${g.rank}</b>`;
  else if (g.rank <= NEAR_RANK) rankTxt = `排名 <b>${g.rank}</b>，越来越近了`;
  else rankTxt = `排名 <b>${g.rank}</b> / ${state.total}，还很远`;
  fb.innerHTML = `
    <div class="fb-word">${escapeHtml(g.word)}</div>
    <div class="fb-meter"><i style="width:${g.percent}%;background:${color}"></i></div>
    <div class="fb-score">相似度 <b style="color:${color}">${fmtPct(g.percent)}%</b></div>
    <div class="fb-rank">${rankTxt}</div>`;
}

function renderList() {
  const ul = $('guessList');
  const sorted = [...state.guesses].sort((a, b) => b.sim - a.sim);
  ul.innerHTML = sorted.map(g => {
    const hit = g.rank === 1;
    const color = hit ? '#2ecc71' : colorFor(g.percent);
    return `<li class="${hit ? 'g-hit' : ''}" style="border-left-color:${color}">
      <span class="g-word">${escapeHtml(g.word)}</span>
      <span class="g-rank">#<b>${g.rank}</b></span>
      <span class="g-pct" style="color:${hit ? '#fff' : color}">${fmtPct(g.percent)}%</span>
    </li>`;
  }).join('');
}

function updateHintBtn() {
  $('hintBtn').textContent = `💡 提示 (${state.hintsLeft})`;
  $('hintBtn').disabled = state.hintsLeft <= 0;
}

/* ---------- 提示: 向后端要一个接近词 ---------- */
async function useHint() {
  if (state.hintsLeft <= 0 || state.busy) return;
  // 用一个特殊请求让后端给提示(后端按当前 target 返回排名更靠前的词)
  state.busy = true;
  try {
    const res = await api('/guess', { word: '__HINT__' });
    if (res.word && res.word !== '__HINT__') {
      state.hintsLeft--;
      const g = { word: res.word + ' 💡', percent: res.percent, rank: res.rank, sim: res.sim };
      state.guesses.push(g);
      $('guessCount').textContent = state.guesses.length;
      renderFeedback({ word: res.word + ' (提示)', percent: g.percent, rank: g.rank, sim: g.sim });
      renderList();
      updateHintBtn();
    }
  } catch (e) { /* ignore */ }
  state.busy = false;
}

/* ---------- 胜利 ---------- */
function win() {
  const best = parseInt(localStorage.getItem('semguess_best') || '999999', 10);
  const isNewBest = state.guesses.length < best;
  if (isNewBest) localStorage.setItem('semguess_best', String(state.guesses.length));
  const wins = parseInt(localStorage.getItem('semguess_wins') || '0', 10) + 1;
  localStorage.setItem('semguess_wins', String(wins));
  // 目标词从列表里取(命中那个)
  const hit = state.guesses.find(g => g.rank === 1);
  $('winWord').textContent = hit ? hit.word : '目标词';
  $('winSub').textContent = `用了 ${state.guesses.length} 次猜中`;
  $('winBest').textContent = isNewBest
    ? `🏆 新纪录！(累计过关 ${wins})` : `累计过关 ${wins} · 最佳 ${best} 次`;
  $('winOverlay').classList.remove('hidden');
}

/* ---------- 小工具 ---------- */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}

/* ---------- 屏幕切换 ---------- */
function showStart() { $('startScreen').classList.remove('hidden'); $('gameScreen').classList.add('hidden'); }
function showGame() { $('startScreen').classList.add('hidden'); $('gameScreen').classList.remove('hidden'); }

/* ---------- 事件 + 启动 ---------- */
function bind() {
  const input = $('guessInput');
  $('submitBtn').addEventListener('click', () => submitGuess(input.value));
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') submitGuess(input.value);
  });
  $('hintBtn').addEventListener('click', useHint);
  $('newBtn').addEventListener('click', async () => {
    if (confirm('放弃本局, 换一个新词?')) { state.round++; await newRound(); }
  });
  $('playAgain').addEventListener('click', async () => {
    $('winOverlay').classList.add('hidden');
    state.round++; await newRound();
  });
  // 开始按钮: 连接后端 -> 进游戏页
  $('startBtn').addEventListener('click', startGame);
}

async function startGame() {
  const btn = $('startBtn');
  const status = $('startStatus');
  btn.disabled = true;
  btn.textContent = '准备中…';
  status.textContent = '正在连接游戏服务器…';
  // 轮询后端就绪
  let ok = false;
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch('/status').then(r => r.json());
      if (res.ready) { ok = true; break; }
    } catch (e) { /* 还没起 */ }
    status.textContent = `等待服务器启动… (${i+1}s)。若超过30秒, 请确认已双击 启动游戏.bat`;
    await new Promise(r => setTimeout(r, 1000));
  }
  if (!ok) {
    btn.disabled = false; btn.textContent = '开始游戏';
    status.textContent = '❌ 无法连接服务器。请先运行 启动游戏.bat';
    return;
  }
  status.textContent = '服务器就绪, 进入游戏…';
  showGame();
  await newRound();
}

async function init() {
  bind();
  // 先显示开始页, 不立即加载后端(降低首屏负担)
  showStart();
}
init();
