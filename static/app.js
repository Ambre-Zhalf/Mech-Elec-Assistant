const chat = document.getElementById("chat");
const input = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
const newChatBtn = document.getElementById("newChatBtn");
const searchInput = document.getElementById("searchInput");
const convList = document.getElementById("convList");
const sidebarToggle = document.getElementById("sidebarToggle");
const graphBackBtn = document.getElementById("graphBackBtn");
const graphView = document.getElementById("graphView");
const composer = document.querySelector(".composer");
const appEl = document.querySelector(".app");
const booksOverlay = document.getElementById("booksOverlay");
const booksModalTitle = document.getElementById("booksModalTitle");
const booksBackBtn = document.getElementById("booksBackBtn");
const booksCloseBtn = document.getElementById("booksCloseBtn");
const booksMenu = document.getElementById("booksMenu");
const booksSearchView = document.getElementById("booksSearchView");
const booksMineView = document.getElementById("booksMineView");
const booksMdView = document.getElementById("booksMdView");
const bookSearchInput = document.getElementById("bookSearchInput");
const bookSearchBtn = document.getElementById("bookSearchBtn");
const bookStatus = document.getElementById("bookStatus");
const bookProgress = document.getElementById("bookProgress");
const bookSearchLog = document.getElementById("bookSearchLog");
const bookResults = document.getElementById("bookResults");
const bookMineList = document.getElementById("bookMineList");
const bookDropZone = document.getElementById("bookDropZone");
const bookFileInput = document.getElementById("bookFileInput");
const bookMineStatus = document.getElementById("bookMineStatus");
const bookMdStatus = document.getElementById("bookMdStatus");
const bookMdList = document.getElementById("bookMdList");
const bookNameOverlay = document.getElementById("bookNameOverlay");
const bookNameInput = document.getElementById("bookNameInput");
const bookNameCancel = document.getElementById("bookNameCancel");
const bookNameOk = document.getElementById("bookNameOk");
const bookParseOverlay = document.getElementById("bookParseOverlay");
const bookParseTitle = document.getElementById("bookParseTitle");
const bookParseText = document.getElementById("bookParseText");
const bookParseClose = document.getElementById("bookParseClose");
const bookParseProgressWrap = document.getElementById("bookParseProgressWrap");
const bookParseProgressFill = document.getElementById("bookParseProgressFill");
const bookParsePercent = document.getElementById("bookParsePercent");
const bookParseLog = document.getElementById("bookParseLog");

let sessionId = localStorage.getItem("session_id") || crypto.randomUUID();
localStorage.setItem("session_id", sessionId);
let clientId = localStorage.getItem("client_id") || crypto.randomUUID();
localStorage.setItem("client_id", clientId);
let allConvs = [];
let graphMode = false;
let chatMode = "plan";
const modeBtn = document.getElementById("modeBtn");
const modeMenu = document.getElementById("modeMenu");
const modeLabel = document.getElementById("modeLabel");
const modeIcon = document.getElementById("modeIcon");

function b64encodeUtf8(s) {
  return btoa(unescape(encodeURIComponent(s)));
}

function b64decodeUtf8(s) {
  return decodeURIComponent(escape(atob(s)));
}

function isGraphJson(obj) {
  return obj && typeof obj === "object" &&
    Array.isArray(obj.nodes) && Array.isArray(obj.edges);
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");
}

