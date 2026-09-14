"""Escalation & Human Handoff (Day 2, feature 75).

Creates escalation records, computes which are stale against a real deadline,
builds human-readable handoff documents and resolves (archives) records.
External notification channels remain honest: without a backend the channel
reports NOT_CONFIGURED.
"""

import uuid
from datetime import datetime, timedelta

from core.kv import KeyValueStore
from core.output import output_manager

STATUSES = ("open", "escalated", "resolved")


class EscalationManager:

    def __init__(self, kv=None, now_fn=None):
        self.kv = kv or KeyValueStore("data/escalation.json")
        self._now = now_fn or (lambda: datetime.now())

    # ------------------------------------------------------------------
    def _today(self):
        return self._now().isoformat()

    def escalate(self, request, to, priority="medium", reason="",
                 deadline_minutes=60, context=None, attempted_actions=None,
                 assets=None, next_steps=None):
        death = self._now() + timedelta(minutes=deadline_minutes)
        record = {
            "id": str(uuid.uuid4())[:8],
            "status": "open",
            "to": to,
            "priority": priority,
            "ticket": f"ARV-ESC-{uuid.uuid4().hex[:6].upper()}",
            "request": request,
            "reason": reason,
            "deadline": death.isoformat(),
            "created_at": self._today(),
            "resolved_at": None,
            "context": context or request,
            "attempted_actions": attempted_actions or [],
            "assets": assets or [],
            "next_steps": next_steps or [],
            "channels": {},
        }
        records = self.kv.get("escalations", {})
        records[record["id"]] = record
        self.kv.set("escalations", records)
        return record

    # ------------------------------------------------------------------
    def get(self, escalation_id):
        return self.kv.get("escalations", {}).get(escalation_id)

    def all(self):
        return self.kv.get("escalations", {})

    def auto_remind(self):
        """Flag escalations whose deadline has passed but are still unresolved."""
        now = self._now()
        records = self.all()
        stale = []
        for esc in records.values():
            if esc["status"] in ("open", "escalated"):
                deadline = datetime.fromisoformat(esc["deadline"])
                if now > deadline:
                    esc["stale"] = True
                    esc["status"] = "escalated"
                    stale.append(esc)
                else:
                    esc["stale"] = False
        self.kv.set("escalations", records)
        return stale

    # ------------------------------------------------------------------
    def handoff_summary(self, escalation_id, directory=None):
        esc = self.get(escalation_id)
        if esc is None:
            raise KeyError(f"no escalation '{escalation_id}'")
        lines = [
            f"# Human Handoff — {esc['ticket']}",
            "",
            f"- **Status:** {esc['status']}",
            f"- **Assigned to:** {esc['to']}",
            f"- **Priority:** {esc['priority']}",
            f"- **Created:** {esc['created_at']}",
            f"- **Deadline:** {esc['deadline']}",
            "",
            "## Context",
            f"_Request:_ {esc['request']}",
            str(esc["context"]),
            "",
            "## Attempted Actions",
        ]
        actions = esc["attempted_actions"] or []
        if actions:
            lines.extend(f"- {a}" for a in actions)
        else:
            lines.append("_None recorded._")
        lines += ["", "## Assets"]
        assets = esc["assets"] or []
        if assets:
            lines.extend(f"- {a}" for a in assets)
        else:
            lines.append("_None recorded._")
        lines += ["", "## Next Steps"]
        steps = esc["next_steps"] or ["Acknowledge and assign an owner.",
                                     "Review context and attempted actions.",
                                     "Decide on resolution or further escalation."]
        lines.extend(f"{i}. {s}" for i, s in enumerate(steps, 1))

        content = "\n".join(lines) + "\n"
        target = directory or "Output/Escalations"
        result = output_manager.write(target, f"handoff_{esc['id']}.md", content)
        esc["handoff_path"] = result["path"]
        self.kv.set("escalations", self.all())
        return {"content": content, "path": result["path"], "escalation": esc}

    # ------------------------------------------------------------------
    def notify_channel(self, escalation_id, channel):
        """External notification is honest: no real backend -> NOT_CONFIGURED."""
        esc = self.get(escalation_id)
        if esc is None:
            raise KeyError(f"no escalation '{escalation_id}'")
        backend = _channel_backend(channel)
        esc["channels"][channel] = backend
        self.kv.set("escalations", self.all())
        return {"channel": channel, "status": backend.get("status")}

    # ------------------------------------------------------------------
    def resolve(self, escalation_id, resolution=None, by=None):
        esc = self.get(escalation_id)
        if esc is None:
            raise KeyError(f"no escalation '{escalation_id}'")
        esc["status"] = "resolved"
        esc["resolved_at"] = self._today()
        esc["resolution"] = resolution
        esc["resolved_by"] = by
        records = self.kv.get("escalations", {})
        records[escalation_id] = esc
        self.kv.set("escalations", records)
        return esc


def _channel_backend(channel):
    # No external notification backend is wired in this build -> honest.
    return {
        "status": "NOT_CONFIGURED",
        "channel": channel,
        "message": "no external notification backend configured",
    }


__all__ = ["EscalationManager", "STATUSES"]
