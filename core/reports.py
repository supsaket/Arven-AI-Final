"""Report Builder (Day 2, feature 72).

Assembles markdown reports from sections and tables with real rendering,
templating and durable export through the shared output manager.
"""

from datetime import datetime

from core.kv import KeyValueStore
from core.output import output_manager

_TEMPLATES = {
    "summary": {
        "title": "Executive Summary",
        "meta": "Prepared {date}",
        "sections": ["Overview", "Highlights", "Risks"],
        "closing": "Next actions are tracked alongside this summary.",
    },
    "status": {
        "title": "Status Report",
        "meta": "Generated {date}",
        "sections": ["Current Status", "Blockers", "Completed"],
        "closing": None,
    },
    "weekly": {
        "title": "Weekly Report",
        "meta": "Week ending {date}",
        "sections": ["Week Highlights", "Metrics", "Plans for Next Week"],
        "closing": None,
    },
}


class ReportBuilder:

    def __init__(self, kv=None, output_dir="Output/Reports", date_fn=None):
        self.kv = kv or KeyValueStore("data/reports.json")
        self.output_dir = output_dir
        self.date_fn = date_fn or (lambda: datetime.now())

    # ------------------------------------------------------------------
    def _today(self):
        return self.date_fn().strftime("%Y-%m-%d")

    def _content_key(self, name):
        return f"report::{name}"

    # ------------------------------------------------------------------
    def add_section(self, title, body, name="summary"):
        """Append a body under ``title`` for report ``name``."""
        content = self.kv.get(self._content_key(name), {"sections": [], "tables": []})
        content["sections"].append({"title": title, "body": body})
        self.kv.set(self._content_key(name), content)
        return True

    def add_table(self, title, headers, rows, name="summary"):
        content = self.kv.get(self._content_key(name), {"sections": [], "tables": []})
        content["tables"].append({
            "title": title,
            "headers": list(headers),
            "rows": [list(r) for r in rows],
        })
        self.kv.set(self._content_key(name), content)
        return True

    # ------------------------------------------------------------------
    def from_template(self, name):
        if name not in _TEMPLATES:
            raise ValueError(f"unknown template '{name}'")
        return dict(_TEMPLATES[name])

    # ------------------------------------------------------------------
    def render(self, name, format="md"):
        if format not in ("md", "markdown"):
            raise ValueError("only 'md'/'markdown' format is supported")
        template = self.from_template(name)
        content = self.kv.get(self._content_key(name), {"sections": [], "tables": []})

        lines = [f"# {template['title']}\n"]
        lines.append(f"> {template['meta'].format(date=self._today())}\n")

        # emit stored sections that match template section headings, then any extra
        ordered = template["sections"]
        for heading in ordered:
            bodies = [s["body"] for s in content["sections"]
                      if s["title"] == heading]
            if bodies:
                lines.append(f"## {heading}\n")
                for body in bodies:
                    lines.append(f"{body}\n")

        # leftover sections not covered by template headings
        remaining = [s for s in content["sections"]
                     if s["title"] not in ordered]
        for section in remaining:
            lines.append(f"## {section['title']}\n")
            lines.append(f"{section['body']}\n")

        for table in content["tables"]:
            lines.extend(self._render_table(table))

        if template.get("closing"):
            lines.append(f"- {template['closing']}")

        return "\n".join(lines).rstrip() + "\n"

    def _render_table(self, table):
        headers = table["headers"]
        rows = table["rows"]
        lines = [f"### {table['title']}"]
        lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows:
            padded = list(row) + [""] * (len(headers) - len(row))
            cells = padded[:len(headers)]
            lines.append("| " + " | ".join(str(c) for c in cells) + " |")
        return lines

    # ------------------------------------------------------------------
    def export(self, name, directory=None):
        target = directory or self.output_dir
        content = self.render(name)
        result = output_manager.write(target, f"{name}_report.md", content)
        return result["path"]


__all__ = ["ReportBuilder"]
