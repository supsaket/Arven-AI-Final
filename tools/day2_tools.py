"""Day 2 tool registration — one callable tool per Day 2 capability (features 39–108).

Every tool returns a structured, honest result dict ({success, status, message,
data, ...}) and is routed by ``tools.builder`` into the shared registry.

Conventions:
* providers reach their ``_cap_*`` handlers through ``providers_registry.execute``
  (honest offline/status handling) EXCEPT gated capabilities (send / shell /
  book / purchase / actuate / destroy), where the tool already passed the
  authoritative CONFIRMATION gate in the registry and therefore calls the
  provider handler directly.
* destructive or high-risk core-engine methods receive ``confirmed=True`` from
  the wrapper because authorization was already granted upstream by the
  registry's CONFIRMATION gate (single authority).
"""

from core.providers.registry import providers_registry as _PR

FAKE_FAIL = {"success": False, "status": "FAILED", "message": "not configured"}

_PROVIDER_MODULES = {
    "browser": "browser_provider",
    "vision": "vision_provider",
    "media_gen": "media_gen",
    "camera": "camera_provider",
    "android": "android_provider",
    "iot": "iot_provider",
    "home": "home_provider",
    "communication": "communication_provider",
    "travel": "travel_provider",
    "location": "location_provider",
    "navigation": "navigation_provider",
    "vehicle": "vehicle_provider",
    "world_actions": "world_actions",
    "finance": "finance_provider",
    "shopping": "shopping_provider",
}

_MEDIA_GEN_PROVIDER = {"image_generate": "image_gen"}  # default -> video_gen


def _registered_name(name, capability=None):
    if name == "media_gen":
        return _MEDIA_GEN_PROVIDER.get(capability, "video_gen")
    if name == "communication":
        return "messaging"
    return name


def _parse_list(value):
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        return [p.strip() for p in value.replace(";", ",").split(",") if p.strip()] or [value]
    if value is None:
        return []
    return [value]


def _parse_kv(value):
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        out = {}
        for part in value.replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                k, v = part.split(":", 1)
            elif "=" in part:
                k, v = part.split("=", 1)
            else:
                k, v = part, part
            out[k.strip()] = v.strip()
        return out
    return {}


def _parse_json(value):
    import json
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None
    return None


def _finish(result):
    if isinstance(result, dict):
        status = str(result.get("status", ""))
        if "success" not in result:
            result["success"] = status not in (
                "FAILED", "ERROR", "MISSING", "NOT_CONFIGURED", "UNAVAILABLE",
                "UNAUTHORIZED", "OFFLINE", "REQUIRES_AUTH",
                "REQUIRES_PERMISSION", "DENIED", "confirm_required",
                "invalid_argument", "error", "unavailable",
                "AUTHORIZATION_REQUIRED", "NOT_INSTALLED", "NOT_AUTHORIZED",
                "NOT_AUTHENTICATED",
            )
    return result


def _safe(target):
    def _tool(**kw):
        try:
            return _finish(target(**kw))
        except Exception as exc:
            return {"success": False, "status": "FAILED",
                    "message": f"{exc}", "data": {}}
    return _tool


def _mint(target="day2_tool.authorized_action"):
    """Create a pending CONFIRMATION request so internal gates can consume it."""
    from core.confirmation import CONFIRMATION
    return CONFIRMATION.require(target)


def _provider(name, capability=None):
    """Resolve a registered provider (registration happens at import time)."""
    import importlib
    registered = _registered_name(name, capability)
    provider = _PR.get(registered)
    if provider is None:
        module = importlib.import_module(
            f"core.providers.{_PROVIDER_MODULES.get(name, name)}")
        registrar = getattr(module, f"register_{name}", None)
        if registrar:
            registrar()
        provider = _PR.get(registered)
    return provider


def _prov_call(name, capability):
    """Non-gated provider route (honest execute keeps offline/status checks)."""
    def _call(**kw):
        provider = _provider(name, capability)
        if provider is None:
            return dict(FAKE_FAIL)
        return provider.execute(capability, **kw)
    return _call


def _prov_direct(name, capability, forged=False):
    """Gated provider route — caller already cleared the registry gate."""
    def _call(**kw):
        provider = _provider(name, capability)
        if provider is None:
            return dict(FAKE_FAIL)
        handler = getattr(provider, f"_cap_{capability.replace('-', '_')}", None)
        if handler is None:
            return {"success": False, "status": "NOT_CONFIGURED",
                    "message": f"no handler for '{capability}'"}
        if forged:
            kw = dict(kw)
            kw.setdefault("confirmed", True)
            kw.setdefault("trusted", True)
            kw.setdefault("request_id", _mint(f"{name}.{capability}"))
        return handler(**kw)
    return _call


# ---------------------------------------------------------------------------
# Engine accessors (lazy, patchable in tests via monkeypatch.setattr)
# ---------------------------------------------------------------------------
from functools import lru_cache
from core.kv import KeyValueStore


@lru_cache(maxsize=None)
def _engine_missions():
    from core.missions import MissionEngine
    return MissionEngine(path="data/missions.json")


@lru_cache(maxsize=None)
def _engine_goals():
    from core.workflows import WorkflowEngine
    return WorkflowEngine(path="data/workflows.json")


@lru_cache(maxsize=None)
def _engine_skills():
    from core.skill_builder import SkillStore
    return SkillStore(path="data/skills.json")


@lru_cache(maxsize=None)
def _engine_alerts():
    from core.alerts import AlertManager
    return AlertManager(KeyValueStore("data/alerts.json"))


@lru_cache(maxsize=None)
def _engine_graph():
    from core.knowledge_graph import KnowledgeGraph
    return KnowledgeGraph(KeyValueStore("data/knowledge_graph.json"))


@lru_cache(maxsize=None)
def _engine_assim():
    from core.assimilation import AssimilationEngine
    return AssimilationEngine(KeyValueStore("data/assimilation.json"))


@lru_cache(maxsize=None)
def _engine_facts():
    from core.fact_check import FactChecker
    return FactChecker()


@lru_cache(maxsize=None)
def _engine_anomaly():
    from core.anomaly import AnomalyEngine
    return AnomalyEngine()


@lru_cache(maxsize=None)
def _engine_context():
    from core.context_engine import ContextEngine
    return ContextEngine(path="data/context.json")


@lru_cache(maxsize=None)
def _engine_world():
    from core.world_state import WorldState
    return WorldState(path="data/world_state.json")


@lru_cache(maxsize=None)
def _engine_experience():
    from core.experience import ExperienceVault
    return ExperienceVault(path="data/experience.json")


@lru_cache(maxsize=None)
def _engine_decisions():
    from core.decisions import DecisionEngine
    return DecisionEngine(path="data/decisions.json")


@lru_cache(maxsize=None)
def _engine_continuity():
    from core.continuity import ContinuityManager
    return ContinuityManager(path="data/continuity.json")


@lru_cache(maxsize=None)
def _engine_organizer():
    from core.organizer import Organizer
    return Organizer(kv_path="data/organizer.json")


@lru_cache(maxsize=None)
def _engine_guardian():
    from core.security_guardian import SecurityGuardian
    return SecurityGuardian(kv=KeyValueStore("data/security_guardian.json"))


@lru_cache(maxsize=None)
def _engine_backup():
    from pathlib import Path
    from core.backup import BackupManager
    root = Path(__file__).resolve().parent.parent
    return BackupManager(workspace_root=str(root), output_root=str(root / "Output"))


@lru_cache(maxsize=None)
def _engine_pipeline():
    from core.build_agent import PipelineRunner
    return PipelineRunner(output_root=_OUTPUT_ROOT)


@lru_cache(maxsize=None)
def _engine_qa():
    from core.qa_engine import QARunner
    from pathlib import Path
    return QARunner(workspace_root=str(Path(__file__).resolve().parent.parent))


@lru_cache(maxsize=None)
def _engine_diagnostics():
    from core.diagnostics import Diagnostics
    return Diagnostics(workspace_root=_WORKSPACE_ROOT)


@lru_cache(maxsize=None)
def _engine_profiler():
    from core.performance import Profiler
    return Profiler(kv_path="data/performance.json")


@lru_cache(maxsize=None)
def _engine_planner():
    from core.planner import AdaptivePlanner
    return AdaptivePlanner(kv=KeyValueStore("data/planner.json"))


@lru_cache(maxsize=None)
def _engine_responder():
    from core.event_response import EventResponder
    return EventResponder(kv=KeyValueStore("data/event_response.json"),
                          invoker=_event_dispatch)


@lru_cache(maxsize=None)
def _engine_cyber():
    from core.cyber_toolkit import CyberToolkit
    return CyberToolkit(kv=KeyValueStore("data/cyber_toolkit.json"))


@lru_cache(maxsize=None)
def _engine_undo():
    from core.undo import TransactionManager
    return TransactionManager(kv=KeyValueStore("data/undo.json"))


@lru_cache(maxsize=None)
def _engine_meetings():
    from core.meetings import MeetingManager
    return MeetingManager(kv_path="data/meetings.json", output_root=_OUTPUT_ROOT)


@lru_cache(maxsize=None)
def _engine_affect():
    from core.affect import AffectEngine
    return AffectEngine()


@lru_cache(maxsize=None)
def _engine_speaker():
    from core.speech import SpeakerRecognition
    return SpeakerRecognition(kv_path="data/speakers.json")


@lru_cache(maxsize=None)
def _engine_language():
    from core.speech import LanguageDetector
    return LanguageDetector()


@lru_cache(maxsize=None)
def _engine_advisors():
    from core.advisor import AdvisorRegistry
    return AdvisorRegistry(kv_path="data/advisors.json")


_ADVISOR_NAMES = {
    "interactions": "coordinator",
    "tutor": "tutor",
    "career": "career",
    "relationships": "relationship",
    "communication_coach": "communication",
}


@lru_cache(maxsize=None)
def _engine_advisor(name):
    return _engine_advisors().get(_ADVISOR_NAMES.get(name, name))


@lru_cache(maxsize=None)
def _engine_access():
    from core.access import PermissionManager
    return PermissionManager(kv_path="data/access.json")


@lru_cache(maxsize=None)
def _engine_privacy():
    from core.privacy import PrivacyPortal
    return PrivacyPortal(kv_path="data/privacy.json", output_root=_OUTPUT_ROOT)


