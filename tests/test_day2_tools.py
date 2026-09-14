"""Day 2 tool wiring tests — features 39-108 (tools/day2_tools.py).

These tests verify the REGISTRY LAYER and the tool->engine/provider wiring
(routing, gating, honest result dicts, real data flow). Engine/proviver
behaviour itself is covered by the feature-specific test files; here every
day-2 tool must be registered, invocable without crashing, honest, and a
representative sample of flows must round-trip real state through hermetic
temp storage (never touching data/arven_memory.db or real data files).
"""

import importlib
import inspect

import pytest

from core.confirmation import CONFIRMATION
from core.kv import KeyValueStore
import tools.day2_tools as d2
from tools.builder import build_registry

VALID_STATUSES = {
    "ok", "AVAILABLE", "UNAVAILABLE", "NOT_CONFIGURED", "OFFLINE",
    "REQUIRES_AUTH", "REQUIRES_PERMISSION", "FAILED", "EXECUTED", "REFUSED",
    "ARMED", "DISARMED", "COMPLETE", "DONE", "LEARNED", "REPLAYED",
    "confirm_required", "denied", "invalid_argument", "error", "unavailable",
    "scheduled", "pending", "completed", "open", "closed", "active",
    "registered", "resolved", "escalated", "stale", "granted", "revoked",
    "known", "ready", "draft", "idle", "running", "stopped",
    "paused", "resumed", "finished", "cancelled", "archived",
    "NOT_INSTALLED", "AUTHORIZATION_REQUIRED", "handled", "unhandled",
    "planned", "replanned", "blocked", "committed", "rolled_back",
    "deprecated", "ESCALATED", "passed", "timeout",
}


@pytest.fixture(scope="module")
def registry():
    return build_registry()


@pytest.fixture(scope="module")
def names(registry):
    return registry.names()


@pytest.fixture(scope="module")
def d2_names():
    return [s["name"] for s in d2.TOOLS]


def mint():
    return CONFIRMATION.require("day2_tool.test.authorized_action")


def _extract(resp, key):
    for cand in (resp, resp.get("data") or {}, resp.get("result") or {}):
        if isinstance(cand, dict) and key in cand:
            return cand[key]
    return None


def _check(resp):
    assert isinstance(resp, dict), resp
    assert "status" in resp, resp
    assert "success" in resp, resp
    assert "action" in resp, resp
    assert resp["status"] in VALID_STATUSES, resp
    return resp


def _ok(resp):
    _check(resp)
    assert (
        resp["success"] is True
        or resp.get("status") in ("ok", "AVAILABLE", "EXECUTED", "DONE",
                                  "COMPLETE", "ARMED", "LEARNED", "REPLAYED")
    ), resp
    return resp


def _patch_provider(monkeypatch, provider):
    monkeypatch.setattr(d2, "_provider",
                        lambda name, capability=None: provider)
    return provider


def _patch_engine(monkeypatch, tmp_path, mod, cls, accessor, **override):
    """Route an engine accessor to temp storage by patching its constructor."""
    module = importlib.import_module(mod)
    klass = getattr(module, cls)
    real_init = klass.__init__

    # Engines that receive ``store``/``kv`` positionally in their accessor
    # (e.g. AlertManager(KeyValueStore(...))) would collide with the same
    # value passed as a keyword. Drop positional args that are overridden.
    try:
        sig_params = [
            p.name for p in inspect.signature(real_init).parameters.values()
            if p.name not in ("self", "kwargs", "args")
            and not p.kind in (inspect.Parameter.VAR_POSITIONAL,
                               inspect.Parameter.VAR_KEYWORD)
        ]
    except (TypeError, ValueError):
        sig_params = []

    def _init(self, *a, **kw):
        a = list(a)
        for index, name in enumerate(sig_params):
            if index < len(a) and name in override:
                a[index] = None
        a = [arg for arg in a if arg is not None]
        kw.update({k: v for k, v in override.items() if v is not None})
        real_init(self, *a, **kw)

    monkeypatch.setattr(klass, "__init__", _init)
    getattr(d2, accessor).cache_clear()


def _kv(tmp_path, name):
    return KeyValueStore(str(tmp_path / name))


# Minimal required args for gated tools so the registry reaches the
# confirmation gate instead of failing on missing required params.
GATED_SAMPLE_ARGS = {
    "android_shell": {"command": "echo hi"},
    "iot_remove": {"device_id": "x"},
    "email_provider_send": {"to": "a@example.com", "subject": "s",
                            "body": "b"},
    "message_send": {"to": "a@example.com", "text": "hi"},
    "travel_book": {"trip_id": "trip-1"},
    "action_execute": {"action_id": "rule-1"},
    "finance_transaction_void": {"transaction_id": "t1"},
    "finance_transaction_delete": {"transaction_id": "t1"},
    "shopping_purchase": {"items": "milk", "store": "corner"},
    "services_start": {"service_id": "api"},
    "services_stop": {"service_id": "api"},
    "mission_cancel": {"mission_id": "m1"},
    "workflow_abort": {"workflow_id": "wf-1"},
    "access_revoke": {"scope": "docs", "action": "write",
                      "principal": "alex"},
    "privacy_erasure": {"scope": "alex"},
    "contingency_execute": {"trigger": "api down"},
    "robot_execute": {"axis": "joint1", "target_deg": 10},
    "robot_replay": {"name": "wave"},
    "robot_arm": {},
    "backup_restore": {"snapshot_id": "snap-1", "target_dir": "restore-out"},
    "cyber_scan": {"target": "localhost", "tool": "dns"},
}


# ---------------------------------------------------------------------------
# Registry / schema integrity
# ---------------------------------------------------------------------------

def test_all_day2_tools_registered(registry, d2_names):
    miss = [n for n in d2_names if not registry.has(n)]
    assert miss == []


