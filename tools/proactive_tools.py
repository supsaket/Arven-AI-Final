"""Proactive assistant tool surface — status + suggestion generation.

The engine lives in ``core.proactive``; these tools wire it into the registry.
"""

from core.logging import logger


def proactive_status(**kwargs):
    try:
        from core.proactive import proactive_engine
        state = proactive_engine.status()
        return {"success": True, "action": "proactive_status", "enabled": state["enabled"],
                "state": state, "message": state["message"]}
    except ImportError:
        return {"success": False, "action": "proactive_status", "enabled": False,
                "message": "Proactive engine not available."}
    except Exception as exc:
        return {"success": False, "action": "proactive_status",
                "message": f"proactive_status error: {exc}"}


def proactive_suggest(**kwargs):
    """Return actionable, non-spammy suggestion(s) based on real signals."""
    try:
        from core.proactive import proactive_engine
        result = proactive_engine.suggest()
        return {"success": True, "action": "proactive_suggest",
                "suggestions": result, "count": len(result),
                "message": f"{len(result)} suggestion(s)."}
    except ImportError:
        return {"success": False, "action": "proactive_suggest", "suggestions": [],
                "message": "Proactive engine not available."}
    except Exception as exc:
        return {"success": False, "action": "proactive_suggest",
                "message": f"proactive_suggest error: {exc}"}


TOOLS = [
    {"name": "proactive_status", "function": proactive_status, "category": "System",
     "backend": "proactive", "risk": "safe"},
    {"name": "proactive_suggest", "function": proactive_suggest, "category": "System",
     "backend": "proactive", "risk": "safe"},
]