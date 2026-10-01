import asyncio
import struct
import unittest
from unittest.mock import MagicMock, patch

from knockknock.proxy.EndpointConnection import EndpointConnection
from knockknock.proxy.KnockingEndpointConnection import KnockingEndpointConnection


class TestEndpointConnection(unittest.TestCase):

    def setUp(self):
        self.mock_shuttle = MagicMock()
        self.conn = EndpointConnection(self.mock_shuttle, "127.0.0.1", 8080)

    def test_init_state(self):
        self.assertEqual(self.conn.destination, ("127.0.0.1", 8080))
        self.assertEqual(self.conn.buffer, b"")
        self.assertFalse(self.conn.closed)
        self.assertEqual(self.conn.connectAttempts, 0)
        self.assertIs(self.conn.shuttle, self.mock_shuttle)
        self.assertIsNone(self.conn.reader)
        self.assertIsNone(self.conn.writer)

    def test_async_connect_success(self):
        async def _run():
            with patch("asyncio.open_connection") as mock_open:
                mock_reader = MagicMock()
                mock_writer = MagicMock()
                mock_sock = MagicMock()
                mock_sock.getsockname.return_value = ("192.168.1.10", 12345)
                mock_writer.get_extra_info.return_value = mock_sock
                mock_open.return_value = (mock_reader, mock_writer)

                self.assertFalse(self.conn.closed)
                result = await self.conn.connect()
                self.assertIs(result, True)
                self.assertEqual(self.conn.connectAttempts, 1)
                self.assertIs(self.conn.reader, mock_reader)
                self.assertIs(self.conn.writer, mock_writer)
                self.mock_shuttle.connectSucceeded.assert_called_once_with("192.168.1.10", 12345)

        asyncio.run(_run())

    def test_async_connect_retries_and_fails(self):
        async def _run():
            self.assertFalse(self.conn.closed)
            with patch("asyncio.open_connection", side_effect=OSError("connection refused")):
                with patch.object(self.conn, "reconnect_hook") as mock_hook:
                    result = await self.conn.connect()
                    self.assertIs(result, False)
                    self.assertEqual(self.conn.connectAttempts, 3)
                    self.assertEqual(mock_hook.call_count, 2)
                    self.assertTrue(self.conn.closed)
                    self.mock_shuttle.handle_close.assert_called_once()

        asyncio.run(_run())

    def test_getsockname_fallback_and_writer(self):
        self.assertEqual(self.conn.getsockname(), ("127.0.0.1", 0))

        mock_writer = MagicMock()
        mock_writer.get_extra_info.return_value = None
        self.conn.writer = mock_writer
        self.assertEqual(self.conn.getsockname(), ("127.0.0.1", 0))

        mock_sock = MagicMock()
        mock_sock.getsockname.return_value = ("10.0.0.2", 9999)
        mock_writer.get_extra_info.return_value = mock_sock
        self.assertEqual(self.conn.getsockname(), ("10.0.0.2", 9999))

    def test_handle_connect(self):
        with patch.object(self.conn, "getsockname", return_value=("192.168.1.50", 54321)):
            self.conn.handle_connect()
            self.mock_shuttle.connectSucceeded.assert_called_once_with("192.168.1.50", 54321)

    def test_handle_close(self):
        mock_writer = MagicMock()
        self.conn.writer = mock_writer

        self.assertFalse(self.conn.closed)
        self.conn.handle_close()
        self.assertTrue(self.conn.closed)
        self.mock_shuttle.handle_close.assert_called_once()
        mock_writer.close.assert_called_once()
        self.assertIsNone(self.conn.writer)
        self.assertIsNone(self.conn.reader)

        # Second close should be no-op
        self.mock_shuttle.handle_close.reset_mock()
        mock_writer.close.reset_mock()
        self.conn.handle_close()
        self.mock_shuttle.handle_close.assert_not_called()
        mock_writer.close.assert_not_called()

    def test_close_handles_oserror(self):
        mock_writer = MagicMock()
        mock_writer.close.side_effect = OSError("close error")
        self.conn.writer = mock_writer
        self.conn.close()
        self.assertIsNone(self.conn.writer)

    def test_handle_error(self):
        with patch.object(self.conn, "reconnect") as mock_reconnect:
            self.conn.handle_error()
            mock_reconnect.assert_called_once()

    def test_reconnect_attempts_under_limit(self):
        self.assertEqual(self.conn.connectAttempts, 0)

        # 1st reconnect
        self.conn.reconnect()
        self.assertEqual(self.conn.connectAttempts, 1)

        # 2nd reconnect
        self.conn.reconnect()
        self.assertEqual(self.conn.connectAttempts, 2)

        # 3rd reconnect
        self.conn.reconnect()
        self.assertEqual(self.conn.connectAttempts, 3)

        # 4th reconnect - should not proceed as connectAttempts is now 3
        self.conn.reconnect()
        self.assertEqual(self.conn.connectAttempts, 3)

    def test_reconnect_hook_default_noop(self):
        self.conn.reconnect_hook()

    def test_handle_read(self):
        self.conn.handle_read(b"incoming payload")
        self.mock_shuttle.receivedData.assert_called_once_with(b"incoming payload")

        self.conn.handle_read(None)
        self.mock_shuttle.receivedData.assert_called_with(b"")

    def test_write_when_open(self):
        mock_writer = MagicMock()
        self.conn.writer = mock_writer
        self.conn.closed = False
        self.conn.write(b"data to send")
        mock_writer.write.assert_called_once_with(b"data to send")

    def test_write_when_closed(self):
        mock_writer = MagicMock()
        self.conn.writer = mock_writer
        self.conn.closed = True
        self.conn.write(b"data to send")
        mock_writer.write.assert_not_called()


class TestKnockingEndpointConnection(unittest.TestCase):

    @patch("knockknock.proxy.KnockingEndpointConnection.time.sleep")
    @patch("knockknock.proxy.KnockingEndpointConnection.subprocess.call")
    def test_init_and_send_knock(self, mock_subproc, mock_sleep):
        mock_shuttle = MagicMock()
        mock_profile = MagicMock()
        mock_profile.getKnockPort.return_value = 22
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
    def test_reconnect_sends_knock(self, mock_subproc, mock_sleep):
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
        self.assertEqual(knocking_conn.connectAttempts, 1)

    @patch("knockknock.proxy.KnockingEndpointConnection.time.sleep")
    @patch("knockknock.proxy.KnockingEndpointConnection.subprocess.call")
    def test_reconnect_hook_sends_knock(self, mock_subproc, mock_sleep):
        mock_shuttle = MagicMock()
        mock_profile = MagicMock()
        mock_profile.getKnockPort.return_value = 22
        mock_profile.encrypt.return_value = struct.pack("!HIIH", 1, 2, 3, 4)

        knocking_conn = KnockingEndpointConnection(
            mock_shuttle, mock_profile, "10.0.0.5", 443
        )
        self.assertEqual(mock_profile.encrypt.call_count, 1)

        knocking_conn.reconnect_hook()
        self.assertEqual(mock_profile.encrypt.call_count, 2)
