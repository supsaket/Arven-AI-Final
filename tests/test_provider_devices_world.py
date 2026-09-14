"""ARVEN Day 2 — devices & world action modules (43, 44, 82, 45, 80, 84, 93, 83, 79).

Focused green tests. Every provider uses a temp-dir ``KeyValueStore``; no
real data files are touched. Honest statuses are asserted exactly:
NOT_CONFIGURED when a backend is absent, REQUIRES_AUTH/PERMISSION at the
gates, OFFLINE when offline — never fabricated success.
"""

import math

import pytest

from core.confirmation import CONFIRMATION
from core.kv import KeyValueStore
from core.providers.base import (
    STATUS_AVAILABLE,
    STATUS_NOT_CONFIGURED,
    STATUS_OFFLINE,
    STATUS_REQUIRES_AUTH,
    STATUS_REQUIRES_PERMISSION,
)

from core.providers.android_provider import AndroidProvider
from core.providers.iot_provider import IoTProvider
from core.providers.home_provider import HomeProvider
from core.providers.communication_provider import (
    CommunicationProvider,
    validate_recipient,
)
from core.providers.travel_provider import TravelProvider
from core.providers.location_provider import LocationProvider, haversine_km
from core.providers.navigation_provider import NavigationProvider
from core.providers.vehicle_provider import VehicleProvider
from core.providers.world_actions import WorldActionsProvider


@pytest.fixture
def kv(tmp_path):
    return KeyValueStore(str(tmp_path / "kv.json"))


# ----------------------------------------------------------------------
# 43 — Android (ADB honesty)
# ----------------------------------------------------------------------
class TestAndroid:

    def test_adb_absent_is_honest_not_configured(self):
        provider = AndroidProvider()
        provider.set_backend(False)
        result = provider.execute("android_status")
        assert result["success"] is False
        assert result["status"] == STATUS_NOT_CONFIGURED
        assert "adb" in result["message"].lower()
        assert provider.check() == STATUS_NOT_CONFIGURED

    def test_adb_shell_refuses_without_confirmation(self):
        provider = AndroidProvider()
        provider.set_backend(False)
        result = provider.execute("android_shell", command="echo hi")
        assert result["status"] == STATUS_REQUIRES_AUTH
        assert result["success"] is False

    def test_adb_devices_not_configured_without_binary(self):
        provider = AndroidProvider()
        provider.set_backend(False)
        result = provider.execute("android_list_devices")
        assert result["status"] == STATUS_NOT_CONFIGURED


# ----------------------------------------------------------------------
# 44 — IoT (simulated flag + persistence + external honesty)
# ----------------------------------------------------------------------
class TestIoT:

    def test_simulated_state_flag_and_persistence(self, kv):
        provider = IoTProvider(kv=kv)
        result = provider.execute(
            "iot_register", device_id="bulb", kind="simulated",
            name="Living Room Bulb", capabilities=["light"],
            state={"on": False})
        assert result["success"] is True

        updated = provider.execute(
            "iot_set_state", device_id="bulb",
            state={"on": True, "brightness": 80})
        assert updated["success"] is True
        assert updated["data"]["simulated"] is True

        fresh = IoTProvider(kv=kv)
        listed = fresh.execute("iot_list")
        bulb = next(d for d in listed["data"]["devices"]
                    if d["id"] == "bulb")
        assert bulb["state"]["on"] is True
        assert bulb["state"]["brightness"] == 80

    def test_external_device_without_backend_is_not_configured(self, kv):
        provider = IoTProvider(kv=kv)
        provider.execute(
            "iot_register", device_id="thermo", kind="thermostat",
            name="Hall Thermostat", simulated=False)
        result = provider.execute(
            "iot_set_state", device_id="thermo", state={"target": 21})
        assert result["status"] == STATUS_NOT_CONFIGURED
        assert result["success"] is False

    def test_remove_requires_confirmation_through_gate(self, kv):
        provider = IoTProvider(kv=kv)
        provider.execute("iot_register", device_id="d1", name="D1")
        refused = provider.execute("iot_remove", device_id="d1")
        assert refused["status"] == STATUS_REQUIRES_AUTH
        request_id = CONFIRMATION.require("remove device", "destructive")
        approved = provider.execute(
            "iot_remove", device_id="d1", confirmed=True, trusted=True,
            request_id=request_id)
        assert approved["success"] is True


