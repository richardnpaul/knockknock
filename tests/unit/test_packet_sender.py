import pytest
from knockknock.PacketSender import calculate_checksum


class TestPacketSenderChecksum:

    def test_calculate_checksum_known_rfc1071_vector(self) -> None:
        # RFC 1071 example: 0x0001 + 0xf203 + 0xf4f5 + 0xf6f7
        data = b"\x00\x01\xf2\x03\xf4\xf5\xf6\xf7"
        assert calculate_checksum(data) == 0x220D

    def test_calculate_checksum_odd_length(self) -> None:
        # Odd-length data pads trailing zero byte (0x01 becomes 0x0100)
        assert calculate_checksum(b"\x01") == 0xFEFF

    def test_calculate_checksum_carry_over_folding(self) -> None:
        # Sum that carries over multiple times into high 16 bits
        data = b"\xff\xfe\xff\xfd"
        # 0xfffe + 0xfffd = 0x1fffb -> (1 + 0xfffb) = 0xfffc -> ~0xfffc = 0x0003
        assert calculate_checksum(data) == 0x0003

    def test_calculate_checksum_empty(self) -> None:
        assert calculate_checksum(b"") == 0xFFFF


class TestPacketSenderIPHeader:

    def test_build_ip_header_structure_and_checksum(self) -> None:
        from knockknock.PacketSender import build_ip_header

        src = "192.168.1.100"
        dst = "192.168.1.200"
        ip_id = 0x1234
        payload_len = 20  # TCP SYN header length

        header = build_ip_header(src, dst, ip_id, payload_len)
        assert len(header) == 20
        # Byte 0: Version (4) in high nibble, IHL (5) in low nibble -> 0x45
        assert header[0] == 0x45
        # Byte 1: DSCP / ECN -> 0x00
        assert header[1] == 0x00
        # Bytes 2-3: Total length (20 + 20 = 40)
        assert header[2:4] == b"\x00\x28"
        # Bytes 4-5: Identification
        assert header[4:6] == b"\x12\x34"
        # Bytes 6-7: Flags (0) + Frag offset (0)
        assert header[6:8] == b"\x00\x00"
        # Byte 8: TTL (64)
        assert header[8] == 64
        # Byte 9: Protocol (6 for TCP)
        assert header[9] == 6
        # Bytes 10-11: Header Checksum - recomputing checksum over the full header must yield 0x0000
        assert calculate_checksum(header) == 0x0000
        # Bytes 12-15: Source IP
        assert header[12:16] == b"\xc0\xa8\x01\x64"
        # Bytes 16-19: Destination IP
        assert header[16:20] == b"\xc0\xa8\x01\xc8"


class TestPacketSenderTCPHeader:

    def test_build_tcp_header_structure_and_checksum(self) -> None:
        import socket
        import struct
        from knockknock.PacketSender import build_tcp_header

        src_ip = "192.168.1.100"
        dst_ip = "192.168.1.200"
        src_port = 54321
        dst_port = 80
        seq = 0x11223344
        ack = 0x55667788
        window = 0x1000

        header = build_tcp_header(
            src_ip, dst_ip, src_port, dst_port, seq, ack, window
        )

        assert len(header) == 20
        # Bytes 0-1: src_port
        assert header[0:2] == struct.pack("!H", src_port)
        # Bytes 2-3: dst_port
        assert header[2:4] == struct.pack("!H", dst_port)
        # Bytes 4-7: seq
        assert header[4:8] == struct.pack("!I", seq)
        # Bytes 8-11: ack
        assert header[8:12] == struct.pack("!I", ack)
        # Byte 12: Data offset = 5 (20 bytes), reserved = 0
        assert header[12] == (5 << 4)
        # Byte 13: Flags -> SYN only (0x02), ACK flag (0x10) unset
        assert header[13] == 0x02
        assert (header[13] & 0x10) == 0
        # Bytes 14-15: Window size
        assert header[14:16] == struct.pack("!H", window)
        # Bytes 16-17: Checksum (must be non-zero for this packet)
        chk = struct.unpack("!H", header[16:18])[0]
        assert chk != 0
        # Bytes 18-19: Urgent pointer
        assert header[18:20] == b"\x00\x00"

        # Verify against pseudo header: total checksum over pseudo + tcp header must be 0
        pseudo_hdr = struct.pack(
            "!4s4sBBH",
            socket.inet_aton(src_ip),
            socket.inet_aton(dst_ip),
            0,
            socket.IPPROTO_TCP,
            len(header),
        )
        assert calculate_checksum(pseudo_hdr + header) == 0x0000


class TestPacketSenderEgressIP:

    def test_get_egress_ip(self) -> None:
        from unittest.mock import MagicMock, patch
        import socket
        from knockknock.PacketSender import get_egress_ip

        mock_socket = MagicMock()
        mock_socket.getsockname.return_value = ("192.168.1.42", 54321)

        with patch("socket.socket", return_value=mock_socket) as mock_socket_cls:
            ip = get_egress_ip("8.8.8.8")
            assert ip == "192.168.1.42"
            mock_socket_cls.assert_called_once_with(
                socket.AF_INET, socket.SOCK_DGRAM
            )
            mock_socket.connect.assert_called_once_with(("8.8.8.8", 80))
            mock_socket.close.assert_called_once()


