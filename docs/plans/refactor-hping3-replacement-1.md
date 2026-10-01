---
goal: Replace hping3 with a pure-Python raw-socket SYN packet sender
version: 1.1
date_created: 2026-10-01
last_updated: 2026-10-01
owner: Architecture & Engineering
status: Planned
tags: [refactoring, modernisation, hping3, raw-socket, packet-injection, client, proxy]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This plan specifies the replacement of the `hping3` external binary dependency with a
self-contained pure-Python raw TCP SYN packet sender.  `hping3` is invoked in two places:

1. [`knockknock.py`](file:///workspaces/knockknock/knockknock.py) — the primary client CLI.
2. [`knockknock/proxy/KnockingEndpointConnection.py`](file:///workspaces/knockknock/knockknock/proxy/KnockingEndpointConnection.py) — the proxy's knocking path.

The replacement constructs a minimal IP + TCP SYN packet manually using Python's
`struct.pack`, calculates the mandatory IP and TCP checksums, sends it through a
`socket.SOCK_RAW` socket (`IPPROTO_TCP` with `IP_HDRINCL`), and closes the socket
immediately — reproducing exactly what `hping3 -S -c 1 -N <id> -M <seq> -L <ack> -w <win>`
does, with no external binary, no libpcap, no UDP, and no kernel-resident code.

This is strictly in scope: the project README explicitly permits raw sockets for packet
*sending* (the client already needs `CAP_NET_RAW` / root on the sending side), while
prohibiting kernel-resident code and packet-capture on the *server* side.

## 1. Requirements & Constraints

- **REQ-001**: Implement `knockknock/PacketSender.py` containing a public function `send_syn(host: str, knock_port: int, ip_id: int, seq: int, ack: int, window: int) -> None` that constructs and transmits one TCP SYN packet using `socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)` with `IP_HDRINCL` set.
- **REQ-002**: The IP and TCP header fields encoded in the knock packet (`ip_id`, `seq`, `ack`, `window`) must map identically to the `hping3` flags `-N` (IP ID), `-M` (seq), `-L` (ack), `-w` (window) currently used in `knockknock.py` and `KnockingEndpointConnection.py`. Specifically, `ack` (holding 4 bytes of ciphertext/HMAC from `struct.unpack('!HIIH', packet_data)`) must be packed into the 32-bit Acknowledgment Number field (bytes 8–11 of the TCP header). The SYN control flag (`0x02`) must be set in the TCP flags field, and the ACK flag must remain unset, matching `hping3 -S -L`.
- **REQ-003**: `PacketSender.py` must compute the RFC 793 / RFC 9293 standard 16-bit one's complement Internet checksum across the TCP pseudo-header (Source IP, Destination IP, zero byte, protocol 6, TCP length) and the full TCP header. Leaving the TCP checksum as `0x0000` is strictly forbidden because it causes packets to be dropped by intermediate routers and destination network stacks.
- **REQ-004**: `PacketSender.py` must automatically determine the local egress source IP using standard UDP routing table introspection (`get_egress_ip(dst_ip: str) -> str`) and use an ephemeral source port (`random.randint(1024, 65535)`) rather than reserved port 0.
- **REQ-005**: Remove `hping3` detection (`existsInPath("hping3")`) and subprocess execution from `knockknock.py`, replacing it with `PacketSender.send_syn(...)`.
- **REQ-006**: Remove `hping3` subprocess execution from `knockknock/proxy/KnockingEndpointConnection.py`, replacing it with `PacketSender.send_syn(...)`.
- **REQ-007**: If the raw socket operations raise `PermissionError` or `OSError` (e.g. process lacks `CAP_NET_RAW` / root), callers must handle the error gracefully, exiting with code 2 (client) or code 3 (proxy), preserving legacy exit code contracts.
- **REQ-008**: The `time.sleep(0.25)` delay following the knock in `KnockingEndpointConnection.sendKnock` must be preserved to allow daemon processing time before the TCP connection attempt proceeds.
- **SEC-001**: All packet header fields (`ip_id`, `seq`, `ack`, `window`, `knock_port`) must be validated as unsigned integers within their respective protocol field widths (16-bit for `ip_id`, `window`, and `knock_port`; 32-bit for `seq` and `ack`) before packing. Values outside bounds must raise `ValueError`.
- **SEC-002**: The destination IP must be validated or resolved via `socket.getaddrinfo` rather than used unvalidated, preventing injection of invalid address types.
- **CON-001**: Zero external dependencies: `PacketSender.py` must use strictly the Python standard library (`socket`, `struct`, `os`, `random`).
- **CON-002**: The `hping3` binary reference must be completely removed from all Python source files and from `INSTALL`.
- **CON-003**: All existing quality gates must continue to pass: 100% statement and branch coverage (`--cov-fail-under=100`), 0 surviving gremlins (`pytest --gremlins --strict-pardons`), `flake8` clean, `mypy --strict` clean.
- **CON-004**: All Docker Compose blackbox E2E tests (`tests/blackbox/run_all.sh`) must pass without modification to the external test contracts. `tests/blackbox/Dockerfile.server` must remove `hping3` from package installation.
- **GUD-001**: Apply TDD — write a failing unit test for each new behaviour before writing the production implementation (`tdd-rules.md`).
- **GUD-002**: Apply the full Verification & Validation meta-loop (`verification-validation-rules.md`) before declaring this plan complete.
- **PAT-001**: Use `unittest.mock.patch("socket.socket")` as the test double for raw socket calls; do not open real raw sockets in unit tests.
- **PAT-002**: Clean architectural separation: packet header construction and checksum calculation functions must be pure, deterministic functions without side effects, allowing 100% unit test coverage without socket mocks.

## 2. Implementation Steps

### Implementation Phase 1: Pure-Python Packet Construction and Checksum Engine

- GOAL-001: Implement `knockknock/PacketSender.py` with pure functions for IP/TCP header construction, Internet checksum calculation, egress IP discovery, and raw socket transmission.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | **[TDD — Red]** Write unit tests in `tests/unit/test_packet_sender.py` for `calculate_checksum(data: bytes) -> int`: (a) test with known RFC 1071 test vectors; (b) test with odd-length byte buffers; (c) test with carry-over addition ensuring proper 16-bit one's complement folding. | | |
| TASK-002 | **[TDD — Red]** Write unit tests in `tests/unit/test_packet_sender.py` for `build_ip_header(src: str, dst: str, ip_id: int, payload_len: int) -> bytes`: (a) assert header length is 20 bytes; (b) assert IPv4 version (4) and IHL (5); (c) assert `ip_id` is packed in network byte order at bytes 4–5; (d) assert protocol is 6 (TCP); (e) assert valid IP header checksum in bytes 10–11. | | |
| TASK-003 | **[TDD — Red]** Write unit tests in `tests/unit/test_packet_sender.py` for `build_tcp_header(src_ip: str, dst_ip: str, src_port: int, dst_port: int, seq: int, ack: int, window: int) -> bytes`: (a) assert header length is 20 bytes; (b) assert `dst_port` is at bytes 2–3; (c) assert `seq` is at bytes 4–7; (d) assert `ack` (containing 4 bytes of ciphertext/HMAC) is packed at bytes 8–11; (e) assert data offset is 5 (20 bytes) and flags byte has only SYN (`0x02`) set with ACK flag unset; (f) assert `window` is at bytes 14–15; (g) assert calculated TCP checksum is non-zero and verifies against pseudo-header. | | |
| TASK-004 | **[TDD — Red]** Write unit tests for `get_egress_ip(dst_ip: str) -> str`: mock `socket.socket` to return a known mock IP; assert that a dummy UDP socket is connected to `(dst_ip, 80)` and `getsockname()[0]` is returned. | | |
| TASK-005 | **[TDD — Red]** Write unit tests for `send_syn(host, knock_port, ip_id, seq, ack, window)`: (a) assert field validation raises `ValueError` on negative or out-of-range values (`ip_id > 65535`, `window > 65535`, `knock_port > 65535`, `seq > 4294967295`, `ack > 4294967295`); (b) mock socket and assert `socket(AF_INET, SOCK_RAW, IPPROTO_TCP)` created, `IP_HDRINCL` set, and `sendto(ip_header + tcp_header, (dst_ip, 0))` called; (c) assert socket closed in `finally` block; (d) assert `PermissionError` is propagated. | | |
| TASK-006 | **[TDD — Green]** Create `knockknock/PacketSender.py` implementing `calculate_checksum`, `build_ip_header`, `build_tcp_header`, `get_egress_ip`, and `send_syn`. Pack `ack` accurately into TCP bytes 8–11, set SYN flag, compute pseudo-header TCP checksum, and make all unit tests pass. | | |
| TASK-007 | **[Refactor]** Run `flake8 knockknock` and `mypy --strict knockknock`; achieve 0 warnings and 0 errors. | | |

### Implementation Phase 2: Client CLI Migration

- GOAL-002: Replace `hping3` subprocess invocation in `knockknock.py` with `PacketSender.send_syn`.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | **[TDD — Red]** Write unit tests in `tests/unit/test_knockknock_main.py` covering `main()` knock dispatch: (a) assert `send_syn` is called with arguments `(host, knockPort, idField, seqField, ackField, winField)` derived from profile encryption; (b) assert `PermissionError` from `send_syn` logs an error message and terminates with `sys.exit(2)`; (c) assert `existsInPath("hping3")` is no longer called or needed. | | |
| TASK-009 | **[TDD — Green]** Update `knockknock.py`: delete `existsInPath`, replace `hping3` subprocess logic with `PacketSender.send_syn(...)` wrapped in `try/except (PermissionError, OSError)`. | | |
| TASK-010 | **[Refactor]** Run `flake8 knockknock.py` and `mypy --strict knockknock.py`; achieve 0 warnings and 0 errors. | | |

### Implementation Phase 3: Proxy Subsystem Migration

- GOAL-003: Replace `hping3` subprocess invocation in `KnockingEndpointConnection.py` with `PacketSender.send_syn`.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-011 | **[TDD — Red]** Write unit tests in `tests/unit/test_proxy_endpoints.py` for `KnockingEndpointConnection.sendKnock`: (a) mock `send_syn` and assert it is called with `(host, knock_port, id_field, seq_field, ack_field, win_field)`; (b) assert `time.sleep(0.25)` is executed after `send_syn`; (c) assert `PermissionError` from `send_syn` logs via syslog and exits with `os._exit(3)`. | | |
| TASK-012 | **[TDD — Green]** Update `knockknock/proxy/KnockingEndpointConnection.py`: remove `subprocess` and `os.devnull` imports; replace `hping3` invocation with `PacketSender.send_syn(...)` wrapped in `try/except (PermissionError, OSError)`. | | |
| TASK-013 | **[Refactor]** Run `flake8 knockknock` and `mypy --strict knockknock`; achieve 0 warnings and 0 errors. | | |

### Implementation Phase 4: Container Environment & Documentation Cleanup

- GOAL-004: Remove `hping3` package requirements from documentation and Docker test images.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-014 | Update `tests/blackbox/Dockerfile.server`: remove `hping3` from `apt-get install`. | | |
| TASK-015 | Update `INSTALL`: remove `hping3` requirement for clients, documenting that client packet generation is fully native in Python standard library requiring only `CAP_NET_RAW` / root. | | |
| TASK-016 | Verify zero occurrences of `hping3` in source and shell files with `grep -rn "hping3" knockknock knockknock.py tests/blackbox/*.sh`. | | |

### Implementation Phase 5: Verification & Validation Meta-Loop Convergence

- GOAL-005: Execute the full verification-validation meta-loop, ensuring 100% coverage, 0 surviving gremlins, and clean blackbox tests.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-017 | Run `pytest --cov=knockknock --cov-branch --cov-report=term-missing --cov-report=annotate:cov_annotate --cov-fail-under=100`. Inspect `cov_annotate/` and resolve any missing statements or branches. | | |
| TASK-018 | Run `pytest --gremlins --gremlin-targets=knockknock --strict-pardons`. Eliminate all surviving mutants until `Survived: 0`. | | |
| TASK-019 | Run `python3 -m compileall -q knockknock` and `flake8 knockknock`. | | |
| TASK-020 | Run `pip install -e .` and verify CLI smoke tests. | | |
| TASK-021 | Execute inner code-review loop (`code-review-and-quality` skill) until 0 findings remain. | | |
| TASK-022 | Execute inner security-review loop (`security-review` skill) until 0 findings remain. | | |
| TASK-023 | Execute Docker Compose blackbox E2E test suite (`tests/blackbox/run_all.sh`) confirming real container knock-and-open and SOCKS5 proxy flows succeed without `hping3`. | | |
| TASK-024 | Convergence check: If any modifications were made during tasks TASK-017 through TASK-023, reset and restart from TASK-017 until outer loop converges with 0 changes on final pass. | | |

## 3. Alternatives

- **ALT-001**: Wrap `scapy` for packet generation. Rejected: `scapy` is a massive dependency that includes libpcap and packet-sniffing facilities explicitly rejected by `README` (ll. 33–34), violating CON-001.
- **ALT-002**: Leave TCP checksum as `0x0000` to avoid checksum computation code. Rejected: violates RFC 793 / RFC 9293 and causes packet rejection by intermediate routers and target OS kernel TCP stacks.
- **ALT-003**: Use UDP instead of raw TCP SYN packets. Rejected: explicitly violates `README` l. 35 ("I don't want something that uses UDP").
- **ALT-004**: Use `ctypes` bindings to `libnet`. Rejected: violates the safe-language requirement (`README` ll. 28–30) and introduces native C library packaging complexity.

## 4. Dependencies

- **DEP-001**: Python standard library `socket` module (`socket.AF_INET`, `socket.SOCK_RAW`, `socket.IPPROTO_TCP`, `socket.IP_HDRINCL`).
- **DEP-002**: Python standard library `struct` and `random` modules.
- **DEP-003**: Linux capability `CAP_NET_RAW` (or `uid == 0`) on client host — unchanged requirement from legacy `hping3`.
- **DEP-004**: `pycryptodome >= 3.20.0` — sole external runtime dependency.

## 5. Files

- **FILE-001**: `knockknock/PacketSender.py` — **New module**. Native raw socket packet builder, Internet checksum calculator, and SYN sender.
- **FILE-002**: `knockknock.py` — Client CLI entry point; replaced `hping3` subprocess with `PacketSender.send_syn`.
- **FILE-003**: `knockknock/proxy/KnockingEndpointConnection.py` — Proxy knock sender; replaced `hping3` subprocess with `PacketSender.send_syn`.
- **FILE-004**: `tests/unit/test_packet_sender.py` — **New test suite**. Unit tests for packet builder, checksum calculation, and socket transmission.
- **FILE-005**: `tests/unit/test_knockknock_main.py` — Unit tests for CLI knock dispatch.
- **FILE-006**: `tests/unit/test_proxy_endpoints.py` — Unit tests for proxy knock connection.
- **FILE-007**: `tests/blackbox/Dockerfile.server` — Blackbox test image; removed `hping3` installation.
- **FILE-008**: `INSTALL` — Documentation updated to remove `hping3` requirement.

## 6. Testing

- **TEST-001**: Unit test suite for RFC 1071 Internet checksum implementation with known test vectors.
- **TEST-002**: Unit test suite asserting IP header structure, network byte order, and checksum verification.
- **TEST-003**: Unit test suite asserting TCP header structure: 4-byte `ack` field preserves ciphertext/HMAC data, SYN control flag set, ACK flag unset, and valid TCP pseudo-header checksum.
- **TEST-004**: Unit test asserting input validation for field bounds (`ip_id`, `seq`, `ack`, `window`, `knock_port`).
- **TEST-005**: Unit test asserting socket lifecycle, `IP_HDRINCL` option configuration, and clean descriptor closure.
- **TEST-006**: 100% statement and branch coverage across `knockknock/PacketSender.py` (`--cov-fail-under=100`).
- **TEST-007**: Mutation testing gate: 100% mutation slaughter rate with `pytest-gremlins` (`Survived: 0`).
- **TEST-008**: Full blackbox Docker Compose suite passing cleanly without `hping3` installed on server or client.

## 7. Risks & Assumptions

- **RISK-001**: The host network interface or intermediate firewall rejects raw TCP packets with unfamiliar sequence/acknowledgment numbers. *Mitigation*: The TCP format emitted by `PacketSender` is bit-for-bit identical to the packet emitted by `hping3`, which has functioned reliably in production and blackbox environments.
- **RISK-002**: Docker containers executing client commands lack `CAP_NET_RAW`. *Mitigation*: `docker-compose.yml` and test runner scripts already grant `--cap-add NET_RAW` for the client container.
- **ASSUMPTION-001**: Client execution environment is Linux kernel >= 3.0 supporting `SOCK_RAW` and `IP_HDRINCL`.
- **ASSUMPTION-002**: Knock packets are IPv4.

## 8. Related Specifications / Further Reading

- [nftables Migration Implementation Plan](file:///workspaces/knockknock/docs/plans/refactor-nftables-migration-1.md)
- [Verification & Validation Rules](file:///workspaces/knockknock/.agents/rules/verification-validation-rules.md)
- [RFC 793 – Transmission Control Protocol](https://www.rfc-editor.org/rfc/rfc793)
- [RFC 1071 – Computing the Internet Checksum](https://www.rfc-editor.org/rfc/rfc1071)
- [Linux man 7 raw](https://man7.org/linux/man-pages/man7/raw.7.html)
