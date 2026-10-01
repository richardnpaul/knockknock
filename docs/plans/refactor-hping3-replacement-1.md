---
goal: Replace hping3 with a pure-Python raw-socket SYN packet sender
version: 1.0
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
`struct.pack`, sends it through a `socket.SOCK_RAW` socket (`IPPROTO_TCP`), and closes
the socket immediately — reproducing exactly what `hping3 -S -c 1` does, with no external
binary, no libpcap, no UDP, and no kernel-resident code.

This is strictly in scope: the project README explicitly permits raw sockets for packet
*sending* (the client already needs `CAP_NET_RAW` / root on the sending side), while
prohibiting kernel-resident code and packet-capture on the *server* side.

## 1. Requirements & Constraints

- **REQ-001**: Implement `knockknock/PacketSender.py` containing a single public function `send_syn(host: str, knock_port: int, ip_id: int, seq: int, ack: int, window: int) -> None` that constructs and transmits one TCP SYN packet using `socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)` with `IP_HDRINCL` set.
- **REQ-002**: The IP header fields encoded in the knock packet (`ip_id`, `seq`, `ack`, `window`) must map identically to the `hping3` flags `-N` (IP ID), `-M` (seq), `-L` (ack), `-w` (window) currently used in `knockknock.py` and `KnockingEndpointConnection.py`.  The on-wire packet format must be byte-for-byte compatible with the daemon's decoding logic.
- **REQ-003**: Remove `hping3` detection (`existsInPath("hping3")`) from `knockknock.py`.  Replace the `subprocess.call(command, ...)` block with a call to `PacketSender.send_syn(...)`.
- **REQ-004**: Remove `hping3` subprocess invocation from `knockknock/proxy/KnockingEndpointConnection.py`.  Replace with a call to `PacketSender.send_syn(...)`.
- **REQ-005**: If the raw socket `bind`/`sendto` call raises `PermissionError` (i.e. the process lacks `CAP_NET_RAW`), both callers must catch the exception and exit with a descriptive error message and code 2 (client) or 3 (proxy), preserving existing exit code contracts.
- **REQ-006**: The `time.sleep(0.25)` delay following the knock in `KnockingEndpointConnection.sendKnock` must be preserved to allow the daemon processing time before the TCP connection attempt proceeds.
- **SEC-001**: All packet header fields (`ip_id`, `seq`, `ack`, `window`) must be validated as unsigned integers within their respective protocol field widths (16-bit for `ip_id` and `window`; 32-bit for `seq` and `ack`) before being packed into the packet.  Values outside range must raise `ValueError`.
- **SEC-002**: The destination IP must be resolved via `socket.getaddrinfo` rather than used raw, to prevent injection of non-IP strings into the socket call.
- **CON-001**: No new external runtime dependencies may be introduced.  `PacketSender.py` must use only Python standard library modules (`socket`, `struct`, `os`).
- **CON-002**: The `hping3` binary reference must be completely removed from all Python source files and from `INSTALL`.  Any remaining documentation references must be updated.
- **CON-003**: All existing quality gates must continue to pass: 100% statement and branch coverage (`--cov-fail-under=100`), 0 surviving gremlins (`pytest --gremlins --strict-pardons`), `flake8` clean, `mypy --strict` clean.
- **CON-004**: All Docker Compose blackbox E2E tests (`tests/blackbox/run_all.sh`) must pass without modification to the external test contracts.  The blackbox client Dockerfile (`tests/blackbox/Dockerfile.client` if present) must not install `hping3`.
- **GUD-001**: Apply TDD — write a failing unit test for each new behaviour before writing the production implementation (`tdd-rules.md`).
- **GUD-002**: Apply the full Verification & Validation meta-loop (`verification-validation-rules.md`) before declaring this plan complete.
- **PAT-001**: Use `unittest.mock.patch("socket.socket")` as the test double for raw socket calls; do not open real raw sockets in unit tests (requires root and a network interface).
- **PAT-002**: Separate packet-construction logic (pure functions over `struct.pack`) from socket I/O so that the construction can be unit-tested without mocking the socket at all.

## 2. Implementation Steps

### Implementation Phase 1: Implement PacketSender