function linkify(s) {
  // 先匹配 [文字](https://...) 形式的 Markdown 链接,再匹配裸链接,统一转为可点击外链
  return s.replace(
    /(\[[^\]\n]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s<>"']+)/g,
    (m) => {
      if (m.charAt(0) === "[") {
        const mm = m.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
        if (mm) {
          return '<a href="' + mm[2] + '" target="_blank" rel="noopener noreferrer">' + mm[1] + "</a>";
        }
      }
      // 裸链接:先截断到第一个中文/全角字符,再去掉结尾的 ASCII 标点
      let rest = "";
      const cjkIdx = m.search(/[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]/);
      if (cjkIdx !== -1) {
        rest = m.slice(cjkIdx);
        m = m.slice(0, cjkIdx);
      }
      let url = m;
      let punct = "";
      const stop = /[.,:!?()）\]【】》”’'"`]$/;
      while (stop.test(url)) {
        punct = url.slice(-1) + punct;
        url = url.slice(0, -1);
      }
      return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + "</a>" + punct + rest;
    }
  );
}

function inlineMd(s) {
  return linkify(escapeHtml(s))
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function toTable(rows) {
  const cells = rows.map(r =>
    r.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => inlineMd(c.trim()))
  );
  const head = cells[0] || [];
  const body = cells.slice(2);
  let html = "<table><thead><tr>" + head.map(c => "<th>" + c + "</th>").join("") + "</tr></thead><tbody>";
  html += body.map(r => "<tr>" + r.map(c => "<td>" + c + "</td>").join("") + "</tr>").join("");
  return html + "</tbody></table>";
}

function renderMd(src) {
  const parts = src.split(/```/);
  let html = "";
  let listType = null;

  const closeList = () => {
    if (listType) { html += "</" + listType + ">"; listType = null; }
  };

  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 1) {
      closeList();
      const raw = parts[i];
      const fence = raw.match(/^([a-zA-Z0-9_-]*)\n([\s\S]*)$/);
      const lang = fence ? fence[1].toLowerCase() : "";
      const code = fence ? fence[2] : raw;
      let codeHtml = '<pre class="code">' + escapeHtml(code) + "</pre>";
      if (lang === "json") {
        codeHtml = '<details class="graph-json-fold"><summary>📄 图谱 JSON · 点击展开</summary>' + codeHtml + "</details>";
        try {
          const parsed = JSON.parse(code.trim());
          if (isGraphJson(parsed)) {
            const encoded = b64encodeUtf8(JSON.stringify(parsed));
            codeHtml += '<div class="graph-import-row">' +
              '<button type="button" class="graph-import-btn" data-graph="' + encoded + '">' +
              "📊 一键导入知识图谱</button></div>";
          }
        } catch (e) { /* 非图谱 JSON,不渲染导入按钮 */ }
      }
      html += codeHtml;
      continue;
    }
    const lines = parts[i].split("\n");
    let table = [];
    const flushTable = () => {
      if (table.length) { closeList(); html += toTable(table); table = []; }
    };
    for (const line of lines) {
      const l = line.trim();
      if (l.startsWith("|")) { closeList(); table.push(line); continue; }
      flushTable();
      if (/^#{1,4}\s/.test(l)) {
        closeList();
        html += "<h4>" + inlineMd(l.replace(/^#+\s*/, "")) + "</h4>";
      } else if (/^[-*]\s/.test(l)) {
        if (listType !== "ul") { closeList(); html += "<ul>"; listType = "ul"; }
        html += "<li>" + inlineMd(l.slice(2)) + "</li>";
      } else if (/^\d+[.、]\s/.test(l)) {
        if (listType !== "ol") { closeList(); html += "<ol>"; listType = "ol"; }
        html += "<li>" + inlineMd(l.replace(/^\d+[.、]\s*/, "")) + "</li>";
      } else if (l.startsWith("<!--QUICK_OPTION:")) {
        closeList();
        const inner = l.slice("<!--QUICK_OPTION:".length, -"-->".length);
        const opts = inner.split("|").map(s => s.trim()).filter(Boolean);
        html += '<div class="quick-options">' + opts.map(o =>
          '<button type="button" class="quick-option" data-opt="' + o.replace(/"/g, "&quot;") + '">' + inlineMd(o) + '</button>'
        ).join("") + '</div>';
      } else if (l === "---" || l === "") {
        closeList();
        if (l === "---") html += "<hr style='border:none;border-top:1px solid var(--border);margin:10px 0'>";
      } else {
        closeList();
        html += "<p>" + inlineMd(l) + "</p>";
      }
    }
    flushTable();
    closeList();
  }
  return html;
}

function buildThinkBox(think, thinkTime) {
  const box = document.createElement("div");
  box.className = "think collapsed";
  const head = document.createElement("button");
  head.type = "button";
  head.className = "think-head";
  const t = thinkTime != null ? "用时 " + Number(thinkTime).toFixed(1) + "s · " : "";
  head.innerHTML = '<span class="dot"></span><span class="think-label"></span>';
  head.querySelector(".think-label").textContent = "已完成思考 · " + t + "点击展开 ▾";
  const body = document.createElement("div");
  body.className = "think-body";
  String(think || "").split("\n").forEach(line => {
    const l = document.createElement("div");
    l.className = "think-line";
    l.textContent = line;
    body.appendChild(l);
  });
  head.addEventListener("click", () => {
    const c = box.classList.toggle("collapsed");
    head.querySelector(".think-label").textContent =
      c ? "已完成思考 · " + t + "点击展开 ▾" : "已完成思考 · " + t + "点击收起 ▴";
  });
  box.appendChild(head);
  box.appendChild(body);
  return box;
}

function appendMsg(role, text, mode, think, thinkTime) {
  const wrap = document.createElement("div");
  wrap.className = "msg " + role + " mode-" + (mode || "plan");
  if (role === "assistant" && think) {
    wrap.appendChild(buildThinkBox(think, thinkTime));
  }
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = renderMd(text);
  wrap.appendChild(bubble);
  chat.appendChild(wrap);
  if (role === "user") lastUserMsg = text;
  if (role === "assistant") {
    attachEnhanceSearch(bubble, text);
    attachRetryBtn(bubble);
  }
  scrollToBottom();
}

function attachRetryBtn(bubble) {
  if (!bubble || bubble.querySelector(".retry-link")) return;
  const btn = document.createElement("div");
  btn.className = "retry-link";
  btn.textContent = "出现bug？点击重试";
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (sendBtn.disabled) return;
    const node = createStreamNode(chatMode);
    setupThinkToggle(node);
    streamRetry({ node, raw: "" });
  });
  bubble.appendChild(btn);
}

// ---------- 增强搜索(Anspire AI Search) ----------

let lastUserMsg = "";
const ENHANCE_RE = /(官网|招聘|岗位|校招|春招|秋招|公司|企业|bilibili|哔哩哔哩|视频|职位|信息来源)/i;

function mayNeedEnhance(text) {
  if (!text || text.length < 5) return false;
  const hasLink = /https?:\/\/[^\s<>"']+/.test(text);
  const hasKeyword = ENHANCE_RE.test(text);
  return hasLink && hasKeyword;
}

function renderAnspireResults(container, results) {
  container.hidden = false;
  const head = '<div class="enhance-head">🔎 增强搜索结果</div>';
  const items = (results || []).map(r => {
    const url = escapeHtml(r.url || "");
    const title = escapeHtml(r.title || "未命名");
    const date = r.date
      ? '<span class="enhance-meta">' + escapeHtml(r.date) + "</span>"
      : "";
    const content = r.content
      ? '<div class="enhance-snippet">' + escapeHtml(r.content) + "</div>"
      : "";
    return (
      '<div class="enhance-item">' +
      '<a class="enhance-item-link" href="' + url + '" target="_blank" rel="noopener noreferrer">' +
      title + "</a>" + date + content + "</div>"
    );
  }).join("");
  container.innerHTML = head + (items || '<div class="enhance-error">未返回结果</div>');
  scrollToBottom();
}

function buildEnhanceRow() {
  const row = document.createElement("div");
  row.className = "enhance-row";

  const link = document.createElement("button");
  link.type = "button";
  link.className = "enhance-link";
  link.textContent = "对搜索结果不满意?使用增强搜索";

  const form = document.createElement("div");
  form.className = "enhance-form";
  form.hidden = true;

  const input = document.createElement("input");
  input.type = "text";
  input.className = "enhance-input";
  input.placeholder = "输入想增强搜索的关键词";
  input.autocomplete = "off";

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "enhance-btn";
  btn.textContent = "增强搜索";

  form.appendChild(input);
  form.appendChild(btn);

  const results = document.createElement("div");
  results.className = "enhance-results";
  results.hidden = true;

  link.addEventListener("click", () => {
    form.hidden = !form.hidden;
    if (!form.hidden) {
      input.value = input.value || (lastUserMsg || "").slice(0, 40);
      input.focus();
    }
  });

  const runSearch = async () => {
    const q = input.value.trim();
    if (!q) {
      input.focus();
      return;
    }
    btn.disabled = true;
    btn.textContent = "搜索中…";
    try {
      const res = await fetch("/api/search/anspire", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, top_k: 10 }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) throw new Error(data.error || "增强搜索失败");
      renderAnspireResults(results, data.results || []);
    } catch (e) {
      results.hidden = false;
      results.innerHTML = '<div class="enhance-error">⚠️ ' + inlineMd(e.message || "增强搜索失败") + "</div>";
      scrollToBottom();
    } finally {
      btn.disabled = false;
      btn.textContent = "增强搜索";
    }
  };

  btn.addEventListener("click", runSearch);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter") {
      e.preventDefault();
      runSearch();
    }
  });

  row.appendChild(link);
  row.appendChild(form);
  row.appendChild(results);
  return row;
}

function attachEnhanceSearch(bubble, text) {
  if (!mayNeedEnhance(text)) return;
  bubble.appendChild(buildEnhanceRow());
}

const INTRO_TEXT = "我是机电学习助手，专注于机电专业的学生规划大学四年的学习，助力他们在大学毕业之际能取得心仪的offer。我有“规划”和“竞赛学习”两种模式，默认为“规划模式”，先对你的基本信息“摸个底”，点击下方的“开始”按钮即可体验。";
let introTimer = null;
let introIntv = null;

function showWelcome() {
  chat.innerHTML = "";
  chat.innerHTML = `
    <div class="welcome">
      <div class="welcome-card">
        <div class="welcome-logo">⚙</div>
        <h2>机电学习助手</h2>
        <p id="introText" class="intro-text"></p>
        <button id="startBtn" class="start-btn" type="button">开始</button>
      </div>
    </div>`;
  startIntro();
}

function startIntro() {
  const el = document.getElementById("introText");
  const btn = document.getElementById("startBtn");
  if (!el || !btn) return;
  // 彻底清理上一次的定时器,避免多个定时器叠加导致输出卡住/重复
  if (introIntv) clearInterval(introIntv);
  if (introTimer) clearTimeout(introTimer);
  btn.style.display = "none";
  el.textContent = "";
  // 创建新对话后，等约 2s，再用流式逐字输出自我介绍
  introTimer = setTimeout(() => {
    let i = 0;
    introIntv = setInterval(() => {
      // 若元素已不在文档中(比如界面被重建),停止写入,避免“看不见地一直输出”
      if (!document.contains(el)) {
        clearInterval(introIntv);
        return;
      }
      if (i < INTRO_TEXT.length) {
        el.textContent = INTRO_TEXT.slice(0, i + 1);
        i++;
      } else {
        clearInterval(introIntv);
        btn.style.display = "";
      }
    }, 45);
  }, 2000);
  btn.addEventListener("click", startPlan);
}

function startPlan() {
  const w = chat.querySelector(".welcome");
  if (w) w.style.display = "none";
  chatMode = "plan";
  updateModeUI();
  sendAsUser("开始");
}

function scrollToBottom() {
  chat.scrollTop = chat.scrollHeight;
}

function createStreamNode(mode) {
  const wrap = document.createElement("div");
  wrap.className = "msg assistant mode-" + (mode || "plan");

  const think = document.createElement("div");
  think.className = "think";

  const head = document.createElement("button");
  head.type = "button";
  head.className = "think-head";
  head.innerHTML = '<span class="dot"></span><span class="think-label">正在思考…</span>';

  const body = document.createElement("div");
  body.className = "think-body";

  think.appendChild(head);
  think.appendChild(body);

  const bubble = document.createElement("div");
  bubble.className = "bubble body";

  wrap.appendChild(think);
  wrap.appendChild(bubble);
  chat.appendChild(wrap);
  scrollToBottom();

  return { wrap, think, head, body, bubble, started: false, startedAt: Date.now() };
}

function addThinkLine(node, text) {
  const line = document.createElement("div");
  line.className = "think-line";
  line.textContent = text;
  node.body.appendChild(line);
  scrollToBottom();
}

function collapseThink(node) {
  if (node.started) return;
  node.started = true;
  node.think.classList.add("collapsed");
  const secs = node.startedAt ? (Date.now() - node.startedAt) / 1000 : null;
  node.secs = secs;
  const time = secs != null ? `用时 ${secs.toFixed(1)}s · ` : "";
  node.head.querySelector(".think-label").textContent = `已完成思考 · ${time}点击展开 ▾`;
}

function setupThinkToggle(node) {
  node.head.addEventListener("click", () => {
    const collapsed = node.think.classList.toggle("collapsed");
    const time = node.secs != null ? `用时 ${node.secs.toFixed(1)}s · ` : "";
    node.head.querySelector(".think-label").textContent =
      collapsed ? `已完成思考 · ${time}点击展开 ▾` : `已完成思考 · ${time}点击收起 ▴`;
  });
}

function handleSse(rawEvent, ctx) {
  let event = "message";
  let data = "";
  for (const line of rawEvent.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return;
  let payload = {};
  try { payload = JSON.parse(data); } catch (e) { payload = {}; }

  if (event === "process") {
    addThinkLine(ctx.node, payload.text || "");
  } else if (event === "content") {
    collapseThink(ctx.node);
    ctx.raw += payload.delta || "";
    ctx.node.bubble.innerHTML = renderMd(ctx.raw);
    scrollToBottom();
  } else if (event === "done") {
    ctx.node.head.querySelector(".dot").style.display = "none";
    collapseThink(ctx.node);
    attachRetryBtn(ctx.node.bubble);
  } else if (event === "error") {
    collapseThink(ctx.node);
    ctx.node.bubble.innerHTML = '<p>⚠️ ' + inlineMd(payload.error || "请求失败") + "</p>";
    scrollToBottom();
    attachRetryBtn(ctx.node.bubble);
  }
}

async function streamChat(message, ctx) {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId, client_id: clientId, mode: chatMode }),
  });
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || "请求失败");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      handleSse(rawEvent, ctx);
    }
  }
}

async function streamRetry(ctx) {
  const res = await fetch("/api/chat/retry", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, client_id: clientId, mode: chatMode }),
  });
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}));
    ctx.node.bubble.innerHTML = "<p>⚠️ " + inlineMd(data.error || "重试失败，请稍后重试") + "</p>";
    collapseThink(ctx.node);
    attachRetryBtn(ctx.node.bubble);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      handleSse(rawEvent, ctx);
    }
  }
}

async function send() {
  const text = input.value.trim();
  if (!text) return;
  appendMsg("user", text, chatMode);
  input.value = "";
  input.style.height = "auto";
  sendBtn.disabled = true;

  const node = createStreamNode(chatMode);
  setupThinkToggle(node);
  const ctx = { node, raw: "" };

  try {
    await streamChat(text, ctx);
    await refreshConversations();
    attachEnhanceSearch(ctx.node.bubble, ctx.raw);
  } catch (err) {
    collapseThink(ctx.node);
    ctx.node.bubble.innerHTML = '<p>⚠️ ' + inlineMd(err.message) + "</p>";
    scrollToBottom();
  } finally {
    ctx.node.head.querySelector(".dot").style.display = "none";
    sendBtn.disabled = false;
    input.focus();
  }
}

async function sendAsUser(text) {
  if (!text) return;
  appendMsg("user", text, chatMode);
  input.value = "";
  input.style.height = "auto";
  sendBtn.disabled = true;
  const node = createStreamNode(chatMode);
  setupThinkToggle(node);
  const ctx = { node, raw: "" };
  try {
    await streamChat(text, ctx);
    await refreshConversations();
    attachEnhanceSearch(ctx.node.bubble, ctx.raw);
  } catch (err) {
    collapseThink(ctx.node);
    ctx.node.bubble.innerHTML = '<p>⚠️ ' + inlineMd(err.message) + "</p>";
    scrollToBottom();
  } finally {
    ctx.node.head.querySelector(".dot").style.display = "none";
    sendBtn.disabled = false;
    input.focus();
  }
}

// ---------- 知识图谱:一键导入 + 图谱视图 ----------

function showGraphView() {
  graphMode = true;
  chat.style.display = "none";
  composer.style.display = "none";
  graphView.hidden = false;
  if (window.KG) {
    window.KG.init();
    window.KG.refreshGraphList();
  }
}

function closeGraphView() {
  graphMode = false;
  graphView.hidden = true;
  chat.style.display = "";
  composer.style.display = "";
}

async function importGraph(jsonStr, btn) {
  if (btn.disabled) return;
  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = "正在导入知识图谱…";
  try {
    const graph = JSON.parse(jsonStr);
    const res = await fetch("/api/graph/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, graph }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "导入失败,请稍后重试");
    btn.textContent = "✅ 已导入,正在打开…";
    showGraphView();
    if (window.KG) window.KG.importGraphResult(data.graph_id);
  } catch (err) {
    btn.textContent = "⚠️ " + (err.message || "导入失败");
    btn.disabled = false;
    setTimeout(() => { btn.textContent = original; }, 5000);
  }
}

// ---------- 侧边栏:历史对话 ----------

function renderConvList() {
  const q = searchInput.value.trim().toLowerCase();
  const list = q
    ? allConvs.filter(c => (c.title || "").toLowerCase().includes(q))
    : allConvs;

  convList.innerHTML = "";
  if (!list.length) {
    const empty = document.createElement("div");
    empty.className = "conv-empty";
    empty.textContent = q ? "没有匹配的对话" : "暂无历史对话";
    convList.appendChild(empty);
    return;
  }

  for (const conv of list) {
    const item = document.createElement("div");
    item.className = "conv-item" + (conv.id === sessionId ? " active" : "");

    const main = document.createElement("button");
    main.type = "button";
    main.className = "conv-main";

    const title = document.createElement("div");
    title.className = "conv-title";
    title.textContent = conv.title || "新对话";

    const meta = document.createElement("div");
    meta.className = "conv-meta";
    meta.textContent = (conv.updated_at || "").slice(5, 16) + " · " + conv.count + " 条";

    main.appendChild(title);
    main.appendChild(meta);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "conv-del";
    del.title = "删除该对话";
    del.setAttribute("data-del", conv.id);
    del.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>';

    main.addEventListener("click", () => loadConversation(conv.id));
    item.appendChild(main);
    item.appendChild(del);
    convList.appendChild(item);
  }
}

async function refreshConversations() {
  try {
    const res = await fetch("/api/sessions?client_id=" + encodeURIComponent(clientId));
    allConvs = await res.json();
    renderConvList();
  } catch (e) {
    allConvs = [];
    renderConvList();
  }
}

async function deleteConversation(id) {
  if (!confirm("确定删除该历史对话吗?此操作不可恢复")) return;
  try {
    const res = await fetch("/api/sessions/" + encodeURIComponent(id) + "?client_id=" + encodeURIComponent(clientId), {
      method: "DELETE",
    });
    if (!res.ok) throw new Error("删除失败");
    allConvs = allConvs.filter(c => c.id !== id);
    if (id === sessionId) {
      sessionId = crypto.randomUUID();
      localStorage.setItem("session_id", sessionId);
      showWelcome();
    }
    renderConvList();
  } catch (e) {
    alert("删除历史对话失败: " + e.message);
  }
}

async function loadConversation(id) {
  sessionId = id;
  localStorage.setItem("session_id", sessionId);
  renderConvList();
  try {
    const res = await fetch("/api/sessions/" + encodeURIComponent(id) + "/messages?client_id=" + encodeURIComponent(clientId));
    const messages = await res.json();
    chat.innerHTML = "";
    if (messages && messages.length) {
      for (const m of messages) appendMsg(m.role, m.content, m.mode, m.think, m.think_time);
    } else {
      showWelcome();
    }
  } catch (e) {
    showWelcome();
  }
  input.focus();
}

function updateModeUI() {
  if (!modeLabel) return;
  document.body.classList.toggle("mode-challenge", chatMode === "challenge");
  if (chatMode === "challenge") {
    modeIcon.textContent = "🏆";
    modeLabel.textContent = "竞赛学习模式";
  } else {
    modeIcon.textContent = "🧭";
    modeLabel.textContent = "规划模式";
  }
}

function startNewChat() {
  sessionId = crypto.randomUUID();
  localStorage.setItem("session_id", sessionId);
  chatMode = "plan";
  updateModeUI();
  sendBtn.disabled = false;
  searchInput.value = "";
  showWelcome();
  renderConvList();
  input.focus();
}

modeBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  modeMenu.hidden = !modeMenu.hidden;
});
modeMenu.addEventListener("click", (e) => {
  const opt = e.target.closest(".mode-option");
  if (opt) {
    chatMode = opt.dataset.mode || "plan";
    updateModeUI();
    modeMenu.hidden = true;
  }
});
document.addEventListener("click", (e) => {
  if (!e.target.closest("#modeSwitch")) modeMenu.hidden = true;
});
updateModeUI();

newChatBtn.addEventListener("click", startNewChat);
searchInput.addEventListener("input", renderConvList);
sendBtn.addEventListener("click", send);
convList.addEventListener("click", e => {
  const del = e.target.closest("[data-del]");
  if (del) {
    e.stopPropagation();
    deleteConversation(del.getAttribute("data-del"));
  }
});
chat.addEventListener("click", e => {
  const btn = e.target.closest(".graph-import-btn");
  if (btn) importGraph(b64decodeUtf8(btn.dataset.graph), btn);
  const qbtn = e.target.closest(".quick-option");
  if (qbtn) sendAsUser(qbtn.dataset.opt);
});
graphBackBtn.addEventListener("click", closeGraphView);

// ---------- 图书:搜索 / 下载 / 我的书籍 ----------

function showBooksMenu() {
  booksMenu.hidden = false;
  booksSearchView.hidden = true;
  booksMineView.hidden = true;
  booksMdView.hidden = true;
  booksModalTitle.textContent = "图书";
  booksBackBtn.hidden = true;
}

function showBooksSearch() {
  booksMenu.hidden = true;
  booksSearchView.hidden = false;
  booksMineView.hidden = true;
  booksMdView.hidden = true;
  booksModalTitle.textContent = "图书搜索";
  booksBackBtn.hidden = false;
}

function showBooksMine() {
  booksMenu.hidden = true;
  booksSearchView.hidden = true;
  booksMineView.hidden = false;
  booksMdView.hidden = true;
  booksModalTitle.textContent = "我的书籍";
  booksBackBtn.hidden = false;
  loadMyBooks();
}

function showBooksMd() {
  booksMenu.hidden = true;
  booksSearchView.hidden = true;
  booksMineView.hidden = true;
  booksMdView.hidden = false;
  booksModalTitle.textContent = "我的书籍（Markdown）";
  booksBackBtn.hidden = false;
  loadMyMarkdowns();
}

function openBooks() {
  booksOverlay.hidden = false;
  showBooksMenu();
}

function closeBooks() {
  booksOverlay.hidden = true;
}

function setBookStatus(text, isError) {
  bookStatus.hidden = !text;
  bookStatus.textContent = text || "";
  bookStatus.classList.toggle("error", !!isError);
}

function formatBookTime(ts) {
  if (!ts) return "";
  const d = new Date(Number(ts));
  if (isNaN(d.getTime())) return "";
  return (d.getMonth() + 1) + "/" + d.getDate() + " " +
    String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
}

function formatBookSize(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let n = bytes, i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return n.toFixed(i ? 1 : 0) + " " + units[i];
}

function renderBookResults(results) {
  if (!results || !results.length) {
    bookResults.innerHTML = '<div class="book-status">未找到相关书籍，请更换关键词重试。</div>';
    return;
  }
  bookResults.innerHTML = results.map(r => {
    const url = r.url || "";
    const download = r.download || "";
    const rawTitle = r.title || "未命名书籍";
    const parts = [];
    if (r.publisher) parts.push(r.publisher);
    if (r.year) parts.push(r.year);
    const title = escapeHtml(rawTitle);
    const titleSuffix = parts.length ? "（" + escapeHtml(parts.join(" · ")) + "）" : "";
    const author = escapeHtml(r.author || "");
    const metaParts = [];
    if (r.language) metaParts.push(escapeHtml(r.language));
    if (r.extension) metaParts.push(escapeHtml(r.extension.toUpperCase()));
    if (r.filesize) metaParts.push(escapeHtml(r.filesize));
    const urlEsc = escapeHtml(url);
    const dlEsc = escapeHtml(download);
    const dlTitle = escapeHtml(rawTitle + (r.author ? " - " + r.author : ""));
    return '<div class="book-result-item">' +
      '<div class="book-result-main">' +
        '<div class="book-result-title">' + title + titleSuffix + '</div>' +
        (author ? '<div class="book-result-author">' + author + '</div>' : '') +
        (metaParts.length ? '<div class="book-result-meta">' + metaParts.join(" · ") + '</div>' : '') +
        '<a class="book-result-link" href="' + urlEsc + '" target="_blank" rel="noopener noreferrer">书籍页</a>' +
        (download ? ' <span class="book-result-sep">·</span> <a class="book-result-link" href="' + dlEsc + '" target="_blank" rel="noopener noreferrer">下载页</a>' : '') +
      '</div>' +
      '<div class="book-actions">' +
        '<button class="book-btn primary" data-download="' + urlEsc + '" data-dlurl="' + dlEsc + '" data-title="' + dlTitle + '">下载</button>' +
      '</div></div>';
  }).join("");
}

async function searchBooks() {
  const q = bookSearchInput.value.trim();
  if (!q) return;
  bookSearchBtn.disabled = true;
  bookResults.innerHTML = "";
  setBookStatus("正在搜索“" + q + "”…", false);
  bookProgress.hidden = false;
  bookProgress.querySelector(".book-progress-fill").style.width = "0%";
  bookSearchLog.hidden = false;
  bookSearchLog.textContent = "";
  let lastLogs = 0;
  try {
    const res = await fetch("/api/books/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: q }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "搜索失败");
    await new Promise((resolve) => {
      const timer = setInterval(async () => {
        try {
          const sr = await fetch("/api/books/search/status/" + encodeURIComponent(data.task_id));
          const st = await sr.json().catch(() => ({}));
          if (!sr.ok) throw new Error(st.error || "获取进度失败");
          const logs = st.logs || [];
          if (logs.length > lastLogs) {
            lastLogs = logs.length;
            bookSearchLog.textContent = logs.join("\n");
            bookSearchLog.scrollTop = bookSearchLog.scrollHeight;
          }
          if (st.status === "done") {
            clearInterval(timer);
            bookProgress.querySelector(".book-progress-fill").style.width = "100%";
            setBookStatus("");
            renderBookResults((st.result && st.result.results) || []);
            resolve();
          } else if (st.status === "error") {
            clearInterval(timer);
            setBookStatus("⚠️ " + (st.error || "搜索失败"), true);
            if (st.logs && st.logs.length) bookSearchLog.textContent = st.logs.join("\n");
            resolve();
          }
        } catch (e) {
          clearInterval(timer);
          setBookStatus("⚠️ " + (e.message || "搜索失败"), true);
          resolve();
        }
      }, 700);
    });
  } catch (e) {
    setBookStatus("⚠️ " + (e.message || "搜索失败"), true);
  } finally {
    bookSearchBtn.disabled = false;
    bookProgress.hidden = true;
    bookSearchLog.hidden = false;
  }
}

async function downloadBook(btn) {
  const url = btn.dataset.download;
  const downloadUrl = btn.dataset.dlurl || "";
  const title = btn.dataset.title || "";
  btn.disabled = true;
  btn.classList.add("downloading");
  btn.innerHTML = '<span class="dl-fill"></span><span class="dl-pct">0%</span>';
  setBookStatus("正在登录并下载 PDF，请稍候…", false);
  try {
    const res = await fetch("/api/books/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, download_url: downloadUrl, title }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "下载失败");
    await new Promise((resolve) => {
      const timer = setInterval(async () => {
        try {
          const sr = await fetch("/api/books/download/status/" + encodeURIComponent(data.task_id));
          const st = await sr.json().catch(() => ({}));
          if (!sr.ok) throw new Error(st.error || "获取进度失败");
          const pct = Math.max(0, Math.min(100, Math.round(st.progress || 0)));
          const fill = btn.querySelector(".dl-fill");
          const pctEl = btn.querySelector(".dl-pct");
          if (fill) fill.style.width = pct + "%";
          if (pctEl) pctEl.textContent = pct + "%";
          if (st.status === "done") {
            clearInterval(timer);
            btn.classList.remove("downloading");
            btn.innerHTML = "已保存";
            setBookStatus("✅ 已下载并保存：" + ((st.result && st.result.filename) || ""), false);
            resolve();
          } else if (st.status === "error") {
            clearInterval(timer);
            btn.classList.remove("downloading");
            btn.innerHTML = "重试";
            btn.disabled = false;
            setBookStatus("⚠️ " + (st.error || "下载失败"), true);
            resolve();
          }
        } catch (e) {
          clearInterval(timer);
          btn.classList.remove("downloading");
          btn.innerHTML = "重试";
          btn.disabled = false;
          setBookStatus("⚠️ " + (e.message || "下载失败"), true);
          resolve();
        }
      }, 700);
    });
  } catch (e) {
    btn.classList.remove("downloading");
    btn.innerHTML = "重试";
    btn.disabled = false;
    setBookStatus("⚠️ " + (e.message || "下载失败"), true);
  }
}

function renderMyBooks(books) {
  if (!books || !books.length) {
    bookMineList.innerHTML = '<div class="book-status">暂无书籍，去“图书搜索”下载一本吧。</div>';
    return;
  }
  bookMineList.innerHTML = books.map(b => {
    const fname = escapeHtml(b.filename);
    return '<div class="book-mine-item">' +
      '<div class="book-mine-main">' +
        '<div class="book-mine-name">' + fname + '</div>' +
        '<div class="book-mine-meta">' + formatBookSize(b.size) + ' · ' + escapeHtml(formatBookTime(b.mtime)) + '</div>' +
      '</div>' +
      '<div class="book-actions">' +
        '<a class="book-btn" href="/api/books/file/' + encodeURIComponent(b.filename) + '" target="_blank" rel="noopener noreferrer">打开</a>' +
        '<button class="book-btn" data-parse-book="' + fname + '">识别</button>' +
        '<button class="book-btn danger" data-delete-book="' + fname + '">删除</button>' +
      '</div></div>';
  }).join("");
}

async function loadMyBooks() {
  bookMineList.innerHTML = '<div class="book-status">加载中…</div>';
  try {
    const res = await fetch("/api/books");
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "加载失败");
    renderMyBooks(data.books || []);
  } catch (e) {
    bookMineList.innerHTML = '<div class="book-status error">⚠️ ' + escapeHtml(e.message || "加载失败") + '</div>';
  }
}

async function deleteBook(filename) {
  if (!confirm("确定删除该书吗?")) return;
  try {
    const res = await fetch("/api/books/" + encodeURIComponent(filename), { method: "DELETE" });
    if (!res.ok) throw new Error("删除失败");
    loadMyBooks();
  } catch (e) {
    alert("删除失败: " + (e.message || ""));
  }
}

async function renderMarkdownInto(text, title) {
  bookParseTitle.textContent = title || "预览";
  // 先把公式($...$ / $$...$$)换成占位符,避免 marked 把数学里的 _、* 当强调破坏
  const mathChunks = [];
  const re = /(\$\$[\s\S]*?\$\$|\$[^$\n]*?\$)/g;
  let protectedText = (text || "").replace(re, m => {
    const idx = mathChunks.length;
    mathChunks.push(m);
    return "MATHPLACEHOLDER" + idx + "X";
  });
  let html = window.marked ? marked.parse(protectedText) : escapeHtml(protectedText);
  for (let i = 0; i < mathChunks.length; i++) {
    html = html.split("MATHPLACEHOLDER" + i + "X").join(mathChunks[i]);
  }
  // 识别结果的图是相对路径,前端不提供,去掉避免破图
  html = html.replace(/<img\b[^>]*>/gi, "");
  bookParseText.innerHTML = html;
  bookParseOverlay.hidden = false;
  if (window.MathJax && MathJax.typesetPromise) {
    try {
      if (MathJax.startup) await MathJax.startup.promise;
      await MathJax.typesetPromise([bookParseText]);
    } catch (e) {
      console.warn("MathJax 渲染失败", e);
    }
  }
}

const parseBusy = new Set();
const parseTaskId = Object.create(null);

function showParseProgressUI(title) {
  bookParseTitle.textContent = title;
  bookParseProgressWrap.hidden = false;
  bookParseProgressFill.style.width = "0%";
  bookParsePercent.textContent = "0%";
  bookParseLog.hidden = false;
  bookParseLog.textContent = "";
  bookParseText.innerHTML = "";
  bookParseProgressWrap.scrollIntoView({ block: "start" });
  bookParseOverlay.hidden = false;
}

function pollParseTask(taskId, filename) {
  return new Promise((resolve) => {
    let lastLogCount = 0;
    const timer = setInterval(async () => {
      let st;
      try {
        const res = await fetch("/api/pdf/parse/status/" + encodeURIComponent(taskId));
        st = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(st.error || "获取进度失败");
      } catch (e) {
        clearInterval(timer);
        bookParseText.textContent = "⚠️ " + (e.message || "获取进度失败");
        resolve();
        return;
      }
      const pct = Math.max(0, Math.min(100, Math.round(st.progress || 0)));
      bookParseProgressFill.style.width = pct + "%";
      bookParsePercent.textContent = pct + "%";
      const logs = st.logs || [];
      if (logs.length > lastLogCount) {
        lastLogCount = logs.length;
        bookParseLog.textContent = logs.join("\n");
        bookParseLog.scrollTop = bookParseLog.scrollHeight;
      }
      if (st.status === "done") {
        clearInterval(timer);
        bookParseProgressFill.style.width = "100%";
        bookParsePercent.textContent = "100%";
        const res = st.result || {};
        let text = res.text || "识别完成";
        if (res.md_filename) text += "\n\n—— 已保存到「我的书籍（Markdown）」：" + res.md_filename;
        await renderMarkdownInto(text, "识别《" + filename + "》");
        resolve();
      } else if (st.status === "error") {
        clearInterval(timer);
        bookParseText.textContent = "⚠️ " + (st.error || "识别失败");
        if (st.logs && st.logs.length) bookParseLog.textContent = st.logs.join("\n");
        resolve();
      }
    }, 1000);
  });
}

async function parseBook(filename) {
  const mdName = filename.replace(/\.pdf$/i, "") + ".md";
  let existing = false;
  try {
    const rr = await fetch("/api/books/md");
    const dd = await rr.json().catch(() => ({}));
    existing = (dd.markdowns || []).some(m => m.filename === mdName);
  } catch (e) {}
  if (existing && !confirm("「我的书籍（Markdown）」已存在《" + filename + "》的识别结果，是否重新识别？")) {
    return;
  }
  if (parseBusy.has(filename)) {
    showParseProgressUI("识别《" + filename + "》…");
    if (parseTaskId[filename]) pollParseTask(parseTaskId[filename], filename);
    return;
  }
  parseBusy.add(filename);
  showParseProgressUI("识别《" + filename + "》…");
  try {
    const res = await fetch("/api/pdf/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "启动识别失败");
    parseTaskId[filename] = data.task_id;
    await pollParseTask(data.task_id, filename);
  } catch (e) {
    bookParseText.textContent = "⚠️ " + (e.message || "识别失败");
  } finally {
    parseBusy.delete(filename);
    delete parseTaskId[filename];
  }
}

async function openMarkdownViewer(filename) {
  bookParseTitle.textContent = "查看《" + filename + "》";
  bookParseText.textContent = "加载中…";
  bookParseProgressWrap.hidden = true;
  bookParseLog.hidden = true;
  bookParseOverlay.hidden = false;
  try {
    const res = await fetch("/api/books/md/file/" + encodeURIComponent(filename));
    const text = await res.text();
    if (!res.ok) throw new Error("加载失败");
    await renderMarkdownInto(text, "查看《" + filename + "》");
  } catch (e) {
    bookParseText.textContent = "⚠️ " + (e.message || "加载失败");
  }
}

function closeViewMenu() {
  const m = document.querySelector(".view-menu");
  if (m) m.remove();
}

function showViewMenu(btn, filename) {
  closeViewMenu();
  const menu = document.createElement("div");
  menu.className = "view-menu";
  menu.innerHTML =
    '<button type="button" data-view-act="online">在线查看</button>' +
    '<button type="button" data-view-act="file">文档查看</button>';
  document.body.appendChild(menu);
  const r = btn.getBoundingClientRect();
  menu.style.left = Math.min(window.innerWidth - 160, Math.max(8, r.left)) + "px";
  menu.style.top = Math.min(window.innerHeight - 100, r.bottom + 6) + "px";
  menu.addEventListener("click", (e) => {
    const act = e.target.closest("[data-view-act]");
    if (!act) return;
    if (act.dataset.viewAct === "online") openMarkdownViewer(filename);
    else window.open("/api/books/md/file/" + encodeURIComponent(filename), "_blank");
    closeViewMenu();
  });
  setTimeout(() => {
    document.addEventListener("click", function closeOnDoc(e) {
      if (!e.target.closest(".view-menu")) {
        closeViewMenu();
        document.removeEventListener("click", closeOnDoc);
      }
    });
  }, 0);
}

function setBookMdStatus(text, isError) {
  bookMdStatus.hidden = !text;
  bookMdStatus.textContent = text || "";
  bookMdStatus.classList.toggle("error", !!isError);
}

async function deleteMarkdown(filename) {
  if (!confirm("确定删除该 Markdown 吗?")) return;
  try {
    const res = await fetch("/api/books/md/" + encodeURIComponent(filename), { method: "DELETE" });
    if (!res.ok) throw new Error("删除失败");
    loadMyMarkdowns();
  } catch (e) {
    alert("删除失败: " + (e.message || ""));
  }
}

function renderMyMarkdowns(markdowns) {
  if (!markdowns || !markdowns.length) {
    bookMdList.innerHTML = '<div class="book-status">暂无 Markdown。请在“我的书籍”中点击书的“识别”，结果会自动保存到这里。</div>';
    return;
  }
  bookMdList.innerHTML = markdowns.map(m => {
    const fname = escapeHtml(m.filename);
    return '<div class="book-mine-item">' +
      '<div class="book-mine-main">' +
        '<div class="book-mine-name">' + fname + '</div>' +
        '<div class="book-mine-meta">' + formatBookSize(m.size) + ' · ' + escapeHtml(formatBookTime(m.mtime)) + '</div>' +
      '</div>' +
      '<div class="book-actions">' +
        '<button class="book-btn" data-view-md="' + fname + '">查看</button>' +
        '<button class="book-btn danger" data-delete-md="' + fname + '">删除</button>' +
      '</div></div>';
  }).join("");
}

async function loadMyMarkdowns() {
  bookMdList.innerHTML = '<div class="book-status">加载中…</div>';
  try {
    const res = await fetch("/api/books/md");
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "加载失败");
    renderMyMarkdowns(data.markdowns || []);
  } catch (e) {
    bookMdList.innerHTML = '<div class="book-status error">⚠️ ' + escapeHtml(e.message || "加载失败") + '</div>';
  }
}

// ---------- 我的书籍:本地上传 PDF ----------

let pendingUploadFile = null;

function setBookMineStatus(text, isError) {
  bookMineStatus.hidden = !text;
  bookMineStatus.textContent = text || "";
  bookMineStatus.classList.toggle("error", !!isError);
}

function showNameDialog(file) {
  pendingUploadFile = file || null;
  bookNameInput.value = "";
  bookNameOverlay.hidden = false;
  bookNameInput.focus();
}

function hideNameDialog() {
  pendingUploadFile = null;
  bookNameOverlay.hidden = true;
}

async function uploadBookFile(file, title) {
  const res = await fetch("/api/books/upload?title=" + encodeURIComponent(title), {
    method: "POST",
    headers: { "Content-Type": "application/pdf" },
    body: file,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) throw new Error(data.error || "上传失败");
  return data;
}

async function submitBookName() {
  const title = bookNameInput.value.trim();
  if (!title) { bookNameInput.focus(); return; }
  if (!pendingUploadFile) return;
  const file = pendingUploadFile;
  bookNameOk.disabled = true;
  bookNameOk.textContent = "添加中…";
  setBookMineStatus("正在上传《" + title + "》…", false);
  try {
    await uploadBookFile(file, title);
    hideNameDialog();
    setBookMineStatus("✅ 已添加《" + title + "》", false);
    await loadMyBooks();
  } catch (e) {
    hideNameDialog();
    setBookMineStatus("⚠️ " + (e.message || "上传失败"), true);
  } finally {
    bookNameOk.disabled = false;
    bookNameOk.textContent = "添加";
  }
}

const booksBtn2 = document.getElementById("booksBtn2");
const graphBtn2 = document.getElementById("graphBtn2");
if (booksBtn2) booksBtn2.addEventListener("click", openBooks);
if (graphBtn2) graphBtn2.addEventListener("click", () => {
  if (graphMode) closeGraphView(); else showGraphView();
});
booksCloseBtn.addEventListener("click", closeBooks);
booksBackBtn.addEventListener("click", showBooksMenu);
booksOverlay.addEventListener("click", e => {
  if (e.target === booksOverlay) closeBooks();
});
booksMenu.querySelectorAll("[data-books]").forEach(b => {
  b.addEventListener("click", () => {
    if (b.dataset.books === "search") showBooksSearch();
    else if (b.dataset.books === "md") showBooksMd();
    else showBooksMine();
  });
});
bookSearchBtn.addEventListener("click", searchBooks);
bookSearchInput.addEventListener("keydown", e => {
  if (e.key === "Enter") searchBooks();
});
bookResults.addEventListener("click", e => {
  const btn = e.target.closest("[data-download]");
  if (btn) downloadBook(btn);
});
bookMineList.addEventListener("click", e => {
  const parseBtn = e.target.closest("[data-parse-book]");
  if (parseBtn) { parseBook(parseBtn.dataset.parseBook); return; }
  const btn = e.target.closest("[data-delete-book]");
  if (btn) deleteBook(btn.dataset.deleteBook);
});
bookMdList.addEventListener("click", e => {
  const viewBtn = e.target.closest("[data-view-md]");
  if (viewBtn) { showViewMenu(viewBtn, viewBtn.dataset.viewMd); return; }
  const btn = e.target.closest("[data-delete-md]");
  if (btn) deleteMarkdown(btn.dataset.deleteMd);
});
bookDropZone.addEventListener("click", () => bookFileInput.click());
bookDropZone.addEventListener("dragover", e => {
  e.preventDefault();
  bookDropZone.classList.add("dragover");
});
bookDropZone.addEventListener("dragleave", () => bookDropZone.classList.remove("dragover"));
bookDropZone.addEventListener("drop", e => {
  e.preventDefault();
  bookDropZone.classList.remove("dragover");
  const file = e.dataTransfer.files && e.dataTransfer.files[0];
  if (file) showNameDialog(file);
});
bookFileInput.addEventListener("change", () => {
  const file = bookFileInput.files && bookFileInput.files[0];
  if (file) showNameDialog(file);
  bookFileInput.value = "";
});
bookNameCancel.addEventListener("click", hideNameDialog);
bookNameOk.addEventListener("click", submitBookName);
bookNameInput.addEventListener("keydown", e => {
  if (e.key === "Enter") {
    e.preventDefault();
    submitBookName();
  }
});
bookNameOverlay.addEventListener("click", e => {
  if (e.target === bookNameOverlay) hideNameDialog();
});
bookParseClose.addEventListener("click", () => { bookParseOverlay.hidden = true; });
bookParseOverlay.addEventListener("click", e => {
  if (e.target === bookParseOverlay) bookParseOverlay.hidden = true;
});

input.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});
input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 200) + "px";
});
sidebarToggle.addEventListener("click", () => {
  appEl.classList.toggle("sidebar-collapsed");
});

refreshConversations();
showWelcome();
input.focus();

// 支持 #graph 直达知识图谱视图
if (location.hash === "#graph") showGraphView();
