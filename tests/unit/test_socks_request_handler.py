import asyncio
import io
import struct
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from knockknock.proxy.SocksRequestHandler import SocksRequestHandler


class TestSocksRequestHandler(unittest.TestCase):
    def setUp(self):
        self.mock_sock = MagicMock()
        self.mock_profiles = MagicMock()
        self.handler = SocksRequestHandler(self.mock_sock, self.mock_profiles)
        self.handler.push = MagicMock()

    def test_init(self):
        self.assertEqual(self.handler.INITIAL_HEADER_LEN, 2)
        self.assertEqual(self.handler.REQUEST_HEADER_LEN, 4)
        self.assertEqual(self.handler.state, 0)
        self.assertIsNone(self.handler.endpoint)
        self.assertEqual(self.handler.input, [])

    def test_init_with_reader_writer(self):
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_profiles = MagicMock()
        handler = SocksRequestHandler(mock_reader, mock_writer, mock_profiles)
        self.assertIs(handler.reader, mock_reader)
        self.assertIs(handler.writer, mock_writer)
        self.assertIs(handler.profiles, mock_profiles)

    def test_byte_helper(self):
        self.assertEqual(self.handler._byte(65), 65)
        self.assertEqual(self.handler._byte("A"), 65)
        self.assertEqual(self.handler._byte(b"A"), 65)
        self.assertEqual(self.handler._byte(bytearray(b"A")), 65)

    def test_send_success_response(self):
        self.handler.sendSuccessResponse("192.168.1.1", 8080)
        expected = b"\x05\x00\x00\x01\xc0\xa8\x01\x01" + struct.pack("!H", 8080)
        self.handler.push.assert_called_once_with(expected)

    def test_send_command_not_supported_response(self):
        self.handler.sendCommandNotSupportedResponse()
        expected = b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00"
        self.handler.push.assert_called_once_with(expected)

    def test_send_address_not_supported_response(self):
        self.handler.sendAddressNotSupportedResponse()
        expected = b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00"
        self.handler.push.assert_called_once_with(expected)

    def test_send_authentication_response(self):
        self.handler.sendAuthenticationResponse(0x00)
        self.handler.push.assert_called_once_with(b"\x05\x00")

    def test_process_headers_valid_version_5(self):
        self.handler.input = b"\x05\x02"
        method_count = self.handler.processHeaders()
        self.assertEqual(method_count, 2)

    @patch.object(SocksRequestHandler, "handle_close")
    def test_process_headers_invalid_version(self, mock_close):
        self.handler.input = b"\x04\x01"
        res = self.handler.processHeaders()
        self.assertIsNone(res)
        mock_close.assert_called_once()

    def test_process_auth_method_success_no_auth(self):
        self.handler.input = b"\x02\x00"
        res = self.handler.processAuthenticationMethod()
        self.assertEqual(res, self.handler.REQUEST_HEADER_LEN)
        self.handler.push.assert_called_once_with(b"\x05\x00")

    @patch.object(SocksRequestHandler, "handle_close")
    def test_process_auth_method_failure_no_supported_auth(self, mock_close):
        self.handler.input = b"\x02\x01"
        res = self.handler.processAuthenticationMethod()
        self.assertIsNone(res)
        self.handler.push.assert_called_once_with(b"\x05\xff")
        mock_close.assert_called_once()

    @patch.object(SocksRequestHandler, "handle_close")
    def test_process_request_header_unsupported_command(self, mock_close):
        # Command 0x02 (BIND)
        self.handler.input = b"\x05\x02\x00\x01"
        res = self.handler.processRequestHeader()
        self.assertIsNone(res)
        self.handler.push.assert_called_once_with(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
        mock_close.assert_called_once()

    def test_process_request_header_ipv4(self):
        self.handler.state = 2
        # Command 0x01 (CONNECT), addressType 0x01 (IPv4)
        self.handler.input = b"\x05\x01\x00\x01"
        res = self.handler.processRequestHeader()
        self.assertEqual(res, 6)
        self.assertEqual(self.handler.state, 3)

    def test_process_request_header_domain(self):
        self.handler.state = 2
        # Command 0x01 (CONNECT), addressType 0x03 (Domain name)
        self.handler.input = b"\x05\x01\x00\x03"
        res = self.handler.processRequestHeader()
        self.assertEqual(res, 1)
        self.assertEqual(self.handler.state, 2)

    @patch.object(SocksRequestHandler, "handle_close")
    def test_process_request_header_unsupported_address_type(self, mock_close):
        # Command 0x01 (CONNECT), addressType 0x04 (IPv6)
        self.handler.input = b"\x05\x01\x00\x04"
        res = self.handler.processRequestHeader()
        self.assertIsNone(res)
        self.handler.push.assert_called_once_with(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
        mock_close.assert_called_once()

    def test_process_address_header(self):
        # 11 bytes domain length
        self.handler.input = b"\x0b"
        res = self.handler.processAddressHeader()
        self.assertEqual(res, 13)

    @patch("knockknock.proxy.SocksRequestHandler.EndpointConnection")
    @patch.object(SocksRequestHandler, "set_terminator")
    def test_process_address_and_port_ipv4_no_profile(self, mock_set_term, mock_endpoint_cls):
        self.mock_profiles.getProfileForIP.return_value = None
        self.handler.addressType = 0x01
        # 127.0.0.1:8080 (0x1f90 = 8080)
        self.handler.input = b"\x7f\x00\x00\x01\x1f\x90"

        self.handler.processAddressAndPort()

        self.assertEqual(self.handler.address, "127.0.0.1")
        self.assertEqual(self.handler.port, 8080)
        self.mock_profiles.getProfileForIP.assert_called_once_with("127.0.0.1")
        self.mock_profiles.getProfileForName.assert_not_called()
        mock_set_term.assert_called_once_with(None)
        mock_endpoint_cls.assert_called_once_with(self.handler, "127.0.0.1", 8080)
        self.assertEqual(self.handler.endpoint, mock_endpoint_cls.return_value)

    @patch("knockknock.proxy.SocksRequestHandler.KnockingEndpointConnection")
    @patch.object(SocksRequestHandler, "set_terminator")
    def test_process_address_and_port_ipv4_with_profile(self, mock_set_term, mock_knocking_cls):
        mock_profile = MagicMock()
        self.mock_profiles.getProfileForIP.return_value = mock_profile
        self.handler.addressType = 0x01
        self.handler.input = b"\x0a\x00\x00\x02\x00\x16"  # 10.0.0.2:22

        self.handler.processAddressAndPort()

        self.assertEqual(self.handler.address, "10.0.0.2")
        self.assertEqual(self.handler.port, 22)
        self.mock_profiles.getProfileForIP.assert_called_once_with("10.0.0.2")
        self.mock_profiles.getProfileForName.assert_not_called()
        mock_set_term.assert_called_once_with(None)
        mock_knocking_cls.assert_called_once_with(self.handler, mock_profile, "10.0.0.2", 22)
        self.assertEqual(self.handler.endpoint, mock_knocking_cls.return_value)

    @patch("knockknock.proxy.SocksRequestHandler.EndpointConnection")
    @patch.object(SocksRequestHandler, "set_terminator")
    def test_process_address_and_port_domain_no_profile(self, mock_set_term, mock_endpoint_cls):
        self.mock_profiles.getProfileForName.return_value = None
        self.handler.addressType = 0x03
        self.handler.input = b"example.com\x01\xbb"  # example.com:443

        self.handler.processAddressAndPort()

        self.assertEqual(self.handler.address, "example.com")
        self.assertEqual(self.handler.port, 443)
        self.mock_profiles.getProfileForName.assert_called_once_with("example.com")
        self.mock_profiles.getProfileForIP.assert_not_called()
        mock_set_term.assert_called_once_with(None)
        mock_endpoint_cls.assert_called_once_with(self.handler, "example.com", 443)

    @patch("knockknock.proxy.SocksRequestHandler.KnockingEndpointConnection")
    @patch.object(SocksRequestHandler, "set_terminator")
    def test_process_address_and_port_domain_with_profile(self, mock_set_term, mock_knocking_cls):
        mock_profile = MagicMock()
        self.mock_profiles.getProfileForName.return_value = mock_profile
        self.handler.addressType = 0x03
        self.handler.input = b"secret.internal\x1f\x90"  # 8080

        self.handler.processAddressAndPort()

        self.assertEqual(self.handler.address, "secret.internal")
        self.assertEqual(self.handler.port, 8080)
        self.mock_profiles.getProfileForName.assert_called_once_with("secret.internal")
        self.mock_profiles.getProfileForIP.assert_not_called()
        mock_set_term.assert_called_once_with(None)
        mock_knocking_cls.assert_called_once_with(self.handler, mock_profile, "secret.internal", 8080)

    @patch("knockknock.proxy.SocksRequestHandler.EndpointConnection")
    def test_setup_endpoint_unknown_address_type(self, mock_endpoint_cls):
        self.handler.addressType = 0x99
        self.handler.address = "unknown"
        self.handler.port = 1234
        self.handler.setupEndpoint()
        self.mock_profiles.getProfileForIP.assert_not_called()
        self.mock_profiles.getProfileForName.assert_not_called()
        mock_endpoint_cls.assert_called_once_with(self.handler, "unknown", 1234)

    @patch("knockknock.proxy.SocksRequestHandler.EndpointConnection")
    @patch.object(SocksRequestHandler, "set_terminator")
    def test_process_address_and_port_string_addr_bytes(self, mock_set_term, mock_endpoint_cls):
        self.mock_profiles.getProfileForName.return_value = None
        self.handler.addressType = 0x03
        # String input instead of bytes
        self.handler.input = "host.test\x00\x50"

        self.handler.processAddressAndPort()

        self.assertEqual(self.handler.address, "host.test")
        self.assertEqual(self.handler.port, 80)

    def test_collect_incoming_data_buffering_when_no_endpoint(self):
        self.handler.endpoint = None
        self.handler.collect_incoming_data(b"chunk1")
        self.handler.collect_incoming_data(b"chunk2")
        self.assertEqual(self.handler.input, [b"chunk1", b"chunk2"])

    def test_collect_incoming_data_forwarding_when_endpoint_present(self):
        mock_endpoint = MagicMock()
        self.handler.endpoint = mock_endpoint
        self.handler.collect_incoming_data(b"stream_data")
        mock_endpoint.write.assert_called_once_with(b"stream_data")
        self.assertEqual(self.handler.input, [])

    def test_collect_incoming_data_when_input_not_list(self):
        self.handler.endpoint = None
        self.handler.input = b"init"
        self.handler.collect_incoming_data(b"next")
        self.assertEqual(self.handler.input, [b"init", b"next"])

    def test_handle_close_with_endpoint(self):
        mock_endpoint = MagicMock()
        mock_writer = MagicMock()
        self.handler.endpoint = mock_endpoint
        self.handler.writer = mock_writer

        self.handler.handle_close()
        self.assertTrue(self.handler.closed)
        mock_endpoint.handle_close.assert_called_once()
        mock_writer.close.assert_called_once()
        self.assertIsNone(self.handler.writer)
        self.assertIsNone(self.handler.reader)

        # Idempotent close
        mock_endpoint.handle_close.reset_mock()
        mock_writer.close.reset_mock()
        self.handler.handle_close()
        mock_endpoint.handle_close.assert_not_called()
        mock_writer.close.assert_not_called()

    def test_handle_close_without_endpoint(self):
        self.handler.endpoint = None
        mock_writer = MagicMock()
        mock_writer.close.side_effect = OSError("close fail")
        self.handler.writer = mock_writer

        self.handler.handle_close()
        self.assertTrue(self.handler.closed)
        self.assertIsNone(self.handler.writer)

    def test_connect_succeeded(self):
        self.handler.connectSucceeded("10.0.0.1", 1234)
        expected = b"\x05\x00\x00\x01\x0a\x00\x00\x01" + struct.pack("!H", 1234)
        self.handler.push.assert_called_once_with(expected)

    def test_received_data(self):
        self.handler.receivedData(b"server_reply")
        self.handler.push.assert_called_once_with(b"server_reply")

    def test_push_real_writer(self):
        mock_writer = MagicMock()
        handler = SocksRequestHandler(MagicMock(), mock_writer, self.mock_profiles)
        handler.push(b"data")
        mock_writer.write.assert_called_once_with(b"data")

        # When closed, push does not write
        mock_writer.write.reset_mock()
        handler.closed = True
        handler.push(b"more")
        mock_writer.write.assert_not_called()

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_print_hex(self, mock_stdout):
        self.handler.printHex(b"\x01\x02\xff")
        self.assertIn("0x1 0x2 0xff", mock_stdout.getvalue())

        mock_stdout.truncate(0)
        mock_stdout.seek(0)
        self.handler.printHex("AB")
        self.assertIn("0x41 0x42", mock_stdout.getvalue())

    def test_found_terminator_state_progression(self):
        # Step 0: Header -> 0x05, 1 auth method
        self.handler.state = 0
        self.handler.input = [b"\x05", b"\x01"]
        self.handler.found_terminator()
        self.assertEqual(self.handler.state, 1)
        self.assertEqual(self.handler.terminator, 1)

        # Step 1: Auth method -> 0x00 (No Auth)
        self.handler.input = [b"\x00"]
        self.handler.found_terminator()
        self.assertEqual(self.handler.state, 2)
        self.assertEqual(self.handler.terminator, 4)

        # Step 2: Request header -> CONNECT IPv4
        self.handler.input = [b"\x05\x01\x00\x01"]
        self.handler.found_terminator()
        # State jumps from 2 to 3 inside processRequestHeader, then +1 in found_terminator -> 4
        self.assertEqual(self.handler.state, 4)
        self.assertEqual(self.handler.terminator, 6)

        # Step 4: Address and port -> triggers _state_processAddressAndPort
        with patch.object(self.handler, "processAddressAndPort"):
            self.handler.input = [b"\x7f\x00\x00\x01\x1f\x90"]
            self.handler.found_terminator()
            self.assertEqual(self.handler.state, 5)

    def test_handle_none_reader_writer(self):
        async def _run():
            handler = SocksRequestHandler(None, None, self.mock_profiles)
            await handler.handle()
            self.assertFalse(handler.closed)

        asyncio.run(_run())

    def test_handle_invalid_version(self):
        async def _run():
            mock_reader = AsyncMock()
            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_reader.readexactly.return_value = b"\x04\x01"

            handler = SocksRequestHandler(mock_reader, mock_writer, self.mock_profiles)
            await handler.handle()
            self.assertTrue(handler.closed)

        asyncio.run(_run())

    def test_handle_unsupported_auth(self):
        async def _run():
            mock_reader = AsyncMock()
            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_reader.readexactly.side_effect = [
                b"\x05\x01",  # Greeting: VER=5, 1 method
                b"\x02",  # Method: USERNAME/PASSWORD (not supported)
            ]

            handler = SocksRequestHandler(mock_reader, mock_writer, self.mock_profiles)
            await handler.handle()
            mock_writer.write.assert_called_with(b"\x05\xff")
            self.assertTrue(handler.closed)

        asyncio.run(_run())

    def test_handle_unsupported_command(self):
        async def _run():
            mock_reader = AsyncMock()
            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_reader.readexactly.side_effect = [
                b"\x05\x01",  # Greeting
                b"\x00",  # No auth
                b"\x05\x02\x00\x01",  # Command 0x02 (BIND - unsupported)
            ]

            handler = SocksRequestHandler(mock_reader, mock_writer, self.mock_profiles)
            await handler.handle()
            mock_writer.write.assert_any_call(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
            mock_writer.drain.assert_called()
            self.assertTrue(handler.closed)

        asyncio.run(_run())

    def test_handle_unsupported_address_type(self):
        async def _run():
            mock_reader = AsyncMock()
            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_reader.readexactly.side_effect = [
                b"\x05\x01",  # Greeting
                b"\x00",  # No auth
                b"\x05\x01\x00\x04",  # Command 0x01 (CONNECT), addressType 0x04 (IPv6 - unsupported)
            ]

            handler = SocksRequestHandler(mock_reader, mock_writer, self.mock_profiles)
            await handler.handle()
            mock_writer.write.assert_any_call(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
            self.assertTrue(handler.closed)

        asyncio.run(_run())

    def test_handle_success_ipv4_pipeline(self):
        async def _run():
            mock_reader = AsyncMock()
            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_reader.readexactly.side_effect = [
                b"\x05\x01",  # Greeting
                b"\x00",  # No Auth
                b"\x05\x01\x00\x01",  # CONNECT IPv4
                b"\x7f\x00\x00\x01\x1f\x90",  # 127.0.0.1:8080
            ]
            self.mock_profiles.getProfileForIP.return_value = None

            handler = SocksRequestHandler(mock_reader, mock_writer, self.mock_profiles)
            with patch.object(handler, "_stream_bidirectional", new_callable=AsyncMock) as mock_stream:
                with patch("knockknock.proxy.SocksRequestHandler.EndpointConnection") as mock_endpoint_cls:
                    mock_endpoint = AsyncMock()
                    mock_endpoint.handle_close = MagicMock()
                    mock_endpoint.connect.return_value = True
                    mock_endpoint_cls.return_value = mock_endpoint

                    await handler.handle()

                    mock_endpoint.connect.assert_called_once()
                    mock_stream.assert_called_once()
                    self.assertTrue(handler.closed)

        asyncio.run(_run())

    def test_handle_success_domain_pipeline(self):
        async def _run():
            mock_reader = AsyncMock()
            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_reader.readexactly.side_effect = [
                b"\x05\x01",  # Greeting
                b"\x00",  # No Auth
                b"\x05\x01\x00\x03",  # CONNECT Domain
                b"\x0b",  # 11 bytes domain length
                b"example.com\x01\xbb",  # example.com:443
            ]
            self.mock_profiles.getProfileForName.return_value = None

            handler = SocksRequestHandler(mock_reader, mock_writer, self.mock_profiles)
            with patch.object(handler, "_stream_bidirectional", new_callable=AsyncMock) as mock_stream:
                with patch("knockknock.proxy.SocksRequestHandler.EndpointConnection") as mock_endpoint_cls:
                    mock_endpoint = AsyncMock()
                    mock_endpoint.handle_close = MagicMock()
                    mock_endpoint.connect.return_value = True
                    mock_endpoint_cls.return_value = mock_endpoint

                    await handler.handle()

                    self.assertEqual(handler.address, "example.com")
                    self.assertEqual(handler.port, 443)
                    mock_endpoint.connect.assert_called_once()
                    mock_stream.assert_called_once()

        asyncio.run(_run())

    def test_handle_endpoint_connect_fails(self):
        async def _run():
            mock_reader = AsyncMock()
            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_reader.readexactly.side_effect = [
                b"\x05\x01",
                b"\x00",
                b"\x05\x01\x00\x01",
                b"\x7f\x00\x00\x01\x1f\x90",
            ]
            self.mock_profiles.getProfileForIP.return_value = None

            handler = SocksRequestHandler(mock_reader, mock_writer, self.mock_profiles)
            with patch("knockknock.proxy.SocksRequestHandler.EndpointConnection") as mock_endpoint_cls:
                mock_endpoint = AsyncMock()
                mock_endpoint.handle_close = MagicMock()
                mock_endpoint.connect.return_value = False
                mock_endpoint_cls.return_value = mock_endpoint

                await handler.handle()
                self.assertTrue(handler.closed)

        asyncio.run(_run())

    def test_handle_endpoint_none_after_process_address_and_port(self):
        async def _run():
            mock_reader = AsyncMock()
            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_reader.readexactly.side_effect = [
                b"\x05\x01",
                b"\x00",
                b"\x05\x01\x00\x01",
                b"\x7f\x00\x00\x01\x1f\x90",
            ]
            handler = SocksRequestHandler(mock_reader, mock_writer, self.mock_profiles)
            with patch.object(handler, "processAddressAndPort"):
                handler.endpoint = None
                await handler.handle()
                self.assertTrue(handler.closed)

        asyncio.run(_run())

    def test_handle_incomplete_read_error(self):
        async def _run():
            mock_reader = AsyncMock()
            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_reader.readexactly.side_effect = asyncio.IncompleteReadError(b"\x05", 2)

            handler = SocksRequestHandler(mock_reader, mock_writer, self.mock_profiles)
            await handler.handle()
            self.assertTrue(handler.closed)

        asyncio.run(_run())

    def test_drain_writer_handles_oserror(self):
        async def _run():
            handler = SocksRequestHandler(MagicMock(), None, self.mock_profiles)
            await handler._drain_writer()

            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock(side_effect=OSError("drain fail"))
            handler.writer = mock_writer
            await handler._drain_writer()

        asyncio.run(_run())

    def test_stream_bidirectional_transfers_data(self):
        async def _run():
            mock_client_reader = AsyncMock()
            mock_client_writer = MagicMock()
            mock_client_writer.drain = AsyncMock()
            mock_endpoint_reader = AsyncMock()
            mock_endpoint_writer = MagicMock()
            mock_endpoint_writer.drain = AsyncMock()

            wait_event = asyncio.Event()

            client_called = False

            async def client_read(_size):
                nonlocal client_called
                if not client_called:
                    client_called = True
                    return b"client_msg"
                return b""

            endpoint_called = False

            async def endpoint_read(_size):
                nonlocal endpoint_called
                if not endpoint_called:
                    endpoint_called = True
                    return b"endpoint_msg"
                await wait_event.wait()
                return b""

            mock_client_reader.read.side_effect = client_read
            mock_endpoint_reader.read.side_effect = endpoint_read

            handler = SocksRequestHandler(mock_client_reader, mock_client_writer, self.mock_profiles)
            mock_endpoint = MagicMock()
            mock_endpoint.reader = mock_endpoint_reader
            mock_endpoint.writer = mock_endpoint_writer
            handler.endpoint = mock_endpoint

            await handler._stream_bidirectional()

            mock_endpoint.write.assert_called_with(b"client_msg")
            mock_client_writer.write.assert_called_with(b"endpoint_msg")

        asyncio.run(_run())

    def test_endpoint_drain_calls_drain_and_handles_error(self):
        async def _run():
            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_endpoint = MagicMock()
            mock_endpoint.writer = mock_writer

            handler = SocksRequestHandler(MagicMock(), MagicMock(), self.mock_profiles)
            handler.endpoint = mock_endpoint
            await handler._endpoint_drain()
            mock_writer.drain.assert_called_once()

            mock_writer.drain = AsyncMock(side_effect=OSError("endpoint drain fail"))
            await handler._endpoint_drain()

            mock_endpoint.writer = None
            await handler._endpoint_drain()

            handler.endpoint = None
            await handler._endpoint_drain()

        asyncio.run(_run())

    def test_handle_close_endpoint_present_writer_none(self):
        mock_endpoint = MagicMock()
        self.handler.endpoint = mock_endpoint
        self.handler.writer = None
        self.handler.handle_close()
        self.assertTrue(self.handler.closed)
        mock_endpoint.handle_close.assert_called_once()

    def test_found_terminator_when_input_is_bytes(self):
        self.handler.state = 0
        self.handler.input = b"\x05\x01"
        self.handler.found_terminator()
        self.assertEqual(self.handler.state, 1)

    def test_copy_stream_handles_oserror_on_drain(self):
        async def _run():
            mock_reader = AsyncMock()
            mock_reader.read.side_effect = [b"data", b""]
            mock_write = MagicMock()
            mock_drain = AsyncMock(side_effect=OSError("drain error"))

            await self.handler._copy_stream(mock_reader, mock_write, mock_drain)
            mock_write.assert_called_once_with(b"data")
            mock_drain.assert_called_once()

        asyncio.run(_run())