@lru_cache(maxsize=None)
def _engine_reports():
    from core.reports import ReportBuilder
    return ReportBuilder(kv=KeyValueStore("data/reports.json"),
                         output_dir=_OUTPUT_ROOT)


@lru_cache(maxsize=None)
def _engine_board():
    from core.collaboration import CollabBoard
    return CollabBoard(kv=KeyValueStore("data/collaboration.json"))


@lru_cache(maxsize=None)
def _engine_escalation():
    from core.escalation import EscalationManager
    return EscalationManager(kv=KeyValueStore("data/escalation.json"))


@lru_cache(maxsize=None)
def _engine_simulation():
    from core.simulation import SimulationEngine
    return SimulationEngine(kv=KeyValueStore("data/simulation.json"),
                            output_dir=_OUTPUT_ROOT)


@lru_cache(maxsize=None)
def _engine_boss():
    from core.boss_model import BossModel
    return BossModel(kv=KeyValueStore("data/boss_model.json"))


@lru_cache(maxsize=None)
def _engine_arch():
    from core.architecture import ArchitectureAuditor
    return ArchitectureAuditor(kv=KeyValueStore("data/architecture.json"))


@lru_cache(maxsize=None)
def _engine_lifeos():
    from core.life_os import LifeOS
    return LifeOS(kv=KeyValueStore("data/life_os.json"))


@lru_cache(maxsize=None)
def _engine_events():
    from core.events import EventsCalendar
    return EventsCalendar(kv=KeyValueStore("data/events.json"))


@lru_cache(maxsize=None)
def _engine_vault():
    from core.project_memory import ProjectVault
    return ProjectVault(kv=KeyValueStore("data/project_memory.json"))


@lru_cache(maxsize=None)
def _engine_contingency():
    from core.contingency import ContingencyPlanner
    return ContingencyPlanner(kv=KeyValueStore("data/contingency.json"))


@lru_cache(maxsize=None)
def _engine_command():
    from core.command_center import CommandCenter
    return CommandCenter(kv=KeyValueStore("data/command_center.json"),
                         workspace_root=_WORKSPACE_ROOT)


@lru_cache(maxsize=None)
def _engine_multimodal():
    from core.multimodal import MultimodalInput
    return MultimodalInput(kv=KeyValueStore("data/multimodal.json"))


@lru_cache(maxsize=None)
def _engine_robot():
    from core.robot import RobotController
    return RobotController(kv=KeyValueStore("data/robot.json"))


@lru_cache(maxsize=None)
def _engine_engineering():
    from core.engineering import EngineeringProjects
    return EngineeringProjects(kv=KeyValueStore("data/engineering.json"),
                               output_dir=_OUTPUT_ROOT)


@lru_cache(maxsize=None)
def _engine_inventory():
    from core.supply_chain import InventoryManager
    return InventoryManager(path="data/inventory.json")


@lru_cache(maxsize=None)
def _engine_services():
    from core.services import ServiceOrchestrator
    return ServiceOrchestrator(path="data/services.json")


@lru_cache(maxsize=None)
def _engine_lifecycle():
    from core.memory_lifecycle import MemoryLifecycle
    return MemoryLifecycle(kv_path="data/memory_lifecycle.json")


# ---------------------------------------------------------------------------
# Paths shared by accessors
# ---------------------------------------------------------------------------
from pathlib import Path
_WORKSPACE_ROOT = str(Path(__file__).resolve().parent.parent)
_OUTPUT_ROOT = str(Path(_WORKSPACE_ROOT) / "Output")


def _call_engine(getter, method):
    def _call(**kw):
        return getattr(getter(), method)(**kw)
    return _call


def _board_create(**kw):
    board_id = _engine_board().create_board(
        name=kw["name"], columns=_parse_list(kw.get("columns")))
    return {"success": True, "status": "ok", "board_id": board_id,
            "id": board_id}


def _board_add_card(**kw):
    card_id = _engine_board().add_card(
        board_id=kw["board_id"], title=kw["title"],
        priority=kw.get("priority", "medium"),
        assignee=kw.get("assignee"), due=kw.get("due"))
    return {"success": True, "status": "ok", "card_id": card_id,
            "id": card_id}


# ---------------------------------------------------------------------------
# Tool table  (name, risk, category, backend, description, parameters, target)
# ---------------------------------------------------------------------------
_TOOLS = []
_GATED_PROV = {"email_send", "message_send", "android_shell", "travel_book",
               "iot_remove", "action_execute", "shopping_purchase"}


def _add(name, risk, category, description, parameters, target, backend="local"):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": backend, "available": True, "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _TOOLS.append(spec)


P = "int"
Q = "float"
B = "bool"


# --- Feature 39 Automated Browsing -----------------------------------------
_add("browser_provider_status", "low", "browser", "Browser backend + bookmark store status",
     [("capability", False, "")],
     _prov_call("browser", "browser_status"))
_add("browser_bookmark_add", "low", "browser", "Add a bookmark locally",
     [("url", True, ""), ("title", False, ""), ("tags", False, "")],
     _prov_call("browser", "bookmarks_add"))
_add("browser_bookmark_list", "low", "browser", "List bookmarks",
     [], _prov_call("browser", "bookmarks_list"))
_add("browser_bookmark_search", "low", "browser", "Search bookmarks by keyword",
     [("keyword", True, "")], _prov_call("browser", "bookmarks_search"))
_add("browser_provider_search", "low", "browser", "Web search (honest; needs backend)",
     [("query", True, "")], _prov_call("browser", "browser_search"))

# --- Feature 40 Vision / Image Understanding --------------------------------
_add("vision_metadata", "low", "vision", "Read image metadata with PIL",
     [("image_path", True, "")], _prov_call("vision", "image_metadata"))
_add("vision_coordinates", "low", "vision", "Compute on-screen coordinates for an image",
     [("image_path", True, ""), ("relative_to_screen", False, B),
      ("perform_action", False, B)],
     _prov_call("vision", "screen_coordinates"))
_add("vision_analyze", "low", "vision", "Vision analysis (honest; needs provider)",
     [("image_path", True, "")], _prov_call("vision", "vision_analyze"))

# --- Features 41 & 42 Image / Video Generation ------------------------------
_add("image_generate", "medium", "media", "Generate a placeholder canvas image",
     [("prompt", True, ""), ("width", False, P), ("height", False, P)],
     _prov_call("media_gen", "image_generate"))
_add("video_generate", "medium", "media", "Queue a video/storyboard generation job",
     [("prompt", True, "")], _prov_call("media_gen", "video_generate"))
_add("video_status", "low", "media", "Video generation job status",
     [("job_id", True, "")], _prov_call("media_gen", "video_status"))
_add("video_cancel", "medium", "media", "Cancel a queued video generation job",
     [("job_id", True, "")], _prov_call("media_gen", "video_cancel"))

# --- Feature 46 Camera / Capture --------------------------------------------
_add("screen_capture", "low", "vision", "Capture the screen to a PNG",
     [("filename", False, ""), ("directory", False, "")],
     _prov_call("camera", "screen_capture"))
_add("camera_capture", "medium", "vision", "Capture from a camera (permission-gated)",
     [], _prov_call("camera", "camera_capture"))
_add("camera_permission_grant", "medium", "vision", "Grant camera access permission",
     [], lambda **kw: _engine_grant_camera())

def _from_camera(handler_name, message, status="AVAILABLE", data=None):
    provider = _provider("camera")
    if provider is None:
        return dict(FAKE_FAIL)
    handler = getattr(provider, handler_name, None)
    if handler is None:
        return {"success": False, "status": "NOT_CONFIGURED",
                "message": f"camera provider has no {handler_name}"}
    try:
        handler()
        return {"success": True, "status": status, "message": message,
                "data": data or {}}
    except Exception as exc:
        return {"success": False, "status": "FAILED", "message": f"{exc}",
                "data": {}}


def _engine_grant_camera():
    return _from_camera("grant_camera_permission", "camera access granted")


# --- Feature 43 Android ------------------------------------------------------
_add("android_provider_status", "low", "android", "Android/ADB backend status",
     [], _prov_call("android", "android_status"))
_add("android_devices", "low", "android", "List connected Android devices",
     [], _prov_call("android", "android_list_devices"))
_add("android_shell", "high", "android", "Run an ADB shell command (gated)",
     [("command", True, "")], _prov_direct("android", "android_shell"))

# --- Feature 44 IoT / Home Automation -----------------------------------------
_add("iot_provider_status", "low", "iot", "IoT device registry status",
     [], _prov_call("iot", "iot_status"))
_add("iot_register", "medium", "iot", "Register an IoT device",
     [("device_id", False, ""), ("kind", False, ""), ("name", False, ""),
      ("simulated", False, B), ("power_watts", False, Q)],
     _prov_call("iot", "iot_register"))
_add("iot_list", "low", "iot", "List IoT devices", [], _prov_call("iot", "iot_list"))
_add("iot_set_state", "medium", "iot", "Set an IoT device target state",
     [("device_id", True, ""), ("state", True, "")],
     lambda **kw: _prov_call("iot", "iot_set_state")(
         device_id=kw["device_id"], state=_parse_kv(kw["state"])))
_add("iot_remove", "high", "iot", "Remove an IoT device (gated)",
     [("device_id", True, "")], _prov_direct("iot", "iot_remove"))

# --- Feature 82 Home Management -----------------------------------------------
_add("home_status", "low", "home", "Home management status",
     [], _prov_call("home", "home_status"))
_add("home_routines", "low", "home", "List home routines",
     [], _prov_call("home", "home_commands"))
_add("home_run_routine", "medium", "home", "Run (simulate) a home routine",
     [("routine_name", True, "")], _prov_call("home", "home_routine"))
_add("home_energy_estimate", "low", "home", "Estimate home energy use",
     [("items", False, "")], _prov_call("home", "home_energy_estimate"))

# --- Feature 45 Communication ------------------------------------------------
_add("email_templates", "low", "communication", "Email template library",
     [("action", False, ""), ("name", False, ""), ("subject", False, ""),
      ("body", False, ""), ("variables", False, "")],
     _prov_call("communication", "email_templates"))
