"""Feature 122 tools — Extreme Long-Context Intelligence Engine surface."""

from functools import lru_cache

from tools.day2_tools import _safe, _parse_list, _parse_json

_ctx_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _ctx_tools.append(spec)


@lru_cache(maxsize=1)
def _ctx():
    import core.long_context as engine
    return engine


def _ctx_detect(**kw):
    return _ctx().detect()


def _ctx_budget(**kw):
    return _ctx().budget(str(kw.get("text") or ""),
                         max_context=kw.get("max_context"),
                         reserved=kw.get("reserved"))


def _ctx_process(**kw):
    return _ctx()._ENGINE.process(
        input_text=str(kw.get("input_text") or "") or None,
        documents=_parse_json(kw.get("documents")),
        max_context=kw.get("max_context"),
        compress_ratio=kw.get("compress_ratio"),
        top_k=kw.get("top_k"))


def _ctx_status(**kw):
    return _ctx()._ENGINE.status()


def _ctx_document(**kw):
    return _ctx()._ENGINE.long_document(
        paths=_parse_list(kw.get("paths")) or (kw.get("paths")
                                               if isinstance(kw.get("paths"),
                                                             str) else None),
        max_context=kw.get("max_context"),
        top_k=kw.get("top_k"),
        compress_ratio=kw.get("compress_ratio"))


def _ctx_checkpoint(**kw):
    state = _parse_json(kw.get("state")) if kw.get("state") else {}
    return _ctx()._ENGINE.checkpoint(state, name=str(kw.get("name")
                                                     or "checkpoint"))


def _ctx_restore(**kw):
    return _ctx()._ENGINE.restore(path=kw.get("path"), name=kw.get("name"))


# --- Feature 122 ----------------------------------------------------------
_add("ctx_detect", "low", "long-context",
     "Honest detection of MODEL, PROVIDER, MAX_CONTEXT window "
     "(never fabricated)",
     [], _ctx_detect)
_add("ctx_budget", "low", "long-context",
     "Token budgeting: usage/remaining + USE_NATIVE_CONTEXT vs "
     "RETRIEVE->COMPRESS->COMPACT strategy",
     [("text", True, "input text to budget"),
      ("max_context", False, "override window"),
      ("reserved", False, "reserved fraction (default 0.25)")],
     _ctx_budget)
_add("ctx_process", "low", "long-context",
     "Run the long-context pipeline on a single input (chunk/compress/"
     "retrieve/summarize)",
     [("input_text", True, "large text to process"),
      ("max_context", False, "override window"),
      ("compress_ratio", False, "0..1 compression ratio"),
      ("top_k", False, "retrieval hit count")],
     _ctx_process)
_add("ctx_document", "low", "long-context",
     "Process a long document/codebase: load files, budget, compact, "
     "retrieve important content",
     [("paths", False, "JSON list of file paths"),
      ("max_context", False, "override window"),
      ("top_k", False, "retrieval hit count"),
      ("compress_ratio", False, "compression ratio")],
     _ctx_document)
_add("ctx_checkpoint", "low", "long-context",
     "Persist a process state to Output as a restorable checkpoint",
     [("state", False, "JSON state to persist"),
      ("name", False, "checkpoint name")],
     _ctx_checkpoint)
_add("ctx_restore", "low", "long-context",
     "Restore a checkpoint by path or the most recent one",
     [("path", False, "checkpoint file path"),
      ("name", False, "optional name")],
     _ctx_restore)


TOOLS = _ctx_tools

__all__ = ["TOOLS"]