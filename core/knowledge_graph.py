"""Knowledge graph (Day 2, feature 65) — persisted, non-destructive.

Nodes are never hard-deleted: ``remove_node`` marks a tombstone (``retired``)
and moves the id into the retired list so nothing is lost. Adding the node
again revives it. Incident edges are removed on retirement so the graph stays
consistent; ``check_consistency`` still reports any dangling edge that
appears through external tampering.

Hierarchical relations (``is_a``, ``kind_of``, ``part_of`` …) reject edges
that would introduce a cycle; non-hierarchical edges may cycle freely.
"""

import heapq
import time

from core.kv import KeyValueStore

HIERARCHICAL_RELATIONS = {
    "is_a",
    "kind_of",
    "part_of",
    "subclass_of",
    "instance_of",
}

_NODES_KEY = "graph.nodes"
_EDGES_KEY = "graph.edges"
_RETIRED_KEY = "graph.retired"


def _edge_key(src, dst, relation):
    return f"{src}\x1f{dst}\x1f{relation}"


class KnowledgeGraph:

    def __init__(self, store):
        self.kv = store if isinstance(store, KeyValueStore) else KeyValueStore(store)

    # ------------------------------------------------------------------
    def _nodes(self):
        return dict(self.kv.get(_NODES_KEY, {}) or {})

    def _edges_store(self):
        return dict(self.kv.get(_EDGES_KEY, {}) or {})

    def _save_retired(self, retired):
        self.kv.set(_RETIRED_KEY, retired)
        return retired

    def retired(self):
        return list(self.kv.get(_RETIRED_KEY, []) or [])

    # ------------------------------------------------------------------
    def node(self, node_id):
        node_id = str(node_id)
        record = self._nodes().get(node_id)
        return dict(record) if record else None

    def nodes(self):
        return [dict(n) for n in self._nodes().values()]

    def edges(self):
        return [dict(e) for e in self._edges_store().values()]

    def add_node(self, node_id, node_type="entity", attrs=None):
        node_id = str(node_id)
        attrs = dict(attrs or {})

        def update(nodes):
            nodes = dict(nodes or {})
            previous = nodes.get(node_id)
            if previous:
                previous = dict(previous)
                if previous.get("retired"):
                    previous["retired"] = False
                    previous["retired_at"] = None
                    previous["revived_at"] = time.time()
                previous["type"] = str(node_type)
                merged = dict(previous.get("attrs", {}) or {})
                merged.update(attrs)
                previous["attrs"] = merged
                nodes[node_id] = previous
                return nodes
            nodes[node_id] = {
                "id": node_id,
                "type": str(node_type),
                "attrs": attrs,
                "retired": False,
                "created_at": time.time(),
            }
            return nodes

        self.kv.update(_NODES_KEY, update, default={})
        self.kv.update(
            _RETIRED_KEY,
            lambda old: [i for i in (list(old or []) if old else []) if i != node_id],
            default=[],
        )
        return node_id

    # ------------------------------------------------------------------
    def add_edge(self, src, dst, relation, weight=1.0):
        src, dst, relation = str(src), str(dst), str(relation)
        weight = float(weight)
        nodes = self._nodes()
        if src not in nodes or dst not in nodes:
            raise ValueError("edge endpoints must exist")
        if nodes[src]["retired"] or nodes[dst]["retired"]:
            raise ValueError("edge endpoints must not be retired")
        if relation in HIERARCHICAL_RELATIONS and self._would_cycle(src, dst, relation):
            return {"added": False, "reason": "cycle", "key": _edge_key(src, dst, relation)}

        key = _edge_key(src, dst, relation)

        def update(edges):
            edges = dict(edges or {})
            edges[key] = {
                "src": src,
                "dst": dst,
                "relation": relation,
                "weight": weight,
                "added_at": time.time(),
            }
            return edges

        self.kv.update(_EDGES_KEY, update, default={})
        return {"added": True, "key": key, "reason": None}

    def _would_cycle(self, src, dst, relation):
        if src == dst:
            return True
        edges = [e for e in self._edges_store().values()]
        adj = {}
        for edge in edges:
            if edge["relation"] in HIERARCHICAL_RELATIONS:
                adj.setdefault(edge["src"], []).append(edge["dst"])
        frontier = [dst]
        seen = set()
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            if current == src:
                return True
            frontier.extend(adj.get(current, []))
        return False

    # ------------------------------------------------------------------
    def neighbors(self, node_id, relation=None):
        node_id = str(node_id)
        result = []
        for edge in self.edges():
            if edge["src"] == node_id and (relation is None or edge["relation"] == relation):
                result.append({
                    "node": edge["dst"],
                    "relation": edge["relation"],
                    "weight": edge["weight"],
                })
        result.sort(key=lambda r: r["node"])
        return result

    def shortest_path(self, start, end):
        start, end = str(start), str(end)
        if start == end:
            return {"found": True, "path": [start], "weight": 0.0}

        adj = {}
        for edge in self.edges():
            adj.setdefault(edge["src"], []).append((edge["dst"], float(edge["weight"])))

        if start not in adj:
            return {"found": False, "path": [], "weight": None}

        dist = {start: 0.0}
        previous = {}
        frontier = [(0.0, start)]
        visited = set()
        while frontier:
            current_dist, current = heapq.heappop(frontier)
            if current in visited:
                continue
            visited.add(current)
            if current == end:
                break
            for neighbor, weight in adj.get(current, []):
                candidate = current_dist + weight
                if candidate < dist.get(neighbor, float("inf")):
                    dist[neighbor] = candidate
                    previous[neighbor] = current
                    heapq.heappush(frontier, (candidate, neighbor))

        if end not in dist:
            return {"found": False, "path": [], "weight": None}

        path = [end]
        current = end
        while current != start:
            current = previous[current]
            path.append(current)
        path.reverse()
        return {"found": True, "path": path, "weight": round(dist[end], 6)}

    def subgraph(self, node_type):
        nodes = [n for n in self._nodes().values()
                 if n["type"] == node_type and not n["retired"]]
        ids = {n["id"] for n in nodes}
        edges = [e for e in self.edges() if e["src"] in ids and e["dst"] in ids]
        return {"type": node_type, "nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------
    def remove_node(self, node_id):
        node_id = str(node_id)
        nodes = self._nodes()
        if node_id not in nodes:
            return False

        def update(nodes):
            nodes = dict(nodes or {})
            if node_id in nodes:
                record = dict(nodes[node_id])
                record["retired"] = True
                record["retired_at"] = time.time()
                nodes[node_id] = record
            return nodes

        self.kv.update(_NODES_KEY, update, default={})

        def drop(edges):
            return {
                key: edge
                for key, edge in (edges or {}).items()
                if edge["src"] != node_id and edge["dst"] != node_id
            }

        self.kv.update(_EDGES_KEY, drop, default={})
        self.kv.update(
            _RETIRED_KEY,
            lambda old: list(old or []) + ([node_id] if node_id not in (old or []) else []),
            default=[],
        )
        return True

    # ------------------------------------------------------------------
    def check_consistency(self):
        nodes = self._nodes()
        dangling = []
        for key, edge in self._edges_store().items():
            src_record = nodes.get(edge["src"])
            dst_record = nodes.get(edge["dst"])
            if src_record is None or dst_record is None:
                dangling.append({"key": key, "edge": edge, "reason": "endpoint_missing"})
            elif src_record["retired"] or dst_record["retired"]:
                dangling.append({"key": key, "edge": edge, "reason": "endpoint_retired"})
        return {"ok": len(dangling) == 0, "dangling_edges": dangling}

    def summarize(self):
        nodes = self._nodes()
        edges = self._edges_store()
        active = [n for n in nodes.values() if not n["retired"]]
        by_type = {}
        for node in active:
            by_type[node["type"]] = by_type.get(node["type"], 0) + 1
        by_relation = {}
        for edge in edges.values():
            by_relation[edge["relation"]] = by_relation.get(edge["relation"], 0) + 1
        return {
            "nodes": len(active),
            "retired_nodes": len(self.retired()),
            "edges": len(edges),
            "by_type": by_type,
            "by_relation": by_relation,
            "consistency": self.check_consistency(),
        }


__all__ = ["KnowledgeGraph"]