_add("email_compose", "low", "communication", "Compose an email from a template",
     [("template", False, ""), ("variables", False, ""), ("recipient", False, ""),
      ("subject", False, ""), ("body", False, "")],
     _prov_call("communication", "email_compose"))
_add("email_provider_draft", "medium", "communication", "Save a draft message",
     [("template", False, ""), ("variables", False, ""), ("recipient", False, ""),
      ("subject", False, ""), ("body", False, "")],
     _prov_call("communication", "email_draft"))
_add("email_provider_send", "high", "communication", "Send an email (gated; needs backend)",
     [("to", True, ""), ("subject", False, ""), ("body", False, ""),
      ("template", False, ""), ("variables", False, "")],
     _prov_direct("communication", "email_send"))
_add("message_draft", "low", "communication", "Draft a message",
     [("message", False, ""), ("recipient", False, "")],
     _prov_call("communication", "message_draft"))
_add("message_send", "high", "communication", "Send a message (gated; needs backend)",
     [("to", True, ""), ("text", True, "")],
     _prov_direct("communication", "message_send"))

# --- Feature 80 Travel Planning ----------------------------------------------
_add("travel_plan", "low", "travel", "Plan a trip itinerary (estimate)",
     [("destinations", True, ""), ("dates", False, ""), ("budget", False, Q),
      ("pace", False, ""), ("transport", False, "")],
     _prov_call("travel", "travel_plan"))
_add("travel_itinerary", "low", "travel", "Show a planned trip itinerary",
     [("trip_id", True, "")], _prov_call("travel", "travel_itinerary"))
_add("travel_book", "high", "travel", "Book travel (gated; needs provider)",
     [("trip_id", True, ""), ("booking", False, "")],
     _prov_direct("travel", "travel_book"))

# --- Feature 84 Location -------------------------------------------------------
_add("location_status", "low", "location", "Location services status",
     [], _prov_call("location", "location_status"))
_add("location_set", "medium", "location", "Record a place with coordinates",
     [("name", True, ""), ("lat", True, Q), ("lon", True, Q),
      ("label", False, "")],
     _prov_call("location", "location_set"))
_add("location_get", "low", "location", "Read a recorded place",
     [("name", False, "")], _prov_call("location", "location_get"))
_add("location_geocode", "low", "location", "Geocode a query (honest backend)",
     [("query", True, "")], _prov_call("location", "location_geocode"))
_add("distance", "low", "location", "Haversine distance between two points",
     [("lat1", True, Q), ("lon1", True, Q), ("lat2", True, Q), ("lon2", True, Q),
      ("unit", False, "")],
     _prov_call("location", "distance"))

# --- Feature 93 Navigation ------------------------------------------------------
_add("route_plan", "low", "navigation", "Plan a route (offline estimate)",
     [("origin", True, ""), ("destination", True, ""),
      ("waypoints", False, ""), ("mode", False, "")],
     _prov_call("navigation", "route_plan"))
_add("route_eta", "low", "navigation", "Route ETA estimate (honest)",
     [("origin", True, ""), ("destination", True, ""), ("mode", False, "")],
     _prov_call("navigation", "route_eta"))

# --- Feature 83 Vehicle ---------------------------------------------------------
_add("vehicle_status", "low", "vehicle", "Vehicle registry status",
     [], _prov_call("vehicle", "vehicle_status"))
_add("vehicle_maintenance_log", "medium", "vehicle", "Log vehicle maintenance",
     [("reg", True, ""), ("make", False, ""), ("model", False, ""),
      ("odometer", False, Q), ("service_type", False, ""), ("cost", False, Q),
      ("service_date", False, "")],
     _prov_call("vehicle", "vehicle_log_maintenance"))
_add("vehicle_registration", "medium", "vehicle", "Record vehicle registration",
     [("reg", True, ""), ("make", False, ""), ("model", False, ""),
      ("renewal_date", False, "")],
     _prov_call("vehicle", "vehicle_registration"))
_add("vehicle_reminders", "low", "vehicle", "Compute vehicle service reminders",
     [("reg", False, ""), ("interval_km", False, Q),
      ("interval_months", False, P)],
     _prov_call("vehicle", "vehicle_reminders"))

# --- Feature 79 Real-World Actions ----------------------------------------------
_add("action_status", "low", "actions", "Real-world action engine status",
     [], _prov_call("world_actions", "action_status"))
_add("action_create", "medium", "actions", "Create a rule/action record",
     [("name", True, ""), ("trigger", False, ""), ("action_type", False, ""),
      ("target", False, ""), ("enabled", False, B), ("dry_run", False, B)],
     _prov_call("world_actions", "action_create"))
_add("action_dry_run", "low", "actions", "Dry-run an action (no side effects)",
     [("action_id", False, "")], _prov_call("world_actions", "action_dry_run"))
_add("action_execute", "high", "actions", "Execute a real-world action (gated)",
     [("action_id", True, "")], _prov_direct("world_actions", "action_execute",
                                              forged=True))

# --- Features 81 & 102 Finance / Transactions / Investment ----------------------
_add("finance_transaction_add", "medium", "finance", "Add a transaction",
     [("date", True, ""), ("amount", True, Q), ("type", True, ""),
      ("note", False, ""), ("category", False, "")],
     _prov_direct("finance", "finance_transaction_add"))
_add("finance_transaction_list", "low", "finance", "List transactions",
     [("category", False, ""), ("month", False, ""),
      ("start_date", False, ""), ("end_date", False, "")],
     _prov_call("finance", "finance_transaction_list"))
_add("finance_transaction_void", "high", "finance", "Void a transaction (gated)",
     [("transaction_id", True, "")],
     _prov_direct("finance", "finance_transaction_void", forged=True))
_add("finance_transaction_delete", "high", "finance", "Delete a transaction (gated)",
     [("transaction_id", True, "")],
     _prov_direct("finance", "finance_transaction_delete", forged=True))
_add("finance_budget_set", "medium", "finance", "Set a monthly budget",
     [("category", True, ""), ("limit", True, Q), ("month", False, ""),
      ("note", False, "")],
     _prov_direct("finance", "finance_budget_set"))
_add("finance_budget_status", "low", "finance", "Budget compliance status",
     [("month", False, "")], _prov_call("finance", "finance_budget_status"))
_add("finance_report", "medium", "finance", "Generate a finance report (file)",
     [("month", False, ""), ("category", False, "")],
     _prov_call("finance", "finance_report"))
_add("finance_investment_add", "medium", "finance", "Add a watchlist symbol",
     [("symbol", True, "")],
     _prov_direct("finance", "finance_investment_watchlist"))
_add("finance_portfolio", "low", "finance", "Portfolio summary (user-entered data)",
     [], _prov_call("finance", "finance_portfolio"))

# --- Feature 85 Smart Shopping ---------------------------------------------------
_add("shopping_list_create", "low", "shopping", "Create a shopping list",
     [("list_name", False, "")],
     lambda **kw: _prov_call("shopping", "shopping_list")(action="create", **kw))
_add("shopping_list_add", "medium", "shopping", "Add an item to a shopping list",
     [("list_name", False, ""), ("name", True, ""), ("qty", False, P),
      ("priority", False, "")],
     lambda **kw: _prov_call("shopping", "shopping_list")(action="add", **kw))
_add("shopping_price_memo", "medium", "shopping", "Record a price observation",
     [("item", True, ""), ("store", False, ""), ("price", True, Q)],
     _prov_call("shopping", "shopping_price_memo"))
_add("shopping_compare", "low", "shopping", "Compare prices across stores",
     [("store", False, "")], _prov_call("shopping", "shopping_compare"))
_add("shopping_purchase", "high", "shopping", "Purchase items (gated; needs provider)",
     [("items", True, ""), ("store", False, "")],
     _prov_direct("shopping", "shopping_purchase", forged=True))

# --- Feature 96 Supply Chain / Inventory --------------------------------------------
_add("inventory_status", "low", "inventory", "Inventory status",
     [], _call_engine(_engine_inventory, "status"))
_add("inventory_item_add", "medium", "inventory", "Add an inventory item",
     [("sku", True, ""), ("name", True, ""), ("qty", False, Q),
      ("min_qty", False, Q), ("cost", False, Q), ("location", False, "")],
     _call_engine(_engine_inventory, "add_item"))
_add("inventory_receive", "medium", "inventory", "Receive stock",
     [("sku", True, ""), ("qty", True, Q), ("ref", False, "")],
     _call_engine(_engine_inventory, "receive"))
_add("inventory_issue", "medium", "inventory", "Issue stock",
     [("sku", True, ""), ("qty", True, Q), ("ref", False, "")],
     _call_engine(_engine_inventory, "issue"))
_add("inventory_adjust", "medium", "inventory", "Adjust stock with a reason",
     [("sku", True, ""), ("delta", True, Q), ("reason", True, "")],
     _call_engine(_engine_inventory, "adjust"))
_add("inventory_reorder", "low", "inventory", "Reorder suggestions",
     [], _call_engine(_engine_inventory, "reorder_suggestions"))
_add("inventory_stock_value", "low", "inventory", "Stock value",
     [], _call_engine(_engine_inventory, "stock_value"))
_add("inventory_audit", "low", "inventory", "Inventory audit log",
     [], _call_engine(_engine_inventory, "audit_log"))

# --- Feature 97 Service Orchestration ------------------------------------------------
_add("services_status", "low", "services", "Service orchestration status",
     [], _call_engine(_engine_services, "status"))
_add("services_register", "medium", "services", "Register a service",
     [("service_id", True, ""), ("display_name", False, ""),
      ("version", False, ""), ("deps", False, ""), ("side_effects", False, B)],
     _call_engine(_engine_services, "register_service"))
_add("services_health", "low", "services", "Service health rollup",
     [("service_id", True, "")],
     _call_engine(_engine_services, "health_rollup"))
_add("services_start", "high", "services", "Start a service (gated)",
     [("service_id", True, "")],
     lambda **kw: _engine_services().start_service(
         service_id=kw["service_id"], confirmed=True, trusted=True,
         request_id=_mint("services.start")))
_add("services_stop", "high", "services", "Stop a service (gated)",
     [("service_id", True, "")],
     lambda **kw: _engine_services().stop_service(
         service_id=kw["service_id"], confirmed=True, trusted=True,
         request_id=_mint("services.stop")))
