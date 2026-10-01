import random
import socket
import struct


def _validate_range(name: str, val: int, min_val: int, max_val: int) -> None:
    if val < min_val or val > max_val:
        raise ValueError(f"Invalid {name}: {val}")


def calculate_checksum(data: bytes) -> int:
    if len(data) & 1:
        data += b"\x00"

    checksum = sum(int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2))

    while checksum >> 16:
        checksum = (checksum & 0xFFFF) + (checksum >> 16)

    return ~checksum & 0xFFFF


def build_ip_header(src: str, dst: str, ip_id: int, payload_len: int) -> bytes:
    version_ihl = (4 << 4) | 5
    tos = 0
    total_len = 20 + payload_len
    flags_frag = 0
    ttl = 64
    proto = socket.IPPROTO_TCP  # 6
    checksum = 0
    src_bytes = socket.inet_aton(src)
    dst_bytes = socket.inet_aton(dst)

    header_without_checksum = struct.pack(
        "!BBHHHBBH4s4s",
        version_ihl,
        tos,
        total_len,
        ip_id,
        flags_frag,
        ttl,
        proto,
        checksum,
        src_bytes,
        dst_bytes,
    )

    chk = calculate_checksum(header_without_checksum)
    return header_without_checksum[:10] + struct.pack("!H", chk) + header_without_checksum[12:]


def build_tcp_header(
    src_ip: str,
    dst_ip: str,
    src_port: int,
    dst_port: int,
    seq: int,
    ack: int,
    window: int,
) -> bytes:
    data_offset = 5 << 4  # 5 32-bit words (20 bytes)
    flags = 0x02  # SYN only
    urgent_ptr = 0
    checksum = 0

    tcp_header_no_checksum = struct.pack(
        "!HHIIBBHHH",
        src_port,
        dst_port,
        seq,
        ack,
        data_offset,
        flags,
        window,
        checksum,
        urgent_ptr,
    )

    src_bytes = socket.inet_aton(src_ip)
    dst_bytes = socket.inet_aton(dst_ip)
    pseudo_header = struct.pack(
        "!4s4sBBH",
        src_bytes,
        dst_bytes,
        0,
        socket.IPPROTO_TCP,
        len(tcp_header_no_checksum),
    )

    chk = calculate_checksum(pseudo_header + tcp_header_no_checksum)
    return tcp_header_no_checksum[:16] + struct.pack("!H", chk) + tcp_header_no_checksum[18:]


def get_egress_ip(dst_ip: str) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((dst_ip, 80))
        return str(sock.getsockname()[0])
    finally:
        sock.close()


def send_syn(
    host: str,
    knock_port: int,
    ip_id: int,
    seq: int,
    ack: int,
    window: int,
) -> None:
    _validate_range("knock_port", knock_port, 1, 65535)
    _validate_range("ip_id", ip_id, 0, 65535)
    _validate_range("seq", seq, 0, 4294967295)
    _validate_range("ack", ack, 0, 4294967295)
    _validate_range("window", window, 0, 65535)

    addr_info = socket.getaddrinfo(host, knock_port, socket.AF_INET)
    dst_ip = str(addr_info[0][4][0])

    src_ip = get_egress_ip(dst_ip)
    src_port = random.randint(1024, 65535)

    tcp_header = build_tcp_header(src_ip, dst_ip, src_port, knock_port, seq, ack, window)
    ip_header = build_ip_header(src_ip, dst_ip, ip_id, len(tcp_header))
    packet = ip_header + tcp_header

    sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
        sock.sendto(packet, (dst_ip, 0))
    finally:
        sock.close()
