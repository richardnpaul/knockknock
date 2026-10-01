import io
import pytest
from unittest.mock import MagicMock, patch

from knockknock.PortOpener import PortOpener


class TestPortOpener:

    def test_open_success(self):
        fake_stream = io.StringIO()
        opener = PortOpener(fake_stream, openDuration=15)

        opener.open("192.168.1.50", 22)
        assert fake_stream.getvalue() == "192.168.1.50\n22\n"

    def test_open_failure_exits(self):
        broken_stream = MagicMock()
        broken_stream.write.side_effect = BrokenPipeError("Pipe closed")
        opener = PortOpener(broken_stream, openDuration=15)

        with patch("syslog.syslog") as mock_syslog, patch("os._exit") as mock_exit:
            opener.open("192.168.1.50", 22)
            mock_syslog.assert_called_once_with("knockknock:  Error, PortOpener process has died.  Terminating.")
            mock_exit.assert_called_once_with(4)

    def test_wait_for_requests_processes_knock_and_exits_on_eof(self):
        # Stream provides one knock, then EOF with empty port to kill or-to-and mutant
        input_data = "10.0.0.99\n8080\n10.0.0.99\n\n"
        stream = io.StringIO(input_data)
        opener = PortOpener(stream, openDuration=10)

        with patch("subprocess.call") as mock_subprocess_call, \
             patch("knockknock.PortOpener.RuleTimer") as mock_rule_timer_class, \
             patch("syslog.syslog") as mock_syslog, \
             patch("os._exit") as mock_exit:

            # Make os._exit raise a SystemExit so the while True loop terminates in test
            mock_exit.side_effect = SystemExit(4)

            with pytest.raises(SystemExit):
                opener.waitForRequests()

            # Verify iptables command was executed with shell=False
            mock_subprocess_call.assert_called_once()
            called_args = mock_subprocess_call.call_args[0][0]
            assert called_args[0] == "iptables"
            assert called_args[1] == "-I"
            assert "-s" in called_args
            assert "10.0.0.99" in called_args
            assert "--dport" in called_args
            assert "8080" in called_args
            assert mock_subprocess_call.call_args[1].get("shell") is False

            # Verify RuleTimer was initialized with duration and started
            mock_rule_timer_class.assert_called_once()
            mock_rule_timer_instance = mock_rule_timer_class.return_value
            mock_rule_timer_instance.start.assert_called_once()

            # Verify clean exit when EOF reached
            mock_syslog.assert_called_with("knockknock.PortOpener: Parent process is closed.  Terminating.")
            mock_exit.assert_called_with(4)

    def test_wait_for_requests_exits_when_port_empty(self):
        input_data = "10.0.0.99\n\n"
        stream = io.StringIO(input_data)
        opener = PortOpener(stream, openDuration=10)

        with patch("subprocess.call") as mock_subprocess_call, \
             patch("syslog.syslog") as mock_syslog, \
             patch("os._exit") as mock_exit:
            mock_exit.side_effect = SystemExit(4)
            with pytest.raises(SystemExit):
                opener.waitForRequests()

            mock_subprocess_call.assert_not_called()
            mock_syslog.assert_called_once_with("knockknock.PortOpener: Parent process is closed.  Terminating.")
            mock_exit.assert_called_once_with(4)


    def test_wait_for_requests_exits_when_source_ip_empty(self):
        input_data = "\n8080\n"
        stream = io.StringIO(input_data)
        opener = PortOpener(stream, openDuration=10)

        with patch("subprocess.call") as mock_subprocess_call, \
             patch("syslog.syslog") as mock_syslog, \
             patch("os._exit") as mock_exit:
            mock_exit.side_effect = SystemExit(4)
            with pytest.raises(SystemExit):
                opener.waitForRequests()

            mock_subprocess_call.assert_not_called()
            mock_syslog.assert_called_once_with("knockknock.PortOpener: Parent process is closed.  Terminating.")
            mock_exit.assert_called_once_with(4)


