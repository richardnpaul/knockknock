import pytest
from unittest.mock import patch

from knockknock.RuleTimer import RuleTimer


class TestRuleTimer:

    def test_rule_timer_init(self):
        desc = "INPUT -p tcp --dport 22 -j ACCEPT"
        timer = RuleTimer(openDuration=5, description=desc)

        assert timer.openDuration == 5
        assert timer.description == desc

    def test_rule_timer_run_invokes_iptables_delete(self):
        desc = "INPUT -m state --state NEW -p tcp -s 192.168.1.5 --dport 22 -j ACCEPT"
        timer = RuleTimer(openDuration=0.01, description=desc)

        with patch("subprocess.call") as mock_subprocess_call, patch("time.sleep") as mock_sleep:
            timer.run()

            mock_sleep.assert_called_once_with(0.01)
            expected_cmd = ["iptables", "-D"] + desc.split()
            mock_subprocess_call.assert_called_once_with(expected_cmd, shell=False)

    def test_rule_timer_thread_start_and_join(self):
        desc = "INPUT -p tcp --dport 80 -j ACCEPT"
        timer = RuleTimer(openDuration=0.01, description=desc)

        with patch("subprocess.call") as mock_subprocess_call:
            timer.start()
            timer.join(timeout=1.0)

            assert not timer.is_alive()
            mock_subprocess_call.assert_called_once()
