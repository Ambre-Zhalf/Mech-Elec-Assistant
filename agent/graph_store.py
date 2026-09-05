"""知识图谱存储:移植自 zstp 后端(Express + sql.js),改为 Python sqlite3。

独立使用 data/graph.db,与机电助手自身的 agent.db 互不干扰。
表结构与 zstp 对齐:graphs / nodes / edges / import_history。
"""

import json
import os
import sqlite3
import time
import uuid

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "graph.db")

GRAPH_FILE_NAME = "一键导入:学习计划知识图谱"


def _now():
    return int(time.time() * 1000)


def _conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init(conn)
    return conn


def _init(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS graphs(
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            nodeCount INTEGER DEFAULT 0,
            edgeCount INTEGER DEFAULT 0,
            createdAt INTEGER NOT NULL,
            updatedAt INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS nodes(
            id TEXT NOT NULL,
            graphId TEXT NOT NULL,
            label TEXT NOT NULL,
            type TEXT DEFAULT 'default',
            properties TEXT DEFAULT '{}',
            sourceFile TEXT DEFAULT '',
            createdAt INTEGER NOT NULL,
            PRIMARY KEY(id, graphId)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS edges(
            id TEXT NOT NULL,
            graphId TEXT NOT NULL,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            label TEXT DEFAULT '',
            weight INTEGER DEFAULT 1,
            properties TEXT DEFAULT '{}',
            sourceFile TEXT DEFAULT '',
            createdAt INTEGER NOT NULL,
            PRIMARY KEY(id, graphId)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS import_history(
            id TEXT NOT NULL,
            graphId TEXT NOT NULL,
            fileName TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            nodesAdded INTEGER DEFAULT 0,
            edgesAdded INTEGER DEFAULT 0,
            PRIMARY KEY(id, graphId)
        )
        """
    )
    conn.commit()


# ---------- 图谱列表 / 详情 ----------

def list_graphs():
    conn = _conn()
    rows = conn.execute("SELECT * FROM graphs ORDER BY updatedAt DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_graph(graph_id):
    conn = _conn()
    graph = conn.execute("SELECT * FROM graphs WHERE id=?", (graph_id,)).fetchone()
    if not graph:
        conn.close()
        return None
    nodes = [
        {**dict(r), "properties": json.loads(r["properties"] or "{}")}
        for r in conn.execute("SELECT * FROM nodes WHERE graphId=?", (graph_id,)).fetchall()
    ]
    edges = [
        {**dict(r), "properties": json.loads(r["properties"] or "{}")}
        for r in conn.execute("SELECT * FROM edges WHERE graphId=?", (graph_id,)).fetchall()
    ]
    history = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM import_history WHERE graphId=? ORDER BY timestamp DESC",
            (graph_id,),
        ).fetchall()
    ]
    conn.close()
    return {**dict(graph), "nodes": nodes, "edges": edges, "importHistory": history}


def save_graph(graph_id, name=None, nodes=(), edges=(), import_history=()):
    """整体保存:图谱不存在则创建,存在则全量替换节点/边/导入历史(对齐 zstp PUT /:id)。"""
    now = _now()
    conn = _conn()
    existing = conn.execute("SELECT * FROM graphs WHERE id=?", (graph_id,)).fetchone()
    if existing:
        conn.execute("DELETE FROM nodes WHERE graphId=?", (graph_id,))
        conn.execute("DELETE FROM edges WHERE graphId=?", (graph_id,))
        conn.execute("DELETE FROM import_history WHERE graphId=?", (graph_id,))
        conn.execute(
            "UPDATE graphs SET name=?, nodeCount=?, edgeCount=?, updatedAt=? WHERE id=?",
            (name or existing["name"], len(nodes), len(edges), now, graph_id),
        )
    else:
        conn.execute(
            "INSERT INTO graphs(id, name, nodeCount, edgeCount, createdAt, updatedAt) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (graph_id, name or "图谱", len(nodes), len(edges), now, now),
        )
    for n in nodes:
        conn.execute(
            "INSERT OR REPLACE INTO nodes(id, graphId, label, type, properties, sourceFile, createdAt) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (
                n["id"], graph_id, n["label"], n.get("type") or "default",
                json.dumps(n.get("properties") or {}, ensure_ascii=False),
                n.get("sourceFile") or "", n.get("createdAt") or now,
            ),
        )
    for e in edges:
        conn.execute(
            "INSERT OR REPLACE INTO edges(id, graphId, source, target, label, weight, properties, sourceFile, createdAt) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                e["id"], graph_id, e["source"], e["target"], e.get("label") or "",
                e.get("weight") or 1,
                json.dumps(e.get("properties") or {}, ensure_ascii=False),
                e.get("sourceFile") or "", e.get("createdAt") or now,
            ),
        )
    for h in import_history:
        conn.execute(
            "INSERT OR REPLACE INTO import_history(id, graphId, fileName, timestamp, nodesAdded, edgesAdded) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (
                h["id"], graph_id, h["fileName"],
                h.get("timestamp") or now, h.get("nodesAdded") or 0, h.get("edgesAdded") or 0,
            ),
        )
    conn.commit()
    conn.close()


def rename_graph(graph_id, name):
    conn = _conn()
    conn.execute("UPDATE graphs SET name=?, updatedAt=? WHERE id=?", (name, _now(), graph_id))
    conn.commit()
    conn.close()


def delete_graph(graph_id):
    conn = _conn()
    conn.execute("DELETE FROM nodes WHERE graphId=?", (graph_id,))
    conn.execute("DELETE FROM edges WHERE graphId=?", (graph_id,))
    conn.execute("DELETE FROM import_history WHERE graphId=?", (graph_id,))
    conn.execute("DELETE FROM graphs WHERE id=?", (graph_id,))
    conn.commit()
    conn.close()


# ---------- 按次撤销导入 ----------

def remove_import(graph_id, import_id):
    """删除某一次导入:清掉其边与孤立节点(对齐 zstp DELETE /:id/imports/:importId)。"""
    conn = _conn()
    record = conn.execute(
        "SELECT * FROM import_history WHERE id=? AND graphId=?", (import_id, graph_id)
    ).fetchone()
    if not record:
        conn.close()
        return False

    file_name = record["fileName"]
    conn.execute("DELETE FROM edges WHERE graphId=? AND sourceFile=?", (graph_id, file_name))

    connected = set()
    for r in conn.execute("SELECT source, target FROM edges WHERE graphId=?", (graph_id,)).fetchall():
        connected.add(r["source"])
        connected.add(r["target"])

    file_nodes = conn.execute(
        "SELECT id FROM nodes WHERE graphId=? AND sourceFile=?", (graph_id, file_name)
    ).fetchall()
    for n in file_nodes:
        if n["id"] not in connected:
            conn.execute("DELETE FROM nodes WHERE id=? AND graphId=?", (n["id"], graph_id))

    conn.execute("DELETE FROM import_history WHERE id=? AND graphId=?", (import_id, graph_id))

    nc = conn.execute("SELECT COUNT(*) c FROM nodes WHERE graphId=?", (graph_id,)).fetchone()["c"]
    ec = conn.execute("SELECT COUNT(*) c FROM edges WHERE graphId=?", (graph_id,)).fetchone()["c"]
    conn.execute(
        "UPDATE graphs SET nodeCount=?, edgeCount=?, updatedAt=? WHERE id=?",
        (nc, ec, _now(), graph_id),
    )
    conn.commit()
    conn.close()
    return True


# ---------- 一键导入(大模型 nodes/edges JSON → 新图谱) ----------

def _normalize_graph(graph):
    """把大模型输出的 nodes/edges(计算机发展.json 格式)转为存储格式,边引用节点 id。"""
    raw_nodes = graph.get("nodes") or []
    raw_edges = graph.get("edges") or []
    now = _now()

    node_id_of_label = {}
    nodes = []

    def ensure_node(label, node_type="default", properties=None):
        if label in node_id_of_label:
            return node_id_of_label[label]
        node_id = f"n_{now}_{len(nodes)}"
        node_id_of_label[label] = node_id
        nodes.append(
            {
                "id": node_id,
                "label": label,
                "type": node_type or "default",
                "properties": properties or {},
                "sourceFile": GRAPH_FILE_NAME,
                "createdAt": now,
            }
        )
        return node_id

    for n in raw_nodes:
        label = str((n or {}).get("label") or "").strip()
        if not label:
            continue
        ensure_node(
            label,
            (n.get("type") or "default") if isinstance(n, dict) else "default",
            n.get("properties") if isinstance(n, dict) else {},
        )

    edges = []
    for e in raw_edges:
        source_label = str((e or {}).get("source") or "").strip()
        target_label = str((e or {}).get("target") or "").strip()
        if not source_label or not target_label:
            continue
        # 边指向的实体若未出现在 nodes 中,自动补默认节点,保证图谱完整
        source_id = ensure_node(source_label)
        target_id = ensure_node(target_label)
        edges.append(
            {
                "id": f"e_{now}_{len(edges)}",
                "source": source_id,
                "target": target_id,
                "label": (e.get("label") or "") if isinstance(e, dict) else "",
                "weight": 1,
                "properties": {},
                "sourceFile": GRAPH_FILE_NAME,
                "createdAt": now,
            }
        )

    import_history = [
        {
            "id": f"imp_{now}",
            "fileName": GRAPH_FILE_NAME,
            "timestamp": now,
            "nodesAdded": len(nodes),
            "edgesAdded": len(edges),
        }
    ]
    return nodes, edges, import_history


def create_graph_from_json(graph, name=None):
    """一键导入:把 {nodes, edges} JSON 建成一张新图谱,返回 graph_id。"""
    if not graph or (not graph.get("nodes") and not graph.get("edges")):
        raise ValueError("图谱内容为空,无法导入")
    nodes, edges, import_history = _normalize_graph(graph)
    graph_id = f"g_{_now()}_{uuid.uuid4().hex[:6]}"
    save_graph(graph_id, name=name or "四年学习计划图谱",
               nodes=nodes, edges=edges, import_history=import_history)
    return graph_id
