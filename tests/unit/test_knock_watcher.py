import unittest
from unittest.mock import MagicMock, patch

from knockknock.KnockWatcher import KnockWatcher
from knockknock.MacFailedException import MacFailedException


class TestKnockWatcher(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock()
        self.mock_config.getWindow.return_value = 100
        self.mock_log_file = MagicMock()
        self.mock_profiles = MagicMock()
        self.mock_port_opener = MagicMock()

        self.watcher = KnockWatcher(self.mock_config, self.mock_log_file, self.mock_profiles, self.mock_port_opener)

    @patch("knockknock.KnockWatcher.syslog.syslog")
    @patch("knockknock.KnockWatcher.LogEntry")
    def test_tail_and_process_successful_knock(self, mock_log_entry_cls, mock_syslog):
        mock_entry = MagicMock()
        mock_entry.getDestinationPort.return_value = 22
        mock_entry.getEncryptedData.return_value = b"ciphertext_16bytes"
        mock_entry.getSourceIP.return_value = "192.168.1.100"
        mock_log_entry_cls.return_value = mock_entry

        mock_profile = MagicMock()
        mock_profile.decrypt.return_value = 2222
        self.mock_profiles.getProfileForPort.return_value = mock_profile

        self.mock_log_file.tail.return_value = ["line1"]

        self.watcher.tailAndProcess()

        mock_log_entry_cls.assert_called_once_with("line1")
        self.mock_profiles.getProfileForPort.assert_called_once_with(22)
        mock_profile.decrypt.assert_called_once_with(b"ciphertext_16bytes", 100)
        self.mock_port_opener.open.assert_called_once_with("192.168.1.100", 2222)
        mock_syslog.assert_called_once_with("Received authenticated port-knock for port 2222 from 192.168.1.100")

    @patch("knockknock.KnockWatcher.syslog.syslog")
    @patch("knockknock.KnockWatcher.LogEntry")
    def test_tail_and_process_profile_none(self, mock_log_entry_cls, mock_syslog):
        mock_entry = MagicMock()
        mock_entry.getDestinationPort.return_value = 80
        mock_log_entry_cls.return_value = mock_entry

        self.mock_profiles.getProfileForPort.return_value = None
        self.mock_log_file.tail.return_value = ["line_unmatched_port"]

        self.watcher.tailAndProcess()

        self.mock_port_opener.open.assert_not_called()
        mock_syslog.assert_not_called()

    @patch("knockknock.KnockWatcher.syslog.syslog")
    @patch("knockknock.KnockWatcher.LogEntry")
    def test_tail_and_process_mac_failed(self, mock_log_entry_cls, mock_syslog):
        mock_entry = MagicMock()
        mock_entry.getDestinationPort.return_value = 22
        mock_entry.getEncryptedData.return_value = b"corrupt"
        mock_log_entry_cls.return_value = mock_entry

        mock_profile = MagicMock()
        mock_profile.decrypt.side_effect = MacFailedException()
        self.mock_profiles.getProfileForPort.return_value = mock_profile

        self.mock_log_file.tail.return_value = ["line_corrupt_mac"]

        self.watcher.tailAndProcess()

        mock_profile.decrypt.assert_called_once_with(b"corrupt", 100)
        self.mock_port_opener.open.assert_not_called()
        mock_syslog.assert_not_called()

    @patch("knockknock.KnockWatcher.syslog.syslog")
    @patch("knockknock.KnockWatcher.LogEntry")
    def test_tail_and_process_unrecognized_line_exception(self, mock_log_entry_cls, mock_syslog):
        mock_log_entry_cls.side_effect = ValueError("Invalid line format")
        self.mock_log_file.tail.return_value = ["bogus line"]

        self.watcher.tailAndProcess()

        self.mock_port_opener.open.assert_not_called()
        mock_syslog.assert_called_once_with("knocknock skipping unrecognized line.")

    @patch("knockknock.KnockWatcher.syslog.syslog")
    @patch("knockknock.KnockWatcher.LogEntry")
    def test_tail_and_process_multiple_lines_mixed(self, mock_log_entry_cls, mock_syslog):
        def log_entry_side_effect(line):
            if line == "invalid":
                raise ValueError("Bad")
            entry = MagicMock()
            if line == "valid":
                entry.getDestinationPort.return_value = 22
                entry.getEncryptedData.return_value = b"data"
                entry.getSourceIP.return_value = "10.0.0.1"
            else:
                entry.getDestinationPort.return_value = 999
            return entry

        mock_log_entry_cls.side_effect = log_entry_side_effect

        mock_profile = MagicMock()
        mock_profile.decrypt.return_value = 8080

        def get_profile_side_effect(port):
            if port == 22:
                return mock_profile
            return None

        self.mock_profiles.getProfileForPort.side_effect = get_profile_side_effect
        self.mock_log_file.tail.return_value = ["invalid", "noprofile", "valid"]

        self.watcher.tailAndProcess()

        self.mock_port_opener.open.assert_called_once_with("10.0.0.1", 8080)
        mock_syslog.assert_any_call("knocknock skipping unrecognized line.")
        mock_syslog.assert_any_call("Received authenticated port-knock for port 8080 from 10.0.0.1")