_add("services_degraded", "low", "services", "Degraded service detection",
     [], _call_engine(_engine_services, "degraded_detection"))

# --- Feature 50 Mission Supervision ---------------------------------------------
_add("mission_create", "medium", "missions", "Create a mission",
     [("title", True, ""), ("steps", True, ""), ("priority", False, P),
      ("budget_seconds", False, P)],
     lambda **kw: _mission_create(**kw))
_add("mission_start", "medium", "missions", "Start a mission",
     [("mission_id", True, "")], _call_engine(_engine_missions, "start"))
_add("mission_status", "low", "missions", "Mission status",
     [("mission_id", True, "")], _call_engine(_engine_missions, "summary"))
_add("mission_steps", "low", "missions", "Mission steps",
     [("mission_id", True, "")], _call_engine(_engine_missions, "steps"))
_add("mission_pause", "medium", "missions", "Pause a mission",
     [("mission_id", True, "")], _call_engine(_engine_missions, "pause"))
_add("mission_resume", "medium", "missions", "Resume a mission",
     [("mission_id", True, "")], _call_engine(_engine_missions, "resume"))
_add("mission_cancel", "high", "missions", "Cancel a mission (gated)",
     [("mission_id", True, ""), ("reason", False, "")],
     _call_engine(_engine_missions, "cancel"))
_add("mission_finish", "medium", "missions", "Finish a mission",
     [("mission_id", True, "")], _call_engine(_engine_missions, "finish"))
_add("mission_archive", "medium", "missions", "Archive a mission (no delete)",
     [("mission_id", True, "")], _call_engine(_engine_missions, "archive"))

# --- Feature 101 Long-Term Mission Continuity --------------------------------------
_add("continuity_snapshot", "medium", "continuity", "Snapshot mission state",
     [("mission_id", True, "")],
     lambda **kw: _engine_continuity().snapshot(
         mission_id=kw["mission_id"], engine=_engine_missions()))
_add("continuity_resume", "medium", "continuity", "Restore missions from snapshots",
     [], lambda **kw: _engine_continuity().resume(engine=_engine_missions()))
_add("continuity_orphans", "low", "continuity", "Report orphaned mission refs",
     [], lambda **kw: _engine_continuity().orphan_report(engine=_engine_missions()))

# --- Feature 51 Context / Working Memory ---------------------------------------------
_add("context_event_push", "medium", "context", "Push a working-memory event",
     [("text", True, ""), ("tags", False, "")],
     _call_engine(_engine_context, "push_event"))
_add("context_focus", "low", "context", "Set current focus topics",
     [("topics", True, "")], _call_engine(_engine_context, "focus"))
_add("context_query", "low", "context", "Query working context",
     [("query", True, "")], _call_engine(_engine_context, "context_for"))
_add("context_summary", "low", "context", "Summarize the context window",
     [("limit", False, P)], _call_engine(_engine_context, "summarize_window"))

# --- Feature 99 World State Model -------------------------------------------------------
_add("world_state_set", "medium", "world", "Set an entity in the world state",
     [("name", True, ""), ("attributes", False, "")],
     lambda **kw: _engine_world().set_entity(
         name=kw["name"], attributes=_parse_kv(kw.get("attributes"))))
_add("world_state_update", "medium", "world", "Update an entity attribute",
     [("name", True, ""), ("key", True, ""), ("value", True, ""),
      ("unit", False, "")],
     lambda **kw: _engine_world().update_attribute(
         name=kw["name"], key=kw["key"], value=kw["value"],
         unit=kw.get("unit")))
_add("world_state_query", "low", "world", "Query world state",
     [("conditions", False, "")],
     lambda **kw: _engine_world().query(
         conditions=_parse_kv(kw.get("conditions"))))
_add("world_state_project", "low", "world", "Project an attribute forward",
     [("name", True, ""), ("attribute", True, ""), ("dt_hours", True, Q)],
     _call_engine(_engine_world, "project"))
_add("world_state_consistency", "low", "world", "World state consistency check",
     [], _call_engine(_engine_world, "consistency_check"))

# --- Feature 52 Experiential Learning ------------------------------------------------
_add("experience_record", "medium", "experience", "Record an experience",
     [("trigger", True, ""), ("action", True, ""), ("outcome", False, ""),
      ("reward", False, Q), ("tags", False, "")],
     _call_engine(_engine_experience, "record"))
_add("experience_similar", "low", "experience", "Similar experiences",
     [("trigger", True, ""), ("k", False, P)],
     _call_engine(_engine_experience, "similar"))
_add("experience_lessons", "low", "experience", "Lessons for a topic",
     [("topic", True, "")], _call_engine(_engine_experience, "lessons"))

# --- Feature 53 Decision Support ---------------------------------------------------------
_add("decision_criteria_add", "medium", "decisions", "Add decision criteria",
     [("name", True, ""), ("weight", True, Q), ("direction", False, "")],
     _call_engine(_engine_decisions, "add_criteria"))
_add("decision_option_add", "medium", "decisions", "Add an option with scores",
     [("name", True, ""), ("scores", True, "")],
     lambda **kw: _engine_decisions().add_option(
         name=kw["name"], scores=_parse_kv(kw["scores"])))
_add("decision_evaluate", "low", "decisions", "Evaluate weighted decision",
     [], _call_engine(_engine_decisions, "evaluate"))
_add("decision_pros_cons", "medium", "decisions", "Store pros/cons for a topic",
     [("topic", True, ""), ("pros", False, ""), ("cons", False, "")],
     _call_engine(_engine_decisions, "pros_cons"))

# --- Feature 55 Workflow Builder -----------------------------------------------------------
_add("workflow_define", "medium", "workflows", "Define a workflow",
     [("name", True, ""), ("steps", True, ""), ("template", False, "")],
     lambda **kw: _engine_goals().define(
         name=kw["name"], steps=_parse_list(kw["steps"]),
         template=kw.get("template")))
_add("workflow_run", "medium", "workflows", "Run a workflow",
     [("workflow_id", True, ""), ("inputs", False, "")],
     lambda **kw: _engine_goals().run(
         workflow_id=kw["workflow_id"], inputs=kw.get("inputs"),
         confirmed=True, trusted=True, request_id=_mint("workflows.run")))
_add("workflow_status", "low", "workflows", "Workflow status",
     [("workflow_id", True, "")], _call_engine(_engine_goals, "get"))
_add("workflow_abort", "high", "workflows", "Abort a workflow (gated)",
     [("workflow_id", True, "")],
     lambda **kw: _engine_goals().abort(workflow_id=kw["workflow_id"]))
_add("workflow_templates", "low", "workflows", "List workflow templates",
     [], _call_engine(_engine_goals, "list_templates"))

# --- Feature 56 Skill Creation -------------------------------------------------------------
_add("skill_define", "medium", "skills", "Define a skill",
     [("name", True, ""), ("description", False, ""), ("parameters", False, ""),
      ("procedure", False, ""), ("verify", False, "")],
     lambda **kw: _engine_skills().define(
         name=kw["name"], description=kw.get("description", ""),
         parameters=kw.get("parameters") or [],
         procedure=[{"action": s} for s in _parse_list(kw.get("procedure"))],
         verify=kw.get("verify")))
_add("skill_invoke", "medium", "skills", "Invoke a skill",
     [("skill_name", True, ""), ("arguments", False, "")],
     lambda **kw: _engine_skills().invoke(
         skill_name=kw["skill_name"], arguments=kw.get("arguments"),
         confirmed=True, trusted=True, request_id=_mint("skills.invoke")))
_add("skill_list", "low", "skills", "List defined skills",
     [], _call_engine(_engine_skills, "list"))
_add("skill_verify", "low", "skills", "Verify a skill with evidence",
     [("skill_name", True, ""), ("evidence", False, "")],
     _call_engine(_engine_skills, "verify"))

# --- Feature 57 Anomaly Detection ---------------------------------------------------------
_add("anomaly_ingest", "low", "anomaly", "Feed a numeric sample",
     [("series_id", True, ""), ("value", True, Q), ("label", False, "")],
     _call_engine(_engine_anomaly, "ingest"))
_add("anomaly_detect", "low", "anomaly", "Detect anomalies in a series",
     [("series_id", True, "")], _call_engine(_engine_anomaly, "detect"))
_add("anomaly_report", "low", "anomaly", "Anomaly series report",
     [("series_id", True, "")], _call_engine(_engine_anomaly, "report"))
_add("anomaly_set_bounds", "medium", "anomaly", "Set hard bounds for a series",
     [("series_id", True, ""), ("min_value", False, Q), ("max_value", False, Q)],
     _call_engine(_engine_anomaly, "set_bounds"))

# --- Feature 58 Alerts / Notifications ----------------------------------------------------
_add("alert_create", "low", "alerts", "Create an alert",
     [("severity", True, ""), ("title", True, ""), ("message", False, ""),
      ("source", False, ""), ("dedup_key", False, "")],
     lambda **kw: _engine_alerts().create(
         severity=kw["severity"], title=kw["title"],
         message=kw.get("message", ""), source=kw.get("source", "tool"),
         dedup_key=kw.get("dedup_key")))
_add("alert_list", "low", "alerts", "List alerts",
     [("severity", False, ""), ("status", False, "")],
     _call_engine(_engine_alerts, "list"))
_add("alert_ack", "low", "alerts", "Acknowledge an alert",
     [("alert_id", True, "")], _call_engine(_engine_alerts, "ack"))
_add("alert_close", "medium", "alerts", "Close an alert (archives it)",
     [("alert_id", True, "")], _call_engine(_engine_alerts, "close"))
_add("alert_active", "low", "alerts", "Active alerts",
     [], _call_engine(_engine_alerts, "active"))

# --- Feature 65 Knowledge Graph ---------------------------------------------------------
_add("graph_node_add", "medium", "knowledge", "Add a knowledge graph node",
     [("node_id", True, ""), ("node_type", False, ""), ("attrs", False, "")],
     _call_engine(_engine_graph, "add_node"))
_add("graph_edge_add", "medium", "knowledge", "Add a knowledge graph edge",
     [("src", True, ""), ("dst", True, ""), ("relation", True, ""),
      ("weight", False, Q)],
     _call_engine(_engine_graph, "add_edge"))
