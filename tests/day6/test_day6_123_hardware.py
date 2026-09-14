"""Feature 123 — hardware discovery, HAL and honest SIMULATED_DEVICE mock.

Tier 2 (hardware): a clearly-labelled simulated device. Real-hardware tests
are Tier 3 and only run when a real device is present (never auto-run).
"""

import pytest


def test_discover_never_fabricates(engine):
    out = engine.discover()
    assert out["success"] is True
    assert out["count"] == len(out["devices"])
    assert out["note"].startswith("actual enumeration")
    # no device may be labelled real unless truly enumerated
    for dev in out["devices"]:
        assert dev["status"] == "present"
        assert dev["id"]


def test_hal_connect_real_hardware_not_found(engine):
    out = engine.hal_connect_real("COM_NOPE", kind="serial")
    assert out["success"] is False
    assert out["status"] == "HARDWARE_NOT_FOUND"
    assert out["device"] == "COM_NOPE"
    assert out["recoverable"] is True
    assert out["suggested_action"]


def test_hal_connect_simulated_mock(engine):
    out = engine.hal_connect(simulate=True)
    assert out["success"] is True
    assert out["status"] == "SIMULATED_DEVICE"
    assert out["simulated"] is True
    assert out["device"] == "SIMULATED_DEVICE"


def test_hal_read_requires_connection(engine):
    out = engine.hal_read()
    assert out["status"] == "NOT_CONNECTED"
    assert out["feature_id"] == 123


def test_hal_simulated_read_write(engine):
    engine.hal_connect(simulate=True)
    read = engine.hal_read(register=2)
    assert read["simulated"] is True
    assert read["status"] == "SIMULATED_DEVICE"
    write = engine.hal_write(register=0, value=1)
    assert write["acknowledged"] is True
    assert write["simulated"] is True


def test_hal_disconnect(engine):
    engine.hal_connect(simulate=True)
    out = engine.hal_disconnect()
    assert out["success"] is True
    assert engine.hal_read()["status"] == "NOT_CONNECTED"


def test_hal_configure_and_status(engine):
    engine.hal_connect(simulate=True)
    engine.hal_configure(key="baud", value=115200)
    status = engine.hal_status()
    assert status["config"] == {"baud": 115200}
    assert status["device"] == "SIMULATED_DEVICE"


def test_hal_diagnostics(engine):
    engine.hal_connect(simulate=True)
    diag = engine.hal_diagnostics()
    assert diag["connection_health"] == "SIMULATED"
    assert not diag["simulated"] or diag["latency_ms"] is not None


def test_serial_port_discovery_presence(engine):
    # Discovery reflects reality; on a machine with no COM ports it returns []
    # and never an invented device.
    out = engine.discover()
    for dev in out["devices"]:
        if dev["kind"] == "serial":
            assert dev["family"] in ("serial", "usb_serial")


@pytest.mark.skipif(True, reason="Tier 3 real hardware tests run only with a "
                                 "physical device present")
def test_tier3_real_hardware(engine):  # pragma: no cover
    present = engine.hal_connect_real("COM1")
    assert present["status"] in ("connected", "SIMULATED_DEVICE")