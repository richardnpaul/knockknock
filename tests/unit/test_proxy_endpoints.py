import asyncore
import socket
import struct
import unittest
from unittest.mock import MagicMock, patch

from knockknock.proxy.EndpointConnection import EndpointConnection
from knockknock.proxy.KnockingEndpointConnection import KnockingEndpointConnection


class TestEndpointConnection(unittest.TestCase):
    @patch.object(EndpointConnection, "connect")
    @patch.object(EndpointConnection, "create_socket")
    def setUp(self, mock_create_socket, mock_connect):
        asyncore.socket_map.clear()
        self.mock_shuttle = MagicMock()
        self.conn = EndpointConnection(self.mock_shuttle, "127.0.0.1", 8080)
        self.conn.socket = MagicMock()

    def tearDown(self):
        asyncore.socket_map.clear()

    def test_init_state(self):
        self.assertEqual(self.conn.destination, ("127.0.0.1", 8080))
        self.assertEqual(self.conn.buffer, b"")
        self.assertFalse(self.conn.closed)
        self.assertEqual(self.conn.connectAttempts, 0)
        self.assertIs(self.conn.shuttle, self.mock_shuttle)

    def test_handle_connect(self):
        self.conn.socket.getsockname.return_value = ("192.168.1.50", 54321)
        self.conn.handle_connect()
        self.mock_shuttle.connectSucceeded.assert_called_once_with("192.168.1.50", 54321)

    @patch.object(EndpointConnection, "close")
    def test_handle_close(self, mock_close):
        self.assertFalse(self.conn.closed)
        self.conn.handle_close()
        self.assertTrue(self.conn.closed)
        self.mock_shuttle.handle_close.assert_called_once()
        mock_close.assert_called_once()

        # Second close should be no-op
        self.mock_shuttle.handle_close.reset_mock()
        mock_close.reset_mock()
        self.conn.handle_close()
        self.mock_shuttle.handle_close.assert_not_called()
        mock_close.assert_not_called()

    @patch.object(EndpointConnection, "reconnect")
    def test_handle_error(self, mock_reconnect):
        self.conn.handle_error()
        mock_reconnect.assert_called_once()

    @patch.object(EndpointConnection, "connect")
    @patch.object(EndpointConnection, "create_socket")
    @patch.object(EndpointConnection, "close")
    def test_reconnect_attempts_under_limit(self, mock_close, mock_create_socket, mock_connect):
        self.assertEqual(self.conn.connectAttempts, 0)
        
        # 1st reconnect
        self.conn.reconnect()
        self.assertEqual(self.conn.connectAttempts, 1)
        mock_close.assert_called_once()
        mock_create_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_connect.assert_called_once_with(("127.0.0.1", 8080))

        # 2nd reconnect
        self.conn.reconnect()
        self.assertEqual(self.conn.connectAttempts, 2)
        self.assertEqual(mock_close.call_count, 2)

        # 3rd reconnect
        self.conn.reconnect()
        self.assertEqual(self.conn.connectAttempts, 3)
        self.assertEqual(mock_close.call_count, 3)

        # 4th reconnect - should not proceed as connectAttempts is now 3 (not < 3)
        self.conn.reconnect()
        self.assertEqual(self.conn.connectAttempts, 3)
        self.assertEqual(mock_close.call_count, 3)

    @patch.object(EndpointConnection, "recv")
    def test_handle_read(self, mock_recv):
        mock_recv.return_value = b"incoming payload"
        self.conn.handle_read()
        mock_recv.assert_called_once_with(4096)
        self.mock_shuttle.receivedData.assert_called_once_with(b"incoming payload")

    @patch.object(EndpointConnection, "send")
    def test_write_when_open(self, mock_send):
        self.conn.closed = False
        self.conn.write(b"data to send")
        mock_send.assert_called_once_with(b"data to send")

    @patch.object(EndpointConnection, "send")
    def test_write_when_closed(self, mock_send):
        self.conn.closed = True
        self.conn.write(b"data to send")
        mock_send.assert_not_called()


class TestKnockingEndpointConnection(unittest.TestCase):
    @patch("knockknock.proxy.KnockingEndpointConnection.time.sleep")
    @patch("knockknock.proxy.KnockingEndpointConnection.subprocess.call")
    @patch.object(EndpointConnection, "connect")
    @patch.object(EndpointConnection, "create_socket")
    def test_init_and_send_knock(self, mock_create_socket, mock_connect, mock_subproc, mock_sleep):
        mock_shuttle = MagicMock()
        mock_profile = MagicMock()
        mock_profile.getKnockPort.return_value = 22
        # Pack 12 bytes for !HIIH: id=100, seq=200000, ack=300000, win=4096
        encrypted_bytes = struct.pack("!HIIH", 100, 200000, 300000, 4096)
        mock_profile.encrypt.return_value = encrypted_bytes

        knocking_conn = KnockingEndpointConnection(
            mock_shuttle, mock_profile, "192.168.1.200", 80
        )

        mock_profile.encrypt.assert_called_once_with(struct.pack("!H", 80))
        mock_profile.getKnockPort.assert_called_once()
        mock_sleep.assert_called_once_with(0.25)

        expected_command = [
            "hping3", "-q", "-S", "-c", "1",
            "-p", "22",
            "-N", "100",
            "-w", "4096",
            "-M", "200000",
            "-L", "300000",
            "192.168.1.200"
        ]
        self.assertTrue(mock_subproc.called)
        called_args, called_kwargs = mock_subproc.call_args
        self.assertEqual(called_args[0], expected_command)
        self.assertEqual(called_kwargs["shell"], False)

        self.assertEqual(knocking_conn.host, "192.168.1.200")
        self.assertEqual(knocking_conn.port, 80)
        self.assertIs(knocking_conn.profile, mock_profile)

    @patch("knockknock.proxy.KnockingEndpointConnection.time.sleep")
    @patch("knockknock.proxy.KnockingEndpointConnection.subprocess.call")
    @patch.object(EndpointConnection, "connect")
    @patch.object(EndpointConnection, "create_socket")
    @patch.object(EndpointConnection, "reconnect")
    def test_reconnect_sends_knock(self, mock_parent_reconnect, mock_create_socket, mock_connect, mock_subproc, mock_sleep):
        mock_shuttle = MagicMock()
        mock_profile = MagicMock()
        mock_profile.getKnockPort.return_value = 22
        mock_profile.encrypt.return_value = struct.pack("!HIIH", 1, 2, 3, 4)

        knocking_conn = KnockingEndpointConnection(
            mock_shuttle, mock_profile, "10.0.0.5", 443
        )
        self.assertEqual(mock_profile.encrypt.call_count, 1)

        knocking_conn.reconnect()
        self.assertEqual(mock_profile.encrypt.call_count, 2)
        mock_parent_reconnect.assert_called_once()