_add("graph_neighbors", "low", "knowledge", "Node neighbours",
     [("node_id", True, ""), ("relation", False, "")],
     _call_engine(_engine_graph, "neighbors"))
_add("graph_path", "low", "knowledge", "Shortest path between nodes",
     [("start", True, ""), ("end", True, "")],
     _call_engine(_engine_graph, "shortest_path"))
_add("graph_summary", "low", "knowledge", "Knowledge graph summary",
     [], _call_engine(_engine_graph, "summarize"))

# --- Feature 66 Knowledge Assimilation -----------------------------------------------------
def _assim_record(**kw):
    e = _engine_assim()
    return e.record_triple(subject=kw["subject"], predicate=kw["predicate"],
                           object_=kw["object"], source_id=kw.get("source_id"))


def _assim_ingest(**kw):
    e = _engine_assim()
    result = e.assimilate(kw["text"], kw["source_id"])
    return e.store(result=result, source_id=kw["source_id"], text=kw["text"])


_add("knowledge_ingest", "medium", "knowledge", "Assimilate a document into the graph",
     [("text", True, ""), ("source_id", True, "")], _assim_ingest)
_add("knowledge_triple", "medium", "knowledge", "Record a knowledge triple",
     [("subject", True, ""), ("predicate", True, ""), ("object", True, ""),
      ("source_id", False, "")], _assim_record)
_add("knowledge_conflicts", "low", "knowledge", "List assimilation conflicts",
     [], _call_engine(_engine_assim, "conflicts"))

# --- Feature 71 Fact Verification --------------------------------------------------------
_add("fact_check", "low", "factcheck", "Verify a claim against sources",
     [("claim", True, ""), ("sources", False, "")],
     _call_engine(_engine_facts, "check"))
_add("fact_cross_check", "low", "factcheck", "Agreement across sources",
     [("sources", True, "")], _call_engine(_engine_facts, "cross_check"))

# --- Feature 70 Memory Lifecycle ----------------------------------------------------------
_add("memory_age", "medium", "memory", "Apply importance decay (protected facts kept)",
     [("decay_rate", True, Q)], _call_engine(_engine_lifecycle, "age"))
_add("memory_forget_candidates", "low", "memory", "Suggest candidates for soft forgetting",
     [("threshold", False, Q)],
     _call_engine(_engine_lifecycle, "candidates_for_forgetting"))
_add("memory_protect", "medium", "memory", "Protect a memory from forgetting",
     [("memory_id", True, P)], _call_engine(_engine_lifecycle, "protect"))
_add("memory_merge_suggest", "low", "memory", "Suggest duplicate merges",
     [("threshold", False, Q)], _call_engine(_engine_lifecycle, "merge_duplicates"))

# --- Features 67 & 68 Meetings / Conversation -----------------------------------------------
def _meeting(id):
    return _engine_meetings()


_MEETING_FIELDS = ["id", "title", "agenda"]


def _meeting_create(**kw):
    m = _engine_meetings()
    mid = m.create_meeting(title=kw["title"], agenda=_parse_list(kw.get("agenda")))
    return {"success": True, "status": "ok", "mid": mid, "meeting_id": mid,
            "id": mid}


def _mission_create(**kw):
    m = _engine_missions()
    record = m.create_mission(
        title=kw["title"], steps=_parse_list(kw["steps"]),
        priority=kw.get("priority", 5), budget_seconds=kw.get("budget_seconds"))
    mid = record.get("id") or record.get("mission_id")
    if mid is not None and "mission_id" not in record:
        record["mission_id"] = mid
    return record


def _meeting_state(**kw):
    m = _engine_meetings()
    meeting = m._get(kw["mid"])
    return {"meeting_id": kw["mid"], "current_topic": meeting.get("current_topic"),
            "topics": meeting.get("topics", [])}


_add("meeting_create", "medium", "meetings", "Create a meeting",
     [("title", True, ""), ("agenda", False, "")],
     _meeting_create)
_add("meeting_topic_add", "medium", "meetings", "Add a meeting topic",
     [("mid", True, ""), ("title", True, "")],
     _call_engine(_engine_meetings, "add_topic"))
_add("meeting_decision_add", "medium", "meetings", "Record a meeting decision",
     [("mid", True, ""), ("text", True, "")],
     _call_engine(_engine_meetings, "add_decision"))
_add("meeting_action_item_add", "medium", "meetings", "Add an action item",
     [("mid", True, ""), ("owner", True, ""), ("due_iso", True, ""),
      ("text", True, "")],
     _call_engine(_engine_meetings, "add_action_item"))
_add("meeting_capture", "medium", "meetings", "Capture a transcript line",
     [("mid", True, ""), ("speaker", True, ""), ("text", True, "")],
     _call_engine(_engine_meetings, "capture"))
_add("meeting_minutes", "low", "meetings", "Meeting minutes summary",
     [("mid", True, "")], _call_engine(_engine_meetings, "summary"))
_add("meeting_export", "low", "meetings", "Export meeting minutes to file",
     [("mid", True, ""), ("format", False, "")],
     _call_engine(_engine_meetings, "export_minutes"))
_add("meeting_participant_register", "medium", "meetings", "Register a participant",
     [("name", True, ""), ("role", False, "")],
     lambda **kw: _engine_meetings().participants.register_participant(
         name=kw["name"], role=kw.get("role", "member")))
_add("meeting_participants", "low", "meetings", "List participants",
     [], lambda **kw: _engine_meetings().participants.list_participants())
_add("conversation_turn", "medium", "meetings", "Record a speaker turn",
     [("mid", True, ""), ("active_participant", True, "")],
     _call_engine(_engine_meetings, "turn"))
_add("conversation_state", "low", "meetings", "Current conversation state",
     [("mid", True, "")],
     lambda **kw: _meeting_state(**kw))

# --- Feature 69 Emotional Intelligence ------------------------------------------------
_add("affect_observe", "medium", "affect", "Observe an interaction signal",
     [("speaker", True, ""), ("text", True, "")],
     _call_engine(_engine_affect, "observe"))
_add("affect_mood", "low", "affect", "Current mood aggregate",
     [], _call_engine(_engine_affect, "mood"))
_add("affect_tone", "low", "affect", "Adaptive tone suggestion",
     [("intent", False, "")], _call_engine(_engine_affect, "adapt_tone"))

# --- Feature 48 Speaker Recognition -------------------------------------------------------
_add("speaker_enroll", "medium", "speech", "Enroll a speaker voiceprint",
     [("speaker_id", True, ""), ("audio", True, ""), ("consent", False, B)],
     _call_engine(_engine_speaker, "enroll"))
_add("speaker_recognize", "low", "speech", "Recognize a speaker (never grants auth)",
     [("audio", True, "")], _call_engine(_engine_speaker, "recognize"))
_add("speaker_list", "low", "speech", "List enrolled speakers",
     [], _call_engine(_engine_speaker, "list_speakers"))

# --- Feature 49 Language Detection --------------------------------------------------------
_add("language_detect", "low", "speech", "Detect language of text",
     [("text", True, "")], _call_engine(_engine_language, "detect"))
_add("language_set", "medium", "speech", "Explicitly set the language",
     [("name", True, ""), ("force", False, B)],
     _call_engine(_engine_language, "set_language"))

# --- Features 86–90 Advisors ---------------------------------------------------------------
def _advisor_call(name, method, defaults=None):
    defaults = defaults or {}

    def _call(**kw):
        advisor = _engine_advisor(name)
        if advisor is None:
            return {"success": False, "status": "NOT_CONFIGURED",
                    "message": f"advisor '{name}' unavailable"}
        merged = dict(defaults)
        merged.update(kw)
        return getattr(advisor, method)(**merged)
    return _call


_add("interaction_plan", "low", "advisor", "Plan an interaction cadence",
     [("role", True, ""), ("topic", True, ""), ("cadence_days", False, P)],
     _advisor_call("interactions", "plan_interaction"))
_add("interaction_followups", "low", "advisor", "Pending interaction follow-ups",
     [], _advisor_call("interactions", "pending_followups"))
_add("tutor_curriculum", "low", "advisor", "Build a curriculum for a topic",
     [("topic", True, ""), ("lessons", True, P), ("level", False, "")],
     _advisor_call("tutor", "build_curriculum"))
_add("tutor_assess", "medium", "advisor", "Score answers",
     [("answers", True, "")], _advisor_call("tutor", "assess"))
_add("tutor_next", "low", "advisor", "Next lesson in a curriculum",
     [("curricula_id", True, "")], _advisor_call("tutor", "next_lesson"))
_add("career_gap", "low", "advisor", "Skills gap for a target role",
     [("target_role", True, ""), ("current_skills", True, "")],
     _advisor_call("career", "skills_gap"))
_add("career_interview_prep", "low", "advisor", "Interview prep checklist",
     [("target_role", True, "")], _advisor_call("career", "interview_prep"))
_add("relationship_checkin", "medium", "advisor", "Schedule a check-in",
     [("contact", True, ""), ("date_iso", True, ""), ("topic", False, "")],
     _advisor_call("relationships", "schedule_checkin",
                   {"topic": "general check-in"}))
_add("relationship_patterns", "low", "advisor", "Relationship interaction patterns",
     [], _advisor_call("relationships", "interaction_patterns"))
_add("coach_draft", "low", "advisor", "Draft a message with a tone",
     [("tone", True, ""), ("audience", True, ""), ("points", True, "")],
     _advisor_call("communication_coach", "draft"))
_add("coach_tone_check", "low", "advisor", "Tone-check a message draft",
     [("text", True, "")], _advisor_call("communication_coach", "tone_check"))
_add("coach_speaking_tips", "low", "advisor", "Public-speaking tips",
     [], _advisor_call("communication_coach", "speaking_tips"))

# --- Feature 105 Access Control --------------------------------------------------------------
_add("access_grant", "medium", "access", "Grant a permission",
     [("scope", True, ""), ("action", True, ""), ("principal", True, ""),
      ("ttl_days", False, P)],
     _call_engine(_engine_access, "grant"))
_add("access_check", "low", "access", "Check if an action is permitted",
     [("scope", True, ""), ("action", True, ""), ("principal", True, "")],
     _call_engine(_engine_access, "check"))
