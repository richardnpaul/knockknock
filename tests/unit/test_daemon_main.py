import importlib.util
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

daemon_path = Path(__file__).resolve().parent.parent.parent / "knockknock-daemon.py"
spec = importlib.util.spec_from_file_location("knockknock_daemon", str(daemon_path))
assert spec is not None and spec.loader is not None
knockknock_daemon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(knockknock_daemon)


class TestDaemonMain:
    def test_handle_firewall_initialises_nft_and_attaches_signal_handlers(self) -> None:
        mock_nft_setup = MagicMock()
        mock_config = MagicMock()
        mock_config.getDelay.return_value = 15
        mock_stream = MagicMock()
        mock_port_opener = MagicMock()

        signal_handlers = {}

        def fake_signal(sig, handler):
            signal_handlers[sig] = handler

        with (
            patch.object(knockknock_daemon, "NftSetup", return_value=mock_nft_setup) as mock_nft_cls,
            patch("signal.signal", side_effect=fake_signal),
            patch.object(knockknock_daemon, "PortOpener", return_value=mock_port_opener) as mock_opener_cls,
        ):
            knockknock_daemon.handleFirewall(mock_stream, mock_config)

            mock_nft_cls.assert_called_once_with()
            mock_nft_setup.initialise.assert_called_once_with()
            mock_opener_cls.assert_called_once_with(mock_stream, 15, on_exit=mock_nft_setup.teardown)
            mock_port_opener.waitForRequests.assert_called_once_with()
            mock_nft_setup.teardown.assert_called_once_with()

            # Verify signal handlers registered
            assert signal.SIGTERM in signal_handlers
            assert signal.SIGINT in signal_handlers

            # Test SIGTERM handler invokes teardown and exits
            with patch("os._exit") as mock_exit:
                mock_nft_setup.reset_mock()
                signal_handlers[signal.SIGTERM](signal.SIGTERM, None)
                mock_nft_setup.teardown.assert_called_once_with()
                mock_exit.assert_called_once_with(0)

            # Test SIGINT handler invokes teardown and exits
            with patch("os._exit") as mock_exit:
                mock_nft_setup.reset_mock()
                signal_handlers[signal.SIGINT](signal.SIGINT, None)
                mock_nft_setup.teardown.assert_called_once_with()
                mock_exit.assert_called_once_with(0)

    def test_handle_firewall_teardown_on_exception(self) -> None:
        mock_nft_setup = MagicMock()
        mock_config = MagicMock()
        mock_config.getDelay.return_value = 15
        mock_stream = MagicMock()
        mock_port_opener = MagicMock()
        mock_port_opener.waitForRequests.side_effect = RuntimeError("stream error")

        with (
            patch.object(knockknock_daemon, "NftSetup", return_value=mock_nft_setup),
            patch("signal.signal"),
            patch.object(knockknock_daemon, "PortOpener", return_value=mock_port_opener),
        ):
            with pytest.raises(RuntimeError):
                knockknock_daemon.handleFirewall(mock_stream, mock_config)

            mock_nft_setup.teardown.assert_called_once_with()
