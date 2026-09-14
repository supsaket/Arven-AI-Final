"""Advisor modules — Interactions Coordinator (86), Personal Tutor (87),
Career Coach (88), Relationship Coach (89), Communication Coach (90).

All advisors log sessions via ``KeyValueStore`` and include a ``disclaimer``
stating outputs are informational guidance only.
"""

import os
import time
import uuid
from datetime import datetime, timezone

from core.kv import KeyValueStore
from core.output import OutputManager

_DISCLAIMER = (
    "This output is informational guidance only and does not constitute "
    "professional advice."
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _uid():
    return uuid.uuid4().hex[:8]


# ------------------------------------------------------------------
# AdvisorBase
# ------------------------------------------------------------------

class AdvisorBase:
    """Base class: session lifecycle, kv-backed."""

    def __init__(self, kv, name="advisor"):
        self._kv = kv
        self._name = name

    def start_session(self, goal):
        sid = _uid()
        session = {
            "id": sid,
            "goal": goal,
            "exchanges": [],
            "started_at": _now_iso(),
        }
        self._kv.set(f"_session_{sid}", session)
        return sid

    def log_exchange(self, session_id, prompt, response):
        key = f"_session_{session_id}"
        session = self._kv.get(key)
        if session is None:
            return {"status": "FAILED", "reason": "Session not found"}
        session["exchanges"].append({
            "prompt": prompt,
            "response": response,
            "at": _now_iso(),
        })
        self._kv.set(key, session)
        return {"status": "AVAILABLE"}

    def session_summary(self, session_id):
        session = self._kv.get(f"_session_{session_id}")
        if session is None:
            return {"status": "FAILED", "reason": "Session not found"}
        return {
            "id": session["id"],
            "goal": session["goal"],
            "exchange_count": len(session["exchanges"]),
            "started_at": session["started_at"],
        }


# ------------------------------------------------------------------
# Interactions Coordinator (86)
# ------------------------------------------------------------------

class InteractionsCoordinator:
    """Role/topic planner: cadence suggestions + follow-up tracking."""

    def __init__(self, kv):
        self._kv = kv
        if self._kv.get("_followups") is None:
            self._kv.set("_followups", [])

    def plan_interaction(self, role, topic, cadence_days=7):
        plan = {
            "role": role,
            "topic": topic,
            "cadence_days": cadence_days,
            "created_at": _now_iso(),
        }
        return plan

    def add_followup(self, owner, description, due_iso):
        followups = self._kv.get("_followups", [])
        fu = {
            "id": _uid(),
            "owner": owner,
            "description": description,
            "due": due_iso,
            "status": "pending",
            "added_at": _now_iso(),
        }
        followups.append(fu)
        self._kv.set("_followups", followups)
        return fu

    def pending_followups(self):
        return [
            fu for fu in self._kv.get("_followups", [])
            if fu["status"] == "pending"
        ]

    def complete_followup(self, fid):
        followups = self._kv.get("_followups", [])
        for fu in followups:
            if fu["id"] == fid:
                fu["status"] = "completed"
                fu["completed_at"] = _now_iso()
        self._kv.set("_followups", followups)
        return {"status": "AVAILABLE"}


# ------------------------------------------------------------------
# Personal Tutor (87)
# ------------------------------------------------------------------

class PersonalTutor(AdvisorBase):

    def __init__(self, kv):
        super().__init__(kv, "tutor")
        if self._kv.get("_curricula") is None:
            self._kv.set("_curricula", {})

    def build_curriculum(self, topic, lessons, level="beginner"):
        cid = _uid()
        modules = []
        for i, lesson_title in enumerate(lessons, 1):
            modules.append({
                "module": i,
                "title": lesson_title,
                "quiz_draft": {
                    "question": f"What is the main concept of '{lesson_title}'?",
                    "options": [
                        f"Core idea of {lesson_title}",
                        "Unrelated concept",
                        "None of the above",
                    ],
                    "answer": 0,
                },
                "completed": False,
            })
        curriculum = {
            "id": cid,
            "topic": topic,
            "level": level,
            "modules": modules,
            "created_at": _now_iso(),
        }
        curricula = self._kv.get("_curricula", {})
        curricula[cid] = curriculum
        self._kv.set("_curricula", curricula)
        return curriculum

    def assess(self, answers):
        """answers: list of {module_id, selected_index}"""
        score = 0
        total = len(answers)
        for a in answers:
            if a.get("selected_index") == a.get("correct_index"):
                score += 1
        return {
            "score": score,
            "total": total,
            "percentage": round(score / total * 100, 1) if total else 0,
            "status": "AVAILABLE",
        }

    def next_lesson(self, curricula_id):
        curricula = self._kv.get("_curricula", {}).get(curricula_id)
        if curricula is None:
            return {"status": "FAILED", "reason": "Curriculum not found"}
        for m in curricula["modules"]:
            if not m["completed"]:
                return {"module": m, "status": "AVAILABLE"}
        return {"status": "UNAVAILABLE", "reason": "All modules completed"}


# ------------------------------------------------------------------
# Career Coach (88)
# ------------------------------------------------------------------

_ROLE_SKILLS = {
    "software_engineer": [
        "python", "javascript", "git", "sql", "testing",
        "system_design", "algorithms", "docker", "linux", "api_design",
    ],
    "data_scientist": [
        "python", "statistics", "machine_learning", "sql", "pandas",
        "numpy", "data_visualization", "feature_engineering", "deep_learning", "nlp",
    ],
    "product_manager": [
        "roadmap", "user_research", "stakeholder_management",
        "metrics", "prioritization", "agile", "communication",
        "market_analysis", "wireframing", "sql",
    ],
    "devops_engineer": [
        "linux", "docker", "kubernetes", "terraform", "ci_cd",
        "monitoring", "scripting", "cloud_aws", "networking", "security",
    ],
}


class CareerCoach(AdvisorBase):

    def __init__(self, kv):
        super().__init__(kv, "career")

    def skills_gap(self, target_role, current_skills):
        ref = _ROLE_SKILLS.get(target_role, [])
        current_lower = {s.lower() for s in current_skills}
        gaps = [s for s in ref if s.lower() not in current_lower]
        matched = [s for s in ref if s.lower() in current_lower]
        action_plan = []
        for i, gap in enumerate(gaps, 1):
            action_plan.append({
                "step": i,
                "skill": gap,
                "action": f"Acquire {gap} through practice/coursework",
            })
        return {
            "target_role": target_role,
            "matched": matched,
            "gaps": gaps,
            "gap_count": len(gaps),
            "action_plan": action_plan,
            "disclaimer": _DISCLAIMER,
        }

    def interview_prep(self, target_role):
        checklist = [
            f"Research common {target_role} interview questions",
            "Prepare STAR-method responses",
            "Review key technical concepts",
            "Prepare questions for interviewer",
            "Practice mock interview",
        ]
        return {
            "target_role": target_role,
            "checklist": checklist,
            "disclaimer": _DISCLAIMER,
        }


# ------------------------------------------------------------------
# Relationship Coach (89)
# ------------------------------------------------------------------

class RelationshipCoach(AdvisorBase):

    def __init__(self, kv):
        super().__init__(kv, "relationship")
        if self._kv.get("_checkins") is None:
            self._kv.set("_checkins", [])
        if self._kv.get("_appreciation_log") is None:
            self._kv.set("_appreciation_log", [])

    def interaction_patterns(self):
        frameworks = [
            "active listening before responding",
            "use 'I feel' statements instead of 'you always'",
            "schedule regular check-ins",
            "express appreciation daily",
            "conflict: pause, reflect, respond",
        ]
        return {
            "suggestions": frameworks,
            "disclaimer": _DISCLAIMER,
        }

    def schedule_checkin(self, contact, date_iso, topic):
        checkins = self._kv.get("_checkins", [])
        entry = {
            "id": _uid(),
            "contact": contact,
            "date": date_iso,
            "topic": topic,
            "status": "scheduled",
            "created_at": _now_iso(),
        }
        checkins.append(entry)
        self._kv.set("_checkins", checkins)
        return entry

    def list_checkins(self):
        return list(self._kv.get("_checkins", []))

    def log_appreciation(self, contact, message):
        log = self._kv.get("_appreciation_log", [])
        entry = {
            "contact": contact,
            "message": message,
            "at": _now_iso(),
        }
        log.append(entry)
        self._kv.set("_appreciation_log", log)
        return entry

    def conflict_resolution(self):
        frameworks = [
            {
                "name": "Nonviolent Communication",
                "steps": ["observe without evaluating", "express feelings",
                          "state needs", "make clear request"],
            },
            {
                "name": "Thomas-Kilmann Model",
                "steps": ["competing", "collaborating", "compromising",
                          "avoiding", "accommodating"],
            },
        ]
        return {"frameworks": frameworks, "disclaimer": _DISCLAIMER}


# ------------------------------------------------------------------
# Communication Coach (90)
# ------------------------------------------------------------------

_TONE_LEXICON = {
    "formal": {"therefore", "consequently", "furthermore", "regarding",
               "pursuant", "respectfully", "sincerely", "dear"},
    "aggressive": {"must", "demand", "insist", "immediately", "never",
                   "always", "absolutely"},
    "friendly": {"happy", "glad", "wonderful", "great", "love",
                 "thanks", "please", "awesome"},
    "passive": {"maybe", "perhaps", "might", "possibly", "sometimes",
                "sort of", "kind of"},
}


class CommunicationCoach(AdvisorBase):

    def __init__(self, kv):
        super().__init__(kv, "communication")

    def draft(self, tone, audience, points):
        structure = {
            "greeting": f"Dear {audience},",
            "body": [],
            "closing": "Best regards,",
            "tone": tone,
        }
        for point in points:
            structure["body"].append(f"- {point}")
        return {
            "draft": structure,
            "disclaimer": _DISCLAIMER,
        }

    def tone_check(self, text):
        text_lower = (text or "").lower()
        flags = {}
        for tone, words in _TONE_LEXICON.items():
            hits = [w for w in words if w in text_lower]
            flags[tone] = {
                "detected": len(hits) > 0,
                "hits": hits,
            }
        suggestions = []
        if flags.get("aggressive", {}).get("detected"):
            suggestions.append("Consider softening assertive language.")
        if flags.get("passive", {}).get("detected"):
            suggestions.append("Consider using more direct language.")
        if not any(f.get("detected") for f in flags.values()):
            suggestions.append("Tone appears neutral.")
        return {
            "flags": flags,
            "suggestions": suggestions,
            "disclaimer": _DISCLAIMER,
        }

    def speaking_tips(self):
        return {
            "tips": [
                "Maintain eye contact",
                "Vary vocal pace and pitch",
                "Pause for emphasis",
                "Use concrete examples",
                "Ask open-ended questions",
            ],
            "disclaimer": _DISCLAIMER,
        }


# ------------------------------------------------------------------
# Advisor Registry
# ------------------------------------------------------------------

class AdvisorRegistry:
    """Maps advisor names to factories."""

    def __init__(self, kv_path="data/advisors.json"):
        self._kv = KeyValueStore(kv_path)
        self._builders = {
            "coordinator": lambda kv: InteractionsCoordinator(kv),
            "tutor": lambda kv: PersonalTutor(kv),
            "career": lambda kv: CareerCoach(kv),
            "relationship": lambda kv: RelationshipCoach(kv),
            "communication": lambda kv: CommunicationCoach(kv),
        }

    def get(self, name):
        builder = self._builders.get(name)
        if builder is None:
            return None
        return builder(self._kv)

    def available(self):
        return list(self._builders.keys())


__all__ = [
    "AdvisorBase", "AdvisorRegistry",
    "InteractionsCoordinator", "PersonalTutor",
    "CareerCoach", "RelationshipCoach", "CommunicationCoach",
    "_DISCLAIMER",
]
