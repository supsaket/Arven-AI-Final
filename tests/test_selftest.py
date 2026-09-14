"""Self-test harness contract (row 35) — real checks, honest status."""

from core.selftest import SelfTestRunner, selftest


class TestChecker:

    def test_adding_and_running(self):
        runner = SelfTestRunner()
        runner.add("trivially_true", lambda: {"ok": True, "status": "ok"})
        report = runner.run()
        assert report["passed"] == 1
        assert report["failed"] == 0

    def test_false_is_failure(self):
        runner = SelfTestRunner()
        runner.add("wrong", lambda: False)
        report = runner.run()
        assert report["failed"] == 1

    def test_unavailable_is_not_pass(self):
        runner = SelfTestRunner()
        runner.add("missing_backend", lambda: {"ok": True, "status": "ok",
                                               "available": False})
        report = runner.run()
        assert report["failed"] == 1

    def test_raising_check_is_failure(self):
        runner = SelfTestRunner()

        def broken():
            raise RuntimeError("boom")

        runner.add("broken", broken)
        report = runner.run()
        assert report["failed"] == 1
        assert report["failures"][0]["name"] == "broken"

    def test_format_selftest(self):
        runner = SelfTestRunner()
        runner.add("a_check", lambda: {"ok": True, "status": "ok"})
        report = runner.run()
        text = runner.format_selftest(report)
        assert "=== ARVEN SELF-TEST ===" in text
        assert "TOTAL 1 | PASSED 1 | FAILED 0" in text.replace("\r", "")


class TestSecurityCheck:

    def test_blocked_dangerous_command(self):
        runner = SelfTestRunner()
        allowed, _ = runner.security_check("rm -rf / important")
        assert allowed is False

    def test_allowed_clean_command(self):
        runner = SelfTestRunner()
        allowed, _ = runner.security_check("list my files")
        assert allowed is True


class TestDefaultRunner:

    def test_default_selftest_runs(self):
        report = selftest.run()
        assert report["total"] >= 8
        assert report["failed"] == 0