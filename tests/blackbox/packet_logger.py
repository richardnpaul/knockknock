#!/usr/bin/env python3
"""Captures raw TCP packets on eth0 and appends kernel-formatted log lines to /var/log/kern.log.
This ensures knockknock-daemon receives iptables-compatible logs even in restricted container environments.
"""
import os
import socket
import struct
import sys
import time

LOG_PATH = "/var/log/kern.log"

def main():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    log_file = open(LOG_PATH, "a")

    try:
        raw_sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0800))
    except Exception as e:
        sys.stderr.write(f"packet_logger could not open raw socket: {e}\n")
        sys.exit(0)

    while True:
        try:
            packet = raw_sock.recv(2048)
            if len(packet) < 34:
                continue

            # Ethernet header: 14 bytes
            ip_header = packet[14:]
            ip_proto = ip_header[9]
            if ip_proto != 6:  # TCP only
                continue

            ihl = (ip_header[0] & 0x0F) * 4
            if len(ip_header) < ihl + 20:
                continue

            id_val = struct.unpack("!H", ip_header[4:6])[0]
            src_ip = socket.inet_ntoa(ip_header[12:16])
            dst_ip = socket.inet_ntoa(ip_header[16:20])

            tcp_header = ip_header[ihl:]
            src_port, dst_port, seq_val, ack_val, _, win_val = struct.unpack(
                "!HHIIHH", tcp_header[:16]
            )

            log_line = (
                f"Oct  1 12:00:00 server kernel: IN=eth0 OUT= "
                f"SRC={src_ip} DST={dst_ip} PROTO=TCP SPT={src_port} DPT={dst_port} "
                f"ID={id_val} SEQ={seq_val} ACK={ack_val} WINDOW={win_val} SYN URGP=0\n"
            )
            log_file.write(log_line)
            log_file.flush()
        except Exception:
            time.sleep(0.01)

if __name__ == "__main__":
    main()
