import asyncio
import importlib.util
import os
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from knockknock.Profile import Profile
from knockknock.Profiles import Profiles

script_path = Path(__file__).resolve().parent.parent.parent / "knockknock-proxy.py"
spec = importlib.util.spec_from_file_location("knockknock_proxy", script_path)
assert spec is not None and spec.loader is not None
proxy_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy_mod)
ProxyServer = proxy_mod.ProxyServer


class TestProxyPipelineIntegration(unittest.TestCase):
    def setUp(self):
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

        self.server_ready = threading.Event()
        self.proxy_server = ProxyServer(self.proxy_port, self.profiles)
        self.loop = asyncio.new_event_loop()
        self.server_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.server_thread.start()
        self.server_ready.wait(timeout=5.0)

    def _run_event_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.proxy_server.start())
        self.server_ready.set()
        self.loop.run_forever()

    def tearDown(self):
        if hasattr(self, "loop") and self.loop.is_running():
            if hasattr(self, "proxy_server"):
                self.loop.call_soon_threadsafe(self.proxy_server.close)
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.server_thread.join(timeout=2.0)
        elif hasattr(self, "proxy_server"):
            self.proxy_server.close()
        if hasattr(self, "target_socket"):
            self.target_socket.close()
        self.temp_dir.cleanup()

    @patch("knockknock.proxy.KnockingEndpointConnection.send_syn")
    @patch("knockknock.proxy.KnockingEndpointConnection.time.sleep")
    def test_socks_proxy_pipeline_with_knocking_profile(self, mock_sleep, mock_send_syn):
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

        self.assertTrue(mock_send_syn.called)
        called_args = mock_send_syn.call_args[0]
        self.assertEqual(called_args[0], "127.0.0.1")
        self.assertEqual(called_args[1], 2222)  # Knock port

        # 4. Stream data bidirectional
        client.sendall(b"HELLO_SOCKS")
        echo_thread.join(timeout=2.0)

        response = client.recv(1024)
        self.assertEqual(response, b"HELLO_SOCKS_ECHO")
        client.close()

    @patch("knockknock.proxy.KnockingEndpointConnection.send_syn")
    def test_socks_proxy_pipeline_direct_without_profile(self, mock_send_syn):
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
        mock_send_syn.assert_not_called()

        client.sendall(b"REQUEST")
        echo_thread.join(timeout=2.0)

        response = client.recv(1024)
        self.assertEqual(response, b"DIRECT_REQUEST")
        client.close()