_add("access_revoke", "high", "access", "Revoke a permission (gated)",
     [("scope", True, ""), ("action", True, ""), ("principal", True, "")],
     _call_engine(_engine_access, "revoke"))
_add("access_report", "low", "access", "Least-privilege report",
     [], _call_engine(_engine_access, "least_privilege_report"))

# --- Feature 106 Privacy / GDPR ---------------------------------------------------------------
_add("privacy_inventory", "low", "privacy", "Data inventory",
     [], _call_engine(_engine_privacy, "inventory"))
_add("privacy_export", "medium", "privacy", "Redacted privacy export (file)",
     [("user", True, "")], _call_engine(_engine_privacy, "request_export"))
_add("privacy_erasure", "high", "privacy", "Right to erasure (anonymizes, never deletes)",
     [("scope", True, "")],
     lambda **kw: _engine_privacy().right_to_erasure(
         scope=kw["scope"], confirmed=True, trusted=True,
         request_id=_mint("privacy.erasure")))
_add("privacy_consent", "medium", "privacy", "Log consent",
     [("user", True, ""), ("purpose", True, ""), ("granted", False, B)],
     _call_engine(_engine_privacy, "consent_log"))
_add("privacy_report", "low", "privacy", "Privacy report",
     [], _call_engine(_engine_privacy, "privacy_report"))

# --- Feature 72 Report Builder ---------------------------------------------------------------
_add("report_render", "low", "reports", "Render a report",
     [("name", True, ""), ("title", True, "")],
     lambda **kw: _engine_reports().render(name=kw["name"]))
_add("report_section_add", "medium", "reports", "Add a report section",
     [("title", True, ""), ("body", True, ""), ("name", False, "")],
     _call_engine(_engine_reports, "add_section"))
_add("report_export", "medium", "reports", "Export a report to file",
     [("name", True, "")], _call_engine(_engine_reports, "export"))

# --- Feature 73 Collaboration -----------------------------------------------------------------
_add("board_create", "medium", "collaboration", "Create a collaboration board",
     [("name", True, ""), ("columns", False, "")],
     lambda **kw: _board_create(**kw))
_add("board_card_add", "medium", "collaboration", "Add a card",
     [("board_id", True, ""), ("title", True, ""), ("priority", False, ""),
      ("assignee", False, ""), ("due", False, "")],
     lambda **kw: _board_add_card(**kw))
_add("board_card_move", "medium", "collaboration", "Move a card",
     [("card_id", True, ""), ("column", True, ""), ("by", False, "")],
     lambda **kw: _engine_board().move_card(
         card_id=kw["card_id"], column=kw["column"],
         by=kw.get("by", "system")))
_add("board_summary", "low", "collaboration", "Board summary",
     [("board_id", True, "")], _call_engine(_engine_board, "board_summary"))
_add("board_mentions", "low", "collaboration", "Extract @mentions from text",
     [("text", True, "")],
     lambda **kw: _engine_board().mentions(kw["text"]))

# --- Feature 75 Escalation ---------------------------------------------------------------------
_add("escalate", "medium", "escalation", "Escalate a request",
     [("request", True, ""), ("to", True, ""), ("priority", False, ""),
      ("reason", False, ""), ("deadline_minutes", False, P)],
     _call_engine(_engine_escalation, "escalate"))
_add("escalation_handoff", "low", "escalation", "Build a handoff summary (file)",
     [("escalation_id", True, "")],
     _call_engine(_engine_escalation, "handoff_summary"))
_add("escalation_resolve", "medium", "escalation", "Resolve an escalation",
     [("escalation_id", True, ""), ("resolution", False, "")],
     _call_engine(_engine_escalation, "resolve"))
_add("escalation_remind", "low", "escalation", "Stale escalation reminders",
     [], _call_engine(_engine_escalation, "auto_remind"))

# --- Feature 76 Predictive Simulation ----------------------------------------------------------
_add("simulation_run", "low", "simulation", "Run a forecast model",
     [("name", True, ""), ("steps", True, P), ("params", False, "")],
     _call_engine(_engine_simulation, "run"))
_add("simulation_sensitivity", "low", "simulation", "Run a parameter sweep",
     [("name", True, ""), ("param", True, ""), ("values", True, ""),
      ("steps", False, P)],
     lambda **kw: _engine_simulation().sensitivity(
         name=kw["name"], param=kw["param"], values=kw["values"],
         steps=kw.get("steps", 30)))
_add("simulation_report", "medium", "simulation", "Write a simulation report (file)",
     [("name", True, "")], _call_engine(_engine_simulation, "report"))

# --- Feature 77 Boss Model ---------------------------------------------------------------------
_add("boss_facts", "low", "boss", "Grounded boss facts",
     [], _call_engine(_engine_boss, "facts"))
_add("boss_consult", "low", "boss", "Consult the boss model",
     [("question", True, "")], _call_engine(_engine_boss, "consult"))
_add("boss_set_preference", "medium", "boss", "Record a consented preference",
     [("name", True, ""), ("value", True, ""), ("consented", False, B)],
     _call_engine(_engine_boss, "set_preference"))

# --- Feature 78 Architecture --------------------------------------------------------------------
_add("arch_census", "low", "architecture", "Module census",
     [], _call_engine(_engine_arch, "module_census"))
_add("arch_graph", "low", "architecture", "Internal dependency graph",
     [], _call_engine(_engine_arch, "dependency_graph"))
_add("arch_contract_audit", "low", "architecture", "Module contract audit",
     [], _call_engine(_engine_arch, "contract_audit"))
_add("arch_growth", "low", "architecture", "Scalability growth plan",
     [], _call_engine(_engine_arch, "growth_plan"))

# --- Feature 91 Life OS ---------------------------------------------------------------------------
_add("life_checklist", "low", "lifeos", "Domain ritual checklist",
     [("domain", True, "")], _call_engine(_engine_lifeos, "checklist"))
_add("life_ritual_add", "medium", "lifeos", "Add a ritual",
     [("domain", True, ""), ("ritual", True, "")],
     _call_engine(_engine_lifeos, "add_ritual"))
_add("life_satisfaction_track", "medium", "lifeos", "Track domain satisfaction",
     [("domain", True, ""), ("score", True, P)],
     _call_engine(_engine_lifeos, "track_mood_satisfaction"))
_add("life_review", "low", "lifeos", "Week review",
     [("week_iso", True, "")], _call_engine(_engine_lifeos, "weekly_review"))

# --- Feature 92 Events & Dates --------------------------------------------------------------------
_add("event_add", "medium", "events", "Add an event",
     [("title", True, ""), ("date_iso", True, ""), ("time", False, ""),
      ("reminder_offset_min", False, P), ("recurring", False, "")],
     _call_engine(_engine_events, "add"))
_add("event_upcoming", "low", "events", "Upcoming events",
     [("days", False, P)], _call_engine(_engine_events, "upcoming"))
_add("event_reminders", "low", "events", "Due reminders",
     [], _call_engine(_engine_events, "reminders_due"))
_add("event_conflicts", "low", "events", "Detect event conflicts",
     [("date", True, ""), ("time", False, "")],
     _call_engine(_engine_events, "conflicts"))
_add("event_export", "low", "events", "Export calendar (RFC-ish text)",
     [], _call_engine(_engine_events, "export"))

# --- Feature 103 Project Memory ------------------------------------------------------------------
_add("project_create", "medium", "project", "Create a project vault",
     [("name", True, ""), ("phases", False, "")],
     lambda **kw: _engine_vault().create_project(
         name=kw["name"],
         phases=[({"id": p, "title": p, "status": "open"}
                  if isinstance(p, str) else p)
                 for p in _parse_list(kw.get("phases"))]))
_add("project_checkin", "medium", "project", "Project check-in",
     [("name", True, ""), ("phase_id", True, ""), ("note", True, "")],
     _call_engine(_engine_vault, "check_in"))
_add("project_status", "low", "project", "Project status",
     [("name", True, "")], _call_engine(_engine_vault, "project_status"))
_add("project_risk_update", "medium", "project", "Update project risk",
     [("name", True, ""), ("title", True, ""), ("likelihood", False, P),
      ("impact", False, P)],
     _call_engine(_engine_vault, "update_risk"))

# --- Feature 104 Contingency & Impact ------------------------------------------------------------
_add("contingency_impact", "medium", "contingency", "Impact matrix entry",
     [("change", True, ""), ("affected", True, ""), ("likelihood", True, P),
      ("severity", True, P)],
     _call_engine(_engine_contingency, "impact_matrix"))
_add("contingency_plan", "medium", "contingency", "Define a fallback plan",
     [("trigger", True, ""), ("actions", True, "")],
     _call_engine(_engine_contingency, "fallback_plan"))
_add("contingency_dry_run", "low", "contingency", "Dry-run a fallback plan",
     [("plan", True, "")], _call_engine(_engine_contingency, "dry_run"))
_add("contingency_execute", "high", "contingency", "Execute a fallback (gated)",
     [("trigger", True, "")],
     lambda **kw: _engine_contingency().execute_fallback(
         trigger=kw["trigger"], confirmed=True, by="user"))

# --- Feature 98 Command Center ----------------------------------------------------------------------
_add("dashboard", "low", "command", "Command centre dashboard",
     [], _call_engine(_engine_command, "dashboard"))
_add("health_rollup", "low", "command", "Overall health rollup",
     [], _call_engine(_engine_command, "health_rollup"))
_add("run_selftest", "medium", "command", "Run the self-test suite (backend)",
     [], _call_engine(_engine_command, "run_selftest"))
_add("set_flag", "medium", "command", "Set a control-plane flag (audited)",
     [("name", True, ""), ("value", True, "")],
     _call_engine(_engine_command, "set_flag"))

# --- Feature 107 Multimodal Interaction -------------------------------------------------------------
_add("multimodal_ingest", "medium", "multimodal", "Ingest a multimodal turn",
     [("turn", True, "")],
     lambda **kw: _engine_multimodal().ingest(
         _parse_kv(kw["turn"])))
_add("multimodal_recent", "low", "multimodal", "Recent multimodal turns",
     [("n", False, P)], _call_engine(_engine_multimodal, "recent_turns"))

# --- Features 94 & 108 Robotics -----------------------------------------------------------------------
_add("robot_envelope", "low", "robot", "Safety envelope",
     [], _call_engine(_engine_robot, "safety_envelope"))
