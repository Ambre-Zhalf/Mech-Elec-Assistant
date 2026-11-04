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
const sidebarBackdrop = document.getElementById("sidebarBackdrop");
const kgPanelToggle = document.getElementById("kgPanelToggle");
const onlineCount = document.getElementById("onlineCount");
const logoutBtn = document.getElementById("logoutBtn");
const recordsBtn = document.getElementById("recordsBtn");
const loginOverlay = document.getElementById("loginOverlay");
const loginNickname = document.getElementById("loginNickname");
const loginPassword = document.getElementById("loginPassword");
const loginOkBtn = document.getElementById("loginOkBtn");
const loginMsg = document.getElementById("loginMsg");
const adminRecordsOverlay = document.getElementById("adminRecordsOverlay");
const adminCloseBtn = document.getElementById("adminCloseBtn");
const adminRecordsList = document.getElementById("adminRecordsList");
const booksOverlay = document.getElementById("booksOverlay");
const booksModalTitle = document.getElementById("booksModalTitle");
const booksBackBtn = document.getElementById("booksBackBtn");
const booksCloseBtn = document.getElementById("booksCloseBtn");
const courseBtn2 = document.getElementById("courseBtn2");
const courseOverlay = document.getElementById("courseOverlay");
const courseCloseBtn = document.getElementById("courseCloseBtn");
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
// 暂时下架：以下引用属于“利用本机 MinerU 扫描 PDF”的识别 / “我的书籍(Markdown)”功能,元素仍在页面但不会被使用
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
    r.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => {
      let cell = inlineMd(c.trim());
      cell = cell.replace(/\[\[QUERY:([^\]]*)\]\]/g, (m, q) => {
        const name = q.trim().replace(/"/g, "&quot;");
        return '<button type="button" class="query-btn" data-query="' + name + '" title="点击查询该课程的 B 站视频">查询</button>';
      });
      return cell;
    })
  );
  const head = cells[0] || [];
  const body = cells.slice(2);
  let html = "<table><thead><tr>" + head.map(c => "<th>" + c + "</th>").join("") + "</tr></thead><tbody>";
  html += body.map(r => "<tr>" + r.map(c => "<td>" + c + "</td>").join("") + "</tr>").join("");
  return '<div class="table-wrap">' + html + "</tbody></table></div>";
}

function renderCompanyCard(lines) {
  let name = "", reason = "", web = "";
  for (const raw of lines) {
    const t = (raw || "").trim().replace(/^[-*]\s*/, "").replace(/^\d+[.、]\s*/, "");
    if (t.indexOf("企业名称") === 0) name = t.replace(/^企业名称[:：]?\s*/, "");
    else if (t.indexOf("推荐理由") === 0) reason = t.replace(/^推荐理由[:：]?\s*/, "");
    else if (t.indexOf("官方网址") === 0) web = t.replace(/^官方网址[:：]?\s*/, "");
  }
  let h = '<div class="company-card">';
  if (name) h += '<div class="company-card-line"><span class="cc-label">企业名称:</span>' + escapeHtml(name) + "</div>";
  if (reason) h += '<div class="company-card-line"><span class="cc-label">推荐理由:</span>' + escapeHtml(reason) + "</div>";
  if (web) h += '<div class="company-card-line">' + escapeHtml(web) + "</div>";
  if (name) h += pickRow("company", name);
  h += "</div>";
  return h;
}

