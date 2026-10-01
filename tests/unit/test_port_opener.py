import io
from unittest.mock import MagicMock, patch

import pytest

from knockknock.PortOpener import PortOpener


class TestPortOpener:
    def test_open_success(self) -> None:
        fake_stream = io.StringIO()
        opener = PortOpener(fake_stream, openDuration=15)

        opener.open("192.168.1.50", 22)
        assert fake_stream.getvalue() == "192.168.1.50\n22\n"

    def test_open_failure_exits(self) -> None:
        broken_stream = MagicMock()
        broken_stream.write.side_effect = BrokenPipeError("Pipe closed")
        opener = PortOpener(broken_stream, openDuration=15)

        with patch("syslog.syslog") as mock_syslog, patch("os._exit") as mock_exit:
            opener.open("192.168.1.50", 22)
            mock_syslog.assert_called_once_with("knockknock:  Error, PortOpener process has died.  Terminating.")
            mock_exit.assert_called_once_with(4)

    def test_wait_for_requests_processes_knock_and_exits_on_eof(self) -> None:
        input_data = "10.0.0.1\n22\n10.0.0.1\n\n"
        stream = io.StringIO(input_data)
        mock_on_exit = MagicMock()
        opener = PortOpener(stream, openDuration=15, on_exit=mock_on_exit)

        with (
            patch("subprocess.call") as mock_subprocess_call,
            patch("syslog.syslog") as mock_syslog,
            patch("os._exit") as mock_exit,
        ):
            mock_exit.side_effect = SystemExit(4)

            with pytest.raises(SystemExit):
                opener.waitForRequests()

            mock_subprocess_call.assert_called_once_with(
                [
                    opener.nft_path,
                    "add",
                    "element",
                    "inet",
                    "knockknock",
                    "open_ports",
                    "{ 10.0.0.1 . 22 timeout 15s }",
                ],
                shell=False,
            )
            mock_on_exit.assert_called_once_with()
            mock_syslog.assert_called_with("knockknock.PortOpener: Parent process is closed.  Terminating.")
            mock_exit.assert_called_with(4)

    @pytest.mark.parametrize(
        "ip,port,expected_element",
        [
            ("255.255.255.255", "1", "{ 255.255.255.255 . 1 timeout 15s }"),
            ("0.0.0.0", "65535", "{ 0.0.0.0 . 65535 timeout 15s }"),
        ],
    )
    def test_wait_for_requests_valid_boundary_ports_and_ips(self, ip: str, port: str, expected_element: str) -> None:
        input_data = f"{ip}\n{port}\n"
        stream = io.StringIO(input_data)
        opener = PortOpener(stream, openDuration=15)

        with (
            patch("subprocess.call") as mock_subprocess_call,
            patch("syslog.syslog"),
            patch("os._exit", side_effect=SystemExit(4)),
        ):
            with pytest.raises(SystemExit):
                opener.waitForRequests()

            mock_subprocess_call.assert_called_once_with(
                [opener.nft_path, "add", "element", "inet", "knockknock", "open_ports", expected_element],
                shell=False,
            )

    def test_wait_for_requests_exits_when_port_empty(self) -> None:
        input_data = "10.0.0.99\n\n"
        stream = io.StringIO(input_data)
        mock_on_exit = MagicMock()
        opener = PortOpener(stream, openDuration=10, on_exit=mock_on_exit)

        with (
            patch("subprocess.call") as mock_subprocess_call,
            patch("syslog.syslog") as mock_syslog,
            patch("os._exit") as mock_exit,
        ):
            mock_exit.side_effect = SystemExit(4)
            with pytest.raises(SystemExit):
                opener.waitForRequests()

            mock_subprocess_call.assert_not_called()
            mock_on_exit.assert_called_once_with()
            mock_syslog.assert_called_once_with("knockknock.PortOpener: Parent process is closed.  Terminating.")
            mock_exit.assert_called_once_with(4)

    def test_wait_for_requests_exits_when_source_ip_empty(self) -> None:
        input_data = "\n8080\n"
        stream = io.StringIO(input_data)
        opener = PortOpener(stream, openDuration=10)

        with (
            patch("subprocess.call") as mock_subprocess_call,
            patch("syslog.syslog") as mock_syslog,
            patch("os._exit") as mock_exit,
        ):
            mock_exit.side_effect = SystemExit(4)
            with pytest.raises(SystemExit):
                opener.waitForRequests()

            mock_subprocess_call.assert_not_called()
            mock_syslog.assert_called_once_with("knockknock.PortOpener: Parent process is closed.  Terminating.")
            mock_exit.assert_called_once_with(4)

    @pytest.mark.parametrize(
        "invalid_ip",
        [
            "256.0.0.1",
            "10.0.0",
            "10.0.0.01",
            "10.0.0.1.2",
            "10.0.0.a",
            "-1.0.0.1",
            "abc",
            "10.0.0.300",
        ],
    )
    def test_wait_for_requests_invalid_source_ip_exits(self, invalid_ip: str) -> None:
        input_data = f"{invalid_ip}\n22\n"
        stream = io.StringIO(input_data)
        mock_on_exit = MagicMock()
        opener = PortOpener(stream, openDuration=15, on_exit=mock_on_exit)

        with (
            patch("subprocess.call") as mock_subprocess_call,
            patch("syslog.syslog") as mock_syslog,
            patch("os._exit") as mock_exit,
        ):
            mock_exit.side_effect = SystemExit(4)
            with pytest.raises(SystemExit):
                opener.waitForRequests()

            mock_subprocess_call.assert_not_called()
            mock_on_exit.assert_called_once_with()
            mock_syslog.assert_called_once_with("knockknock.PortOpener: Invalid source IP received.  Terminating.")
            mock_exit.assert_called_once_with(4)

    @pytest.mark.parametrize(
        "invalid_port",
        [
            "0",
            "65536",
            "-1",
            "abc",
            "80a",
            "99999",
        ],
    )
    def test_wait_for_requests_invalid_port_exits(self, invalid_port: str) -> None:
        input_data = f"10.0.0.1\n{invalid_port}\n"
        stream = io.StringIO(input_data)
        mock_on_exit = MagicMock()
        opener = PortOpener(stream, openDuration=15, on_exit=mock_on_exit)

        with (
            patch("subprocess.call") as mock_subprocess_call,
            patch("syslog.syslog") as mock_syslog,
            patch("os._exit") as mock_exit,
        ):
            mock_exit.side_effect = SystemExit(4)
            with pytest.raises(SystemExit):
                opener.waitForRequests()

            mock_subprocess_call.assert_not_called()
            mock_on_exit.assert_called_once_with()
            mock_syslog.assert_called_once_with("knockknock.PortOpener: Invalid port received.  Terminating.")
            mock_exit.assert_called_once_with(4)

    def test_is_valid_ipv4_boundaries(self) -> None:
        assert PortOpener._is_valid_ipv4("255.255.255.255") is True
        assert PortOpener._is_valid_ipv4("254.254.254.254") is True
        assert PortOpener._is_valid_ipv4("256.0.0.1") is False
        assert PortOpener._is_valid_ipv4("0.0.0.0") is True
        assert PortOpener._is_valid_ipv4("10.0.0") is False
        assert PortOpener._is_valid_ipv4("10.0.0.1.2") is False
        assert PortOpener._is_valid_ipv4("10.0.0.01") is False
        assert PortOpener._is_valid_ipv4("10.0.0.a") is False
        assert PortOpener._is_valid_ipv4("-1.0.0.1") is False
        assert PortOpener._is_valid_ipv4("") is False

    def test_is_valid_port_boundaries(self) -> None:
        assert PortOpener._is_valid_port("1") is True
        assert PortOpener._is_valid_port("2") is True
        assert PortOpener._is_valid_port("0") is False
        assert PortOpener._is_valid_port("65535") is True
        assert PortOpener._is_valid_port("65534") is True
        assert PortOpener._is_valid_port("65536") is False
        assert PortOpener._is_valid_port("abc") is False
        assert PortOpener._is_valid_port("") is False
        assert PortOpener._is_valid_port("-1") is False
        assert PortOpener._is_valid_port("80a") is False
