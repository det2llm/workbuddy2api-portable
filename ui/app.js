/* WorkBuddy2API 控制面板前端逻辑 */
'use strict';

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

let STATE = null;
let logSince = 0;
let pendingAuth = null;
let keyVisible = false;
let MODEL_LIST = [];
let currentRealm = 'cn';

/* ───────── 工具 ───────── */
async function api(path, method, body) {
  const opt = { method: method || 'GET', headers: {} };
  if (body) {
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(body);
  }
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({ ok: false, error: '返回不是 JSON' }));
  if (!j.ok && j.error) toast(j.error, true);
  return j;
}

function toast(msg, isErr) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast show' + (isErr ? ' err' : ' ok');
  clearTimeout(t._t);
  t._t = setTimeout(() => { t.className = 'toast'; }, 2800);
}

function copy(text) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => toast('已复制'), () => fallback());
  } else fallback();
  function fallback() {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); toast('已复制'); } catch (e) { toast('复制失败', true); }
    document.body.removeChild(ta);
  }
}

function stat(label, value, cls) {
  return `<div class="stat"><span>${label}</span><b class="${cls || ''}">${value}</b></div>`;
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function goto(view) {
  $$('.nav-item').forEach((x) => x.classList.toggle('active', x.dataset.view === view));
  $$('.view').forEach((v) => v.classList.toggle('active', v.id === 'view-' + view));
}

/* ───────── 状态刷新 ───────── */
async function refreshState() {
  const r = await api('/api/state');
  if (!r.ok) return;
  STATE = r.data;
  renderTop();
  renderInstall();
  renderAccounts();
  renderRun();
}

function renderTop() {
  const s = STATE.service;
  $('#svcDot').className = 'dot ' + (s.running ? (s.health ? 'on' : 'bad') : 'off');
  $('#svcText').textContent = s.running
    ? (s.health ? '运行中 · 健康' : '运行中 · 探活失败') : '已停止';
  $('#svcPort').textContent = s.port;
  $('#svcPid').textContent = s.pid || '-';
  $('#svcAcc').textContent = STATE.accounts.length;
  $('#svcModel').textContent = STATE.models.count + (STATE.models.source === '文档' ? '(文档)' : '');
  $('#sidePath').textContent = STATE.root;
}

function renderInstall() {
  const e = STATE.env, c = STATE.config;
  $('#envPy').textContent = e.python + (e.python_bundled ? '（项目自带 runtime）' : '（系统 Python）');
  $('#envPyExe').textContent = e.python_exe || '-';
  $('#envGo').textContent = e.go ? '已安装' : '未安装（便携版无需）';
  $('#envExe').textContent = e.exe.exists ? `存在 · ${e.exe.size_mb}MB · ${e.exe.mtime}` : '缺失！';
  $('#envSrc').textContent = e.src ? '存在（可 go build）' : '无（便携版）';
  if (document.activeElement !== $('#inPort')) $('#inPort').value = c.port;
  if (document.activeElement !== $('#inKey')) $('#inKey').value = c.api_key;
  if (document.activeElement !== $('#inHost')) $('#inHost').value = STATE.lan_ip;
  $('#lanHint').textContent = `自动探测到：${STATE.lan_ip}`;
  $('#chkAutostart').checked = STATE.autostart.enabled;
  $('#autoBadge').textContent = STATE.autostart.enabled ? '已启用' : '未启用';
  $('#autoBadge').className = 'badge ' + (STATE.autostart.enabled ? 'on' : 'off');
  $('#autoPath').textContent = STATE.autostart.path || '';

  const key = keyVisible ? (c.api_key || '（未设置）') : (c.api_key ? '••••••••' : '（未设置）');
  $('#accessList').innerHTML =
    `<div class="kv"><span>网关地址</span><b>${esc(STATE.base_url)}</b></div>` +
    `<div class="kv"><span>本机地址</span><b>${esc(STATE.local_url)}</b></div>` +
    `<div class="kv"><span>API 密钥</span><b>${esc(key)}</b></div>` +
    `<div class="kv"><span>探活地址</span><b>${esc(STATE.healthz)}</b></div>` +
    `<div class="kv"><span>局域网 IP</span><b>${esc(STATE.lan_ip)}</b></div>` +
    `<div class="kv"><span>日志文件</span><b>${esc(STATE.log_file)}</b></div>`;
  $('#guideBox').value = STATE.client_guide || '（尚未生成客户端配置.md，先执行一次上面的安装）';
}

function renderAccounts() {
  const tb = $('#tblAcc').querySelector('tbody');
  const list = STATE.accounts;
  if (!list.length) {
    tb.innerHTML = '<tr><td class="empty" colspan="6">auths/ 下还没有账号，先点上面的「获取登录链接」</td></tr>';
  } else {
    tb.innerHTML = list.map((a) => {
      let left = '-';
      if (a.remain_h != null) {
        left = a.expired ? `已过期 (${a.expire_at})`
          : (a.remain_h > 48 ? `${Math.round(a.remain_h / 24)} 天` : `${a.remain_h} 小时`);
      }
      const cls = a.expired ? 'bad' : (a.remain_h != null && a.remain_h < 24 ? 'warn' : 'ok');
      return `<tr>
        <td>${esc(a.nickname)}</td>
        <td class="mono">${esc(a.uid)}</td>
        <td>${esc(a.realm)}</td>
        <td class="${cls}">${esc(left)}</td>
        <td class="mono">${esc(a.file)}</td>
        <td><button class="btn ghost sm" data-del="${esc(a.file)}">删除</button></td>
      </tr>`;
    }).join('');
    tb.querySelectorAll('[data-del]').forEach((b) => {
      b.onclick = async () => {
        if (!confirm('确定删除账号文件 ' + b.dataset.del + ' 吗？')) return;
        const r = await api('/api/account/delete', 'POST', { file: b.dataset.del });
        if (r.ok) { toast('已删除'); refreshState(); }
      };
    });
  }
}

function renderRun() {
  const s = STATE.service;
  $('#statGridRun').innerHTML =
    stat('运行状态', s.running ? (s.health ? '运行中 · 健康' : '运行中 · 探活失败') : '已停止',
      s.running ? (s.health ? 'ok' : 'warn') : 'bad') +
    stat('PID / 端口', `${s.pid || '-'} / ${s.port}`) +
    stat('启动方式', s.mode === 'console' ? '前台' : (s.mode === 'hidden' ? '后台' : (s.running ? '外部' : '-'))) +
    stat('启动时间', s.started_at || '-') +
    stat('探活 /healthz', s.health ? '正常' : (s.running ? '失败' : '-'), s.health ? 'ok' : 'bad') +
    stat('鉴权', STATE.config.api_key ? '已开启' : '未开启', STATE.config.api_key ? 'ok' : 'warn');
}

/* ───────── 模型列表 ───────── */
function renderModels() {
  const kw = ($('#modelFilter').value || '').trim().toLowerCase();
  const rows = MODEL_LIST.filter((m) =>
    !kw || (m.id || '').toLowerCase().includes(kw) || (m.name || '').toLowerCase().includes(kw));
  const tb = $('#tblModels').querySelector('tbody');
  if (!MODEL_LIST.length) {
    tb.innerHTML = '<tr><td class="empty" colspan="5">还没有拉到模型列表，点「重新拉取模型列表」或先完成添加账号</td></tr>';
  } else if (!rows.length) {
    tb.innerHTML = '<tr><td class="empty" colspan="5">没有匹配的模型</td></tr>';
  } else {
    tb.innerHTML = rows.map((m) => `<tr>
      <td class="mono">${esc(m.id)}</td>
      <td>${esc(m.name || '-')}</td>
      <td>${esc(m.credits || '-')}</td>
      <td class="desc">${esc(m.description || '')}</td>
      <td><button class="btn ghost sm" data-mid="${esc(m.id)}">复制 ID</button></td>
    </tr>`).join('');
    tb.querySelectorAll('[data-mid]').forEach((b) => {
      b.onclick = () => copy(b.dataset.mid);
    });
  }
  $('#modelBadge').textContent = `${MODEL_LIST.length} 个`;
  $('#modelBadge').className = 'badge' + (MODEL_LIST.length ? ' on' : ' off');
}

async function loadModels(silent) {
  const r = await api('/api/models/list', 'POST', {});
  if (!r.ok) return;
  MODEL_LIST = r.models || [];
  $('#modelMsg').textContent = `来源：${r.source}${r.count ? '' : '（网关未运行或账号未加载）'}`;
  renderModels();
  if (!silent) toast(MODEL_LIST.length ? `已拉取 ${MODEL_LIST.length} 个模型` : '未取到模型，检查网关是否运行');
}

/* ───────── 日志 ───────── */
async function pollLogs() {
  try {
    const r = await fetch('/api/logs?since=' + logSince);
    const j = await r.json();
    if (j.lines && j.lines.length) {
      const body = $('#logBody');
      const frag = document.createDocumentFragment();
      j.lines.forEach((l) => {
        const d = document.createElement('div');
        d.className = 'lg ' + l.level;
        d.innerHTML = `<span class="t">${esc(l.t)}</span><span class="m">${esc(l.text)}</span>`;
        frag.appendChild(d);
        logSince = Math.max(logSince, l.id);
      });
      body.appendChild(frag);
      while (body.childElementCount > 1500) body.removeChild(body.firstChild);
      if ($('#chkAutoscroll').checked) body.scrollTop = body.scrollHeight;
    }
  } catch (e) { /* 忽略轮询错误 */ }
}

/* ───────── 步骤 1：安装 / 配置 ───────── */
function collectInstall(startNow) {
  const mode = ($$('input[name=keymode]').find((x) => x.checked) || {}).value || 'custom';
  let key = $('#inKey').value.trim();
  if (mode === 'none') key = '';
  if (mode === 'random' && !key) {
    key = 'sk-' + Math.random().toString(36).slice(2, 14) + Math.random().toString(36).slice(2, 14);
    $('#inKey').value = key;
  }
  return {
    port: $('#inPort').value.trim() || '8080',
    api_key: key,
    host: $('#inHost').value.trim(),
    autostart: $('#chkAutostart').checked,
    start_now: !!startNow,
    refresh_models: $('#chkModels').checked,
  };
}

async function runInstall(startNow) {
  const btn = startNow ? $('#btnInstall') : $('#btnSaveCfg');
  btn.disabled = true;
  const r = await api('/api/install', 'POST', collectInstall(startNow));
  btn.disabled = false;
  if (!r.ok) return;
  $('#installPreview').innerHTML =
    `<b>已完成。</b><br>网关地址：<code>${esc(r.base_url || STATE.base_url)}</code><br>` +
    `探活地址：<code>${esc(STATE.healthz)}</code><br>` +
    `已生成 <code>config.json</code> / <code>4_run.bat</code> / <code>4_run-hidden.vbs</code>` +
    (r.models ? `<br>模型清单：${esc(r.models.msg || '')}` : '');
  toast('配置已应用');
  refreshState();
}

/* ───────── 侧栏二维码 ───────── */
const QR_KEY = 'wb2a_qr_closed';

function syncQr() {
  const closed = localStorage.getItem(QR_KEY) === '1';
  $('#qrBox').hidden = closed;
  $('#btnQrShow').hidden = !closed;
}

function initQr() {
  const img = $('#qrImg');
  img.onerror = () => { $('#qrBox').hidden = true; $('#btnQrShow').hidden = true; };
  if (img.complete && img.naturalWidth === 0) { $('#qrBox').hidden = true; }
  syncQr();
  $('#btnQrClose').onclick = () => {
    localStorage.setItem(QR_KEY, '1');
    syncQr();
    toast('已关闭，点底部「显示二维码」可重新显示');
  };
  $('#btnQrShow').onclick = () => { localStorage.removeItem(QR_KEY); syncQr(); };
}

/* ───────── 启动 / 停止 ───────── */
function runMode() {
  return ($$('input[name=runmode]').find((x) => x.checked) || {}).value || 'hidden';
}
async function doStart() {
  const mode = runMode();
  const r = await api('/api/service/start', 'POST', { mode });
  if (r.ok) toast(mode === 'console' ? '已前台启动（已弹出控制台窗口）' : '已后台启动');
  refreshState();
}
async function doStop() {
  const r = await api('/api/service/stop', 'POST', {});
  if (r.ok) toast(r.killed && r.killed.length ? '已停止 PID ' + r.killed.join(',') : '没有运行中的网关');
  refreshState();
}
async function doRestart() {
  const mode = runMode();
  const r = await api('/api/service/restart', 'POST', { mode });
  if (r.ok) toast('已重启');
  refreshState();
}
async function setAuto(on) {
  const r = await api('/api/autostart', 'POST', { enabled: on });
  if (r.ok) toast(r.msg || '已更新');
  refreshState();
}

/* ───────── 事件绑定 ───────── */
function bind() {
  $$('.nav-item').forEach((it) => { it.onclick = () => goto(it.dataset.view); });

  $('#btnRefresh').onclick = () => { refreshState(); toast('已刷新'); };
  $('#btnQuickStart').onclick = doStart;
  $('#btnQuickStop').onclick = doStop;
  $('#btnOpenRoot').onclick = () => api('/api/open', 'POST', { target: 'root' });

  // ── 步骤 1
  $('#btnCheckPort').onclick = async () => {
    const r = await api('/api/port/check', 'POST', { port: $('#inPort').value.trim() });
    if (!r.ok) return;
    const h = $('#portHint');
    h.textContent = r.pids.length
      ? `端口 ${r.port} 已被占用（PID ${r.pids.join(', ')}）`
      : `端口 ${r.port} 空闲，可以放心使用。`;
    h.style.color = r.pids.length ? '#d97706' : '#16a34a';
  };
  $('#btnKillPort').onclick = async () => {
    const port = parseInt($('#inPort').value.trim(), 10);
    if (!confirm(`确定结束占用端口 ${port} 的进程吗？`)) return;
    const r = await api('/api/port/kill', 'POST', { port });
    if (r.ok) toast(r.killed.length ? '已结束 PID ' + r.killed.join(',') : '该端口没有占用进程');
    refreshState();
  };
  $$('input[name=keymode]').forEach((x) => {
    x.onchange = () => { if (x.value === 'none') $('#inKey').value = ''; };
  });
  $('#btnGenKey').onclick = () => {
    $('#inKey').value = 'sk-' + Math.random().toString(36).slice(2, 16) + Math.random().toString(36).slice(2, 12);
    $$('input[name=keymode]').find((r) => r.value === 'custom').checked = true;
  };
  $('#btnUseLan').onclick = () => { $('#inHost').value = STATE.lan_ip; };
  $('#btnInstall').onclick = () => runInstall(true);
  $('#btnSaveCfg').onclick = () => runInstall(false);
  $('#btnGotoStep2').onclick = () => goto('account');
  $('#btnCopyBase').onclick = () => copy(STATE.base_url);
  $('#btnShowKey').onclick = () => { keyVisible = !keyVisible; renderInstall(); };
  $('#btnCopyGuide').onclick = () => copy($('#guideBox').value);

  // ── 步骤 2
  $$('input[name=realm]').forEach((x) => { x.onchange = () => { currentRealm = x.value; }; });
  $('#btnGetUrl').onclick = async () => {
    const b = $('#btnGetUrl');
    b.disabled = true; b.textContent = '获取中…';
    const r = await api('/api/account/begin', 'POST', { realm: currentRealm });
    b.disabled = false; b.textContent = '重新获取登录链接';
    if (!r.ok) return;
    pendingAuth = r;
    $('#authBox').hidden = false;
    $('#authUrl').textContent = r.auth_url;
    $('#authUrl').href = r.auth_url;
    $('#btnFinishLogin').disabled = false;
    $('#acctResult').innerHTML = '';
  };
  $('#btnOpenUrl').onclick = () => { if (pendingAuth) window.open(pendingAuth.auth_url, '_blank'); };
  $('#btnCopyUrl').onclick = () => { if (pendingAuth) copy(pendingAuth.auth_url); };
  $('#btnFinishLogin').onclick = async () => {
    if (!pendingAuth) return;
    const b = $('#btnFinishLogin');
    b.disabled = true; b.textContent = '处理中…（会重启网关并拉取模型）';
    const r = await api('/api/account/complete', 'POST', {
      realm: pendingAuth.realm,
      state: pendingAuth.state,
      auto: $('#chkAutoAfter').checked,
    });
    b.disabled = false; b.textContent = '我已完成登录，完成添加';
    if (!r.ok) {
      $('#acctResult').innerHTML = '<span class="err">未完成：' + esc(r.error || '') + '</span>';
      return;
    }
    const m = r.models || {};
    $('#acctResult').innerHTML =
      `<span class="ok">添加成功！</span> 昵称 ${esc(r.nickname)} · UID <code>${esc(r.uid)}</code>` +
      `<br>已保存 <code>${esc(r.file)}</code>` +
      (r.checkin ? `<br>每日签到：${esc(r.checkin)}` : '') +
      `<br>网关：<b>${r.gateway && r.gateway.health ? '已重载，探活正常' : '未就绪，请到步骤 ③ 手动启动'}</b>` +
      `<br>模型列表：<b>${esc((m.count || 0) + ' 个')}</b>（来源：${esc(m.source || '-')}）`;
    pendingAuth = null;
    $('#authBox').hidden = true;
    if (m.list) { MODEL_LIST = m.list; $('#modelMsg').textContent = `来源：${m.source}`; renderModels(); }
    refreshState();
  };
  $('#btnOpenAuths').onclick = () => api('/api/open', 'POST', { target: 'auths' });
  $('#btnReloadModels').onclick = () => loadModels(false);
  $('#modelFilter').oninput = renderModels;

  // ── 步骤 3
  $('#btnDoStart').onclick = doStart;
  $('#btnDoRestart').onclick = doRestart;
  $('#btnDoStop').onclick = doStop;
  $('#btnProbe').onclick = async () => {
    await refreshState();
    toast(STATE.service.health ? '探活正常' : '探活失败，看下方日志');
  };
  $('#btnOpenLogs').onclick = () => api('/api/open', 'POST', { target: 'logs' });
  $('#btnOpenHealth').onclick = () => window.open(STATE.healthz, '_blank');
  $('#btnOpenStatus').onclick = () => {
    window.open(STATE.local_url.replace('/v1', '/status'), '_blank');
    const k = STATE.config.api_key;
    if (k) { copy(k); toast('已打开 /status，API 密钥已复制到剪贴板'); }
  };
  $('#btnAutoOn').onclick = () => setAuto(true);
  $('#btnAutoOff').onclick = () => setAuto(false);

  // ── 日志
  $('#btnClearLog').onclick = async () => {
    await api('/api/logs/clear', 'POST', {});
    $('#logBody').innerHTML = '';
  };
}

/* ───────── 启动 ───────── */
bind();
initQr();
refreshState().then(() => loadModels(true));
renderModels();
pollLogs();
setInterval(pollLogs, 800);
setInterval(refreshState, 5000);