# ----------------------------------------------------------------------
# 82 — Home (routine simulation + energy arithmetic)
# ----------------------------------------------------------------------
class TestHome:

    def test_routine_only_runs_simulated_devices(self, kv):
        iot = IoTProvider(kv=kv)
        iot.execute("iot_register", device_id="bulb", kind="simulated",
                    name="Bulb", state={"on": True})
        iot.execute("iot_register", device_id="thermo", kind="thermostat",
                    name="Thermo", simulated=False)

        home = HomeProvider(kv=kv)
        home.manager.add_routine(
            "evening",
            description="lights off, heat off",
            steps=[{"device_id": "bulb", "target_state": {"on": False}},
                   {"device_id": "thermo", "target_state": {"target": 18}}])

        result = home.execute("home_routine", routine_name="evening")
        assert result["success"] is True
        data = result["data"]
        assert [e["device_id"] for e in data["executed"]] == ["bulb"]
        assert data["executed"][0]["simulated"] is True
        skipped_ids = {s["device_id"] for s in data["skipped"]}
        assert "thermo" in skipped_ids

        persisted = IoTProvider(kv=kv).execute("iot_list")
        bulb = next(d for d in persisted["data"]["devices"]
                    if d["id"] == "bulb")
        assert bulb["state"]["on"] is False

    def test_energy_estimate_real_arithmetic(self, kv):
        home = HomeProvider(kv=kv)
        home.registry.register(
            device_id="bulb", name="Bulb", power_watts=60, hours_per_day=3)
        result = home.execute("home_energy_estimate")
        assert result["success"] is True
        assert result["data"]["estimate"] is True
        assert abs(result["data"]["total_kwh"] - 0.18) < 1e-6

        items_result = home.execute(
            "home_energy_estimate",
            items=[{"name": "kettle", "watts": 1000, "hours": 2}])
        assert abs(items_result["data"]["total_kwh"] - 2.0) < 1e-6


# ----------------------------------------------------------------------
# 45 — Communication (compose/validate/templates + gate + backend honesty)
# ----------------------------------------------------------------------
class TestCommunication:

    def _provider(self, kv):
        return CommunicationProvider(kv=kv)

    def test_template_add_apply_and_compose(self, kv):
        provider = self._provider(kv)
        added = provider.execute(
            "email_templates", action="add", name="welcome",
            subject="Hi {name}", body="Welcome {name} to {org}!")
        assert added["success"] is True

        composed = provider.execute(
            "email_compose", template="welcome",
            variables={"name": "Ada", "org": "Arven"})
        assert composed["data"]["subject"] == "Hi Ada"
        assert composed["data"]["body"] == "Welcome Ada to Arven!"

        listed = provider.execute("email_templates")
        assert any(t["name"] == "welcome" for t in listed["data"]["templates"])

    def test_recipient_validation_rules(self):
        valid_email, kind, _ = validate_recipient("ada@example.com")
        assert valid_email is True and kind == "email"
        valid_phone, phone_kind, _ = validate_recipient("+15551234567")
        assert valid_phone is True and phone_kind == "phone"
        bad_email, _, _ = validate_recipient("not-an-email")
        assert bad_email is False

    def test_draft_saves(self, kv):
        provider = self._provider(kv)
        provider.execute(
            "email_templates", action="add", name="welcome",
            subject="Hi {name}", body="Welcome {name} to {org}!")
        draft = provider.execute(
            "email_draft", template="welcome",
            variables={"name": "Ada", "org": "Arven"},
            recipient="ada@example.com")
        assert draft["success"] is True
        assert draft["data"]["draft"]["recipient"] == "ada@example.com"

    def test_send_refused_when_not_confirmed(self, kv):
        provider = self._provider(kv)
        refused = provider.execute(
            "email_send", to="ada@example.com", subject="Hi", body="Hello")
        assert refused["status"] == STATUS_REQUIRES_AUTH
        assert refused["success"] is False
        refused_msg = provider.execute(
            "message_send", to="+15551234567", text="ping")
        assert refused_msg["status"] == STATUS_REQUIRES_AUTH

    def test_send_honest_not_configured_without_backend(self, kv):
        provider = self._provider(kv)
        request_id = CONFIRMATION.require("send email", "high")
        result = provider.execute(
            "email_send", to="ada@example.com", subject="Hi", body="Hello",
            confirmed=True, request_id=request_id)
        assert result["status"] == STATUS_NOT_CONFIGURED
        assert result["data"]["sent"] is False
        assert "not sent" in result["message"].lower()
        assert provider.check() == STATUS_NOT_CONFIGURED