def test_specs_complete(registry, d2_names):
    seen = set()
    for spec in d2.TOOLS:
        assert spec["name"] not in seen, f"duplicate tool {spec['name']}"
        seen.add(spec["name"])
        assert spec["name"] in d2_names
        for key in ("risk", "category", "description", "function"):
            assert key in spec, spec["name"]
        assert spec["risk"] in ("safe", "low", "medium", "high", "destructive")
        assert callable(spec["function"])
        for p in spec["parameters"]:
            assert p["name"] not in ("confirmed", "trusted", "request_id",
                                     "_cleared"), spec["name"]
            assert p["hint"] in ("", "int", "float", "bool"), p
            assert isinstance(p["required"], bool)
        tool = registry.get(spec["name"])
        assert tool is not None
        assert tool.available is True
        assert tool.schema()["risk"] is not None


def test_full_registry_has_no_duplicates(registry):
    assert len(registry.names()) == len(set(registry.names()))


def test_every_day2_tool_has_valid_schema_in_registry(registry, d2_names):
    for name in d2_names:
        schema = registry.describe(name)
        assert "parameters" in schema
        for p in schema["parameters"]:
            assert p["name"]
            assert "required" in p


# ---------------------------------------------------------------------------
# Gating: every high/destructive risk tool requires confirmation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name",
    [s["name"] for s in d2.TOOLS
     if s["risk"] in ("high", "destructive")],
    ids=lambda n: n,
)
def test_high_risk_tools_deny_without_confirmation(registry, name):
    resp = registry.invoke(name, **GATED_SAMPLE_ARGS.get(name, {}))
    _check(resp)
    assert resp["status"] in ("confirm_required", "denied"), resp


@pytest.mark.parametrize(
    "name",
    [s["name"] for s in d2.TOOLS
     if s["risk"] in ("high", "destructive")],
    ids=lambda n: n,
)
def test_high_risk_tools_run_with_confirmation(registry, name, monkeypatch):
    req = CONFIRMATION.require(f"test.gate.{name}")
    resp = registry.invoke(name, confirmed=True, trusted=True, request_id=req,
                           **GATED_SAMPLE_ARGS.get(name, {}))
    _check(resp)
    assert resp["status"] not in ("confirm_required", "denied"), resp


# ---------------------------------------------------------------------------
# Provider routing — hermetic provider instances (no real data dirs)
# ---------------------------------------------------------------------------

def test_finance_provider_flow(registry, tmp_path, monkeypatch):
    from core.providers.finance_provider import FinanceProvider
    prov = FinanceProvider(kv_path=str(tmp_path / "finance.json"),
                           output_dir=str(tmp_path / "out"))
    _patch_provider(monkeypatch, prov)

    _ok(registry.invoke("finance_transaction_add", date="2026-09-01",
                        amount=12.5, type="expense", note="lunch",
                        category="food", confirmed=True, trusted=True,
                        request_id=mint()))
    listing = _check(registry.invoke("finance_transaction_list",
                                     month="2026-09"))
    assert _extract(listing, "count") is not None or len(listing) > 0
    _ok(registry.invoke("finance_budget_set", category="food", limit=500,
                        month="2026-09", confirmed=True, trusted=True,
                        request_id=mint()))
    _check(registry.invoke("finance_budget_status", month="2026-09"))
    _check(registry.invoke("finance_portfolio"))
    _ok(registry.invoke("finance_investment_add", symbol="AAPL",
                        confirmed=True, trusted=True, request_id=mint()))
    _check(registry.invoke("finance_report", month="2026-09"))


def test_shopping_provider_flow(registry, tmp_path, monkeypatch):
    from core.providers.shopping_provider import ShoppingProvider
    prov = ShoppingProvider(kv_path=str(tmp_path / "shopping.json"))
    _patch_provider(monkeypatch, prov)
    _ok(registry.invoke("shopping_list_create", list_name="groceries"))
    _ok(registry.invoke("shopping_list_add", list_name="groceries",
                        name="milk", qty=2, priority="high"))
    _ok(registry.invoke("shopping_price_memo", item="milk",
                        store="corner", price=3.5))
    _check(registry.invoke("shopping_compare", store="corner"))
    _check(registry.invoke("shopping_purchase", items="milk", store="corner",
                           confirmed=True, trusted=True, request_id=mint()))


def test_iot_provider_flow(registry, tmp_path, monkeypatch):
    from core.providers.iot_provider import IoTProvider
    prov = IoTProvider(kv=_kv(tmp_path, "iot.json"))
    _patch_provider(monkeypatch, prov)
    _check(registry.invoke("iot_provider_status"))
    _ok(registry.invoke("iot_register", device_id="lamp1", kind="light",
                        simulated=True))
    _ok(registry.invoke("iot_set_state", device_id="lamp1", state="on"))
    _check(registry.invoke("iot_list"))
    _check(registry.invoke("iot_remove", device_id="lamp1",
                           confirmed=True, trusted=True, request_id=mint()))


def test_home_provider_flow(registry, tmp_path, monkeypatch):
    from core.providers.home_provider import HomeProvider
    prov = HomeProvider(kv=_kv(tmp_path, "home.json"))
    _patch_provider(monkeypatch, prov)
    _check(registry.invoke("home_status"))
    _check(registry.invoke("home_routines"))
    _check(registry.invoke("home_run_routine", routine_name="morning"))
    _check(registry.invoke("home_energy_estimate", items="lamp:5"))


def test_location_provider_flow(registry, tmp_path, monkeypatch):
    from core.providers.location_provider import LocationProvider
    prov = LocationProvider(kv=_kv(tmp_path, "location.json"))
    _patch_provider(monkeypatch, prov)
    _ok(registry.invoke("location_set", name="home", lat=40.0, lon=-74.0))
    _check(registry.invoke("location_get", name="home"))
    _ok(registry.invoke("distance", lat1=40.0, lon1=-74.0,
                        lat2=40.1, lon2=-74.2, unit="km"))
    _check(registry.invoke("location_geocode", query="union square"))
    _check(registry.invoke("location_status"))


def test_navigation_provider_flow(registry, tmp_path, monkeypatch):
    from core.providers.navigation_provider import NavigationProvider
    prov = NavigationProvider(kv=_kv(tmp_path, "navigation.json"))
    _patch_provider(monkeypatch, prov)
    _check(registry.invoke("route_plan", origin="a", destination="b"))
    _check(registry.invoke("route_eta", origin="a", destination="b"))


