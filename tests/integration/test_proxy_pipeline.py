import asyncore
import importlib
import os
import socket
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from knockknock.Profile import Profile
from knockknock.Profiles import Profiles

import importlib.util
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent.parent / "knockknock-proxy.py"
spec = importlib.util.spec_from_file_location("knockknock_proxy", script_path)
proxy_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy_mod)
ProxyServer = proxy_mod.ProxyServer


class TestProxyPipelineIntegration(unittest.TestCase):
    def setUp(self):
        asyncore.socket_map.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.profiles_dir = os.path.join(self.temp_dir.name, "profiles")
        os.makedirs(self.profiles_dir)

        # Profile for 127.0.0.1
        self.server_profile_path = os.path.join(self.profiles_dir, "localhost")
        os.makedirs(self.server_profile_path)
        self.profile = Profile(
            self.server_profile_path,
            b"key1234567890123",
            b"mac1234567890123",
            0,
            2222,
        )
        self.profile.setIPAddrs(["127.0.0.1"])
        self.profile.serialize()

        self.profiles = Profiles(self.profiles_dir)
        for p in self.profiles.profiles:
            p.setIPAddrs(["127.0.0.1"])

        # Start a real target echo server
        self.target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.target_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.target_socket.bind(("127.0.0.1", 0))
        self.target_port = self.target_socket.getsockname()[1]
        self.target_socket.listen(5)

        # Start ProxyServer on an ephemeral port
        self.proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.proxy_socket.bind(("127.0.0.1", 0))
        self.proxy_port = self.proxy_socket.getsockname()[1]
        self.proxy_socket.close()

        self.proxy_server = ProxyServer(self.proxy_port, self.profiles)

        self.running = True
        self.asyncore_thread = threading.Thread(target=self._run_asyncore, daemon=True)
        self.asyncore_thread.start()

    def _run_asyncore(self):
        while self.running:
            asyncore.loop(timeout=0.05, count=1)

    def tearDown(self):
        self.running = False
        time.sleep(0.05)
        if hasattr(self, "proxy_server"):
            self.proxy_server.close()
        if hasattr(self, "target_socket"):
            self.target_socket.close()
        asyncore.close_all()
        asyncore.socket_map.clear()
        self.temp_dir.cleanup()

    @patch("knockknock.proxy.KnockingEndpointConnection.subprocess.call")
    @patch("knockknock.proxy.KnockingEndpointConnection.time.sleep")
    def test_socks_proxy_pipeline_with_knocking_profile(self, mock_sleep, mock_subprocess):
        mock_subprocess.return_value = 0

        # Echo server thread
        def echo_server_worker():
            conn, _ = self.target_socket.accept()
            data = conn.recv(1024)
            if data:
                conn.sendall(data + b"_ECHO")
            conn.close()

        echo_thread = threading.Thread(target=echo_server_worker, daemon=True)
        echo_thread.start()

        # Client connects to SOCKS proxy
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(3.0)
        client.connect(("127.0.0.1", self.proxy_port))

        # 1. SOCKS5 Greeting: 1 method: 0x00 No Auth
        client.sendall(b"\x05\x01\x00")
        greeting_resp = client.recv(2)
        self.assertEqual(greeting_resp, b"\x05\x00")

        # 2. SOCKS5 Connect Request to 127.0.0.1:<target_port>
        req = b"\x05\x01\x00\x01\x7f\x00\x00\x01" + struct.pack("!H", self.target_port)
        client.sendall(req)

        # 3. Receive SOCKS5 Success Response (blocks until knock and connect complete)
        connect_resp = client.recv(10)
        self.assertEqual(connect_resp[:4], b"\x05\x00\x00\x01")

        self.assertTrue(mock_subprocess.called)
        called_cmd = mock_subprocess.call_args[0][0]
        self.assertEqual(called_cmd[0], "hping3")
        self.assertIn("-p", called_cmd)
        port_index = called_cmd.index("-p") + 1
        self.assertEqual(called_cmd[port_index], "2222")  # Knock port

        # 4. Stream data bidirectional
        client.sendall(b"HELLO_SOCKS")
        echo_thread.join(timeout=2.0)

        response = client.recv(1024)
        self.assertEqual(response, b"HELLO_SOCKS_ECHO")
        client.close()

    @patch("knockknock.proxy.KnockingEndpointConnection.subprocess.call")
    def test_socks_proxy_pipeline_direct_without_profile(self, mock_subprocess):
        # Empty profiles
        empty_dir = tempfile.mkdtemp()
        self.proxy_server.profiles = Profiles(empty_dir)

        def echo_server_worker():
            conn, _ = self.target_socket.accept()
            data = conn.recv(1024)
            if data:
                conn.sendall(b"DIRECT_" + data)
            conn.close()

        echo_thread = threading.Thread(target=echo_server_worker, daemon=True)
        echo_thread.start()

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(3.0)
        client.connect(("127.0.0.1", self.proxy_port))

        client.sendall(b"\x05\x01\x00")
        greeting_resp = client.recv(2)
        self.assertEqual(greeting_resp, b"\x05\x00")

        req = b"\x05\x01\x00\x01\x7f\x00\x00\x01" + struct.pack("!H", self.target_port)
        client.sendall(req)

        connect_resp = client.recv(10)
        self.assertEqual(connect_resp[:4], b"\x05\x00\x00\x01")

        # No knock should have been sent
        mock_subprocess.assert_not_called()

        client.sendall(b"REQUEST")
        echo_thread.join(timeout=2.0)

        response = client.recv(1024)
        self.assertEqual(response, b"DIRECT_REQUEST")
        client.close()
