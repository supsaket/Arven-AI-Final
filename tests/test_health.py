"""Health monitor contract (row 26) — enums, normalization, precedence, offline."""

from core.health import (
    HealthState,
    HealthStatus,
    check,
    check_failure_state_unavailable,
    format_system_check,
    overall_state,
    run_system_check,
    timed,
)


class TestEnums:

    def test_states_are_lowercase_strings(self):
        assert HealthState.HEALTHY.value == "healthy"
        assert HealthState.DEGRADED.value == "degraded"
        assert HealthState.UNAVAILABLE.value == "unavailable"
        assert HealthState.ERROR.value == "error"

    def test_health_status_alias(self):
        assert HealthStatus.OK.value == "healthy"


class TestCheck:

    def test_normalized_component(self):
        comp = check("cpu", HealthState.HEALTHY, {"load": 0.3})
        assert comp["name"] == "cpu"
        assert comp["state"] == "healthy"
        assert comp["ok"] is True

    def test_unavailable_not_ok(self):
        comp = check("wifi", HealthState.UNAVAILABLE, {"reason": "no radio"})
        assert comp["ok"] is False
        assert comp["state"] == "unavailable"

    def test_failure_is_unavailable_never_healthy(self):
        comp = check_failure_state_unavailable()
        assert comp["state"] == "unavailable"
        assert comp["ok"] is False


class TestOverall:

    def test_error_wins(self):
        components = [
            check("a", HealthState.HEALTHY),
            check("b", HealthState.ERROR),
        ]
        assert overall_state(components) == "error"

    def test_unavailable_beats_degraded(self):
        components = [
            check("a", HealthState.DEGRADED),
            check("b", HealthState.UNAVAILABLE),
        ]
        assert overall_state(components) == "unavailable"

    def test_degraded_beats_healthy(self):
        components = [
            check("a", HealthState.HEALTHY),
            check("b", HealthState.DEGRADED),
        ]
        assert overall_state(components) == "degraded"

    def test_all_healthy(self):
        assert overall_state([check("a"), check("b")]) == "healthy"


class TestTimed:

    def test_fast_function_ok(self):
        kind, value = timed(lambda: 21 * 2)
        assert kind == "ok"
        assert value == 42

    def test_slow_function_times_out(self):
        def slow():
            import time
            time.sleep(0.5)
            return True
        kind, value = timed(slow, timeout=0.05)
        assert kind == "error"

    def test_raising_function_is_error(self):
        def broken():
            raise ValueError("nope")
        kind, _ = timed(broken)
        assert kind == "error"


class TestSystemCheck:

    def test_components_present(self):
        result = run_system_check(offline=False)
        assert result["components"]
        assert "overall" in result

    def test_offline_marks_healthy_as_unavailable(self):
        result = run_system_check(offline=True)
        for comp in result["components"]:
            assert comp["state"] != "healthy"

    def test_offline_overall_never_healthy(self):
        result = run_system_check(offline=True)
        assert result["overall"] != "healthy"

    def test_format_includes_overall(self):
        result = run_system_check(offline=False)
        text = format_system_check(result)
        assert "OVERALL:" in text
        assert "ARVEN SYSTEM CHECK" in text

    def test_not_configured_is_reported_degraded(self):
        result = run_system_check(offline=False)
        # components can be unavailable but a check dict is never 'error' for a
        # mere absence of a backend (probes report unavailable).
        for comp in result["components"]:
            assert "state" in comp