def test_vehicle_provider_flow(registry, tmp_path, monkeypatch):
    from core.providers.vehicle_provider import VehicleProvider
    prov = VehicleProvider(kv=_kv(tmp_path, "vehicle.json"))
    _patch_provider(monkeypatch, prov)
    _check(registry.invoke("vehicle_status"))
    _ok(registry.invoke("vehicle_registration", reg="ABC123", make="honda"))
    _ok(registry.invoke("vehicle_maintenance_log", reg="ABC123",
                        service_type="oil", cost=120.0))
    _check(registry.invoke("vehicle_reminders", reg="ABC123"))


def test_travel_provider_flow(registry, tmp_path, monkeypatch):
    from core.providers.travel_provider import TravelProvider
    prov = TravelProvider(kv=_kv(tmp_path, "travel.json"))
    _patch_provider(monkeypatch, prov)
    _ok(registry.invoke("travel_plan", destinations="paris", budget=2000))
    trip_id = None
    listing = _check(registry.invoke("travel_itinerary", trip_id="auto"))
    assert listing is not None
    _check(registry.invoke("travel_book", trip_id="trip-1",
                           confirmed=True, trusted=True, request_id=mint()))


def test_world_actions_provider_flow(registry, tmp_path, monkeypatch):
    from core.providers.world_actions import WorldActionsProvider
    prov = WorldActionsProvider(kv=_kv(tmp_path, "actions.json"))
    _patch_provider(monkeypatch, prov)
    _ok(registry.invoke("action_create", name="water plants",
                        action_type="simulated"))
    _check(registry.invoke("action_dry_run", action_id="rule-1"))
    _check(registry.invoke("action_execute", action_id="rule-1",
                           confirmed=True, trusted=True, request_id=mint()))
    _check(registry.invoke("action_status"))


def test_browser_provider_flow(registry, tmp_path, monkeypatch):
    from core.providers.browser_provider import BrowserProvider
    prov = BrowserProvider(kv_path=str(tmp_path / "browser.json"))
    _patch_provider(monkeypatch, prov)
    _check(registry.invoke("browser_provider_status"))
    _ok(registry.invoke("browser_bookmark_add", url="https://example.com",
                        title="example", tags="web"))
    _check(registry.invoke("browser_bookmark_list"))
    _check(registry.invoke("browser_bookmark_search", keyword="example"))
    _check(registry.invoke("browser_provider_search", query="hello"))


def test_vision_provider_flow(registry, tmp_path, monkeypatch):
    from core.providers.vision_provider import VisionProvider
    image = tmp_path / "pic.png"
    from PIL import Image
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(str(image))
    prov = VisionProvider()
    _patch_provider(monkeypatch, prov)
    _ok(registry.invoke("vision_metadata", image_path=str(image)))
    _check(registry.invoke("vision_coordinates", image_path=str(image)))
    _check(registry.invoke("vision_analyze", image_path=str(image)))


def test_media_gen_provider_flow(registry, tmp_path, monkeypatch):
    from core.providers.media_gen import ImageGenProvider, VideoGenProvider

    class _Both:
        def execute(self, capability, **kw):
            if capability in ("image_generate",):
                return ImageGenProvider(
                    settings={"IMAGE_GENERATION_PROVIDER": "canvas"},
                    output_root=str(tmp_path)).execute(capability, **kw)
            return VideoGenProvider(output_root=str(tmp_path)).execute(
                capability, **kw)

    _patch_provider(monkeypatch, _Both())
    _ok(registry.invoke("image_generate", prompt="sunset", width=16,
                        height=16))
    job = _check(registry.invoke("video_generate", prompt="story"))
    _check(registry.invoke("video_status", job_id="job-1"))
    _check(registry.invoke("video_cancel", job_id="job-1"))


def test_camera_permission_grant(registry, tmp_path, monkeypatch):
    from core.providers.camera_provider import CameraProvider
    camera_path = str(tmp_path / "camera.json")
    prov = CameraProvider(kv_path=camera_path)
    _patch_provider(monkeypatch, prov)
    _ok(registry.invoke("camera_permission_grant"))
    fresh = KeyValueStore(camera_path)
    assert fresh.get("permissions.camera_access") == "granted"


def test_android_provider_honest_unconfigured(registry, tmp_path,
                                              monkeypatch):
    from core.providers.android_provider import AndroidProvider
    _patch_provider(monkeypatch, AndroidProvider())
    resp = _check(registry.invoke("android_provider_status"))
    assert resp["status"] in ("NOT_CONFIGURED", "AVAILABLE", "UNAVAILABLE",
                              "FAILED"), resp
    _check(registry.invoke("android_devices"))
    _check(registry.invoke("android_shell", command="echo hi",
                           confirmed=True, trusted=True, request_id=mint()))


def test_communication_provider_flow(registry, tmp_path, monkeypatch):
    from core.providers.communication_provider import CommunicationProvider
    prov = CommunicationProvider(kv=_kv(tmp_path, "comm.json"))
    _patch_provider(monkeypatch, prov)
    _check(registry.invoke("email_templates", action="list"))
    _check(registry.invoke("email_compose", template="welcome",
                           recipient="a@example.com"))
    _ok(registry.invoke("email_provider_draft", recipient="a@example.com",
                        subject="hi", body="hello"))
    _check(registry.invoke("message_draft", message="hi",
                           recipient="a@example.com"))
    _check(registry.invoke("email_provider_send", to="a@example.com",
                           subject="hi", body="hello", confirmed=True,
                           trusted=True, request_id=mint()))
    _check(registry.invoke("message_send", to="a@example.com", text="hi",
                           confirmed=True, trusted=True, request_id=mint()))


# ---------------------------------------------------------------------------
# Engine flows — hermetic temp stores
# ---------------------------------------------------------------------------

