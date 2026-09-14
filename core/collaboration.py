"""Collaboration / Team board (Day 2, feature 73).

Board/columns/cards model with validation, transition recording, mention
extraction, per-column WIP summaries and a persisted activity log.
"""

import re
import uuid
from datetime import datetime

from core.kv import KeyValueStore

PRIORITIES = ("low", "medium", "high", "urgent")


class CollabBoard:

    def __init__(self, kv=None):
        self.kv = kv or KeyValueStore("data/collab.json")

    # ------------------------------------------------------------------
    def _today(self):
        return datetime.now().isoformat()

    def _log(self, entry):
        entry.setdefault("at", self._today())
        entries = self.kv.get("activity_log", [])
        entries.append(entry)
        self.kv.set("activity_log", entries)

    def activity(self, limit=50):
        return self.kv.get("activity_log", [])[-int(limit):]

    # ------------------------------------------------------------------
    def create_board(self, name, columns=None):
        columns = columns or ["To Do", "In Progress", "Done"]
        board_id = str(uuid.uuid4())[:8]
        board = {
            "id": board_id,
            "name": name,
            "columns": [{"id": _slug(c), "title": c,
                         "cards": [], "wip_limit": None} for c in columns],
        }
        boards = self.kv.get("boards", {})
        boards[board_id] = board
        self.kv.set("boards", boards)
        self._log({"action": "create_board", "board": board_id, "name": name})
        return board_id

    def create_column(self, board_id, title, wip_limit=None):
        board = self._get_board(board_id)
        col = {"id": _slug(title), "title": title,
               "cards": [], "wip_limit": wip_limit}
        board["columns"].append(col)
        self._put_board(board)
        self._log({"action": "create_column", "board": board_id, "title": title})
        return col["id"]

    def get_board(self, board_id):
        return self._get_board(board_id)

    def boards(self):
        return {k: v for k, v in self.kv.get("boards", {}).items()}

    def _get_board(self, board_id):
        boards = self.kv.get("boards", {})
        if board_id not in boards:
            raise KeyError(f"no board '{board_id}'")
        return boards[board_id]

    def _put_board(self, board):
        boards = self.kv.get("boards", {})
        boards[board["id"]] = board
        self.kv.set("boards", boards)

    # ------------------------------------------------------------------
    def add_card(self, board_id, title, priority="medium",
                 assignee=None, due=None, column=None):
        if priority not in PRIORITIES:
            raise ValueError(f"invalid priority '{priority}'; "
                             f"allowed: {PRIORITIES}")
        column = column or self._default_column(board_id)
        board = self._get_board(board_id)
        col = self._find_column(board, column)
        card = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "priority": priority,
            "assignee": assignee,
            "due": due,
            "column": col["id"],
            "transitions": [{"to": col["id"], "by": assignee,
                             "at": self._today()}],
            "created_at": self._today(),
        }
        col["cards"].append(card)
        self._put_board(board)
        self._log({"action": "add_card", "board": board_id,
                   "card": card["id"], "column": col["id"]})
        return card["id"]

    def _default_column(self, board_id):
        board = self._get_board(board_id)
        return board["columns"][0]["title"]

    def _find_column(self, board, column):
        for col in board["columns"]:
            if col["id"] == column or col["title"] == column:
                return col
        raise KeyError(f"no column '{column}' in board '{board['id']}'")

    # ------------------------------------------------------------------
    def move_card(self, card_id, column, by):
        board_key = self._card_board(card_id)
        if board_key is None:
            raise KeyError(f"no card '{card_id}'")
        board = self._get_board(board_key)
        col = self._find_column(board, column)
        card = self._pop_card(board, card_id)
        card["column"] = col["id"]
        card["transitions"].append({"to": col["id"], "by": by,
                                    "at": self._today()})
        col["cards"].append(card)
        self._put_board(board)
        self._log({"action": "move_card", "card": card_id,
                   "to": col["id"], "by": by})
        return card_id

    def _card_board(self, card_id):
        for board_id, board in self.boards().items():
            for col in board["columns"]:
                if any(c["id"] == card_id for c in col["cards"]):
                    return board_id
        return None

    def _pop_card(self, board, card_id):
        for col in board["columns"]:
            for i, card in enumerate(col["cards"]):
                if card["id"] == card_id:
                    return col["cards"].pop(i)
        raise KeyError(f"no card '{card_id}'")

    # ------------------------------------------------------------------
    @staticmethod
    def mentions(text):
        return re.findall(r"@([A-Za-z0-9_.]+)", text or "")

    # ------------------------------------------------------------------
    def board_summary(self, board_id):
        board = self._get_board(board_id)
        summary = {"board": board_id, "name": board["name"], "columns": []}
        for col in board["columns"]:
            active = [c for c in col["cards"] if c["column"] == col["id"]]
            summary["columns"].append({
                "column": col["id"],
                "title": col["title"],
                "count": len(col["cards"]),
                "wip_count": len(active),
            })
        return summary

    def wip(self, board_id):
        summary = self.board_summary(board_id)
        return sum(col["wip_count"] for col in summary["columns"])


def _slug(text):
    import re as _re
    return _re.sub(r"\W+", "_", str(text).strip().lower()) or "column"


__all__ = ["CollabBoard", "PRIORITIES"]
