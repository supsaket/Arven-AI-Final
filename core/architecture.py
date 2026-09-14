"""Architecture & Scalability auditor (Day 2, feature 78).

Real module census over core/, memory/, tools/, brain/, core/providers/ using
``pathlib`` + ``ast``; dependency graph from top-level imports; contract audit
via attribute introspection (reports missing entry points honestly); and a
deterministic growth plan derived from cluster density.
"""

import ast
from pathlib import Path

from core.kv import KeyValueStore

ROOT = Path(__file__).resolve().parent.parent

# Folders we audit for the module census.
CENSUS_FOLDERS = ["core", "memory", "tools", "brain", "core/providers"]

# Expected entry points per key module.
CONTRACTS = {
    "core/kv.py": ["KeyValueStore"],
    "core/output.py": ["OutputManager", "output_manager"],
    "core/capabilities.py": ["Capabilities", "CapabilityStatus"],
    "core/selftest.py": ["SelfTestRunner"],
    "core/providers/registry.py": ["ProviderRegistry", "providers_registry"],
    "tools/registry.py": ["ToolRegistry"],
    "tools/builder.py": ["get_registry", "build_registry"],
    "memory/database.py": ["MemoryDatabase"],
}


class ArchitectureAuditor:

    def __init__(self, kv=None, root=None):
        self.kv = kv or KeyValueStore("data/architecture.json")
        self.root = Path(root) if root else ROOT

    # ------------------------------------------------------------------
    def module_census(self):
        result = {"folders": {}, "total_modules": 0}
        for folder in CENSUS_FOLDERS:
            directory = self.root / folder
            files = []
            if directory.exists():
                files = [p.name for p in sorted(directory.glob("*.py"))
                         if not p.name.startswith("_")]
            result["folders"][folder] = files
            result["total_modules"] += len(files)
        return result

    # ------------------------------------------------------------------
    def dependency_graph(self):
        graph = {"nodes": [], "edges": []}
        node_ids = set()
        for rel, path in self._iter_modules():
            imports = self._top_level_imports(path)
            node_ids.add(rel)
            graph["nodes"].append({"module": rel, "imports": imports})
            for dep in imports:
                if _is_internal(dep):
                    graph["edges"].append({"from": rel, "to": dep})
        graph["nodes"].sort(key=lambda n: n["module"])
        return graph

    def _iter_modules(self):
        for folder in CENSUS_FOLDERS:
            directory = self.root / folder
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*.py")):
                if path.name.startswith("_"):
                    continue
                rel = str(path.relative_to(self.root)).replace("\\", "/")
                yield rel, path

    @staticmethod
    def _top_level_imports(path):
        imports = []
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            return imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split(".")[0])
        return sorted(set(imports))

    def internal_nodes(self):
        graph = self.dependency_graph()
        return [n["module"] for n in graph["nodes"]]

    # ------------------------------------------------------------------
    def contract_audit(self):
        issues = []
        passed = 0
        for rel, expected in CONTRACTS.items():
            path = self.root / rel
            if not path.exists():
                issues.append({"module": rel, "missing": True,
                               "detail": "module file absent"})
                continue
            missing = [attr for attr in expected if not _has_symbol(path, attr)]
            if missing:
                issues.append({"module": rel, "missing": missing,
                               "detail": f"expected entry points not exported: {missing}"})
            else:
                passed += 1
        return {"contracts": len(CONTRACTS), "passed": passed,
                "issues": issues, "clean": not issues}

    # ------------------------------------------------------------------
    def growth_plan(self, cluster_threshold=4):
        """Suggest consolidations for dense clusters (deterministic)."""
        graph = self.dependency_graph()
        suggestion_nodes = []
        clique_density = {}

        # cluster density: module + its direct internal neighbours
        for node in graph["nodes"]:
            neighbours = {e["to"] for e in graph["edges"] if e["from"] == node["module"]}
            neighbours.add(node["module"])
            cluster = self._cluster_size(node["module"], graph)
            clique_density[node["module"]] = cluster

        dense = [name for name, size in clique_density.items()
                 if size >= cluster_threshold]
        suggestions = []
        for name in sorted(dense):
            suggestions.append({
                "module": name,
                "cluster_size": clique_density[name],
                "action": "consolidate",
                "reason": "cluster density exceeds threshold — consider merging "
                          "into a cohesive subpackage",
            })
        if not suggestions:
            suggestions.append({"action": "none",
                                "reason": "no cluster exceeds the density threshold"})
        return {"threshold": cluster_threshold, "density": clique_density,
                "suggestions": suggestions}

    def _cluster_size(self, module, graph):
        internal_nodes = {n["module"] for n in graph["nodes"]}
        # Bounded BFS over internal edges from the module.
        seen = set()
        stack = [module]
        max_hops = 3
        for _ in range(max_hops):
            nxt = set()
            for cur in stack:
                if cur not in internal_nodes:
                    continue
                seen.add(cur)
                for e in graph["edges"]:
                    if e["from"] == cur and e["to"] in internal_nodes \
                            and e["to"] not in seen:
                        nxt.add(e["to"])
                    if e["to"] == cur and e["from"] in internal_nodes \
                            and e["from"] not in seen:
                        nxt.add(e["from"])
            stack = list(nxt)
            if not stack:
                break
        return len(seen)


def _is_internal(name):
    return name in ("core", "memory", "tools", "brain", "config")


def _has_symbol(path, attr):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            if node.name == attr:
                return True
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == attr:
                    return True
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == attr:
                return True
    return False


__all__ = ["ArchitectureAuditor", "CENSUS_FOLDERS", "CONTRACTS"]