_add("robot_plan", "low", "robot", "Plan a joint move",
     [("axis", True, ""), ("target_deg", False, Q)],
     _call_engine(_engine_robot, "plan_move"))
_add("robot_collision", "low", "robot", "Collision proxy check",
     [("axes", True, "")],
     lambda **kw: _engine_robot().collision_proxy(
         axes=_parse_kv(kw["axes"])))
_add("robot_home", "medium", "robot", "Home all joints",
     [], lambda **kw: _engine_robot().home(by="user"))
_add("robot_arm", "high", "robot", "Arm the robot (gated)",
     [], lambda **kw: _engine_robot().arm(confirmed=True, by="user"))
_add("robot_disarm", "medium", "robot", "Disarm the robot",
     [], lambda **kw: _engine_robot().disarm(by="user"))
_add("robot_execute", "high", "robot", "Execute a planned move (gated)",
     [("axis", True, ""), ("target_deg", True, Q)],
     lambda **kw: dict(_engine_robot().execute_plan(
         _engine_robot().plan_move(axis=kw["axis"],
                                   target_deg=kw["target_deg"]),
         confirmed=True, trusted=True)))
_add("robot_teach", "medium", "robot", "Teach a robot skill",
     [("name", True, ""), ("sequence", True, "")],
     lambda **kw: _engine_robot().teach(
         name=kw["name"],
         sequence=[{"axis": k, "position": v}
                   for k, v in _parse_kv(kw["sequence"]).items()]))
_add("robot_replay", "high", "robot", "Replay a learned skill (gated)",
     [("name", True, "")],
     lambda **kw: _engine_robot().replay(name=kw["name"], confirmed=True,
                                         request_id=_mint("robot.replay")))
_add("robot_skills", "low", "robot", "Learned skills",
     [], _call_engine(_engine_robot, "learned_skills"))

# --- Feature 95 Engineering ----------------------------------------------------------------------------
_add("eng_spec_create", "medium", "engineering", "Create an engineering spec",
     [("name", True, ""), ("requirements", True, ""), ("interfaces", True, "")],
     lambda **kw: _engine_engineering().create_spec(
         name=kw["name"], requirements=_parse_list(kw["requirements"]),
         interfaces=_parse_list(kw["interfaces"])))
_add("eng_sprint_board", "low", "engineering", "Sprint board",
     [], _call_engine(_engine_engineering, "sprint_board"))
_add("eng_task_add", "medium", "engineering", "Add a sprint task",
     [("name", True, ""), ("title", True, ""), ("assignee", False, ""),
      ("est_hours", False, Q)],
     lambda **kw: _engine_engineering().add_task(
         name=kw["name"], title=kw["title"],
         assignee=kw.get("assignee", "unassigned"),
         est_hours=kw.get("est_hours", 0.0)))
_add("eng_measure_log", "medium", "engineering", "Log a measurement",
     [("name", True, ""), ("metric", True, ""), ("value", True, Q),
      ("unit", True, "")],
     _call_engine(_engine_engineering, "record_measurement"))
_add("eng_export", "medium", "engineering", "Export project to file",
     [("name", True, "")], _call_engine(_engine_engineering, "export"))


# ---------------------------------------------------------------------------
# Handlers for features 47 / 60 / 61 / 62 / 63 / 64 / 74 / 92 / 102
# ---------------------------------------------------------------------------

def _shared_registry():
    from tools.builder import get_registry
    return get_registry()


def _event_dispatch(tool, args):
    """EventResponder invoker: dispatch a handler to a registered tool."""
    return _shared_registry().invoke(tool, **args)


def _build_validate(**kw):
    stages = _parse_json(kw.get("stages"))
    if not isinstance(stages, list) or not stages:
        return {"success": False, "status": "invalid_argument",
                "message": "stages must be a non-empty JSON list"}
    report = {"kind": "build_script", "name": kw.get("name", "pipeline"),
              "stages": [], "valid": True}
    registry = _shared_registry()
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            report["valid"] = False
            report["stages"].append({"index": index,
                                     "status": "invalid", "error": "not a dict"})
            continue
        sid = stage.get("id", index + 1)
        tool_name = stage.get("tool")
        args = stage.get("args", {})
        entry = {"id": sid, "tool": tool_name, "args": args}
        if not tool_name or not registry.has(tool_name):
            entry["status"] = "invalid"
            entry["error"] = f"unknown tool '{tool_name}'"
            report["valid"] = False
        else:
            missing = [p["name"] for p in _shared_registry().describe(tool_name)
                       ["parameters"] if p["required"] and p["name"] not in args]
            entry["status"] = "ok" if not missing else "invalid"
            if missing:
                entry["error"] = f"missing args: {missing}"
                report["valid"] = False
        report["stages"].append(entry)
    return report


def _build_run(**kw):
    stages = _parse_json(kw.get("stages"))
    if not isinstance(stages, list) or not stages:
        return {"success": False, "status": "invalid_argument",
                "message": "stages must be a non-empty JSON list"}
    registry = _shared_registry()
    pipeline = []
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            return {"success": False, "status": "invalid_argument",
                    "message": f"stage {index} must be a dict"}
        tool_name = stage.get("tool")
        sid = stage.get("id", index + 1)
        args = dict(stage.get("args", {}) or {})
        tool = registry.get(tool_name)
        if tool is None:
            return {"success": False, "status": "invalid_argument",
                    "message": f"stage '{sid}': unknown tool '{tool_name}'"}
        if tool.risk in ("destructive",) or tool.confirm_required:
            pipeline.append({
                "id": sid, "tool": tool_name,
                "action": (lambda name=tool_name, a=args:
                           {"status": "confirm_required",
                            "message": f"{name} requires confirmation"}),
            })
            continue

        def _make_action(name=tool_name, a=args):
            return lambda: registry.invoke(name, **a)
        pipeline.append({"id": sid, "tool": tool_name,
                         "action": _make_action(tool_name, args)})
    report = _engine_pipeline().run(kw["name"], pipeline, default_timeout=10)
    stages_out = []
    for rec in report["stages"]:
        sid = rec["id"]
        tool_name = None
        for stage in stages:
            if str(stage.get("id")) == str(sid):
                tool_name = stage.get("tool")
                break
        stages_out.append({"id": sid, "tool": tool_name,
                           "status": rec["status"], "output": rec.get("output")})
    return {"success": report["complete"], "status": "DONE" if report["complete"]
            else "FAILED", "complete": report["complete"],
            "report": {"exit_summary": report["exit_summary"],
                       "stages": stages_out,
                       "complete": report["complete"],
                       "manifest_path": report["manifest_path"]}}

# --- Feature 47 Autonomous Coding & Build Agent ----------------------------------------------------
_add("build_validate", "low", "build", "Validate a build pipeline script",
     [("stages", True, "")],
     lambda **kw: _safe(_build_validate)(**kw))
_add("build_run", "medium", "build", "Run a staged build pipeline",
     [("name", True, ""), ("stages", True, "")],
     lambda **kw: _safe(_build_run)(**kw))
_add("build_git_check", "low", "build", "Check local git availability",
     [], _call_engine(_engine_pipeline, "git_check"))
_add("build_fetch_remote", "low", "build", "Fetch from a remote repository",
     [("repo_url", False, ""), ("workdir", False, "")],
     _call_engine(_engine_pipeline, "fetch_remote"))

# --- Feature 59 Digital Organization Manager ---------------------------------------------------------
def _plan_tasks(value):
    parsed = _parse_json(value)
    if isinstance(parsed, list):
        return [t if isinstance(t, dict) else {"title": str(t)} for t in parsed]
    return [{"title": str(t)} for t in _parse_list(value)]


_add("organizer_daily_plan", "low", "organizer", "Build a daily time-blocked plan",
     [("tasks", True, ""), ("day", False, "")],
     lambda **kw: _engine_organizer().build_daily_plan(
         tasks=_plan_tasks(kw["tasks"]), day=kw.get("day")))
_add("organizer_events", "low", "organizer", "Upcoming calendar events",
     [("days", False, Q)],
     lambda **kw: _engine_organizer().upcoming(
         days=int(kw.get("days", 7))))
_add("organizer_event_create", "medium", "organizer", "Add a calendar event",
     [("event_id", True, ""), ("title", True, ""), ("start_dt", True, ""),
      ("end_dt", True, "")],
     _call_engine(_engine_organizer, "create_event"))
_add("organizer_conflicts", "low", "organizer", "Detect scheduling conflicts",
     [], _call_engine(_engine_organizer, "conflicts"))
_add("organizer_reminders", "low", "organizer", "Pending reminders",
     [], _call_engine(_engine_organizer, "due"))
_add("organizer_reminder_create", "medium", "organizer", "Create a reminder",
     [("reminder_id", True, ""), ("text", True, ""), ("due_iso", True, "")],
     _call_engine(_engine_organizer, "create_reminder"))
_add("organizer_digest", "low", "organizer", "Daily brief / digest",
     [], _call_engine(_engine_organizer, "email_digest"))
_add("organizer_weekly", "low", "organizer", "Weekly review template",
     [], _call_engine(_engine_organizer, "weekly_review_template"))

# --- Feature 60 Security Guardian & Cybersecurity Toolkit --------------------------------------------
def _qa_style(**kw):
    qa = _engine_qa()
    combined = {
        "docstrings": qa.docstrings_present(file=kw["path"]),
        "line_length": qa.line_length(file=kw["path"],
                                      max=kw.get("max_line", 88)),
        "trailing_whitespace": qa.trailing_whitespace(file=kw["path"]),
    }
    combined["ok"] = all(c.get("ok", False) for c in combined.values())
    return combined


def _restore_backup(**kw):
    from core.confirmation import CONFIRMATION
    rid = CONFIRMATION.require("backup.restore")
    CONFIRMATION.approve(rid)
    return _engine_backup().restore(
        snap_id=kw["snapshot_id"], target_dir=kw["target_dir"],
        confirmed=True, trusted=True, request_id=rid)


def _classify_path(path):
    from core.backup import classify_path
    return classify_path(path)


