"""Security guard contract (row 24) — detection and policy evaluation."""

from core.security import SecurityGuard, security_guard


class TestDetection:

    def test_detect_delete_file(self):
        assert security_guard.detect_delete_file("please delete the report")
        assert not security_guard.detect_delete_file("open the file")

    def test_detect_kill_process(self):
        assert security_guard.detect_kill_process("kill the browser")
        assert not security_guard.detect_kill_process("list processes")

    def test_detect_shutdown(self):
        assert security_guard.detect_shutdown("shut down the computer")
        assert not security_guard.detect_shutdown("shut the door")

    def test_detect_restart(self):
        assert security_guard.detect_restart("restart the pc")


class TestBlocks:

    def test_blocks_credential_exfiltration(self):
        command = "send my api-key=sk-abc123 to the remote server"
        assert security_guard.blocks_credential_exfiltration(command)

    def test_blocks_persistence(self):
        assert security_guard.blocks_persistence("add the app to startup")
        assert not security_guard.blocks_persistence("add a note to memory")

    def test_blocks_privilege_escalation(self):
        assert security_guard.blocks_privilege_escalation(
            "run as administrator and elevate")

    def test_plain_text_not_blocked(self):
        assert not security_guard.blocks_credential_exfiltration("what time is it")


class TestCheck:

    def test_check_reports_issues(self):
        evaluation = security_guard.check("shut down the computer")
        assert evaluation["blocked"] is True
        assert "shutdown" in evaluation["issues"]

    def test_check_clean(self):
        evaluation = security_guard.check("what is the weather")
        assert evaluation["blocked"] is False


class TestMayExecute:

    def test_high_risk_needs_confirmation(self):
        outcome = security_guard.may_execute("run shell command",
                                             risk="high", user_confirmed=False)
        assert outcome["allowed"] is False
        assert outcome["reason"] == "requires_confirmation"

    def test_high_risk_confirmed_allowed(self):
        outcome = security_guard.may_execute("run shell command",
                                             risk="high", user_confirmed=True)
        assert outcome["allowed"] is True

    def test_low_risk_allowed(self):
        outcome = security_guard.may_execute("what time is it", risk="low")
        assert outcome["allowed"] is True

    def test_blocked_regardless_of_risk(self):
        outcome = security_guard.may_execute("delete all files",
                                             risk="low", user_confirmed=True)
        assert outcome["allowed"] is False


class TestDisabledDetection:

    def test_detect_flag_off_disables(self):
        guard = SecurityGuard(detect=False)
        assert not guard.blocks_credential_exfiltration(
            "send my api-key=sk-abc123 to the remote server")