# ----------------------------------------------------------------------
# 80 — Travel (plan arithmetic + booking gate)
# ----------------------------------------------------------------------
class TestTravel:

    def test_plan_arithmetic_and_itinerary(self, kv):
        provider = TravelProvider(kv=kv)
        result = provider.execute(
            "travel_plan",
            destinations=[
                {"name": "Paris", "lat": 48.8566, "lon": 2.3522},
                {"name": "London", "lat": 51.5074, "lon": -0.1278},
            ],
            dates=["2026-07-01", "2026-07-02", "2026-07-03"],
            budget=900, pace="moderate", transport="train")
        assert result["success"] is True
        plan = result["data"]["plan"]
        assert plan["estimate"] is True
        assert len(plan["schedule"]) == 3

        totals = plan["totals"]
        assert totals["budget"] == 900.0
        assert totals["nights"] == 2
        total_spend = (totals["accommodation_total"]
                       + totals["transport_total"] + totals["meals_total"])
        assert abs(total_spend - totals["budget"]) < 0.01

        legs = [e["leg_km"] for e in plan["schedule"] if e.get("leg_km")]
        assert len(legs) == 2
        assert all(300 < leg < 380 for leg in legs)

        itinerary = provider.execute(
            "travel_itinerary", trip_id=plan["trip_id"])
        assert itinerary["success"] is True

    def test_booking_requires_confirmation(self, kv):
        provider = TravelProvider(kv=kv)
        plan = provider.execute(
            "travel_plan", destinations=["Paris"],
            budget=500, transport="car")
        trip_id = plan["data"]["plan"]["trip_id"]

        refused = provider.execute("travel_book", trip_id=trip_id)
        assert refused["status"] == STATUS_REQUIRES_AUTH
        assert refused.get("requires_confirmation") is True

        request_id = CONFIRMATION.require("book trip", "high")
        approved = provider.execute(
            "travel_book", trip_id=trip_id,
            confirmed=True, request_id=request_id)
        assert approved["status"] == STATUS_NOT_CONFIGURED
        assert approved["data"]["booked"] is False


# ----------------------------------------------------------------------
# 84 — Location (permission gate + haversine accuracy)
# ----------------------------------------------------------------------
class TestLocation:

    def test_get_requires_permission_then_works(self, kv):
        provider = LocationProvider(kv=kv, permissions={})
        provider.execute("location_set", name="home",
                         lat=48.8566, lon=2.3522)

        denied = provider.execute("location_get", name="home")
        assert denied["status"] == STATUS_REQUIRES_PERMISSION
        assert denied["data"]["permission"] == "location_access"

        granted = LocationProvider(
            kv=kv, permissions={"location_access": "granted"})
        read = granted.execute("location_get", name="home")
        assert read["success"] is True
        assert read["data"]["place"]["lat"] == 48.8566

    def test_haversine_accuracy_km_and_miles(self, kv):
        provider = LocationProvider(kv=kv, permissions={})
        paris = (48.8566, 2.3522)
        london = (51.5074, -0.1278)
        km = provider.execute(
            "distance", lat1=paris[0], lon1=paris[1], lat2=london[0],
            lon2=london[1])
        assert km["success"] is True
        assert 340 < km["data"]["km"] < 350
        expected_miles = km["data"]["km"] / 1.609344
        assert abs(km["data"]["miles"] - expected_miles) < 0.01
        assert abs(km["data"]["km"] - haversine_km(*paris, *london)) < 1e-3

    def test_geocode_offline_then_not_configured(self, kv):
        offline = LocationProvider(kv=kv, permissions={},
                                   network_probe=lambda: False)
        result = offline.execute("location_geocode", query="Paris")
        assert result["status"] == STATUS_OFFLINE

        online = LocationProvider(kv=kv, permissions={},
                                  network_probe=lambda: True)
        result = online.execute("location_geocode", query="Paris")
        assert result["status"] == STATUS_NOT_CONFIGURED