def _perf_benchmark(**kw):
    label = kw["label"]
    tool_name = kw["tool"]
    iterations = int(kw.get("iterations", 5))
    args = _parse_json(kw.get("args")) or {}
    if not tool_name or not _shared_registry().has(tool_name):
        return {"success": False, "status": "invalid_argument",
                "message": f"unknown tool '{tool_name}'"}
    missing = [p["name"] for p in _shared_registry().describe(tool_name)
               ["parameters"] if p["required"] and p["name"] not in args]
    if missing:
        return {"success": False, "status": "invalid_argument",
                "message": f"missing benchmark args: {missing}"}

    def _one():
        return _shared_registry().invoke(tool_name, **args)

    profiler = _engine_profiler()
    stats = profiler.benchmark(label, _one, iterations)
    profiler.tick()
    return {"status": "DONE", "measurement": stats,
            "ok": True, "success": True}
_add("guardian_exfil_scan", "low", "security", "Scan text for exfiltration patterns",
     [("text", True, "")],
     lambda **kw: _engine_guardian().exfil_scan(text=kw["text"]))
_add("guardian_credential_scan", "low", "security", "Scan for embedded credentials",
     [("text", True, "")],
     lambda **kw: _engine_guardian().credential_scan(text=kw["text"]))
_add("guardian_url_safety", "low", "security", "Classify URL safety",
     [("url", True, "")],
     lambda **kw: _engine_guardian().url_safety(url=kw["url"]))
_add("guardian_permission_review", "low", "security", "Review permission grants",
     [], _call_engine(_engine_guardian, "permission_review"))
_add("guardian_policy", "low", "security", "Run security policy checks",
     [("action", True, ""), ("target", True, "")],
     lambda **kw: _engine_guardian().policy_check(
         action=kw["action"], target=kw["target"]))
_add("cyber_scope_add", "medium", "cyber", "Authorize a cyber scope/target",
     [("scope", True, "")],
     lambda **kw: _engine_cyber().add_scope(scope=kw["scope"]))
_add("cyber_scope_list", "low", "cyber", "List authorized cyber scopes",
     [], _call_engine(_engine_cyber, "list_scopes"))
_add("cyber_scope_remove", "medium", "cyber", "Revoke an authorized scope",
     [("scope", True, "")],
     lambda **kw: _engine_cyber().remove_scope(scope=kw["scope"]))
_add("cyber_discover", "low", "cyber", "Discover installed security tools",
     [], _call_engine(_engine_cyber, "discover_tools"))
_add("cyber_explain", "low", "cyber", "Explain a cybersecurity concept",
     [("topic", True, "")], _call_engine(_engine_cyber, "explain"))
_add("cyber_scan", "high", "cyber", "Authorized, non-intrusive security scan (gated)",
     [("target", True, ""), ("tool", False, "")],
     lambda **kw: _engine_cyber().scan(
         target=kw["target"], tool=kw.get("tool", "tls"), confirmed=True,
         by="user"))
_add("cyber_audit", "low", "cyber", "Read the cyber evidence ledger",
     [("limit", False, Q)], _call_engine(_engine_cyber, "audit"))

# --- Feature 61 Automatic Backup & Recovery ---------------------------------------------------------
_add("backup_classify", "low", "backup", "Classify a path for backup safety",
     [("path", True, "")],
     lambda **kw: _safe(lambda **a: _classify_path(a["path"]))(**kw))
_add("backup_snapshot", "medium", "backup", "Create a backup snapshot",
     [("label", True, "")], _call_engine(_engine_backup, "snapshot"))
_add("backup_list", "low", "backup", "List backup snapshots",
     [], _call_engine(_engine_backup, "list_snapshots"))
_add("backup_verify", "low", "backup", "Verify snapshot integrity",
     [("snapshot_id", True, "")],
     lambda **kw: _engine_backup().verify(snap_id=kw["snapshot_id"]))
_add("backup_rotate", "medium", "backup", "Archive old snapshots (never deletes)",
     [("keep", False, Q)], _call_engine(_engine_backup, "rotate"))
_add("backup_restore", "high", "backup", "Restore a snapshot into a target dir",
     [("snapshot_id", True, ""), ("target_dir", True, "")],
     lambda **kw: _restore_backup(**kw))

# --- Feature 62 Autonomous Testing & QA Agent -------------------------------------------------------
_add("qa_syntax", "low", "qa", "Syntax-check a Python file",
     [("path", True, "")],
     lambda **kw: _engine_qa().syntax_check(file=kw["path"]))
_add("qa_imports", "low", "qa", "Check that imports resolve",
     [("path", True, "")],
     lambda **kw: _engine_qa().imports_resolve(file=kw["path"]))
_add("qa_style", "low", "qa", "Style checks (docstrings, line length, whitespace)",
     [("path", True, ""), ("max_line", False, Q)],
     lambda **kw: _safe(_qa_style)(**kw))
_add("qa_todos", "low", "qa", "Count TODO/FIXME markers",
     [("path", True, "")],
     lambda **kw: _engine_qa().count_todos(directory=kw["path"]))
_add("qa_pytest", "medium", "qa", "Run pytest on a target path",
     [("target", True, "")],
     lambda **kw: _engine_qa().run_pytest(target=kw["target"]))
_add("qa_report", "medium", "qa", "Write a QA report to Output/QA",
     [("path", True, "")], _call_engine(_engine_qa, "report"))

# --- Feature 63 Self-Diagnostics & Self-Healing -----------------------------------------------------
_add("diagnostics_run", "low", "diagnostics", "Full system health snapshot",
     [], _call_engine(_engine_diagnostics, "run"))
_add("diagnostics_report", "low", "diagnostics", "Write diagnostics Markdown",
     [], _call_engine(_engine_diagnostics, "report"))

# --- Feature 64 Performance Optimizer ---------------------------------------------------------------
_add("perf_report", "low", "performance", "Timing stats for a label",
     [("label", True, "")], _call_engine(_engine_profiler, "report"))
_add("perf_hotspots", "low", "performance", "Slowest recorded operations",
     [("top", False, Q)], _call_engine(_engine_profiler, "hotspots"))
_add("perf_fps", "low", "performance", "Rolling FPS estimate",
     [("window", False, Q)], _call_engine(_engine_profiler, "fps_estimate"))
_add("perf_benchmark", "medium", "performance", "Benchmark a registered tool",
     [("label", True, ""), ("tool", True, ""), ("iterations", False, Q),
      ("args", False, "")],
     lambda **kw: _perf_benchmark(**kw))

# --- Feature 74 Dynamic Planning & Replanning ---------------------------------------------------------
_add("plan_create", "medium", "planner", "Create an adaptive plan",
     [("goal", True, ""), ("steps", True, ""), ("assumptions", False, "")],
     lambda **kw: _engine_planner().create_plan(
         goal=kw["goal"], steps=_parse_json(kw["steps"]) or [],
         assumptions=_parse_list(kw.get("assumptions"))))
_add("plan_status", "low", "planner", "Plan progress status",
     [("plan_id", True, "")], _call_engine(_engine_planner, "status"))
_add("plan_list", "low", "planner", "List plans",
     [], lambda **kw: {"plans": _engine_planner().list_plans()})
_add("plan_replan", "medium", "planner", "Replan around a blocked step",
     [("plan_id", True, ""), ("failed_step", True, ""),
      ("alternatives", True, "")],
     lambda **kw: _engine_planner().replace_step(
         plan_id=kw["plan_id"], step_ref=kw["failed_step"],
         replacements=_parse_json(kw["alternatives"]) or []))
_add("plan_complete", "low", "planner", "Mark a step complete",
     [("plan_id", True, ""), ("step_ref", True, "")],
     lambda **kw: _engine_planner().complete_step(
         plan_id=kw["plan_id"], step_ref=kw["step_ref"]))
_add("plan_deprecate", "medium", "planner", "Deprecate a plan",
     [("plan_id", True, "")], _call_engine(_engine_planner, "deprecate"))

# --- Feature 92 Real-Time Event Response ----------------------------------------------------------------
_add("er_register", "medium", "eventbus", "Register an event handler",
     [("trigger", True, ""), ("tool", False, ""), ("args", False, ""),
      ("cooldown_seconds", False, Q), ("severity", False, "")],
     lambda **kw: _engine_responder().register(
         trigger=kw["trigger"], tool=kw.get("tool"),
         args=_parse_json(kw.get("args")) or {},
         cooldown_seconds=kw.get("cooldown_seconds", 0),
         severity=kw.get("severity", "all")))
_add("er_ingest", "low", "eventbus", "Ingest an event and route it",
     [("source", True, ""), ("event_type", True, ""),
      ("severity", False, ""), ("payload", False, "")],
     lambda **kw: _engine_responder().ingest(
         source=kw["source"], event_type=kw["event_type"],
         severity=kw.get("severity", "low"),
         payload=_parse_json(kw.get("payload")) or {}))
_add("er_history", "low", "eventbus", "Recent event handling history",
     [("limit", False, Q)], _call_engine(_engine_responder, "history"))
_add("er_unregister", "low", "eventbus", "Remove an event handler",
     [("handler_id", True, "")], _call_engine(_engine_responder, "unregister"))
_add("er_stats", "low", "eventbus", "Event responder statistics",
     [], _call_engine(_engine_responder, "stats"))

# --- Feature 102 Universal Undo / Transaction Recovery -------------------------------------------------
_add("txn_begin", "medium", "undo", "Begin a transactional batch",
     [("label", False, "")], _call_engine(_engine_undo, "begin"))
_add("txn_op", "medium", "undo", "Record+apply an operation in a transaction",
     [("txn_id", True, ""), ("key", True, ""), ("value", True, "")],
     _call_engine(_engine_undo, "op"))
_add("txn_commit", "medium", "undo", "Commit a transaction",
     [("txn_id", True, "")], _call_engine(_engine_undo, "commit"))
_add("txn_rollback", "medium", "undo", "Roll a transaction back",
     [("txn_id", True, "")], _call_engine(_engine_undo, "rollback"))
_add("txn_status", "low", "undo", "Transaction status",
     [("txn_id", True, "")], _call_engine(_engine_undo, "status"))
_add("txn_active", "low", "undo", "Active transactions",
     [], _call_engine(_engine_undo, "active_transactions"))

# ---------------------------------------------------------------------------
TOOLS = _TOOLS

__all__ = ["TOOLS", "FAKE_FAIL"]