- GOAL-001: Create a pure-Python raw socket SYN packet sender in `knockknock/PacketSender.py` with full unit test coverage.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | **[TDD — Red]** Write failing unit tests in `tests/unit/test_packet_sender.py` for `build_ip_header(src: str, dst: str, ip_id: int, payload_len: int) -> bytes`: (a) returned bytes have length 20; (b) IP version nibble is 4; (c) `ip_id` field appears at bytes 4–5 in network byte order; (d) protocol field is 6 (TCP). | | |
| TASK-002 | **[TDD — Red]** Add failing unit tests for `build_tcp_header(dst_port: int, seq: int, ack: int, window: int) -> bytes`: (a) returned bytes have length 20; (b) SYN flag (`0x02`) is set; (c) `seq` appears at bytes 4–7; (d) `dst_port` appears at bytes 2–3; (e) `window` appears at bytes 14–15. | | |
| TASK-003 | **[TDD — Red]** Add a failing unit test for `send_syn(host, knock_port, ip_id, seq, ack, window)`: patch `socket.socket` to a `MagicMock`; assert `setsockopt(IPPROTO_IP, IP_HDRINCL, 1)` is called; assert `sendto` is called with the concatenation of the IP and TCP headers as the first argument and `(host, 0)` as the second; assert the socket is closed. | | |
| TASK-004 | **[TDD — Red]** Add failing unit tests for validation in `send_syn`: `ValueError` raised when `ip_id > 65535`; `ValueError` raised when `window > 65535`; `ValueError` raised when `seq > 4294967295`; `ValueError` raised when `ack > 4294967295`. | | |
| TASK-005 | **[TDD — Red]** Add a failing unit test asserting that `send_syn` re-raises `PermissionError` unmodified when the socket raises it on `setsockopt`. | | |
| TASK-006 | **[TDD — Green]** Create `knockknock/PacketSender.py` implementing `build_ip_header`, `build_tcp_header`, and `send_syn`.  Construct the IP header (20 bytes, `IP_HDRINCL` format: version+IHL, DSCP, total length, id, flags+frag offset, TTL=64, proto=6, checksum placeholder, src IP, dst IP) and TCP header (20 bytes: src port=0, dst port, seq, ack=0, offset+flags SYN, window, checksum placeholder, urgent=0).  IP checksum is computed with the standard one's complement algorithm; TCP checksum is left as zero (accepted by most kernels when `IP_HDRINCL` is set and the NIC computes it).  Make all tests from TASK-001 through TASK-005 pass. | | |
| TASK-007 | **[Refactor]** Run `flake8 knockknock` and `mypy --strict knockknock`; resolve all findings. | | |

### Implementation Phase 2: Replace hping3 in knockknock.py

- GOAL-002: Remove `hping3` detection and subprocess invocation from the primary client CLI; wire in `PacketSender.send_syn`.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | **[TDD — Red]** Write failing unit tests in `tests/unit/test_knockknock_main.py` (or update existing) covering the `main()` path that previously called `hping3`: (a) `PacketSender.send_syn` is called with the correct arguments derived from `profile.encrypt(packed_port)`; (b) `PermissionError` from `send_syn` prints an error and calls `sys.exit(2)`; (c) `existsInPath` is no longer referenced. | | |
| TASK-009 | **[TDD — Green]** Rewrite the `hping3` block in `knockknock.py`: remove `existsInPath("hping3")` check and `subprocess.call`; replace with `from knockknock.PacketSender import send_syn` and `send_syn(host, knockPort, idField, seqField, ackField, winField)` wrapped in a `try/except PermissionError`. | | |
| TASK-010 | **[TDD — Red]** Write a failing test confirming `existsInPath` is removed from `knockknock.py` (i.e. it is no longer imported or called; inspect the source with `ast` or `importlib`). | | |
| TASK-011 | **[Refactor]** Run `flake8` on `knockknock.py` and `mypy --strict knockknock`; resolve all findings. | | |

### Implementation Phase 3: Replace hping3 in KnockingEndpointConnection

- GOAL-003: Remove the `hping3` subprocess block from the proxy's knocking path; wire in `PacketSender.send_syn`.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | **[TDD — Red]** Write failing unit tests for `KnockingEndpointConnection.sendKnock`: (a) `PacketSender.send_syn` is called with the correct `(host, knock_port, id_field, seq_field, ack_field, win_field)` values; (b) `time.sleep(0.25)` is still called after `send_syn`; (c) `PermissionError` from `send_syn` is caught, logged via `syslog`, and causes `os._exit(3)`. | | |
| TASK-013 | **[TDD — Green]** Rewrite `sendKnock` in `knockknock/proxy/KnockingEndpointConnection.py`: remove `subprocess` import and `hping3` command list; replace with `from knockknock.PacketSender import send_syn` and `send_syn(host, knock_port, id_field, seq_field, ack_field, win_field)` wrapped in `try/except PermissionError`. | | |
| TASK-014 | **[Refactor]** Run `flake8 knockknock` and `mypy --strict knockknock`; resolve all findings. | | |

