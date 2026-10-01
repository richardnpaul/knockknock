import asyncore
import io
import struct
import unittest
from unittest.mock import MagicMock, call, patch

from knockknock.proxy.SocksRequestHandler import SocksRequestHandler


class TestSocksRequestHandler(unittest.TestCase):
    def setUp(self):
        asyncore.socket_map.clear()
        self.mock_sock = MagicMock()
        self.mock_profiles = MagicMock()
        with patch.object(SocksRequestHandler, "set_terminator"):
            self.handler = SocksRequestHandler(self.mock_sock, self.mock_profiles)
        self.handler.push = MagicMock()
        self.handler.close_when_done = MagicMock()

    def tearDown(self):
        asyncore.socket_map.clear()

    def test_init(self):
        self.assertEqual(self.handler.INITIAL_HEADER_LEN, 2)
        self.assertEqual(self.handler.REQUEST_HEADER_LEN, 4)
        self.assertEqual(self.handler.state, 0)
        self.assertIsNone(self.handler.endpoint)
        self.assertEqual(self.handler.input, [])

    def test_byte_helper(self):
        self.assertEqual(self.handler._byte(65), 65)
        self.assertEqual(self.handler._byte("A"), 65)

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
        mock_set_term.assert_called_once_with(None)
        mock_endpoint_cls.assert_called_once_with(self.handler, "127.0.0.1", 8080)
        self.assertEqual(self.handler.endpoint, mock_endpoint_cls.return_value)

    @patch("knockknock.proxy.SocksRequestHandler.KnockingEndpointConnection")
    @patch.object(SocksRequestHandler, "set_terminator")
    def test_process_address_and_port_ipv4_with_profile(self, mock_set_term, mock_knocking_cls):
        mock_profile = MagicMock()
        self.mock_profiles.getProfileForIP.return_value = mock_profile
        self.handler.addressType = 0x01
        self.handler.input = b"\x0a\x00\x00\x02\x00\x16" # 10.0.0.2:22

        self.handler.processAddressAndPort()

        self.assertEqual(self.handler.address, "10.0.0.2")
        self.assertEqual(self.handler.port, 22)
        mock_set_term.assert_called_once_with(None)
        mock_knocking_cls.assert_called_once_with(self.handler, mock_profile, "10.0.0.2", 22)
        self.assertEqual(self.handler.endpoint, mock_knocking_cls.return_value)

    @patch("knockknock.proxy.SocksRequestHandler.EndpointConnection")
    @patch.object(SocksRequestHandler, "set_terminator")
    def test_process_address_and_port_domain_no_profile(self, mock_set_term, mock_endpoint_cls):
        self.mock_profiles.getProfileForName.return_value = None
        self.handler.addressType = 0x03
        self.handler.input = b"example.com\x01\xbb" # example.com:443

        self.handler.processAddressAndPort()

        self.assertEqual(self.handler.address, "example.com")
        self.assertEqual(self.handler.port, 443)
        mock_set_term.assert_called_once_with(None)
        mock_endpoint_cls.assert_called_once_with(self.handler, "example.com", 443)

    @patch("knockknock.proxy.SocksRequestHandler.KnockingEndpointConnection")
    @patch.object(SocksRequestHandler, "set_terminator")
    def test_process_address_and_port_domain_with_profile(self, mock_set_term, mock_knocking_cls):
        mock_profile = MagicMock()
        self.mock_profiles.getProfileForName.return_value = mock_profile
        self.handler.addressType = 0x03
        self.handler.input = b"secret.internal\x1f\x90" # 8080

        self.handler.processAddressAndPort()

        self.assertEqual(self.handler.address, "secret.internal")
        self.assertEqual(self.handler.port, 8080)
        mock_set_term.assert_called_once_with(None)
        mock_knocking_cls.assert_called_once_with(self.handler, mock_profile, "secret.internal", 8080)

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

    @patch("knockknock.proxy.SocksRequestHandler.asynchat.async_chat.handle_close")
    def test_handle_close_with_endpoint(self, mock_super_close):
        mock_endpoint = MagicMock()
        self.handler.endpoint = mock_endpoint
        self.handler.handle_close()
        mock_endpoint.handle_close.assert_called_once()
        mock_super_close.assert_called_once()

    @patch("knockknock.proxy.SocksRequestHandler.asynchat.async_chat.handle_close")
    def test_handle_close_without_endpoint(self, mock_super_close):
        self.handler.endpoint = None
        self.handler.handle_close()
        mock_super_close.assert_called_once()

    def test_connect_succeeded(self):
        self.handler.connectSucceeded("10.0.0.1", 1234)
        expected = b"\x05\x00\x00\x01\x0a\x00\x00\x01" + struct.pack("!H", 1234)
        self.handler.push.assert_called_once_with(expected)

    def test_received_data(self):
        self.handler.receivedData(b"server_reply")
        self.handler.push.assert_called_once_with(b"server_reply")

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_print_hex(self, mock_stdout):
        self.handler.printHex(b"\x01\x02\xff")
        self.assertIn("0x1 0x2 0xff", mock_stdout.getvalue())

        mock_stdout.truncate(0)
        mock_stdout.seek(0)
        self.handler.printHex("AB")
        self.assertIn("0x41 0x42", mock_stdout.getvalue())

    @patch.object(SocksRequestHandler, "set_terminator")
    def test_found_terminator_state_progression(self, mock_set_term):
        # Step 0: Header -> 0x05, 1 auth method
        self.handler.state = 0
        self.handler.input = [b"\x05", b"\x01"]
        self.handler.found_terminator()
        self.assertEqual(self.handler.state, 1)
        mock_set_term.assert_called_with(1)

        # Step 1: Auth method -> 0x00 (No Auth)
        self.handler.input = [b"\x00"]
        self.handler.found_terminator()
        self.assertEqual(self.handler.state, 2)
        mock_set_term.assert_called_with(4) # REQUEST_HEADER_LEN

        # Step 2: Request header -> CONNECT IPv4
        self.handler.input = [b"\x05\x01\x00\x01"]
        self.handler.found_terminator()
        # State jumps from 2 to 3 inside processRequestHeader, then +1 in found_terminator -> 4
        self.assertEqual(self.handler.state, 4)
        mock_set_term.assert_called_with(6)