class TestPacketSenderSendSyn:

    @pytest.mark.parametrize(
        "port,ip_id,seq,ack,window",
        [
            (0, 100, 100, 100, 100),  # port < 1
            (65536, 100, 100, 100, 100),  # port > 65535
            (80, -1, 100, 100, 100),  # ip_id < 0
            (80, 65536, 100, 100, 100),  # ip_id > 65535
            (80, 100, -1, 100, 100),  # seq < 0
            (80, 100, 4294967296, 100, 100),  # seq > 4294967295
            (80, 100, 100, -1, 100),  # ack < 0
            (80, 100, 100, 4294967296, 100),  # ack > 4294967295
            (80, 100, 100, 100, -1),  # window < 0
            (80, 100, 100, 100, 65536),  # window > 65535
        ],
    )
    def test_send_syn_validates_bounds(
        self, port: int, ip_id: int, seq: int, ack: int, window: int
    ) -> None:
        from knockknock.PacketSender import send_syn

        with pytest.raises(ValueError):
            send_syn("192.168.1.1", port, ip_id, seq, ack, window)

    def test_send_syn_success_flow(self) -> None:
        from unittest.mock import MagicMock, patch
        import socket
        from knockknock.PacketSender import send_syn

        mock_raw_sock = MagicMock()

        with patch("socket.getaddrinfo") as mock_getaddrinfo, \
             patch("knockknock.PacketSender.get_egress_ip", return_value="10.0.0.1"), \
             patch("random.randint", return_value=45678), \
             patch("socket.socket", return_value=mock_raw_sock) as mock_sock_cls:

            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", 80))
            ]

            send_syn("example.com", 80, 1234, 56789, 98765, 4096)

            mock_getaddrinfo.assert_called_once_with(
                "example.com", 80, socket.AF_INET
            )
            mock_sock_cls.assert_called_once_with(
                socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP
            )
            mock_raw_sock.setsockopt.assert_called_once_with(
                socket.IPPROTO_IP, socket.IP_HDRINCL, 1
            )
            assert mock_raw_sock.sendto.call_count == 1
            sent_data, dest_addr = mock_raw_sock.sendto.call_args[0]
            assert len(sent_data) == 40  # 20 IP + 20 TCP
            assert dest_addr == ("10.0.0.2", 0)
            mock_raw_sock.close.assert_called_once()

    def test_send_syn_propagates_permission_error_and_closes(self) -> None:
        from unittest.mock import MagicMock, patch
        import socket
        from knockknock.PacketSender import send_syn

        mock_raw_sock = MagicMock()
        mock_raw_sock.setsockopt.side_effect = PermissionError("Operation not permitted")

        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", 80))]), \
             patch("knockknock.PacketSender.get_egress_ip", return_value="10.0.0.1"), \
             patch("socket.socket", return_value=mock_raw_sock):

            with pytest.raises(PermissionError):
                send_syn("10.0.0.2", 80, 1234, 5678, 9012, 1024)

            mock_raw_sock.close.assert_called_once()

    @pytest.mark.parametrize(
        "port,ip_id,seq,ack,window",
        [
            (1, 0, 0, 0, 0),  # Min bounds
            (65535, 65535, 4294967295, 4294967295, 65535),  # Max bounds
        ],
    )
    def test_send_syn_valid_boundaries(
        self, port: int, ip_id: int, seq: int, ack: int, window: int
    ) -> None:
        from unittest.mock import MagicMock, patch
        import socket
        from knockknock.PacketSender import send_syn

        mock_raw_sock = MagicMock()
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", port))]), \
             patch("knockknock.PacketSender.get_egress_ip", return_value="10.0.0.1"), \
             patch("socket.socket", return_value=mock_raw_sock):

            send_syn("10.0.0.2", port, ip_id, seq, ack, window)
            assert mock_raw_sock.sendto.call_count == 1


class TestValidateRange:

    def test_validate_range_below_min(self) -> None:
        from knockknock.PacketSender import _validate_range
        with pytest.raises(ValueError, match="Invalid test_val: 4"):
            _validate_range("test_val", 4, 5, 10)

    def test_validate_range_at_min(self) -> None:
        from knockknock.PacketSender import _validate_range
        _validate_range("test_val", 5, 5, 10)

    def test_validate_range_at_max(self) -> None:
        from knockknock.PacketSender import _validate_range
        _validate_range("test_val", 10, 5, 10)

    def test_validate_range_above_max(self) -> None:
        from knockknock.PacketSender import _validate_range
        with pytest.raises(ValueError, match="Invalid test_val: 11"):
            _validate_range("test_val", 11, 5, 10)