def test_missions_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.missions", "MissionsEngine",
                  "_engine_missions", path=str(tmp_path / "missions.json"))
    created = _ok(registry.invoke("mission_create", title="cleanup",
                                  steps="plan,do,verify"))
    mid = _extract(created, "mission_id")
    assert mid is not None, created
    _ok(registry.invoke("mission_start", mission_id=mid))
    _check(registry.invoke("mission_status", mission_id=mid))
    _check(registry.invoke("mission_steps", mission_id=mid))
    _check(registry.invoke("mission_pause", mission_id=mid))
    _check(registry.invoke("mission_resume", mission_id=mid))
    _check(registry.invoke("mission_finish", mission_id=mid))
    _check(registry.invoke("mission_archive", mission_id=mid))


def test_workflows_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.workflows", "WorkflowEngine",
                  "_engine_goals", path=str(tmp_path / "workflows.json"))
    _ok(registry.invoke("workflow_define", name="onboarding",
                        steps="date_time,system_info"))
    _check(registry.invoke("workflow_templates"))
    listing = _check(registry.invoke("workflow_status",
                                     workflow_id="wf-1"))
    assert listing is not None


def test_skills_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.skill_builder", "SkillStore",
                  "_engine_skills", path=str(tmp_path / "skills.json"))
    _ok(registry.invoke("skill_define", name="summarize",
                        procedure="date_time;system_info"))
    _check(registry.invoke("skill_invoke", skill_name="summarize",
                           arguments={}, confirmed=True,
                           trusted=True, request_id=mint()))
    _check(registry.invoke("skill_list"))
    _check(registry.invoke("skill_verify", skill_name="summarize",
                           evidence="worked"))


def test_context_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.context_engine",
                  "ContextEngine", "_engine_context",
                  path=str(tmp_path / "context.json"))
    _ok(registry.invoke("context_event_push", text="user wants python"))
    _ok(registry.invoke("context_focus", topics="python"))
    _check(registry.invoke("context_query", query="python"))
    _check(registry.invoke("context_summary", limit=5))


def test_world_state_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.world_state", "WorldState",
                  "_engine_world", path=str(tmp_path / "world.json"))
    _ok(registry.invoke("world_state_set", name="apartment",
                        attributes="floor:3"))
    _ok(registry.invoke("world_state_update", name="apartment",
                        key="light", value="on"))
    _check(registry.invoke("world_state_query", conditions="floor"))
    _check(registry.invoke("world_state_project", name="apartment",
                           attribute="light", dt_hours=1.0))
    _check(registry.invoke("world_state_consistency"))


def test_experience_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.experience",
                  "ExperienceVault", "_engine_experience",
                  path=str(tmp_path / "exp.json"))
    _ok(registry.invoke("experience_record", trigger="server down",
                        action="restart", outcome="success", reward=1.0))
    _check(registry.invoke("experience_similar", trigger="server down"))
    _check(registry.invoke("experience_lessons", topic="restart"))


def test_decisions_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.decisions", "DecisionEngine",
                  "_engine_decisions", path=str(tmp_path / "dec.json"))
    _ok(registry.invoke("decision_criteria_add", name="cost", weight=0.6))
    _ok(registry.invoke("decision_option_add", name="A", scores="cost:8"))
    _check(registry.invoke("decision_evaluate"))
    _check(registry.invoke("decision_pros_cons", topic="hire",
                           pros="fast", cons="risky"))


def test_anomaly_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.anomaly", "AnomalyEngine",
                  "_engine_anomaly", path=str(tmp_path / "anomaly.json"))
    for v in (1, 2, 1, 3, 2, 50):
        _ok(registry.invoke("anomaly_ingest", series_id="cpu", value=v))
    _check(registry.invoke("anomaly_detect", series_id="cpu"))
    _check(registry.invoke("anomaly_report", series_id="cpu"))
    _ok(registry.invoke("anomaly_set_bounds", series_id="cpu", min_value=0,
                        max_value=100))


def test_alerts_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.alerts", "AlertManager",
                  "_engine_alerts",
                  store=KeyValueStore(str(tmp_path / "alerts.json")))
    _ok(registry.invoke("alert_create", severity="high", title="disk full",
                        message="90% used", source="health"))
    _check(registry.invoke("alert_list", severity="high"))
    alert_list = _check(registry.invoke("alert_active"))
    alert_id = _extract(alert_list, "alert_id") or _extract(alert_list, "id")
    if alert_id is None:
        listing = _check(registry.invoke("alert_list"))
        alert_id = _extract(listing, "alert_id") or _extract(listing, "id")
    if alert_id is not None:
        _check(registry.invoke("alert_ack", alert_id=alert_id))
        _check(registry.invoke("alert_close", alert_id=alert_id))


def test_knowledge_graph_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.knowledge_graph",
                  "KnowledgeGraph", "_engine_graph",
                  store=KeyValueStore(str(tmp_path / "graph.json")))
    _ok(registry.invoke("graph_node_add", node_id="a"))
    _ok(registry.invoke("graph_node_add", node_id="b"))
    _ok(registry.invoke("graph_edge_add", src="a", dst="b", relation="next"))
    _check(registry.invoke("graph_neighbors", node_id="a"))
    _check(registry.invoke("graph_path", start="a", end="b"))
    _check(registry.invoke("graph_summary"))


def test_assimilation_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.assimilation",
                  "AssimilationEngine", "_engine_assim",
                  store=KeyValueStore(str(tmp_path / "assim.json")))
    _ok(registry.invoke("knowledge_triple", subject="water",
                        predicate="boils_at", object="100c",
                        source_id="s1"))
    report = _check(registry.invoke("knowledge_ingest",
                                    text="cats are animals",
                                    source_id="s2"))
    assert report is not None
    _check(registry.invoke("knowledge_conflicts"))


def test_fact_check_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.fact_check", "FactChecker",
                  "_engine_facts")
    _check(registry.invoke("fact_check", claim="earth is round"))
    _check(registry.invoke("fact_cross_check", sources="a;b"))


def test_memory_lifecycle_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.memory_lifecycle",
                  "MemoryLifecycle", "_engine_lifecycle",
                  kv_path=str(tmp_path / "lifecycle.json"),
                  db_path=str(tmp_path / "arven_memory_test.db"))
    _check(registry.invoke("memory_age", decay_rate=0.5))
    _check(registry.invoke("memory_forget_candidates", threshold=1))
    _ok(registry.invoke("memory_protect", memory_id=999))
    _check(registry.invoke("memory_merge_suggest", threshold=0.9))