### Implementation Phase 4: Documentation & Dockerfile Cleanup

- GOAL-004: Remove all `hping3` references from documentation and container definitions.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-015 | In `INSTALL`, replace the `hping3` installation instructions with a note that `knockknock` no longer requires `hping3` — raw socket packet sending is handled internally.  Update the Prerequisites section accordingly. | | |
| TASK-016 | Search for `hping3` across the entire repository with `grep -r "hping3" /workspaces/knockknock` and confirm zero hits in Python source files.  Update or remove any remaining references in shell scripts, Dockerfiles, or documentation. | | |
| TASK-017 | If `tests/blackbox/Dockerfile.client` installs `hping3`, remove that `apt-get install` line. | | |

### Implementation Phase 5: Verification & Validation Convergence

- GOAL-005: Execute the full outer meta-loop until convergence with zero changes on the final pass.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-018 | Run `pytest --cov=knockknock --cov-branch --cov-report=term-missing --cov-report=annotate:cov_annotate --cov-fail-under=100`. Inspect `cov_annotate/` for any `!`-prefixed lines and add targeted tests to achieve 100% statement and branch coverage. | | |
| TASK-019 | Run `pytest --gremlins --gremlin-targets=knockknock --strict-pardons`. For any surviving gremlin use `pytest --gremlins --gremlin-explain=<id>` to diagnose; add a targeted assertion or simplify the branch. | | |
| TASK-020 | Run `python3 -m compileall -q knockknock` and `flake8 knockknock`; confirm 0 errors. | | |
| TASK-021 | Run `pip install -e .` and verify CLI smoke tests: `knockknock` exits 2, `knockknock-genprofile` exits 3, `knockknock-daemon` exits 3, `knockknock-proxy` exits 3. | | |
| TASK-022 | Execute the inner code-review loop (`code-review-and-quality` skill) until 0 findings remain; set `changes_made = true` for each finding addressed. | | |
| TASK-023 | Execute the inner security-review loop (`security-review` skill) until 0 findings remain; set `changes_made = true` for each finding addressed. | | |
| TASK-024 | Run `tests/blackbox/run_all.sh` against the updated Docker images and confirm all scenarios pass end-to-end (knock → connect → port-closes). | | |
| TASK-025 | Perform the outer convergence check: if any tasks TASK-018 through TASK-024 required code or test changes, restart from TASK-018.  Declare convergence only when a full pass completes with zero changes. | | |

## 3. Alternatives

- **ALT-001**: Wrap `scapy` for packet construction.  Rejected — `scapy` is a large dependency that uses libpcap for capture; the README explicitly prohibits libpcap (`README` l.33–34); it would also violate CON-001.
- **ALT-002**: Use the `pyping3` or `impacket` library for raw packet construction.  Rejected — both introduce external dependencies (CON-001 violation) and are heavier than a 60-line `struct.pack` implementation.
- **ALT-003**: Keep `hping3` but bundle it inside the Docker client image only.  Rejected — this leaves the external binary dependency intact for native installs and adds image bloat; the goal is zero-dependency packet sending.
- **ALT-004**: Use `ctypes` to call `libnet` directly.  Rejected — introduces a native library dependency and contradicts the project's "safe language" philosophy (`README` l.28–30).

## 4. Dependencies

- **DEP-001**: Python standard library `socket` module — `socket.AF_INET`, `socket.SOCK_RAW`, `socket.IPPROTO_TCP`, `socket.IP_HDRINCL`.  Available in all CPython >= 3.3 on Linux with `CAP_NET_RAW`.
- **DEP-002**: Python standard library `struct` module — used for header field packing.
- **DEP-003**: `CAP_NET_RAW` capability (or `uid == 0`) on the *client* host — unchanged from the existing `hping3` requirement (which also requires root).
- **DEP-004**: `pycryptodome >= 3.20.0` — unchanged sole external Python runtime dependency.

## 5. Files