# ----------------------------------------------------------------------
# 93 — Navigation (deterministic offline routing + live honesty)
# ----------------------------------------------------------------------
class TestNavigation:

    def test_route_plan_deterministic_estimate(self, kv):
        provider = NavigationProvider(kv=kv, network_probe=lambda: True)
        origin, destination = (48.8566, 2.3522), (51.5074, -0.1278)
        first = provider.execute(
            "route_plan", origin=origin, destination=destination, mode="drive")
        second = provider.execute(
            "route_plan", origin=origin, destination=destination, mode="drive")

        assert first["success"] is True
        assert first["data"]["estimate"] is True
        assert first["data"]["live"] is False
        assert first["data"]["distance_km"] == second["data"]["distance_km"]
        assert first["data"]["duration_min"] == second["data"]["duration_min"]
        assert 300 < first["data"]["distance_km"] < 380
        expected_min = first["data"]["distance_km"] / 40.0 * 60.0
        assert abs(first["data"]["duration_min"] - expected_min) < 0.1

    def test_route_eta_offline_is_honest(self, kv):
        provider = NavigationProvider(kv=kv, network_probe=lambda: False)
        eta = provider.execute(
            "route_eta", origin=(48.8566, 2.3522),
            destination=(51.5074, -0.1278))
        assert eta["status"] == STATUS_OFFLINE

    def test_route_eta_no_live_backend(self, kv, monkeypatch):
        provider = NavigationProvider(kv=kv, network_probe=lambda: True)
        eta = provider.execute(
            "route_eta", origin=(48.8566, 2.3522),
            destination=(51.5074, -0.1278))
        assert eta["status"] == STATUS_NOT_CONFIGURED


# ----------------------------------------------------------------------
# 83 — Vehicle (user-entered values + datetime reminder math)
# ----------------------------------------------------------------------
class TestVehicle:

    def test_reminder_math_and_registration(self, kv):
        provider = VehicleProvider(kv=kv)
        logged = provider.execute(
            "vehicle_log_maintenance", reg="AB12 CDE", make="Toyota",
            model="Yaris", odometer=20000, service_type="service",
            cost=150.0, service_date="2026-03-01")
        assert logged["success"] is True
        assert logged["data"]["source"] == "user"

        reminder = provider.execute(
            "vehicle_reminders", reg="AB12 CDE", interval_km=10000,
            interval_months=6, as_of="2026-06-01")
        assert reminder["success"] is True
        data = reminder["data"]
        assert data["source"] == "user"
        assert data["due_km"] == 30000.0
        assert data["due_date"] == "2026-09-01"

        provider.execute(
            "vehicle_registration", reg="AB12 CDE", make="Toyota",
            model="Yaris", renewal_date="2026-11-01")
        with_renewal = provider.execute(
            "vehicle_reminders", reg="AB12 CDE", interval_km=10000,
            as_of="2026-06-01")
        kinds = [r["kind"] for r in with_renewal["data"]["reminders"]]
        assert "registration" in kinds


# ----------------------------------------------------------------------
# 79 — World actions (dry-run transcript vs confirmed execution)
# ----------------------------------------------------------------------
class TestWorldActions:

    def test_dry_run_never_executes(self, kv):
        provider = WorldActionsProvider(kv=kv)
        created = provider.execute(
            "action_create", name="open garage", action_type="simulated",
            target={"name": "garage", "simulated": True})
        action_id = created["data"]["action"]["id"]

        dry = provider.execute("action_dry_run", action_id=action_id)
        assert dry["success"] is True
        assert dry["data"]["dry_run"] is True
        assert dry["data"]["executed"] is False
        assert len(dry["data"]["transcript"]) >= 2
        assert all(s["side_effect"] is False
                   for s in dry["data"]["transcript"])

    def test_execute_refused_without_confirmation(self, kv):
        provider = WorldActionsProvider(kv=kv)
        created = provider.execute(
            "action_create", name="open garage", action_type="simulated",
            target={"name": "garage", "simulated": True})
        refused = provider.execute(
            "action_execute", action_id=created["data"]["action"]["id"])
        assert refused["status"] == STATUS_REQUIRES_AUTH
        assert refused["requires_confirmation"] is True

    def test_simulated_local_execution_flagged(self, kv):
        provider = WorldActionsProvider(kv=kv)
        created = provider.execute(
            "action_create", name="open garage", action_type="simulated",
            target={"name": "garage", "simulated": True})
        request_id = CONFIRMATION.require("run action", "high")
        result = provider.execute(
            "action_execute",
            action_id=created["data"]["action"]["id"],
            confirmed=True, request_id=request_id)
        assert result["success"] is True
        assert result["data"]["simulated"] is True
        assert result["data"]["result"]["physical_side_effect"] is False

    def test_real_world_action_honest_without_backend(self, kv):
        provider = WorldActionsProvider(kv=kv)
        created = provider.execute(
            "action_create", name="ring doorbell", action_type="physical",
            target={"name": "front door"})
        request_id = CONFIRMATION.require("run action", "high")
        result = provider.execute(
            "action_execute",
            action_id=created["data"]["action"]["id"],
            confirmed=True, request_id=request_id)
        assert result["status"] == STATUS_NOT_CONFIGURED
        assert result["data"]["executed"] is False
        assert result["data"]["requires_confirmation"] is True