"""大图谱的有界页面投影，完整证据仍保留在数据库中。"""

from __future__ import annotations

from typing import Any


def graph_page(graph: dict[str, Any], *, limit: int, offset: int, q: str,
               batch_offset: int = 0) -> dict[str, Any]:
    """筛选完整节点后切片，汇总指标保持全量含义。"""
    query = q.strip().casefold()
    matches = [node for node in graph["nodes"] if not query or query in
               (node["label"] + " " + node["source_name"]).casefold()]
    nodes = matches[offset:offset + limit]
    ids = {node["id"] for node in nodes}
    batches = []
    for batch in graph["batches"][batch_offset:batch_offset + 20]:
        batches.append({**batch, "payload": {"nodes": [], "edges": []}, "payload_loaded": False,
                        "node_count": len(batch["payload"]["nodes"]),
                        "edge_count": len(batch["payload"]["edges"])})
    profile = {**graph["profile"], "weakness_total": len(graph["profile"]["weaknesses"]),
               "weaknesses": graph["profile"]["weaknesses"][:20]}
    return {**graph, "nodes": nodes, "edges": [edge for edge in graph["edges"]
            if edge["from"] in ids and edge["to"] in ids], "batches": batches, "profile": profile,
            "pagination": {"total": len(matches), "offset": offset, "limit": limit,
                           "has_more": offset + len(nodes) < len(matches),
                           "batch_total": len(graph["batches"]), "batch_offset": batch_offset},
            "edge_total": len(graph["edges"])}