def test_meetings_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.meetings", "MeetingManager",
                  "_engine_meetings", kv_path=str(tmp_path / "meetings.json"),
                  output_root=str(tmp_path / "out"))
    created = _ok(registry.invoke("meeting_create", title="standup",
                                  agenda="sync"))
    mid = _extract(created, "mid") or _extract(created, "meeting_id")
    assert mid is not None, created
    _ok(registry.invoke("meeting_topic_add", mid=mid, title="release"))
    _ok(registry.invoke("meeting_decision_add", mid=mid, text="ship friday"))
    _ok(registry.invoke("meeting_action_item_add", mid=mid, owner="alex",
                        due_iso="2026-09-10", text="prepare notes"))
    _ok(registry.invoke("meeting_capture", mid=mid, speaker="alex",
                        text="we are on track"))
    _ok(registry.invoke("meeting_participant_register", name="alex",
                        role="lead"))
    _check(registry.invoke("meeting_participants"))
    _check(registry.invoke("conversation_turn", mid=mid,
                           active_participant="alex"))
    _check(registry.invoke("conversation_state", mid=mid))
    _check(registry.invoke("meeting_minutes", mid=mid))
    _check(registry.invoke("meeting_export", mid=mid, format="md"))


def test_affect_flow(registry):
    _ok(registry.invoke("affect_observe", speaker="alex",
                        text="this is great"))
    _check(registry.invoke("affect_mood"))
    _check(registry.invoke("affect_tone", intent="comfort"))


def test_speech_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.speech",
                  "SpeakerRecognition", "_engine_speaker",
                  kv_path=str(tmp_path / "speakers.json"))
    enroll = registry.invoke("speaker_enroll", speaker_id="alex",
                             audio="samples/alex.wav", consent=True)
    assert enroll["status"] in ("AVAILABLE", "ok", "FAILED"), enroll
    if enroll["status"] in ("AVAILABLE", "ok"):
        _check(registry.invoke("speaker_list"))
        rec = _check(registry.invoke("speaker_recognize",
                                     audio="samples/alex.wav"))
        assert rec.get("authorized") is False or "authorized" not in rec, rec


def test_language_flow(registry):
    _check(registry.invoke("language_detect", text="bonjour le monde"))
    _check(registry.invoke("language_set", name="fr", force=True))


def test_advisor_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.advisor", "AdvisorRegistry",
                  "_engine_advisors",
                  kv_path=str(tmp_path / "advisors.json"))
    d2._engine_advisor.cache_clear()
    _check(registry.invoke("interaction_plan", role="friend", topic="health"))
    _check(registry.invoke("interaction_followups"))
    _check(registry.invoke("tutor_curriculum", topic="python", lessons=3))
    _check(registry.invoke("tutor_assess", answers="a,b,c"))
    _check(registry.invoke("career_gap", target_role="engineer",
                           current_skills="python"))
    _check(registry.invoke("career_interview_prep", target_role="engineer"))
    _check(registry.invoke("relationship_checkin", contact="mom",
                           date_iso="2026-09-08"))
    _check(registry.invoke("relationship_patterns"))
    _check(registry.invoke("coach_draft", tone="friendly", audience="team",
                           points="ship it"))
    _check(registry.invoke("coach_tone_check", text="please review"))
    _check(registry.invoke("coach_speaking_tips"))


def test_access_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.access", "PermissionManager",
                  "_engine_access", kv_path=str(tmp_path / "access.json"))
    _ok(registry.invoke("access_grant", scope="docs", action="write",
                        principal="alex", ttl_days=7))
    _check(registry.invoke("access_check", scope="docs", action="write",
                           principal="alex"))
    _check(registry.invoke("access_report"))
    _check(registry.invoke("access_revoke", scope="docs", action="write",
                           principal="alex", confirmed=True, trusted=True,
                           request_id=mint()))


def test_privacy_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.privacy", "PrivacyPortal",
                  "_engine_privacy", kv_path=str(tmp_path / "privacy.json"),
                  output_root=str(tmp_path / "out"))
    _check(registry.invoke("privacy_inventory"))
    _ok(registry.invoke("privacy_consent", user="alex", purpose="analytics",
                        granted=True))
    _check(registry.invoke("privacy_export", user="alex"))
    _check(registry.invoke("privacy_report"))
    _check(registry.invoke("privacy_erasure", scope="alex",
                           confirmed=True, trusted=True, request_id=mint()))


def test_reports_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.reports", "ReportBuilder",
                  "_engine_reports",
                  kv=KeyValueStore(str(tmp_path / "reports.json")),
                  output_dir=str(tmp_path / "out"))
    _ok(registry.invoke("report_section_add", title="Intro", body="hi",
                        name="mon"))
    _check(registry.invoke("report_render", name="mon", title="Monthly"))
    _check(registry.invoke("report_export", name="mon"))


def test_collaboration_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.collaboration", "CollabBoard",
                  "_engine_board",
                  kv=KeyValueStore(str(tmp_path / "board.json")))
    created = _ok(registry.invoke("board_create", name="sprint",
                                  columns="todo,done"))
    bid = _extract(created, "board_id") or _extract(created, "id")
    assert bid is not None, created
    card = _ok(registry.invoke("board_card_add", board_id=bid, title="task",
                               priority="high", assignee="alex"))
    cid = _extract(card, "card_id") or _extract(card, "id")
    _check(registry.invoke("board_card_move", card_id=cid, column="done"))
    _check(registry.invoke("board_summary", board_id=bid))
    _check(registry.invoke("board_mentions",
                           text="please @alex review"))


def test_escalation_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.escalation",
                  "EscalationManager", "_engine_escalation",
                  kv=KeyValueStore(str(tmp_path / "esc.json")))
    created = _ok(registry.invoke("escalate", request="access denied",
                                  to="admin", priority="high"))
    eid = _extract(created, "escalation_id") or _extract(created, "id")
    assert eid is not None, created
    _check(registry.invoke("escalation_handoff", escalation_id=eid))
    _check(registry.invoke("escalation_resolve", escalation_id=eid,
                           resolution="fixed"))
    _check(registry.invoke("escalation_remind"))


