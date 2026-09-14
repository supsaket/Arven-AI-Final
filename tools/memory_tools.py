"""Memory tools — store, search and list long-term memories through the
real ``memory.database.MemoryDatabase`` (never a mock).
"""

import re

from memory.database import MemoryDatabase

DB = MemoryDatabase()


def _search_sql(needle):
    return f"%{needle}%"


def _rows_to_dicts(rows):
    memories = []
    for row in rows:
        memories.append({
            "id": row[0],
            "content": row[1],
            "category": row[2],
            "memory_type": row[3],
            "value": row[4],
            "importance": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        })
    return memories


def memory_store(content, category=None, importance=None, **kwargs):
    if not content or not str(content).strip():
        return {"success": False, "action": "memory_store", "message": "no content to store"}
    try:
        content = str(content)
        if category in (None, ""):
            category = "other"
        if importance in (None, ""):
            importance = 5
        memory_id = DB.add(content, category=str(category), importance=int(importance or 5))
        return {"success": True, "action": "memory_store", "memory_id": memory_id,
                "category": str(category), "message": f"Stored memory #{memory_id}."}
    except Exception as exc:
        return {"success": False, "action": "memory_store", "message": f"memory_store error: {exc}"}


def memory_search(query, **kwargs):
    if not query or not str(query).strip():
        return {"success": False, "action": "memory_search", "message": "empty query"}
    try:
        needle = str(query)
        rows = [row for row in DB.get_all()
                if needle.lower() in str(row[1]).lower()
                or (row[4] and needle.lower() in str(row[4]).lower())]
        return {"success": True, "action": "memory_search", "query": needle,
                "results": _rows_to_dicts(rows), "count": len(rows),
                "message": f"Found {len(rows)} matching memories."}
    except Exception as exc:
        return {"success": False, "action": "memory_search", "message": f"memory_search error: {exc}"}


def list_memories(**kwargs):
    try:
        rows = DB.get_all()
        return {"success": True, "action": "list_memories",
                "memories": _rows_to_dicts(rows), "count": len(rows),
                "message": f"{len(rows)} memories stored."}
    except Exception as exc:
        return {"success": False, "action": "list_memories", "message": f"list_memories error: {exc}"}


TOOLS = [
    {"name": "memory_store", "function": memory_store, "category": "Memory",
     "backend": "sqlite", "risk": "medium",
     "parameters": [{"name": "content", "required": True, "hint": "str"},
                    {"name": "category", "required": False, "hint": "str"},
                    {"name": "importance", "required": False, "hint": "int"}]},
    {"name": "memory_search", "function": memory_search, "category": "Memory",
     "backend": "sqlite", "risk": "safe",
     "parameters": [{"name": "query", "required": True, "hint": "str"}]},
    {"name": "list_memories", "function": list_memories, "category": "Memory",
     "backend": "sqlite", "risk": "safe"},
]