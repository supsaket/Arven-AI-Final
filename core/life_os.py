"""Life OS (Day 2, feature 91).

A non-diagnostic, non-clinical life-management layer: domains with default
rituals/checklists, mood/satisfaction tracking with real averaging, a weekly
review, and goal tracking with progress entries. The health domain carries an
explicit non-diagnostic disclaimer.
"""

from datetime import datetime

from core.kv import KeyValueStore

DOMAINS = ("health", "growth", "work", "money", "relationships", "fun")

HEALTH_DISCLAIMER = ("ARVEN Life OS health content is general wellbeing "
                     "tracking only and is NOT medical advice or a diagnostic "
                     "tool. Consult a qualified professional for health "
                     "decisions.")

DEFAULT_RITUALS = {
    "health": ["Hydrate on waking", "Light stretch or walk", "Log sleep hours"],
    "growth": ["Read for 20 minutes", "Review one new idea"],
    "work": ["Plan top 3 priorities", "Close out one task"],
    "money": ["Review spending for the day", "Log any income or expense"],
    "relationships": ["Reach out to someone important", "Express appreciation"],
    "fun": ["Schedule one enjoyable activity", "Take a genuine break"],
}

DEFAULT_CHECKLISTS = {
    "health": ["Slept 7+ hours", "Ate a balanced meal", "Moved today",
               "Hydrated adequately"],
    "growth": ["Learned something new", "Practiced a skill", "Reflected"],
    "work": ["Top priority touched", "Inbox cleared", "Meeting attended"],
    "money": ["Budget checked", "No impulsive spend", "Savings plan on track"],
    "relationships": ["Connected with family", "Helped someone"],
    "fun": ["Did something fun", "Unplugged for a while"],
}


class LifeOS:

    DEFAULT_RITUALS = DEFAULT_RITUALS
    DEFAULT_CHECKLISTS = DEFAULT_CHECKLISTS

    def __init__(self, kv=None):
        self.kv = kv or KeyValueStore("data/life_os.json")
        self.domains = list(DOMAINS)
        self.health_disclaimer = HEALTH_DISCLAIMER

    # ------------------------------------------------------------------
    @staticmethod
    def _check_domain(domain):
        if domain not in DOMAINS:
            raise ValueError(f"unknown domain '{domain}'; allowed: {DOMAINS}")

    def _domain_state(self, domain):
        state = self.kv.get(f"life::{domain}", {"rituals": [], "moods": [],
                                                "checklist": [], "goals": {}})
        return state

    def _put_domain(self, domain, state):
        self.kv.set(f"life::{domain}", state)

    # ------------------------------------------------------------------
    def default_rituals(self, domain):
        self._check_domain(domain)
        return list(DEFAULT_RITUALS.get(domain, []))

    def add_ritual(self, domain, ritual):
        self._check_domain(domain)
        state = self._domain_state(domain)
        if ritual not in state["rituals"]:
            state["rituals"].append(ritual)
            self._put_domain(domain, state)
        return True

    def rituals(self, domain):
        self._check_domain(domain)
        state = self._domain_state(domain)
        merged = list(DEFAULT_RITUALS.get(domain, []))
        for r in state["rituals"]:
            if r not in merged:
                merged.append(r)
        return merged

    # ------------------------------------------------------------------
    def checklist(self, domain):
        self._check_domain(domain)
        if domain == "health":
            self.set_health_ack()
        return list(DEFAULT_CHECKLISTS.get(domain, []))

    def set_health_ack(self):
        state = self.kv.get("life_ack", {})
        state["health_disclaimer_acknowledged"] = True
        state["at"] = datetime.now().isoformat()
        self.kv.set("life_ack", state)
        return True

    # ------------------------------------------------------------------
    def track_mood_satisfaction(self, domain, score):
        self._check_domain(domain)
        score = float(score)
        if not (0 <= score <= 10):
            raise ValueError("score must be between 0 and 10")
        state = self._domain_state(domain)
        state["moods"].append({"score": score, "at": datetime.now().isoformat()})
        self._put_domain(domain, state)
        scores = [m["score"] for m in state["moods"]]
        return {"score": score, "count": len(scores),
                "average": sum(scores) / len(scores)}

    def satisfaction(self, domain):
        self._check_domain(domain)
        state = self._domain_state(domain)
        scores = [m["score"] for m in state["moods"]]
        return {"count": len(scores),
                "average": (sum(scores) / len(scores)) if scores else None}

    # ------------------------------------------------------------------
    def goals(self, domain, goal):
        self._check_domain(domain)
        state = self._domain_state(domain)
        goal_id = goal if isinstance(goal, str) else goal["title"]
        goals = state["goals"]
        current = goals.get(goal_id,
                            {"title": goal_id, "progress": []})
        state["goals"][goal_id] = current
        self._put_domain(domain, state)
        return goal_id

    def add_goal_progress(self, domain, goal, note, percent=None):
        self._check_domain(domain)
        state = self._domain_state(domain)
        goals = state["goals"]
        current = goals.get(goal, {"title": goal, "progress": []})
        current["progress"].append({
            "note": note, "percent": percent,
            "at": datetime.now().isoformat(),
        })
        goals[goal] = current
        state["goals"] = goals
        self._put_domain(domain, state)
        return len(current["progress"])

    # ------------------------------------------------------------------
    def weekly_review(self, week_iso):
        lines = [f"# ARVEN Weekly Review — {week_iso}", ""]
        totals = []
        for domain in DOMAINS:
            state = self._domain_state(domain)
            scores = [m["score"] for m in state["moods"]]
            avg = (sum(scores) / len(scores)) if scores else None
            open_rituals = [r for r in self.rituals(domain) if r != ""]
            lines.append(f"## {domain.title()}")
            lines.append(f"- satisfaction: {round(avg, 2) if avg is not None else 'n/a'}")
            lines.append(f"- rituals tracked: {len(open_rituals)}")
            lines.append(f"- goals: {len(state['goals'])}")
            lines.append("")
            if avg is not None:
                totals.append(avg)

        if totals:
            overall = sum(totals) / len(totals)
            lines.append(f"## Overall mean satisfaction: {round(overall, 2)}")
            lines.append("")

        lines.append(f"> {self.health_disclaimer}")
        return "\n".join(lines)


__all__ = ["LifeOS", "DOMAINS", "HEALTH_DISCLAIMER", "DEFAULT_RITUALS",
           "DEFAULT_CHECKLISTS"]
