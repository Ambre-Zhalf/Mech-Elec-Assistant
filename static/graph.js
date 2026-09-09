/**
 * 知识图谱模块(原生 JS):移植自 zstp 的 Vue + D3 实现。
 * 通过 window.KG 对外暴露 init / open / loadGraph / importGraphResult 等方法。
 */
(function () {
  "use strict";

  // ---------- 颜色 / 半径 ----------
  var TYPE_COLORS = [
    "#4f6df5", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6",
    "#ec4899", "#06b6d4", "#f97316", "#14b8a6", "#6366f1",
    "#a855f7", "#e11d48", "#0891b2", "#ca8a04", "#059669"
  ];
  var typeColorMap = new Map();
  function colorForType(type) {
    var key = String(type || "default").toLowerCase();
    if (!typeColorMap.has(key)) {
      typeColorMap.set(key, TYPE_COLORS[typeColorMap.size % TYPE_COLORS.length]);
    }
    return typeColorMap.get(key);
  }
  function nodeRadius(degree) {
    return Math.max(6, Math.min(20, 6 + Math.sqrt(degree || 0) * 2));
  }

  // ---------- DOM ----------
  var el = {};
  var graphListData = [];   // 后端返回的图谱列表
  var currentGraphId = null;

  // 当前图谱数据
  var nodes = [];
  var links = [];
  var currentGraph = null;

  // D3 状态
  var simulation = null;
  var zoomBehavior = null;
  var svgSel = null;
  var rootSel = null;
  var containerEl = null;
  var width = 800, height = 600;
  var layout = "force";

  // ---------- API ----------
  function api(path, options) {
    return fetch(path, Object.assign({}, options, {
      headers: Object.assign({ "Content-Type": "application/json" }, (options && options.headers) || {})
    })).then(function (res) {
      if (!res.ok) {
        return res.json().catch(function () { return {}; }).then(function (b) {
          throw new Error(b.error || ("请求失败: " + res.status));
        });
      }
      return res.json();
    });
  }

  function listGraphs() { return api("/api/graphs"); }
  function fetchGraph(id) { return api("/api/graphs/" + encodeURIComponent(id)); }
  function saveGraph(id, data) { return api("/api/graphs/" + encodeURIComponent(id), { method: "PUT", body: JSON.stringify(data) }); }
  function renameGraph(id, name) { return api("/api/graphs/" + encodeURIComponent(id), { method: "PATCH", body: JSON.stringify({ name: name }) }); }
  function deleteGraph(id) { return api("/api/graphs/" + encodeURIComponent(id), { method: "DELETE" }); }
  function removeImport(id, importId) { return api("/api/graphs/" + encodeURIComponent(id) + "/imports/" + encodeURIComponent(importId), { method: "DELETE" }); }

  // ---------- 图表尺寸 / 缩放 ----------
  function updateDimensions() {
    if (!containerEl) return;
    var rect = containerEl.getBoundingClientRect();
    width = rect.width || 800;
    height = rect.height || 600;
  }

  function setupZoom() {
    zoomBehavior = d3.zoom()
      .scaleExtent([0.1, 8])
      .on("zoom", function (event) {
        rootSel.attr("transform", event.transform);
      });
    svgSel.call(zoomBehavior)
      .on("dblclick.zoom", null)
      .on("click.background", function (event) {
        if (event.target === svgSel.node()) hideTooltip();
      });
  }

  // ---------- 数据构建 ----------
  function buildData() {
    var oldMap = new Map();
    nodes.forEach(function (n) { oldMap.set(n.id, { x: n.x, y: n.y }); });

    var degreeMap = new Map();
    links.forEach(function (l) {
      degreeMap.set(l.source, (degreeMap.get(l.source) || 0) + 1);
      degreeMap.set(l.target, (degreeMap.get(l.target) || 0) + 1);
    });

    var nodeList = (currentGraph && currentGraph.nodes) || [];
    var edgeList = (currentGraph && currentGraph.edges) || [];
    var nodeIdSet = new Set(nodeList.map(function (n) { return n.id; }));
    var actualLinks = edgeList.filter(function (e) {
      return nodeIdSet.has(e.source) && nodeIdSet.has(e.target);
    });

    nodes = nodeList.map(function (n) {
      var old = oldMap.get(n.id);
      var deg = degreeMap.get(n.id) || 0;
      return {
        id: n.id,
        label: n.label,
        type: n.type,
        properties: n.properties || {},
        sourceFile: n.sourceFile,
        degree: deg,
        color: colorForType(n.type),
        radius: nodeRadius(deg),
        x: old ? old.x : (width / 2 + (Math.random() - 0.5) * 300),
        y: old ? old.y : (height / 2 + (Math.random() - 0.5) * 300)
      };
    });

    var nodeMap = new Map(nodes.map(function (n) { return [n.id, n]; }));
    links = actualLinks.map(function (e) {
      return {
        id: e.id,
        source: nodeMap.get(e.source) || e.source,
        target: nodeMap.get(e.target) || e.target,
        label: e.label || "",
        weight: e.weight || 1
      };
    });
  }

  // ---------- 渲染 ----------
  function renderElements() {
    var g = rootSel;

    // 边
    var edgeSel = g.selectAll("g.graph-edge").data(links, function (d) { return d.id; });
    edgeSel.exit().remove();
    var edgeEnter = edgeSel.enter().append("g").attr("class", "graph-edge");
    edgeEnter.append("line");
    edgeEnter.append("text").attr("class", "graph-edge-label");
    var edgeMerge = edgeEnter.merge(edgeSel);
    edgeMerge.select("line").attr("stroke-width", function (d) { return Math.min(d.weight || 1, 5); });
    edgeMerge.select("text").text(function (d) { return d.label; });

    // 节点
    var nodeSel = g.selectAll("g.graph-node").data(nodes, function (d) { return d.id; });
    nodeSel.exit().remove();
    var nodeEnter = nodeSel.enter().append("g").attr("class", "graph-node");
    nodeEnter.append("circle").attr("class", "node-hit-area");
    nodeEnter.append("circle").attr("class", "node-circle");
    nodeEnter.append("text").attr("class", "graph-node-label");

    var nodeMerge = nodeEnter.merge(nodeSel);
    nodeMerge.select(".node-hit-area").attr("r", function (d) { return d.radius + 10; });
    nodeMerge.select(".node-circle")
      .attr("r", function (d) { return d.radius; })
      .attr("fill", function (d) { return d.color; });
    nodeMerge.select(".graph-node-label")
      .attr("dy", function (d) { return d.radius + 14; })
      .text(function (d) { return d.label; });

    nodeMerge.call(
      d3.drag()
        .on("start", dragStarted)
        .on("drag", dragged)
        .on("end", dragEnded)
    );

    nodeMerge
      .on("mouseenter", function (event, d) { showTooltip(event, d); })
      .on("mousemove", function (event, d) { positionTooltip(event); })
      .on("mouseleave", function () { hideTooltip(); })
      .on("click", function (event, d) {
        event.stopPropagation();
        // 点击节点时高亮其邻居(视觉反馈)
        var highlight = new Set([String(d.id)]);
        links.forEach(function (l) {
          var src = typeof l.source === "object" ? l.source.id : l.source;
          var tgt = typeof l.target === "object" ? l.target.id : l.target;
          if (String(src) === String(d.id)) highlight.add(String(tgt));
          if (String(tgt) === String(d.id)) highlight.add(String(src));
        });
        g.selectAll("g.graph-node .node-circle").classed("highlighted", function (nd) {
          return highlight.has(String(nd.id));
        });
        g.selectAll("g.graph-edge line").classed("highlighted", function (l) {
          var src = typeof l.source === "object" ? l.source.id : l.source;
          var tgt = typeof l.target === "object" ? l.target.id : l.target;
          return highlight.has(String(src)) && highlight.has(String(tgt));
        });
      });
  }

  // ---------- 布局 ----------
  function runForce() {
    if (simulation) { simulation.stop(); simulation = null; }
    var nodeMap = new Map(nodes.map(function (n) { return [n.id, n]; }));
    var resolvedLinks = links.map(function (l) {
      return {
        source: typeof l.source === "object" ? l.source.id : l.source,
        target: typeof l.target === "object" ? l.target.id : l.target,
        label: l.label,
        weight: l.weight
      };
    });
    simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(resolvedLinks).id(function (d) { return d.id; }).distance(90))
      .force("charge", d3.forceManyBody().strength(-240))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius(function (d) { return d.radius + 12; }))
      .on("tick", ticked);
    // 把 labels 存回 links,供 ticked 使用
    links = resolvedLinks;
    links.forEach(function (l) {
      l.__label = l.label;
    });
  }

  function ticked() {
    rootSel.selectAll("g.graph-node")
      .attr("transform", function (d) { return "translate(" + d.x + "," + d.y + ")"; });
    rootSel.selectAll("g.graph-edge line")
      .attr("x1", function (d) { return d.source.x; })
      .attr("y1", function (d) { return d.source.y; })
      .attr("x2", function (d) { return d.target.x; })
      .attr("y2", function (d) { return d.target.y; });
    rootSel.selectAll("g.graph-edge text")
      .attr("x", function (d) { return (d.source.x + d.target.x) / 2; })
      .attr("y", function (d) { return (d.source.y + d.target.y) / 2 - 4; });
  }

  function layoutCircular() {
    var cx = width / 2, cy = height / 2;
    var r = Math.min(width, height) * 0.38;
    var sorted = nodes.slice().sort(function (a, b) { return String(a.type).localeCompare(String(b.type)); });
    var indexMap = new Map(sorted.map(function (n, i) { return [n.id, i]; }));
    nodes.forEach(function (n) {
      var i = indexMap.get(n.id);
      var angle = (2 * Math.PI * i) / Math.max(1, nodes.length) - Math.PI / 2;
      n.x = cx + r * Math.cos(angle);
      n.y = cy + r * Math.sin(angle);
      n.fx = n.x; n.fy = n.y;
    });
  }

  function layoutGrid() {
    var cols = Math.ceil(Math.sqrt(Math.max(1, nodes.length)));
    var rows = Math.ceil(nodes.length / cols);
    var cellW = width / (cols + 1);
    var cellH = height / (rows + 1);
    var sorted = nodes.slice().sort(function (a, b) { return String(a.type).localeCompare(String(b.type)); });
    var indexMap = new Map(sorted.map(function (n, i) { return [n.id, i]; }));
    nodes.forEach(function (n) {
      var i = indexMap.get(n.id);
      n.x = (i % cols + 1) * cellW;
      n.y = (Math.floor(i / cols) + 1) * cellH;
      n.fx = n.x; n.fy = n.y;
    });
  }

  function layoutConcentric() {
    var cx = width / 2, cy = height / 2;
    var sorted = nodes.slice().sort(function (a, b) { return b.degree - a.degree; });
    if (sorted.length === 0) return;
    var rings = [[]];
    var curDeg = sorted[0].degree;
    sorted.forEach(function (n) {
      if (n.degree < curDeg && rings[rings.length - 1].length > 0) {
        rings.push([]); curDeg = n.degree;
      }
      rings[rings.length - 1].push(n);
    });
    if (rings.length === 1 && rings[0].length > 1) {
      var all = rings[0];
      rings[0] = [all[0]];
      rings.push(all.slice(1));
    }
    var maxR = Math.min(width, height) * 0.38;
    var gap = rings.length > 1 ? maxR / rings.length : maxR;
    rings.forEach(function (ring, ri) {
      var r = (ri === 0 && ring.length === 1) ? 0 : gap * (ri + 0.5);
      ring.forEach(function (n, i) {
        var angle = (2 * Math.PI * i) / Math.max(1, ring.length) - Math.PI / 2;
        n.x = cx + r * Math.cos(angle);
        n.y = cy + r * Math.sin(angle);
        n.fx = n.x; n.fy = n.y;
      });
    });
  }

  function applyStaticLayout(name) {
    if (name === "circular") layoutCircular();
    else if (name === "grid") layoutGrid();
    else if (name === "concentric") layoutConcentric();
  }

  function setLayout(name) {
    layout = name;
    if (simulation) { simulation.stop(); simulation = null; }
    var controls = el.controls.querySelectorAll("[data-layout]");
    controls.forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-layout") === name);
    });
    if (name === "force") {
      nodes.forEach(function (n) { n.fx = null; n.fy = null; });
      runForce();
    } else {
      applyStaticLayout(name);
      endPositions();
    }
  }

  function endPositions() {
    rootSel.selectAll("g.graph-node")
      .attr("transform", function (d) { return "translate(" + d.x + "," + d.y + ")"; });
    rootSel.selectAll("g.graph-edge line")
      .attr("x1", function (d) { return d.source.x; })
      .attr("y1", function (d) { return d.source.y; })
      .attr("x2", function (d) { return d.target.x; })
      .attr("y2", function (d) { return d.target.y; });
    rootSel.selectAll("g.graph-edge text")
      .attr("x", function (d) { return (d.source.x + d.target.x) / 2; })
      .attr("y", function (d) { return (d.source.y + d.target.y) / 2 - 4; });
  }

  // ---------- 拖动 ----------
  function dragStarted(event, d) {
    if (!event.active && simulation) simulation.alphaTarget(0.3).restart();
    d.fx = d.x; d.fy = d.y;
  }
  function dragged(event, d) {
    d.fx = event.x; d.fy = event.y;
  }
  function dragEnded(event, d) {
    if (!event.active && simulation) simulation.alphaTarget(0);
    if (layout === "force") { d.fx = null; d.fy = null; }
  }

  // ---------- 缩放 ----------
  function zoomIn() {
    if (svgSel && zoomBehavior) svgSel.transition().duration(300).call(zoomBehavior.scaleBy, 1.3);
  }
  function zoomOut() {
    if (svgSel && zoomBehavior) svgSel.transition().duration(300).call(zoomBehavior.scaleBy, 0.7);
  }
  function resetZoom() {
    if (svgSel && zoomBehavior) svgSel.transition().duration(500).call(zoomBehavior.transform, d3.zoomIdentity);
  }
  function fitToView() {
    if (!svgSel || !zoomBehavior || nodes.length === 0) return;
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodes.forEach(function (n) {
      minX = Math.min(minX, n.x - n.radius);
      minY = Math.min(minY, n.y - n.radius);
      maxX = Math.max(maxX, n.x + n.radius);
      maxY = Math.max(maxY, n.y + n.radius);
    });
    var pad = 50;
    var gw = maxX - minX + pad * 2;
    var gh = maxY - minY + pad * 2;
    var scale = Math.min(width / gw, height / gh, 2);
    var tx = (width - (minX + maxX) * scale) / 2;
    var ty = (height - (minY + maxY) * scale) / 2;
    svgSel.transition().duration(500)
      .call(zoomBehavior.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
  }

  // ---------- 提示框 / 图例 / 空状态 ----------
  function showTooltip(event, d) {
    el.tooltip.innerHTML = buildTooltip(d);
    el.tooltip.hidden = false;
    positionTooltip(event);
  }
  function positionTooltip(event) {
    var rect = containerEl.getBoundingClientRect();
    el.tooltip.style.left = (event.clientX - rect.left + 16) + "px";
    el.tooltip.style.top = (event.clientY - rect.top + 16) + "px";
  }
  function hideTooltip() { el.tooltip.hidden = true; }
  function buildTooltip(d) {
    var html = "<h4>" + escapeHtml(d.label) + "</h4>";
    html += '<span class="type-badge" style="background:' + d.color + '">' + escapeHtml(d.type || "default") + "</span>";
    html += '<div class="prop-row"><span class="prop-key">连接数</span><span>' + d.degree + "</span></div>";
    Object.keys(d.properties || {}).forEach(function (k) {
      html += '<div class="prop-row"><span class="prop-key">' + escapeHtml(k) + "</span><span>" + escapeHtml(String(d.properties[k])) + "</span></div>";
    });
    if (d.sourceFile) {
      html += '<div class="prop-row"><span class="prop-key">来源</span><span>' + escapeHtml(String(d.sourceFile)) + "</span></div>";
    }
    return html;
  }

  function renderLegend() {
    var types = new Set();
    nodes.forEach(function (n) { types.add(n.type || "default"); });
    if (types.size === 0) { el.legend.hidden = true; return; }
    el.legend.hidden = false;
    el.legend.innerHTML = Array.from(types).map(function (t) {
      return '<div class="graph-legend-item"><span class="graph-legend-dot" style="background:' + colorForType(t) + '"></span><span>' + escapeHtml(t) + "</span></div>";
    }).join("");
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ---------- 图谱列表 / 导入历史 ----------
  function formatTime(ts) {
    if (!ts) return "";
    var d = new Date(Number(ts));
    if (isNaN(d.getTime())) return "";
    var now = new Date();
    var sameDay = d.toDateString() === now.toDateString();
    var hh = String(d.getHours()).padStart(2, "0");
    var mm = String(d.getMinutes()).padStart(2, "0");
    return sameDay ? hh + ":" + mm : (d.getMonth() + 1) + "/" + d.getDate() + " " + hh + ":" + mm;
  }

  function renderGraphList() {
    if (!el.graphList) return;
    if (graphListData.length === 0) {
      el.graphList.innerHTML = '<div class="kg-empty">暂无图谱<br><span>导入学习计划后自动创建</span></div>';
      return;
    }
    el.graphList.innerHTML = graphListData.map(function (g) {
      var active = g.id === currentGraphId ? " active" : "";
      return '<div class="kg-graph-item' + active + '">' +
        '<div class="kg-graph-main" data-gid="' + g.id + '">' +
          '<div class="kg-graph-name">' + escapeHtml(g.name) + "</div>" +
          '<div class="kg-graph-meta">' + (g.nodeCount || 0) + " 节点 · " + (g.edgeCount || 0) + " 关系 · " + escapeHtml(formatTime(g.updatedAt || g.createdAt)) + "</div>" +
        "</div>" +
        '<div class="kg-graph-actions">' +
          '<button class="kg-action" data-act-rename="' + g.id + '" title="重命名">✎</button>' +
          '<button class="kg-action danger" data-act-delete="' + g.id + '" title="删除">✕</button>' +
        "</div></div>";
    }).join("");
  }

  function renderImportHistory(history) {
    if (!el.importHistory) return;
    history = history || (currentGraph && currentGraph.importHistory) || [];
    if (history.length === 0) {
      el.importHistory.innerHTML = '<div class="kg-empty">暂无导入记录</div>';
      return;
    }
    // 后端已按时间倒序
    el.importHistory.innerHTML = history.map(function (h) {
      return '<div class="kg-history-item">' +
        '<div class="kg-history-info">' +
          '<div class="kg-history-name">' + escapeHtml(h.fileName) + "</div>" +
          '<div class="kg-history-meta">' + (h.nodesAdded || 0) + " 节点, " + (h.edgesAdded || 0) + " 关系 · " + escapeHtml(formatTime(h.timestamp)) + "</div>" +
        "</div>" +
        '<button class="kg-action" data-remove-import="' + h.id + '" title="撤销该次导入">撤销</button></div>';
    }).join("");
  }

  function updateStats() {
    el.title.textContent = (currentGraph && currentGraph.name) || "知识图谱";
    el.stats.textContent = currentGraph
      ? ((currentGraph.nodes && currentGraph.nodes.length) || 0) + " 节点 · " + ((currentGraph.edges && currentGraph.edges.length) || 0) + " 关系"
      : "";
    el.empty.hidden = nodes.length > 0;
  }

  // ---------- 加载 / 数据流 ----------
  function loadGraph(graphId) {
    return fetchGraph(graphId).then(function (graph) {
      currentGraph = graph;
      currentGraphId = graph.id;
      buildData();
      renderElements();
      renderLegend();
      renderImportHistory(graph.importHistory);
      updateStats();
      if (layout === "force") {
        runForce();
      } else {
        applyStaticLayout(layout);
        endPositions();
      }
      refreshGraphList().then(function () { renderGraphList(); });
    }).catch(function (err) {
      console.error("[KG] loadGraph error:", err);
      updateStats();
    });
  }

  function refreshGraphList() {
    return listGraphs().then(function (list) {
      graphListData = list;
      renderGraphList();
    }).catch(function (err) {
      console.warn("[KG] list error:", err);
      graphListData = [];
      renderGraphList();
    });
  }

  // ---------- 初始化 ----------
  var initialized = false;
  function init() {
    if (initialized) return;
    el.graphView = document.getElementById("graphView");
    el.graphList = document.getElementById("kgGraphList");
    el.importHistory = document.getElementById("kgImportHistory");
    el.title = document.getElementById("kgTitle");
    el.stats = document.getElementById("kgStats");
    el.canvas = document.getElementById("kgCanvas");
    el.svg = document.getElementById("kgSvg");
    el.root = document.getElementById("kgRoot");
    el.legend = document.getElementById("kgLegend");
    el.controls = document.getElementById("kgControls");
    el.tooltip = document.getElementById("kgTooltip");
    el.empty = document.getElementById("kgEmpty");

    if (!el.svg || !el.root || !el.canvas) return;
    containerEl = el.canvas;
    svgSel = d3.select(el.svg);
    rootSel = d3.select(el.root);
    updateDimensions();
    setupZoom();

    // 控件事件
    el.controls.querySelectorAll("[data-act]").forEach(function (b) {
      b.addEventListener("click", function () {
        var act = b.getAttribute("data-act");
        if (act === "zoom-in") zoomIn();
        else if (act === "zoom-out") zoomOut();
        else if (act === "reset") resetZoom();
        else if (act === "fit") fitToView();
      });
    });
    el.controls.querySelectorAll("[data-layout]").forEach(function (b) {
      b.addEventListener("click", function () {
        setLayout(b.getAttribute("data-layout"));
      });
    });

    // 新建 / 列表 / 历史事件
    document.getElementById("kgNewGraph").addEventListener("click", function () {
      createNewGraph();
    });
    el.graphList.addEventListener("click", onGraphListClick);
  el.importHistory.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-remove-import]");
    if (btn) undoImport(btn.getAttribute("data-remove-import"));
  });

    // 自适应
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(function () { updateDimensions(); }).observe(containerEl);
    }

    refreshGraphList().then(function () {
      if (!currentGraphId && graphListData.length > 0) {
        loadGraph(graphListData[0].id);
      } else {
        updateStats();
      }
    });
    initialized = true;
  }

  function onGraphListClick(e) {
    var main = e.target.closest("[data-gid]");
    if (main) {
      loadGraph(main.getAttribute("data-gid"));
      return;
    }
    var ren = e.target.closest("[data-act-rename]");
    if (ren) {
      var gid = ren.getAttribute("data-act-rename");
      var g = graphListData.find(function (x) { return x.id === gid; });
      var name = prompt("重命名图谱", g ? g.name : "");
      if (name && name.trim()) {
        renameGraph(gid, name.trim()).then(refreshGraphList);
      }
      return;
    }
    var del = e.target.closest("[data-act-delete]");
    if (del) {
      var did = del.getAttribute("data-act-delete");
      if (confirm("确定删除该图谱吗?")) {
        deleteGraph(did).then(function () {
          if (did === currentGraphId) setEmptyState();
          refreshGraphList();
        });
      }
    }
  }

  function setEmptyState() {
    currentGraph = null;
    currentGraphId = null;
    nodes = [];
    links = [];
    renderElements();
    renderLegend();
    renderImportHistory([]);
    updateStats();
  }

  function createNewGraph() {
    var name = prompt("新建图谱名称", "新图谱");
    if (!name) return;
    var id = "g_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
    saveGraph(id, { name: name, nodes: [], edges: [], importHistory: [] }).then(function () {
      refreshGraphList().then(function () { loadGraph(id); });
    }).catch(function (err) {
      alert("新建失败: " + err.message);
    });
  }

  function undoImport(importId) {
    if (!currentGraphId) return;
    if (!confirm("撤销该次导入吗?")) return;
    removeImport(currentGraphId, importId).then(function () {
      loadGraph(currentGraphId);
    }).catch(function (err) {
      alert("撤销失败: " + err.message);
    });
  }

  // ---------- 对外接口 ----------
  var KG = {
    init: init,
    refreshGraphList: refreshGraphList,
    loadGraph: loadGraph,
    importGraphResult: function (graphId) {
      loadGraph(graphId);
      refreshGraphList();
    }
  };

  window.KG = KG;
})();
