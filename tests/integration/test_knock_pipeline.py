import io
import os
import struct
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch

from knockknock.DaemonConfiguration import DaemonConfiguration
from knockknock.KnockWatcher import KnockWatcher
from knockknock.LogFile import LogFile
from knockknock.PortOpener import PortOpener
from knockknock.Profile import Profile
from knockknock.Profiles import Profiles


class TestKnockPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.daemon_dir = os.path.join(self.temp_dir.name, "knockknock.d")
        self.profiles_dir = os.path.join(self.daemon_dir, "profiles")
        os.makedirs(self.profiles_dir)

        # Create server profile for knock port 22
        self.cipher_key = b"1234567890abcdef"
        self.mac_key = b"fedcba0987654321"
        self.knock_port = 22

        self.server_profile_path = os.path.join(self.profiles_dir, "testserver")
        os.makedirs(self.server_profile_path)
        self.server_profile = Profile(
            self.server_profile_path,
            self.cipher_key,
            self.mac_key,
            0,
            self.knock_port,
        )
        self.server_profile.serialize()

        # Client profile (same keys and initial counter)
        self.client_profile_path = os.path.join(self.temp_dir.name, "client_profile")
        os.makedirs(self.client_profile_path)
        self.client_profile = Profile(
            self.client_profile_path,
            self.cipher_key,
            self.mac_key,
            0,
            self.knock_port,
        )
        self.client_profile.serialize()

        # Create config file
        self.config_path = os.path.join(self.daemon_dir, "config")
        with open(self.config_path, "w") as f:
            f.write("[main]\ndelay = 10\nerror_window = 50\n")
        self.config = DaemonConfiguration(self.config_path)

        # Create log file
        self.log_path = os.path.join(self.temp_dir.name, "kern.log")
        with open(self.log_path, "w") as f:
            f.write("")

    def tearDown(self):
        self.temp_dir.cleanup()

    def generate_log_line(self, src_ip, dst_port, id_val, seq_val, ack_val, win_val):
        return (
            f"Oct  1 12:00:00 myhost kernel: [  100.123456] "
            f"IN=eth0 OUT= MAC=00:11:22:33:44:55 SRC={src_ip} DST=10.0.0.1 "
            f"LEN=40 TOS=0x00 PREC=0x00 TTL=64 ID={id_val} PROTO=TCP "
            f"SPT=54321 DPT={dst_port} SEQ={seq_val} ACK={ack_val} "
            f"WINDOW={win_val} SYN URGP=0\n"
        )

    @patch("knockknock.PortOpener.subprocess.call")
    def test_full_knock_pipeline_opens_port_and_advances_counter(
        self, mock_subprocess_call
    ):
        mock_subprocess_call.return_value = 0

        # 1. Client encrypts knock for target port 8080
        target_port = 8080
        packed_port = struct.pack("!H", target_port)
        encrypted_data = self.client_profile.encrypt(packed_port)

        id_field, seq_field, ack_field, win_field = struct.unpack("!HIIH", encrypted_data)

        # 2. Kernel logs the packet
        src_ip = "198.51.100.42"
        log_line = self.generate_log_line(
            src_ip, self.knock_port, id_field, seq_field, ack_field, win_field
        )
        with open(self.log_path, "w") as f:
            f.write(log_line)

        # 3. Server pipeline processes the log
        profiles = Profiles(self.profiles_dir)
        pipe_r, pipe_w = os.pipe()

        sender_port_opener = PortOpener(os.fdopen(pipe_w, "w"), self.config.getDelay())
        receiver_port_opener = PortOpener(os.fdopen(pipe_r, "r"), self.config.getDelay())

        log_file = LogFile(self.log_path)

        # Run watcher for 1 line
        watcher = KnockWatcher(self.config, log_file, profiles, sender_port_opener)

        # We simulate 1 line iteration from tail
        with patch.object(log_file, "tail", return_value=[log_line]):
            watcher.tailAndProcess()

        # Close writer to allow reader EOF
        sender_port_opener.stream.close()

        # Process requests on receiver side
        with patch("os._exit", side_effect=SystemExit(4)):
            try:
                receiver_port_opener.waitForRequests()
            except SystemExit:
                pass

        # 4. Verify nftables command executed
        expected_nft_cmd = [
            receiver_port_opener.nft_path,
            "add",
            "element",
            "inet",
            "knockknock",
            "open_ports",
            f"{{ {src_ip} . {target_port} timeout {self.config.getDelay()}s }}",
        ]
        mock_subprocess_call.assert_called_once_with(
            expected_nft_cmd, shell=False
        )

        # 5. Verify server counter advanced to 1
        reloaded_server_profile = Profile(self.server_profile_path)
        self.assertEqual(reloaded_server_profile.counter, 1)

    @patch("knockknock.PortOpener.subprocess.call")
    def test_replay_attack_rejected_by_pipeline(self, mock_subprocess_call):
        target_port = 8080
        packed_port = struct.pack("!H", target_port)
        encrypted_data = self.client_profile.encrypt(packed_port)
        id_field, seq_field, ack_field, win_field = struct.unpack("!HIIH", encrypted_data)

        src_ip = "198.51.100.42"
        log_line = self.generate_log_line(
            src_ip, self.knock_port, id_field, seq_field, ack_field, win_field
        )

        profiles = Profiles(self.profiles_dir)
        mock_opener = MagicMock()
        log_file = LogFile(self.log_path)

        watcher = KnockWatcher(self.config, log_file, profiles, mock_opener)

        # First knock: succeeds
        with patch.object(log_file, "tail", return_value=[log_line]):
            watcher.tailAndProcess()

        self.assertEqual(mock_opener.open.call_count, 1)

        # Replayed second knock: fails because counter has moved forward
        mock_opener.reset_mock()
        with patch.object(log_file, "tail", return_value=[log_line]):
            watcher.tailAndProcess()

        # No open call on replay
        mock_opener.open.assert_not_called()

    @patch("knockknock.PortOpener.subprocess.call")
    def test_tampered_knock_rejected_by_pipeline(self, mock_subprocess_call):
        target_port = 8080
        packed_port = struct.pack("!H", target_port)
        encrypted_data = self.client_profile.encrypt(packed_port)
        id_field, seq_field, ack_field, win_field = struct.unpack("!HIIH", encrypted_data)

        # Tamper with seq_field
        tampered_seq = (seq_field ^ 0x12345678) & 0xFFFFFFFF

        src_ip = "198.51.100.42"
        log_line = self.generate_log_line(
            src_ip, self.knock_port, id_field, tampered_seq, ack_field, win_field
        )

        profiles = Profiles(self.profiles_dir)
        mock_opener = MagicMock()
        log_file = LogFile(self.log_path)

        watcher = KnockWatcher(self.config, log_file, profiles, mock_opener)

        with patch.object(log_file, "tail", return_value=[log_line]):
            watcher.tailAndProcess()

        mock_opener.open.assert_not_called()