def test_simulation_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.simulation",
                  "SimulationEngine", "_engine_simulation",
                  kv=KeyValueStore(str(tmp_path / "sim.json")),
                  output_dir=str(tmp_path / "out"))
    _check(registry.invoke("simulation_run", name="growth", steps=5,
                           params="rate:0.1"))
    _check(registry.invoke("simulation_sensitivity", name="growth",
                           param="rate", values="0.1;0.2;0.3"))
    _check(registry.invoke("simulation_report", name="growth"))


def test_boss_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.boss_model", "BossModel",
                  "_engine_boss", kv=KeyValueStore(str(tmp_path / "boss.json")))
    _check(registry.invoke("boss_facts"))
    _check(registry.invoke("boss_consult", question="should we ship?"))
    _ok(registry.invoke("boss_set_preference", name="cadence",
                        value="weekly", consented=True))


def test_architecture_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.architecture",
                  "ArchitectureAuditor", "_engine_arch",
                  kv=KeyValueStore(str(tmp_path / "arch.json")),
                  root=str(tmp_path))
    _check(registry.invoke("arch_census"))
    _check(registry.invoke("arch_graph"))
    _check(registry.invoke("arch_contract_audit"))
    _check(registry.invoke("arch_growth"))


def test_life_os_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.life_os", "LifeOS",
                  "_engine_lifeos", kv=KeyValueStore(str(tmp_path / "life.json")))
    _check(registry.invoke("life_checklist", domain="health"))
    _ok(registry.invoke("life_ritual_add", domain="health", ritual="walk"))
    _ok(registry.invoke("life_satisfaction_track", domain="health", score=8))
    _check(registry.invoke("life_review", week_iso="2026-09-06"))


def test_events_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.events", "EventsCalendar",
                  "_engine_events", kv=KeyValueStore(str(tmp_path / "ev.json")))
    _ok(registry.invoke("event_add", title="review", date_iso="2026-09-10",
                        reminder_offset_min=30))
    _check(registry.invoke("event_upcoming", days=7))
    _check(registry.invoke("event_reminders"))
    _check(registry.invoke("event_conflicts", date="2026-09-10"))
    _check(registry.invoke("event_export"))


def test_project_memory_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.project_memory",
                  "ProjectVault", "_engine_vault",
                  kv=KeyValueStore(str(tmp_path / "proj.json")))
    _ok(registry.invoke("project_create", name="arven", phases="build,test"))
    _ok(registry.invoke("project_checkin", name="arven", phase_id="build",
                        note="done wiring"))
    _check(registry.invoke("project_status", name="arven"))
    _ok(registry.invoke("project_risk_update", name="arven",
                        title="regression", likelihood=4, impact=3))


def test_contingency_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.contingency",
                  "ContingencyPlanner", "_engine_contingency",
                  kv=KeyValueStore(str(tmp_path / "cont.json")))
    _ok(registry.invoke("contingency_impact", change="move to v2",
                        affected="api", likelihood=3, severity=4))
    _ok(registry.invoke("contingency_plan", trigger="api down",
                        actions="restart"))
    plan = _check(registry.invoke("contingency_dry_run", plan="fallback"))
    assert plan is not None
    _check(registry.invoke("contingency_execute", trigger="api down",
                           confirmed=True, trusted=True, request_id=mint()))


def test_command_center_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.command_center",
                  "CommandCenter", "_engine_command",
                  kv=KeyValueStore(str(tmp_path / "cmd.json")),
                  workspace_root=str(tmp_path))
    _check(registry.invoke("dashboard"))
    _check(registry.invoke("health_rollup"))
    _ok(registry.invoke("set_flag", name="maintenance", value="false"))


def test_multimodal_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.multimodal",
                  "MultimodalInput", "_engine_multimodal",
                  kv=KeyValueStore(str(tmp_path / "multi.json")))
    _ok(registry.invoke("multimodal_ingest", turn="text:hello world"))
    _check(registry.invoke("multimodal_recent", n=3))


def test_robot_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.robot", "RobotController",
                  "_engine_robot", kv=KeyValueStore(str(tmp_path / "rob.json")))
    _check(registry.invoke("robot_envelope"))
    _check(registry.invoke("robot_plan", axis="joint1", target_deg=45))
    _check(registry.invoke("robot_collision", axes="joint1:0"))
    _check(registry.invoke("robot_home"))
    _check(registry.invoke("robot_arm", confirmed=True, trusted=True,
                           request_id=mint()))
    _check(registry.invoke("robot_execute", axis="joint1", target_deg=10,
                           confirmed=True, trusted=True, request_id=mint()))
    _ok(registry.invoke("robot_teach", name="wave",
                        sequence="joint1:0"))
    _check(registry.invoke("robot_replay", name="wave", confirmed=True,
                           trusted=True, request_id=mint()))
    _check(registry.invoke("robot_skills"))
    _check(registry.invoke("robot_disarm"))


def test_engineering_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.engineering",
                  "EngineeringProjects", "_engine_engineering",
                  kv=KeyValueStore(str(tmp_path / "eng.json")),
                  output_dir=str(tmp_path / "out"))
    _ok(registry.invoke("eng_spec_create", name="widget",
                        requirements="r1,r2", interfaces="i1"))
    _check(registry.invoke("eng_sprint_board"))
    _ok(registry.invoke("eng_task_add", name="widget", title="build it",
                        assignee="alex", est_hours=2.0))
    _ok(registry.invoke("eng_measure_log", name="widget", metric="weight",
                        value=1.5, unit="kg"))
    _check(registry.invoke("eng_export", name="widget"))


def test_inventory_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.supply_chain",
                  "InventoryManager", "_engine_inventory",
                  path=str(tmp_path / "inv.json"))
    _check(registry.invoke("inventory_status"))
    _ok(registry.invoke("inventory_item_add", sku="A1", name="widget",
                        qty=10, min_qty=2, cost=5.0))
    _ok(registry.invoke("inventory_receive", sku="A1", qty=5, ref="in1"))
    _ok(registry.invoke("inventory_issue", sku="A1", qty=3, ref="out1"))
    _ok(registry.invoke("inventory_adjust", sku="A1", delta=1,
                        reason="count"))
    _check(registry.invoke("inventory_reorder"))
    _check(registry.invoke("inventory_stock_value"))
    _check(registry.invoke("inventory_audit"))