// 卡片右下角的“选择”按钮(绿色液态胶囊)
function pickRow(kind, value) {
  const v = String(value || "").trim();
  if (!v) return "";
  const title = kind === "job" ? "选择该岗位作为意向岗位" : "选择该公司作为意向公司";
  return '<div class="card-actions"><button type="button" class="pick-btn pick-' + kind +
    '" data-pick="' + v.replace(/"/g, "&quot;") + '" data-kind="' + kind + '" title="' + title + '">选择</button></div>';
}

function renderJobCard(lines) {
  const fields = [];
  for (const raw of lines) {
    let t = (raw || "").trim().replace(/^[-*]\s*/, "").replace(/^\d+[.、]\s*/, "");
    if (!t) continue;
    const m = t.match(/^(.{1,16}?)[:：]\s*([\s\S]*)$/);
    if (m) {
      fields.push({ label: m[1].trim(), segs: [m[2].trim()] });
    } else if (fields.length) {
      fields[fields.length - 1].segs.push(t);
    } else {
      fields.push({ label: "", segs: [t] });
    }
  }
  let jobName = "";
  for (const f of fields) {
    if (!jobName && f.label && f.label.indexOf("岗位") === 0) jobName = f.segs.join(" ").trim();
  }
  let html = '<div class="job-card">';
  for (const f of fields) {
    html += '<div class="job-card-line">';
    if (f.label) html += '<span class="cc-label">' + escapeHtml(f.label) + ':</span>';
    html += f.segs.map(s => linkify(s)).join("<br>");
    html += "</div>";
  }
  if (jobName) html += pickRow("job", jobName);
  html += "</div>";
  return html;
}

function renderMd(src) {
  const parts = src.split(/```/);
  let html = "";
  let listType = null;
  let companyCard = null;
  let jobCard = null;

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
      if (l === "[[JOB_CARD]]") { flushTable(); closeList(); jobCard = []; continue; }
      if (jobCard !== null) {
        if (l === "[[/JOB_CARD]]") {
          html += renderJobCard(jobCard);
          jobCard = null;
        } else {
          jobCard.push(line);
        }
        continue;
      }
      if (l === "[[COMPANY_CARD]]") { flushTable(); closeList(); companyCard = []; continue; }
      if (companyCard !== null) {
        if (l === "[[/COMPANY_CARD]]") {
          html += renderCompanyCard(companyCard);
          companyCard = null;
        } else {
          companyCard.push(line);
        }
        continue;
      }
      if (l.startsWith("|")) { closeList(); table.push(line); continue; }
      flushTable();
      if (/^#{1,4}\s/.test(l)) {
        closeList();
        html += "<h4>" + inlineMd(l.replace(/^#+\s*/, "")) + "</h4>";
      } else if (/^[-*]\s/.test(l)) {
        if (listType === "ol") {
          // 有序列表(如公司1/2/3)里的缩进子项:追加到当前项,保持编号连续不断
          html += "<br>" + inlineMd(l.slice(2));
        } else {
          if (listType !== "ul") { closeList(); html += "<ul>"; listType = "ul"; }
          html += "<li>" + inlineMd(l.slice(2)) + "</li>";
        }
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
      } else if (l.startsWith("[[OPEN_BOOKS]]") && l.endsWith("[[/OPEN_BOOKS]]")) {
        closeList();
        const inner = l.slice("[[OPEN_BOOKS]]".length, -"[[/OPEN_BOOKS]]".length).trim();
        html += '<button type="button" class="books-cta">' + inlineMd(inner) + "</button>";
      } else if (l.startsWith("[[OPEN_COURSE]]") && l.endsWith("[[/OPEN_COURSE]]")) {
        closeList();
        const inner = l.slice("[[OPEN_COURSE]]".length, -"[[/OPEN_COURSE]]".length).trim();
        html += '<button type="button" class="books-cta course-cta">' + inlineMd(inner) + "</button>";
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
  // [[GREEN:...]] → 绿色文字
  html = html.replace(/\[\[GREEN:([^\]]*)\]\]/g, (m, inner) => '<span class="green-text">' + inner + '</span>');
  // [[SEARCH_COMPANY:公司名]] → 「点击搜索」按钮 + 浅灰胶囊框
  html = html.replace(/\[\[SEARCH_COMPANY:([^\]]*)\]\]/g, (m, company) => {
    const name = company.trim();
    return '<span class="search-web-row">' +
      '<span class="search-web-label">官方网址:</span>' +
      '<button type="button" class="search-web-btn" data-company="' + name.replace(/"/g, "&quot;") + '">点击搜索</button>' +
      '<span class="search-web-result">待搜索</span>' +
      '</span>';
  });
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

const INTRO_TEXT = "我是机电学习助手，深耕机电专业学业规划，帮你理清学习方向，毕业拿下心仪 offer。我有“规划”和“竞赛学习”两种模式，默认为“规划模式”，先对你的基本信息“摸个底”，点击下方的“开始”按钮即可体验。";
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
  } else if (event === "sep") {
    // 分段消息:结束当前气泡,另起一个新的助手文本框
    collapseThink(ctx.node);
    const dot = ctx.node.head.querySelector(".dot");
    if (dot) dot.style.display = "none";
    const node = createStreamNode(chatMode);
    setupThinkToggle(node);
    ctx.node = node;
    ctx.raw = "";
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

// 点击卡片右下角“选择”:把该公司/岗位当作意向,自动以用户身份发出名称,由后端进入下一步
function pickCard(btn) {
  if (sendBtn.disabled) return;          // 上一轮还在输出,先等结束
  const name = (btn.dataset.pick || "").trim();
  if (!name) return;
  const kind = btn.dataset.kind || "company";
  // 同类按钮只能选一个:同类型的其他按钮一并置灰,避免重复选择打乱流程
  document.querySelectorAll(".pick-btn.pick-" + kind).forEach(b => { b.disabled = true; });
  btn.classList.add("picked");
  btn.textContent = "已选择";
  const card = btn.closest(".company-card, .job-card");
  if (card) card.classList.add("picked");
  sendAsUser(name);
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
  appEl.classList.remove("kg-drawer-open");
  graphView.hidden = true;
  chat.style.display = "";
  composer.style.display = "";
}

async function importGraph(jsonStr, btn) {
  // 已导入过 → 直接跳转到对应图谱,不再重复建图
  if (btn.dataset.graphId) {
    showGraphView();
    if (window.KG) window.KG.importGraphResult(btn.dataset.graphId);
    return;
  }
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
    btn.textContent = "✅ 已导入";
    btn.disabled = false;
    btn.dataset.graphId = data.graph_id;
    showGraphView();
    if (window.KG) window.KG.importGraphResult(data.graph_id);
  } catch (err) {
    btn.textContent = "⚠️ " + (err.message || "导入失败");
    btn.disabled = false;
    setTimeout(() => { btn.textContent = original; }, 5000);
  }
}

// ---------- 侧边栏:历史对话 ----------

const conversationRenameDialog = document.getElementById("conversationRenameDialog");
const conversationTitleInput = document.getElementById("conversationTitleInput");
const conversationRenameStatus = document.getElementById("conversationRenameStatus");
const titleBackfillDialog = document.getElementById("titleBackfillDialog");
const titleBackfillStatus = document.getElementById("titleBackfillStatus");
const titleBackfillApply = document.getElementById("titleBackfillApply");
let renamingConversationId = "";
let titleBackfillChanges = [];
let titleBackfillVersion = 0;

function titleRequestHeaders() {
  return { "Content-Type": "application/json", Authorization: "Bearer " + authToken };
}

function openConversationRename(id) {
  if (document.getElementById("conversationRenameSave").disabled) return;
  const conversation = allConvs.find(c => c.id === id);
  if (!conversation) return;
  renamingConversationId = id;
  conversationTitleInput.value = conversation.title || "";
  conversationRenameStatus.textContent = "";
  conversationRenameDialog.showModal();
  conversationTitleInput.focus();
  conversationTitleInput.select();
}

document.getElementById("conversationRenameCancel").addEventListener("click", () => conversationRenameDialog.close());
document.getElementById("conversationRenameForm").addEventListener("submit", async event => {
  event.preventDefault();
  const save = document.getElementById("conversationRenameSave");
  if (save.disabled) return;
  const title = conversationTitleInput.value.trim();
  if (!title) {
    conversationRenameStatus.textContent = "请输入标题";
    return;
  }
  save.disabled = true;
  const id = renamingConversationId;
  try {
    const response = await fetch("/api/sessions/" + encodeURIComponent(id), {
      method: "PATCH", headers: titleRequestHeaders(), body: JSON.stringify({ title, client_id: clientId }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "重命名失败");
    await refreshConversations();
    if (renamingConversationId === id) conversationRenameDialog.close();
  } catch (error) {
    conversationRenameStatus.textContent = error.message;
  } finally {
    save.disabled = false;
  }
});

document.getElementById("titleBackfillBtn").addEventListener("click", async () => {
  const version = ++titleBackfillVersion;
  titleBackfillChanges = [];
  titleBackfillApply.disabled = true;
  titleBackfillApply.textContent = "应用这些标题";
  const list = document.getElementById("titleBackfillList");
  list.replaceChildren();
  titleBackfillStatus.textContent = "正在生成预览…";
  titleBackfillDialog.showModal();
  try {
    const response = await fetch("/api/sessions/title-backfill?client_id=" + encodeURIComponent(clientId), {
      headers: titleRequestHeaders(),
    });
    const data = await response.json();
    if (version !== titleBackfillVersion || !titleBackfillDialog.open) return;
    if (!response.ok) throw new Error(data.error || "预览失败");
    titleBackfillChanges = data.changes;
    for (const change of titleBackfillChanges) {
      const item = document.createElement("li");
      const old = document.createElement("span");
      old.className = "old-title";
      old.textContent = change.old_title;
      const next = document.createElement("span");
      next.textContent = "→ " + change.title;
      item.append(old, next);
      list.appendChild(item);
    }
    titleBackfillStatus.textContent = titleBackfillChanges.length
      ? "共 " + titleBackfillChanges.length + " 条默认标题可整理"
      : "没有需要整理的默认标题";
    titleBackfillApply.disabled = !titleBackfillChanges.length;
  } catch (error) {
    if (version === titleBackfillVersion && titleBackfillDialog.open) titleBackfillStatus.textContent = error.message;
  }
});
document.getElementById("titleBackfillClose").addEventListener("click", () => titleBackfillDialog.close());
titleBackfillApply.addEventListener("click", async () => {
  const version = titleBackfillVersion;
  titleBackfillApply.disabled = true;
  try {
    const response = await fetch("/api/sessions/title-backfill", {
      method: "POST", headers: titleRequestHeaders(),
      body: JSON.stringify({ client_id: clientId, changes: titleBackfillChanges }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "整理失败");
    if (version !== titleBackfillVersion || !titleBackfillDialog.open) {
      await refreshConversations();
      return;
    }
    titleBackfillStatus.textContent = "已更新 " + data.updated + " 条标题"
      + (data.skipped ? "，跳过 " + data.skipped + " 条已变化或无权修改的记录" : "");
    titleBackfillApply.textContent = "已完成";
    await refreshConversations();
  } catch (error) {
    if (version === titleBackfillVersion && titleBackfillDialog.open) {
      titleBackfillStatus.textContent = error.message;
      titleBackfillApply.disabled = false;
    }
  }
});

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
    main.title = title.textContent;

    const meta = document.createElement("div");
    meta.className = "conv-meta";
    meta.textContent = (conv.updated_at || "").slice(5, 16) + " · " + conv.count + " 条";

    main.appendChild(title);
    main.appendChild(meta);

    const rename = document.createElement("button");
    rename.type = "button";
    rename.className = "conv-rename";
    rename.title = "重命名对话";
    rename.setAttribute("aria-label", "重命名对话：" + (conv.title || "新对话"));
    rename.textContent = "✎";
    rename.addEventListener("click", () => openConversationRename(conv.id));

    const del = document.createElement("button");
    del.type = "button";
    del.className = "conv-del";
    del.title = "删除该对话";
    del.setAttribute("data-del", conv.id);
    del.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>';

    main.addEventListener("click", () => loadConversation(conv.id));
    item.appendChild(main);
    item.appendChild(rename);
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
  closeSidebarDrawer();
  sessionId = id;
  localStorage.setItem("session_id", sessionId);
  renderConvList();
  try {
    const res = await fetch("/api/sessions/" + encodeURIComponent(id) + "/messages?client_id=" + encodeURIComponent(clientId));
    const messages = await res.json();
    if (id !== sessionId) return;   // 期间又切到了别的对话,放弃这次渲染
    chat.innerHTML = "";
    if (messages && messages.length) {
      for (const m of messages) appendMsg(m.role, m.content, m.mode, m.think, m.think_time);
      scrollToBottom();
    } else {
      showWelcome();
    }
  } catch (e) {
    showWelcome();
  }
  // 登录框还开着时不抢焦点,避免把光标从昵称输入框上抢走
  if (!loginOverlay || loginOverlay.hidden) input.focus();
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
  closeSidebarDrawer();
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
    const chosen = opt.dataset.mode || "plan";
    if (chosen === "challenge") {
      // 竞赛学习已迁移到外部站点:点击“竞赛学习模式”在新标签打开
      window.open("http://47.92.219.134:8369/", "_blank");
      modeMenu.hidden = true;
      return;
    }
    chatMode = chosen;
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
async function searchCompanyWebsite(btn) {
  const company = btn.dataset.company || "";
  if (!company) return;
  const row = btn.closest(".search-web-row");
  const result = row ? row.querySelector(".search-web-result") : null;
  if (btn.disabled || (result && result.dataset.loading === "1")) return;
  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = "搜索中…";
  if (result) result.dataset.loading = "1";
  try {
    const res = await fetch("/api/company/website", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company }),
    });
    const data = await res.json().catch(() => ({}));
    if (data.ok && data.found && data.url) {
      result.classList.remove("notfound");
      result.classList.add("done");
      result.innerHTML = '<a href="' + escapeHtml(data.url) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(data.url) + "</a>";
    } else {
      result.classList.remove("done");
      result.classList.add("notfound");
      result.textContent = "未找到目标公司官网";
    }
  } catch (err) {
    result.classList.remove("done");
    result.classList.add("notfound");
    result.textContent = "未找到目标公司官网";
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
    if (result) delete result.dataset.loading;
  }
}

chat.addEventListener("click", e => {
  const pick = e.target.closest(".pick-btn");
  if (pick) { pickCard(pick); return; }
  const sw = e.target.closest(".search-web-btn");
  if (sw) { searchCompanyWebsite(sw); return; }
  const ctaCourse = e.target.closest(".course-cta");
  if (ctaCourse) { openCourses(); return; }
  const cta = e.target.closest(".books-cta");
  if (cta) { openBooks(); return; }
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

// 暂时下架：“我的书籍（Markdown）”视图入口函数
// function showBooksMd() {
//   booksMenu.hidden = true;
//   booksSearchView.hidden = true;
//   booksMineView.hidden = true;
//   booksMdView.hidden = false;
//   booksModalTitle.textContent = "我的书籍（Markdown）";
//   booksBackBtn.hidden = false;
//   loadMyMarkdowns();
// }

function openBooks() {
  booksOverlay.hidden = false;
  showBooksMenu();
}

function closeBooks() {
  booksOverlay.hidden = true;
}

function openCourses() {
  if (courseOverlay) courseOverlay.hidden = false;
}

function closeCourses() {
  if (courseOverlay) courseOverlay.hidden = true;
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
        // 暂时下架：“识别”按钮,配合“利用本机 MinerU 扫描 PDF”的识别功能下架
        // '<button class="book-btn" data-parse-book="' + fname + '">识别</button>' +
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

/* ---------- 暂时下架：以下为原“利用本机 MinerU 扫描 PDF”的书籍识别 / “我的书籍(Markdown)”相关前端逻辑 ----------
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
---------- 暂时下架 ---------- */

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
if (courseBtn2) courseBtn2.addEventListener("click", openCourses);
if (graphBtn2) graphBtn2.addEventListener("click", () => {
  if (graphMode) closeGraphView(); else showGraphView();
});
booksCloseBtn.addEventListener("click", closeBooks);
booksBackBtn.addEventListener("click", showBooksMenu);
booksOverlay.addEventListener("click", e => {
  if (e.target === booksOverlay) closeBooks();
});
if (courseCloseBtn) courseCloseBtn.addEventListener("click", closeCourses);
if (courseOverlay) {
  courseOverlay.addEventListener("click", e => {
    if (e.target === courseOverlay) closeCourses();
  });
  courseOverlay.addEventListener("click", e => {
    const op = e.target.closest("[data-course]");
    if (op) {
      window.open(op.dataset.course, "_blank");
      closeCourses();
    }
  });
}
booksMenu.querySelectorAll("[data-books]").forEach(b => {
  b.addEventListener("click", () => {
    if (b.dataset.books === "search") showBooksSearch();
    // 暂时下架：原“我的书籍（Markdown）”入口跳转
    // else if (b.dataset.books === "md") showBooksMd();
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
  // 暂时下架：原“识别”按钮点击逻辑
  // const parseBtn = e.target.closest("[data-parse-book]");
  // if (parseBtn) { parseBook(parseBtn.dataset.parseBook); return; }
  const btn = e.target.closest("[data-delete-book]");
  if (btn) deleteBook(btn.dataset.deleteBook);
});
// 暂时下架：原“我的书籍（Markdown）”列表点击逻辑
// bookMdList.addEventListener("click", e => {
//   const viewBtn = e.target.closest("[data-view-md]");
//   if (viewBtn) { showViewMenu(viewBtn, viewBtn.dataset.viewMd); return; }
//   const btn = e.target.closest("[data-delete-md]");
//   if (btn) deleteMarkdown(btn.dataset.deleteMd);
// });
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
// 暂时下架：原“识别结果”弹窗关闭逻辑
// bookParseClose.addEventListener("click", () => { bookParseOverlay.hidden = true; });
// bookParseOverlay.addEventListener("click", e => {
//   if (e.target === bookParseOverlay) bookParseOverlay.hidden = true;
// });

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
// ---- 移动端适配:侧边栏抽屉 / 知识图谱列表面板抽屉 ----
const isMobile = () => window.matchMedia("(max-width: 900px)").matches;

function closeSidebarDrawer() {
  if (isMobile()) appEl.classList.remove("sidebar-open");
}

function syncViewportMode() {
  if (isMobile()) {
    // 进入窄屏:去掉桌面折叠态,侧边栏抽屉默认收起
    appEl.classList.remove("sidebar-collapsed");
    appEl.classList.remove("sidebar-open");
    appEl.classList.remove("kg-drawer-open");
    sidebarToggle.title = "展开侧边栏";
  } else {
    // 回到宽屏:移除抽屉相关类,恢复桌面常驻侧边栏与图谱面板
    appEl.classList.remove("sidebar-open");
    appEl.classList.remove("kg-drawer-open");
    sidebarToggle.title = appEl.classList.contains("sidebar-collapsed") ? "展开侧边栏" : "收起侧边栏";
  }
}

sidebarToggle.addEventListener("click", () => {
  if (isMobile()) {
    const open = appEl.classList.toggle("sidebar-open");
    sidebarToggle.title = open ? "收起侧边栏" : "展开侧边栏";
  } else {
    const collapsed = appEl.classList.toggle("sidebar-collapsed");
    sidebarToggle.title = collapsed ? "展开侧边栏" : "收起侧边栏";
  }
});

if (sidebarBackdrop) {
  sidebarBackdrop.addEventListener("click", () => {
    appEl.classList.remove("sidebar-open");
    appEl.classList.remove("kg-drawer-open");
  });
}
if (kgPanelToggle) {
  kgPanelToggle.addEventListener("click", () => {
    appEl.classList.toggle("kg-drawer-open");
  });
}

window.addEventListener("resize", syncViewportMode);
syncViewportMode();

// ---------- 登录 + 在线人数(轮询) ----------
let nickname = localStorage.getItem("auth_nickname") || "";
let authRole = localStorage.getItem("auth_role") || "";
let authToken = localStorage.getItem("auth_token") || "";

function cleanNickname(s) {
  return (s || "")
    .replace(/[\u0000-\u001f\u007f]/g, "")  // 去掉控制字符
    .replace(/\s+/g, " ")                    // 合并连续空白
    .trim()
    .slice(0, 24);
}

function setLoginMsg(text) {
  if (!loginMsg) return;
  loginMsg.hidden = !text;
  loginMsg.textContent = text || "";
}

async function loginSubmit() {
  const nick = cleanNickname(loginNickname.value);
  const pwd = loginPassword.value;
  if (!nick || !pwd) { setLoginMsg("昵称和密码不能为空"); return; }
  loginOkBtn.disabled = true;
  setLoginMsg("");
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId, nickname: nick, password: pwd }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "登录失败");
    nickname = data.nickname;
    authRole = data.role || "user";
    authToken = data.token || "";
    localStorage.setItem("auth_nickname", nickname);
    localStorage.setItem("auth_role", authRole);
    localStorage.setItem("auth_token", authToken);
    loginOverlay.hidden = true;
    loginPassword.value = "";
    // 登录后开启一段全新对话:避免沿用退出前那段会话的 session_id,
    // 否则界面显示的是自我介绍,点“开始”却把消息发进了上一段对话
    startNewChat();
    startPresenceLoop();
    if (logoutBtn) logoutBtn.hidden = false;
    if (recordsBtn) recordsBtn.hidden = (authRole !== "admin");
    if (authRole === "admin") openAdminRecords();
  } catch (e) {
    setLoginMsg(e.message || "登录失败");
  } finally {
    loginOkBtn.disabled = false;
  }
}

function showLoginGate() {
  setLoginMsg("");
  loginPassword.value = "";
  loginOverlay.hidden = false;
  loginNickname.focus();
}

async function logoutSubmit() {
  const token = authToken;
  nickname = ""; authRole = ""; authToken = "";
  localStorage.removeItem("auth_nickname");
  localStorage.removeItem("auth_role");
  localStorage.removeItem("auth_token");
  if (token) {
    fetch("/api/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    }).catch(() => {});
  }
  if (presenceTimer) { clearInterval(presenceTimer); presenceTimer = null; }
  if (logoutBtn) logoutBtn.hidden = true;
  if (recordsBtn) recordsBtn.hidden = true;
  if (onlineCount) onlineCount.textContent = "";
  closeAdminRecords();
  input.value = "";
  // 退出登录时同样重置到全新对话,保证界面状态与后端会话状态一致
  startNewChat();
  showLoginGate();
}

async function presenceTick() {
  try {
    await fetch("/api/presence/ping", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId, nickname }),
    });
    const res = await fetch("/api/presence/online");
    const data = await res.json().catch(() => ({}));
    if (onlineCount) onlineCount.textContent = "在线 " + (data.online || 0);
  } catch (e) { /* 网络/服务异常时忽略,下一轮再试 */ }
}

let presenceTimer = null;
function startPresenceLoop() {
  if (presenceTimer) return;
  presenceTick();
  presenceTimer = setInterval(presenceTick, 10000);
}

async function initLogin() {
  if (authToken) {
    try {
      const res = await fetch("/api/auth/me?token=" + encodeURIComponent(authToken));
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok) {
        nickname = data.nickname;
        authRole = data.role || "user";
        localStorage.setItem("auth_nickname", nickname);
        localStorage.setItem("auth_role", authRole);
        loginOverlay.hidden = true;
        if (logoutBtn) logoutBtn.hidden = false;
        if (recordsBtn) recordsBtn.hidden = (authRole !== "admin");
        startPresenceLoop();
        return;
      }
    } catch (e) {}
    authToken = ""; nickname = ""; authRole = "";
    localStorage.removeItem("auth_nickname");
    localStorage.removeItem("auth_role");
    localStorage.removeItem("auth_token");
  }
  showLoginGate();
}

// ---------- 管理员:用户记录 ----------
async function openAdminRecords() {
  if (!adminRecordsOverlay) return;
  adminRecordsOverlay.hidden = false;
  adminRecordsList.innerHTML = '<div class="admin-empty">加载中…</div>';
  try {
    const res = await fetch("/api/admin/records?token=" + encodeURIComponent(authToken));
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      adminRecordsList.innerHTML = '<div class="admin-empty">⚠️ ' + escapeHtml(data.error || "加载失败") + "</div>";
      return;
    }
    renderAdminRecords(data.records || []);
  } catch (e) {
    adminRecordsList.innerHTML = '<div class="admin-empty">⚠️ ' + escapeHtml(e.message || "加载失败") + "</div>";
  }
}

function closeAdminRecords() {
  if (adminRecordsOverlay) adminRecordsOverlay.hidden = true;
}

function fmtAdminTime(t) {
  if (!t) return "";
  const d = new Date(String(t).replace(" ", "T"));
  if (isNaN(d.getTime())) return String(t).slice(5, 16);
  return (d.getMonth() + 1) + "/" + d.getDate() + " " +
    String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
}

function renderAdminRecords(records) {
  if (!records || !records.length) {
    adminRecordsList.innerHTML = '<div class="admin-empty">暂无用户记录</div>';
    return;
  }
  adminRecordsList.innerHTML = records.map(u => {
    const msgs = (u.messages || []).map(m => {
      const role = m.role === "user" ? "提问" : "回复";
      return '<div class="admin-msg ' + escapeHtml(m.role) + '">' +
        '<span class="admin-role">' + role + '</span>' +
        '<span class="admin-content">' + escapeHtml(m.content || "") + '</span>' +
        '<span class="admin-time">' + escapeHtml(fmtAdminTime(m.time)) + '</span>' +
      '</div>';
    }).join("");
    const badge = u.role === "admin" ? '<span class="admin-badge admin">管理员</span>' : "";
    return '<div class="admin-user">' +
      '<div class="admin-user-head"><span>' + escapeHtml(u.nickname || "") + '</span>' + badge +
        '<span class="admin-cnt">' + (u.messages || []).length + ' 条</span>' +
        '<button type="button" class="admin-toggle">展开</button></div>' +
      '<div class="admin-user-body" hidden>' + msgs + '</div></div>';
  }).join("");
}

if (loginOkBtn) loginOkBtn.addEventListener("click", loginSubmit);
if (loginPassword) loginPassword.addEventListener("keydown", e => { if (e.key === "Enter") loginSubmit(); });
if (loginNickname) loginNickname.addEventListener("keydown", e => { if (e.key === "Enter") loginPassword.focus(); });
if (logoutBtn) logoutBtn.addEventListener("click", logoutSubmit);
if (recordsBtn) recordsBtn.addEventListener("click", openAdminRecords);
if (adminCloseBtn) adminCloseBtn.addEventListener("click", closeAdminRecords);
if (adminRecordsOverlay) adminRecordsOverlay.addEventListener("click", e => { if (e.target === adminRecordsOverlay) closeAdminRecords(); });
if (adminRecordsList) adminRecordsList.addEventListener("click", e => {
  const btn = e.target.closest(".admin-toggle");
  if (!btn) return;
  const user = btn.closest(".admin-user");
  if (!user) return;
  const body = user.querySelector(".admin-user-body");
  if (!body) return;
  body.hidden = !body.hidden;
  btn.textContent = body.hidden ? "展开" : "收起";
});

refreshConversations();
// 刷新页面后自动接着上次那段对话继续;没有历史消息时会自动回落到自我介绍
loadConversation(sessionId);
initLogin();

// 支持 #graph 直达知识图谱视图
if (location.hash === "#graph") showGraphView();

// ---------- 课程视频查询:后台任务 + 弹窗进度 ----------
const cqOverlay = document.getElementById("courseQueryOverlay");
const cqMinBtn = document.getElementById("cqMinBtn");
const cqSteps = document.getElementById("cqSteps");
const cqResult = document.getElementById("cqResult");
const cqTitle = document.getElementById("cqTitle");

const __courseTasks = {};   // query -> {id, done}
const __courseResult = {};  // query -> markdown result
const __courseLogs = {};    // query -> [log lines]
let __cqPoll = null;        // 当前轮询定时器(每 1s)

function renderCourseSteps(query) {
  if (!cqSteps) return;
  const logs = __courseLogs[query] || [];
  cqSteps.innerHTML = logs.map(l => '<div class="cq-step">' + escapeHtml(l) + "</div>").join("");
}

function renderCourseResult(query) {
  if (!cqResult) return;
  const md = __courseResult[query];
  cqResult.innerHTML = (md != null)
    ? '<div class="cq-result-title">推荐视频(播放量前 3)</div>' + renderMd(md)
    : "";
}

function markCourseDone(query) {
  document.querySelectorAll(".query-btn").forEach(b => {
    if ((b.dataset.query || "") === query) {
      b.classList.add("done");
      b.textContent = "查看";
    }
  });
}

function markCourseRunning(query) {
  document.querySelectorAll(".query-btn").forEach(b => {
    if ((b.dataset.query || "") === query && !b.classList.contains("done")) {
      b.textContent = "查询中…";
    }
  });
}

function stopCoursePoll() {
  if (__cqPoll) { clearInterval(__cqPoll); __cqPoll = null; }
}

function startCoursePoll(query, taskId) {
  stopCoursePoll();
  const tick = async () => {
    try {
      const res = await fetch("/api/course/video/status/" + encodeURIComponent(taskId));
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "查询失败");
      __courseLogs[query] = data.logs || [];
      renderCourseSteps(query);
      if (data.status === "done") {
        __courseResult[query] = data.text || "";
        if (__courseTasks[query]) __courseTasks[query].done = true;
        markCourseDone(query);
        renderCourseResult(query);
        stopCoursePoll();
        return;
      }
      if (data.status === "error") {
        if (cqResult) cqResult.innerHTML = '<div class="cq-error">⚠️ ' + escapeHtml(data.error || "查询失败") + "</div>";
        stopCoursePoll();
      }
    } catch (err) {
      if (cqResult) cqResult.innerHTML = '<div class="cq-error">⚠️ ' + escapeHtml(err.message || "查询失败") + "</div>";
      stopCoursePoll();
    }
  };
  tick();
  __cqPoll = setInterval(tick, 1000);
}

async function openCourseQuery(query) {
  if (!query) return;
  if (cqOverlay) cqOverlay.hidden = false;
  if (cqResult) cqResult.innerHTML = "";
  if (cqTitle) cqTitle.textContent = query;
  // 该课程已查询完成,直接展示缓存结果
  if (__courseResult[query] != null) {
    renderCourseSteps(query);
    renderCourseResult(query);
    return;
  }
  let taskId = (__courseTasks[query] && __courseTasks[query].id);
  if (!taskId) {
    try {
      const res = await fetch("/api/course/video", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "查询失败");
      taskId = data.task_id;
      __courseTasks[query] = { id: taskId, done: false };
    } catch (err) {
      if (cqResult) cqResult.innerHTML = '<div class="cq-error">⚠️ ' + escapeHtml(err.message || "开始查询失败") + "</div>";
      return;
    }
  }
  markCourseRunning(query);
  startCoursePoll(query, taskId);
}

// 点击「查询/查看」→ 打开弹窗并跟踪(或复用)后台任务
document.addEventListener("click", (e) => {
  const q = e.target.closest(".query-btn");
  if (!q) return;
  openCourseQuery(q.dataset.query || "");
});

// 「_」最小化:只关弹窗,不取消后台任务
if (cqMinBtn) cqMinBtn.addEventListener("click", () => {
  if (cqOverlay) cqOverlay.hidden = true;
  stopCoursePoll();
});
