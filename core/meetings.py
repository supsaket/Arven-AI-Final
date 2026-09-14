"""Meeting Management (67) & Conversation State / Participants (68).

Provides structured meeting lifecycle, transcript capture with speaker
attribution, conversation state-machine (turns, topic context), and
exportable minutes.  All state is persisted via ``KeyValueStore``.
"""

import os
import time
import uuid
from datetime import datetime, timezone

from core.kv import KeyValueStore
from core.output import OutputManager


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _uid():
    return uuid.uuid4().hex[:12]


# ------------------------------------------------------------------
# Participant Registry (68)
# ------------------------------------------------------------------

class ParticipantRegistry:
    """Tracks known participants (name, role) inside a kv namespace."""

    def __init__(self, kv):
        self._kv = kv
        if self._kv.get("_participants") is None:
            self._kv.set("_participants", {})

    def register_participant(self, name, role="member"):
        participants = self._kv.get("_participants", {})
        participants[name] = {"role": role, "registered_at": _now_iso()}
        self._kv.set("_participants", participants)
        return participants[name]

    def list_participants(self):
        return dict(self._kv.get("_participants", {}))


# ------------------------------------------------------------------
# Conversation State Machine (68)
# ------------------------------------------------------------------

class ConversationState:
    """Per-meeting state: current topic, speaker turn tracking."""

    def __init__(self, kv):
        self._kv = kv

    @property
    def _state_key(self):
        return "_conv_state"

    def _state(self):
        return self._kv.get(self._state_key, {
            "active_participant": None,
            "current_topic": None,
            "turns": [],
        })

    def turn(self, active_participant):
        state = self._state()
        state["active_participant"] = active_participant
        state["turns"].append({
            "speaker": active_participant,
            "at": _now_iso(),
        })
        self._kv.set(self._state_key, state)
        return state

    def context_switch(self, topic):
        state = self._state()
        state["current_topic"] = topic
        self._kv.set(self._state_key, state)
        return state

    def current(self):
        return self._state()


# ------------------------------------------------------------------
# Meeting Manager (67 + 68)
# ------------------------------------------------------------------

class MeetingManager:
    """Full meeting lifecycle: create, capture, decide, export."""

    def __init__(self, kv_path="data/meetings.json", output_root=None):
        self._kv = KeyValueStore(kv_path)
        self._om = OutputManager(root=output_root) if output_root else OutputManager()
        self.participants = ParticipantRegistry(self._kv)

    # -- helpers to fetch / create meeting record -------------------

    def _get(self, mid):
        meeting = self._kv.get(mid)
        if meeting is None:
            raise KeyError(f"Meeting {mid} not found")
        return meeting

    def _save(self, mid, meeting):
        self._kv.set(mid, meeting)

    # -- creation ---------------------------------------------------

    def create_meeting(self, title, agenda=None):
        mid = _uid()
        meeting = {
            "id": mid,
            "title": title,
            "agenda": list(agenda or []),
            "topics": [],
            "decisions": [],
            "action_items": [],
            "transcript": [],
            "participants": [],
            "current_topic": None,
            "created_at": _now_iso(),
            "summary": None,
        }
        self._save(mid, meeting)
        return mid

    # -- mutations --------------------------------------------------

    def add_topic(self, mid, title):
        meeting = self._get(mid)
        topic = {"title": title, "added_at": _now_iso()}
        meeting["topics"].append(topic)
        meeting["current_topic"] = title
        self._save(mid, meeting)
        return topic

    def add_decision(self, mid, text):
        meeting = self._get(mid)
        decision = {"text": text, "recorded_at": _now_iso()}
        meeting["decisions"].append(decision)
        self._save(mid, meeting)
        return decision

    def add_action_item(self, mid, owner, due_iso, text):
        meeting = self._get(mid)
        item = {
            "owner": owner,
            "due": due_iso,
            "text": text,
            "status": "open",
            "added_at": _now_iso(),
        }
        meeting["action_items"].append(item)
        self._save(mid, meeting)
        return item

    def capture(self, mid, speaker, text):
        meeting = self._get(mid)
        line = {
            "speaker": speaker,
            "text": text,
            "at": _now_iso(),
        }
        meeting["transcript"].append(line)
        self._save(mid, meeting)
        return line

    # -- conversation state shortcuts -------------------------------

    def turn(self, mid, active_participant):
        meeting = self._get(mid)
        state = ConversationState(self._kv)
        s = state.turn(active_participant)
        meeting["current_topic"] = s.get("current_topic")
        self._save(mid, meeting)
        return s

    def context_switch(self, mid, topic):
        meeting = self._get(mid)
        state = ConversationState(self._kv)
        s = state.context_switch(topic)
        meeting["current_topic"] = topic
        self._save(mid, meeting)
        return s

    # -- summary / minutes ------------------------------------------

    def summary(self, mid):
        meeting = self._get(mid)
        state = ConversationState(self._kv).current()
        minutes = {
            "title": meeting["title"],
            "created_at": meeting["created_at"],
            "agenda": meeting["agenda"],
            "decisions": meeting["decisions"],
            "action_items": meeting["action_items"],
            "transcript": meeting["transcript"],
            "participants": list(self.participants.list_participants().keys()),
            "current_topic": state.get("current_topic"),
        }
        meeting["summary"] = minutes
        self._save(mid, meeting)
        return minutes

    # -- export to file ---------------------------------------------

    def export_minutes(self, mid, format="md"):
        minutes = self.summary(mid)
        lines = [
            f"# Minutes: {minutes['title']}",
            f"Created: {minutes['created_at']}",
            "",
            "## Agenda",
        ]
        for item in minutes["agenda"]:
            lines.append(f"- {item}")
        lines += ["", "## Participants"]
        for p in minutes["participants"]:
            lines.append(f"- {p}")
        lines += ["", "## Topics"]
        for t in minutes.get("transcript", []):
            if t.get("speaker"):
                lines.append(f"- [{t['speaker']}]: {t['text']}")
        lines += ["", "## Decisions"]
        for d in minutes["decisions"]:
            lines.append(f"- {d['text']}")
        lines += ["", "## Action Items"]
        for ai in minutes["action_items"]:
            lines.append(f"- [{ai['status']}] {ai['owner']}: {ai['text']} (due {ai['due']})")

        output_dir = os.path.join(str(self._om.root), "Output", "Meetings")
        os.makedirs(output_dir, exist_ok=True)
        path = self._om.next_rw_path(output_dir, minutes["title"], suffix=".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        self._om.metadata_sidecar(path, {"meeting_id": mid, "type": "meeting_minutes"})
        return str(path)


__all__ = ["MeetingManager", "ParticipantRegistry", "ConversationState"]