def test_services_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.services",
                  "ServiceOrchestrator", "_engine_services",
                  path=str(tmp_path / "svc.json"))
    _check(registry.invoke("services_status"))
    _ok(registry.invoke("services_register", service_id="api", version="1.0"))
    _check(registry.invoke("services_health", service_id="api"))
    _check(registry.invoke("services_start", service_id="api",
                           confirmed=True, trusted=True, request_id=mint()))
    _check(registry.invoke("services_stop", service_id="api",
                           confirmed=True, trusted=True, request_id=mint()))
    _check(registry.invoke("services_degraded"))


def test_continuity_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.missions", "MissionsEngine",
                  "_engine_missions", path=str(tmp_path / "missions.json"))
    _patch_engine(monkeypatch, tmp_path, "core.continuity",
                  "ContinuityManager", "_engine_continuity",
                  path=str(tmp_path / "continuity.json"))
    created = _ok(registry.invoke("mission_create", title="long mission",
                                  steps="a,b"))
    mid = _extract(created, "mission_id")
    assert mid is not None, created
    _check(registry.invoke("continuity_snapshot", mission_id=mid))
    _check(registry.invoke("continuity_resume"))
    _check(registry.invoke("continuity_orphans"))


# ---------------------------------------------------------------------------
# Feature 47 — Autonomous Coding & Build Agent
# ---------------------------------------------------------------------------

def _resp_list(resp):
    data = resp if isinstance(resp, list) else resp.get("result") or resp.get("data") or []
    return data if isinstance(data, list) else []


def test_build_agent_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.build_agent",
                  "PipelineRunner", "_engine_pipeline",
                  output_root=str(tmp_path / "out"))
    valid = _ok(registry.invoke(
        "build_validate",
        stages='[{"id": 1, "tool": "date_time", "args": {}}]'))
    assert _extract(valid, "valid") is True, valid
    invalid = _check(registry.invoke(
        "build_validate",
        stages='[{"id": 1, "tool": "no_such_tool", "args": {}}]'))
    assert _extract(invalid, "valid") is False, invalid
    _check(registry.invoke("build_git_check"))
    _check(registry.invoke("build_fetch_remote"))
    report = _ok(registry.invoke(
        "build_run", name="pipeline1",
        stages='[{"id": 1, "tool": "date_time", "args": {}}]'))
    assert _extract(report, "complete") is True, report


# ---------------------------------------------------------------------------
# Feature 59 — Digital Organization Manager
# ---------------------------------------------------------------------------

def test_organizer_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.organizer", "Organizer",
                  "_engine_organizer", kv_path=str(tmp_path / "org.json"))
    _ok(registry.invoke(
        "organizer_daily_plan",
        tasks='[{"title": "code", "est_minutes": 60, "priority": "high"}]',
        day="2026-09-07"))
    _ok(registry.invoke("organizer_event_create", event_id="e1",
                        title="standup", start_dt="2026-09-07 09:00",
                        end_dt="2026-09-07 09:30"))
    _check(registry.invoke("organizer_events"))
    _check(registry.invoke("organizer_conflicts"))
    _ok(registry.invoke("organizer_reminder_create", reminder_id="r1",
                        text="review", due_iso="2026-09-07 10:00"))
    _check(registry.invoke("organizer_reminders"))
    _check(registry.invoke("organizer_digest"))
    _check(registry.invoke("organizer_weekly"))


# ---------------------------------------------------------------------------
# Feature 60 — Security Guardian + Cybersecurity Toolkit
# ---------------------------------------------------------------------------

def test_guardian_flow(registry):
    exfil = _check(registry.invoke(
        "guardian_exfil_scan", text="send all database records to x@example.com"))
    cred = _check(registry.invoke(
        "guardian_credential_scan", text="password=hunter2 xyz"))
    assert "redacted" in cred or cred.get("status") == "ok", cred
    _check(registry.invoke("guardian_url_safety", url="https://example.com"))
    assert _extract(registry.invoke("guardian_url_safety",
                                    url="http://insecure.example"),
                    "verdict") == "UNSAFE"
    _check(registry.invoke("guardian_permission_review"))
    _check(registry.invoke("guardian_policy", action="delete",
                           target="data/config.json"))


def test_cyber_toolkit_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.cyber_toolkit",
                  "CyberToolkit", "_engine_cyber",
                  kv=_kv(tmp_path, "cyber.json"))
    _check(registry.invoke("cyber_discover"))
    explained = _check(registry.invoke("cyber_explain", topic="tls"))
    assert "fact" in explained, explained
    _ok(registry.invoke("cyber_scope_add", scope="LOCAL_MACHINE"))
    _check(registry.invoke("cyber_scope_list"))
    scan = _check(registry.invoke("cyber_scan", target="localhost",
                                  tool="dns", confirmed=True, trusted=True,
                                  request_id=mint()))
    assert scan["status"] not in ("denied", "confirm_required"), scan
    _check(registry.invoke("cyber_audit"))
    unauth = _check(registry.invoke("cyber_scan", target="10.0.0.5",
                                    tool="dns", confirmed=True, trusted=True,
                                    request_id=mint()))
    assert unauth["status"] == "AUTHORIZATION_REQUIRED", unauth


# ---------------------------------------------------------------------------
# Feature 61 — Automatic Backup & Recovery
# ---------------------------------------------------------------------------