- **FILE-001**: `knockknock/PacketSender.py` — **New file**. Pure-Python raw socket SYN sender: `build_ip_header`, `build_tcp_header`, `send_syn`.
- **FILE-002**: `knockknock.py` — Updated to call `PacketSender.send_syn`; `existsInPath` and `subprocess` hping3 block removed.
- **FILE-003**: `knockknock/proxy/KnockingEndpointConnection.py` — Updated to call `PacketSender.send_syn`; `subprocess` hping3 block removed.
- **FILE-004**: `tests/unit/test_packet_sender.py` — **New file**. Unit tests for `build_ip_header`, `build_tcp_header`, `send_syn` (socket mocked), and field validation.
- **FILE-005**: `tests/unit/test_knockknock_main.py` — Updated to test the `send_syn` call path and `PermissionError` handling.
- **FILE-006**: `tests/unit/test_knocking_endpoint_connection.py` — Updated to mock `send_syn` and verify correct arguments and `PermissionError` → `os._exit(3)` handling.
- **FILE-007**: `INSTALL` — Updated to remove `hping3` from prerequisites and note that packet sending is now handled internally.
- **FILE-008**: `tests/blackbox/Dockerfile.client` — Updated to remove `hping3` installation (if present).

## 6. Testing

- **TEST-001**: Unit tests for `build_ip_header` — length, version, ID, protocol field assertions.
- **TEST-002**: Unit tests for `build_tcp_header` — length, SYN flag, seq, dst_port, window field assertions.
- **TEST-003**: Unit tests for `send_syn` with mocked socket — `IP_HDRINCL` setsockopt call; `sendto` argument (concatenated headers, destination tuple); socket closed after send.
- **TEST-004**: Unit tests for `send_syn` field validation — `ValueError` for out-of-range `ip_id`, `window`, `seq`, `ack`.
- **TEST-005**: Unit test for `send_syn` `PermissionError` propagation.
- **TEST-006**: Unit tests for `knockknock.main()` — `send_syn` called with correct arguments derived from `profile.encrypt`; `PermissionError` → `sys.exit(2)`.
- **TEST-007**: Unit tests for `KnockingEndpointConnection.sendKnock` — `send_syn` called with correct arguments; `time.sleep(0.25)` called; `PermissionError` → `os._exit(3)`.
- **TEST-008**: Coverage gate — `pytest --cov=knockknock --cov-branch --cov-report=annotate:cov_annotate --cov-fail-under=100` passes with 0 uncovered lines.
- **TEST-009**: Mutation gate — `pytest --gremlins --gremlin-targets=knockknock --strict-pardons` reports `Survived: 0`.
- **TEST-010**: Blackbox E2E — `tests/blackbox/run_all.sh` passes all knock scenarios without `hping3` present in the client image.

## 7. Risks & Assumptions

- **RISK-001**: Kernel IP checksum handling varies.  Some kernels require the IP checksum field to be pre-computed when `IP_HDRINCL` is set; others recompute it automatically.  *Mitigation*: `PacketSender.build_ip_header` always computes the one's complement checksum correctly regardless of kernel behaviour; the TCP checksum is left as zero (kernel fills it in via `IPPROTO_TCP` socket with `IP_HDRINCL`).
- **RISK-002**: `socket.SOCK_RAW` with `IPPROTO_TCP` and `IP_HDRINCL` is blocked inside Docker containers that lack `CAP_NET_RAW`.  *Mitigation*: The blackbox client container must be run with `--cap-add NET_RAW` (or `cap_add: [NET_RAW]` in `docker-compose.yml`); this mirrors the existing `hping3` requirement.
- **RISK-003**: Some CI runners prohibit raw sockets entirely (e.g., GitHub Actions hosted runners).  *Mitigation*: Unit tests mock the socket; only the blackbox E2E job needs real raw socket capability, and that job runs inside Docker with explicit capability grants.
- **ASSUMPTION-001**: The daemon-side packet decoding logic (field extraction from the IP/TCP headers logged by `nftables`/`kern.log`) is unchanged; `PacketSender` reproduces the identical field layout that `hping3 -S -N -M -L -w` produced.
- **ASSUMPTION-002**: The client host runs Linux with kernel >= 3.0 and standard POSIX socket semantics for `SOCK_RAW`/`IP_HDRINCL`.  macOS and Windows raw socket semantics differ; they are out of scope per the existing project posture.

## 8. Related Specifications / Further Reading

- [Existing Modernisation Plan (Step 3)](file:///workspaces/knockknock/docs/plans/refactor-modernise-codebase-1.md)
- [nftables Migration Plan](file:///workspaces/knockknock/docs/plans/refactor-nftables-migration-1.md)
- [Verification & Validation Rules](file:///workspaces/knockknock/.agents/rules/verification-validation-rules.md)
- [Linux `raw(7)` man page — IP_HDRINCL semantics](https://man7.org/linux/man-pages/man7/raw.7.html)
- [RFC 793 — Transmission Control Protocol (TCP header format)](https://www.rfc-editor.org/rfc/rfc793)
- [RFC 791 — Internet Protocol (IP header format)](https://www.rfc-editor.org/rfc/rfc791)