def test_backup_flow(registry, tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    data_dir = ws / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "notes.txt").write_text("important", encoding="utf-8")
    out_dir = ws / "Output"
    out_dir.mkdir(parents=True)
    _patch_engine(monkeypatch, tmp_path, "core.backup", "BackupManager",
                  "_engine_backup",
                  workspace_root=str(ws), output_root=str(out_dir))
    _check(registry.invoke("backup_classify", path="data/notes.txt"))
    _ok(registry.invoke("backup_snapshot", label="daily"))
    listing = _check(registry.invoke("backup_list"))
    snaps = _resp_list(listing)
    assert snaps and snaps[0]["id"], listing
    snap_id = snaps[0]["id"]
    verify = _check(registry.invoke("backup_verify", snapshot_id=snap_id))
    assert _extract(verify, "verified") is True, verify
    _check(registry.invoke("backup_rotate", keep=2))
    target = tmp_path / "restored"
    restored = _check(registry.invoke(
        "backup_restore", snapshot_id=snap_id, target_dir=str(target),
        confirmed=True, trusted=True, request_id=mint()))
    assert restored["status"] not in ("denied", "confirm_required"), restored
    assert (target / "data" / "notes.txt").is_file()


# ---------------------------------------------------------------------------
# Feature 62 — Autonomous Testing & QA Agent
# ---------------------------------------------------------------------------

def test_qa_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.qa_engine", "QARunner",
                  "_engine_qa", workspace_root=str(tmp_path))
    source = tmp_path / "sample.py"
    source.write_text(
        "def add(a, b):\n    # TODO finish\n    return a + b\n",
        encoding="utf-8")
    syntax = _check(registry.invoke("qa_syntax", path=str(source)))
    assert _extract(syntax, "ok") is True, syntax
    _check(registry.invoke("qa_imports", path=str(source)))
    _check(registry.invoke("qa_style", path=str(source)))
    _check(registry.invoke("qa_todos", path=str(tmp_path)))
    _check(registry.invoke("qa_pytest", target=str(tmp_path / "nope.py")))
    report = _check(registry.invoke("qa_report", path=str(source)))
    assert _extract(report, "overall") in ("PASS", "FAIL"), report


# ---------------------------------------------------------------------------
# Feature 63 — Self-Diagnostics & Self-Healing
# ---------------------------------------------------------------------------

def test_diagnostics_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.diagnostics", "Diagnostics",
                  "_engine_diagnostics", workspace_root=str(tmp_path))
    snap = _check(registry.invoke("diagnostics_run"))
    assert any(k in ("disk", "cpu", "memory", "core_health")
               for k in snap), snap
    _check(registry.invoke("diagnostics_report"))


# ---------------------------------------------------------------------------
# Feature 64 — Performance Optimizer
# ---------------------------------------------------------------------------

def test_performance_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.performance", "Profiler",
                  "_engine_profiler", kv_path=str(tmp_path / "perf.json"))
    bench = _check(registry.invoke(
        "perf_benchmark", label="date", tool="date_time",
        iterations=3))
    assert (bench.get("measurement") or {}).get("iterations") == 3, bench
    _check(registry.invoke("perf_report", label="date"))
    _check(registry.invoke("perf_hotspots", top=5))
    _check(registry.invoke("perf_fps"))


# ---------------------------------------------------------------------------
# Feature 74 — Dynamic Planning & Replanning
# ---------------------------------------------------------------------------

def test_planner_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.planner",
                  "AdaptivePlanner", "_engine_planner",
                  kv=_kv(tmp_path, "planner.json"))
    created = _ok(registry.invoke(
        "plan_create", goal="release v1",
        steps='[{"action": "build", "args": {}}, '
              '{"action": "test", "args": {}}]'))
    assert _extract(created, "id") is not None, created
    pid = _extract(created, "id")
    _check(registry.invoke("plan_status", plan_id=pid))
    _check(registry.invoke("plan_list"))
    replanned = _check(registry.invoke(
        "plan_replan", plan_id=pid, failed_step="1",
        alternatives='[{"action": "rebuild", "args": {}}]'))
    assert _extract(replanned, "status") == "replanned", replanned
    _check(registry.invoke("plan_complete", plan_id=pid, step_ref="1.alt"))
    _check(registry.invoke("plan_deprecate", plan_id=pid))


# ---------------------------------------------------------------------------
# Feature 92 — Real-Time Event Response
# ---------------------------------------------------------------------------

def test_event_response_flow(registry, tmp_path, monkeypatch):
    _patch_engine(monkeypatch, tmp_path, "core.event_response",
                  "EventResponder", "_engine_responder",
                  kv=_kv(tmp_path, "events.json"))
    handler = _ok(registry.invoke(
        "er_register", trigger="disk.full", tool="date_time", args="{}"))
    hid = _extract(handler, "id")
    assert hid, handler
    handled = _check(registry.invoke(
        "er_ingest", source="host1", event_type="disk.full",
        severity="critical", payload="{}"))
    assert handled["status"] == "handled", handled
    _check(registry.invoke("er_history"))
    _check(registry.invoke("er_stats"))
    _check(registry.invoke("er_unregister", handler_id=hid))
    orphan = _check(registry.invoke(
        "er_ingest", source="host1", event_type="fire.alarm",
        severity="critical"))
    assert orphan["status"] == "ESCALATED", orphan


# ---------------------------------------------------------------------------
# Feature 102 — Universal Undo / Transaction Recovery
# ---------------------------------------------------------------------------

def test_undo_flow(registry, tmp_path, monkeypatch):
    store = _kv(tmp_path, "undo.json")
    _patch_engine(monkeypatch, tmp_path, "core.undo",
                  "TransactionManager", "_engine_undo", kv=store)
    begun = _ok(registry.invoke("txn_begin", label="config change"))
    tid = _extract(begun, "id")
    assert tid, begun
    _ok(registry.invoke("txn_op", txn_id=tid, key="theme", value="dark"))
    assert store.get("theme") == "dark"
    _check(registry.invoke("txn_status", txn_id=tid))
    rolled = _check(registry.invoke("txn_rollback", txn_id=tid))
    assert _extract(rolled, "status") == "rolled_back", rolled
    assert store.get("theme") is None
    begun2 = _ok(registry.invoke("txn_begin", label="must commit"))
    tid2 = _extract(begun2, "id")
    _ok(registry.invoke("txn_op", txn_id=tid2, key="theme", value="dark"))
    committed = _check(registry.invoke("txn_commit", txn_id=tid2))
    assert _extract(committed, "status") == "committed", committed
    assert store.get("theme") == "dark"
    _check(registry.invoke("txn_active"))