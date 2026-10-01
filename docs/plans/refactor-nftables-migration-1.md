---
goal: Replace iptables with nftables and eliminate the RuleTimer threading subsystem
version: 1.1
date_created: 2026-10-01
last_updated: 2026-10-01
owner: Architecture & Engineering
status: Planned
tags: [refactoring, modernisation, nftables, firewall, iptables, threading]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This plan specifies the migration of `knockknock-daemon`'s firewall management layer from
the legacy `iptables` userspace tool to `nftables`. The change covers:
[`knockknock/PortOpener.py`](file:///workspaces/knockknock/knockknock/PortOpener.py),
[`knockknock/RuleTimer.py`](file:///workspaces/knockknock/knockknock/RuleTimer.py),
daemon privileged lifecycle in [`knockknock-daemon.py`](file:///workspaces/knockknock/knockknock-daemon.py),
server entrypoint in [`tests/blackbox/server_entrypoint.sh`](file:///workspaces/knockknock/tests/blackbox/server_entrypoint.sh),
and installation instructions in [`INSTALL`](file:///workspaces/knockknock/INSTALL).

`nftables` is the Linux kernel's official successor to `iptables` and is the default
firewall backend on modern Linux distributions. Its native **timed set elements** (`timeout`
keyword) allow the kernel itself to retire an allow-rule after the configured open
duration elapses, making the `threading.Thread`-based `RuleTimer` class redundant.
Eliminating `RuleTimer` removes the only daemon thread from the child process,
reducing concurrency surface and simplifying the privilege-separated root child.

The approach is intentionally conservative: the `nft` CLI tool is invoked via
`subprocess.call(command_list, shell=False)` — preserving the privilege separation model,
security boundary, and test doubles.

## 1. Requirements & Constraints

- **REQ-001**: Replace all `iptables` CLI invocations in `PortOpener.py` and `RuleTimer.py` with equivalent `nft` invocations that maintain firewall semantics: insert a per-source TCP accept entry into a timed set element scoped to a destination port, automatically expiring after `openDuration` seconds.
- **REQ-002**: On daemon startup (`knockknock-daemon.py`), the privileged child process must initialise a dedicated `nftables` table (`inet knockknock`), a named set (`open_ports`) typed `ipv4_addr . inet_service` with `flags timeout`, a base input chain (`input`) with `type filter hook input priority filter - 1; policy accept;`, and a set-matching rule: `ct state new ip saddr . tcp dport @open_ports meter open_limit { ip saddr limit rate 1/minute burst 1 packets } accept`. Initialization must be idempotent (re-entrant safe if restarted).
- **REQ-003**: Eliminate `knockknock/RuleTimer.py` entirely. Rule expiry must be delegated to the kernel via the `timeout` attribute on individual set elements added by `PortOpener` (`nft add element inet knockknock open_ports { <ip> . <port> timeout <duration>s }`).
- **REQ-004**: Teardown must be handled cleanly within the privileged root child process (`handleFirewall`). When the parent process terminates (signaled by pipe EOF in `waitForRequests()`) or when the child receives `SIGTERM`/`SIGINT`, the child must execute `nft delete table inet knockknock` before calling `os._exit()`, ensuring no stale tables or rules persist after daemon shutdown.
- **REQ-005**: The `nft` binary must be located via `PATH` lookup at runtime (`shutil.which("nft")`). If `nft` is absent, the daemon must exit with code 3 and a descriptive error message.
- **REQ-006**: All `nft` invocations must use `subprocess.call(command_list, shell=False)` — no shell interpolation, no string-building with untrusted input.
- **SEC-001**: Source IP addresses received from the IPC pipe must be strictly validated as valid IPv4 dotted-quad addresses (`0-255` per octet) using regex and bounds checks before interpolation into any `nft` command argument to prevent command injection via a compromised parent process.
- **SEC-002**: Port numbers received from the IPC pipe must be validated as integers in range `[1, 65535]` before use.
- **CON-001**: Wire compatibility: the firewall rules must preserve per-source rate-limit semantics (`meter open_limit { ip saddr limit rate 1/minute burst 1 packets }`) so that a single approved connection per source IP proceeds and subsequent attempts are blocked until the rule expires, preventing token starvation across different clients.
- **CON-002**: All existing quality gates must continue to pass: 100% statement and branch coverage (`--cov-fail-under=100`), 0 surviving gremlins (`pytest --gremlins --strict-pardons`), `flake8` clean, `mypy --strict` clean.
- **CON-003**: All Docker Compose blackbox E2E tests (`tests/blackbox/run_all.sh`) must pass. Both `tests/blackbox/Dockerfile.server` and `tests/blackbox/server_entrypoint.sh` must be updated to configure native `nftables` rules for logging knocks and protected port routing.
- **CON-004**: `RuleTimer` must be fully deleted (source file, tests, and all imports); no dead code may remain.
- **GUD-001**: Apply TDD — write a failing unit test for each new behaviour before writing the production implementation (`tdd-rules.md`).
- **GUD-002**: Apply the full Verification & Validation meta-loop (`verification-validation-rules.md`) before declaring this plan complete.
- **PAT-001**: Retain the existing subprocess list-argument pattern (`command_list = [...]`, `subprocess.call(command_list, shell=False)`) for all `nft` invocations.
- **PAT-002**: Locate the `nft` binary using `shutil.which`; store the resolved path at class initialisation time.

## 2. Implementation Steps

### Implementation Phase 1: nft Table, Set, Chain, and Lifecycle Initialisation

- GOAL-001: Implement `knockknock/NftSetup.py` encapsulating binary discovery, idempotent table/set/chain/rule creation, and privileged teardown.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | **[TDD — Red]** Write unit tests in `tests/unit/test_nft_setup.py` asserting `NftSetup.initialise()` issues exact subprocess calls: (a) `add table inet knockknock`; (b) `add set inet knockknock open_ports { type ipv4_addr . inet_service; flags timeout; }`; (c) `add chain inet knockknock input { type filter hook input priority filter - 1; policy accept; }`; (d) `add rule inet knockknock input ct state new ip saddr . tcp dport @open_ports meter open_limit { ip saddr limit rate 1/minute burst 1 packets } accept`. | | |
| TASK-002 | **[TDD — Red]** Write unit tests in `tests/unit/test_nft_setup.py` asserting `NftSetup.teardown()` issues `delete table inet knockknock` via `subprocess.call(..., shell=False)`. | | |
| TASK-003 | **[TDD — Red]** Write unit tests asserting `NftSetup.__init__` raises `SystemExit(3)` when `nft` executable is not discovered on `PATH` via `shutil.which`. | | |
| TASK-004 | **[TDD — Green]** Create `knockknock/NftSetup.py` implementing `NftSetup` class with `__init__`, `initialise`, and `teardown`, making all tests pass. | | |
| TASK-005 | **[TDD — Red]** Write unit tests in `tests/unit/test_daemon_main.py` covering privileged child lifecycle: assert `handleFirewall` initialises `NftSetup`, registers signal handlers for `SIGTERM`/`SIGINT` calling `teardown()`, and invokes `teardown()` when `PortOpener.waitForRequests()` returns/terminates on pipe EOF. | | |
| TASK-006 | **[TDD — Green]** Update `knockknock-daemon.py`: instantiate and initialise `NftSetup` in the privileged child process (`handleFirewall`) before entering `waitForRequests()`, attach child signal handlers, and execute `teardown()` on shutdown. | | |
| TASK-007 | **[Refactor]** Run `flake8 knockknock` and `mypy --strict knockknock`; achieve 0 warnings and 0 errors. | | |

### Implementation Phase 2: PortOpener Migration to Timed Set Elements

- GOAL-002: Rewrite `PortOpener.py` to add timed elements to the `open_ports` set with strict input validation and zero threading dependencies.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | **[TDD — Red]** Write unit tests in `tests/unit/test_port_opener.py` asserting `PortOpener.waitForRequests()`: (a) reads `sourceIP` and `port` from stream and calls `subprocess.call(["nft", "add", "element", "inet", "knockknock", "open_ports", "{ 10.0.0.1 . 22 timeout 15s }"], shell=False)`; (b) terminates with `os._exit(4)` on empty IP or port (pipe EOF); (c) validates `sourceIP` with strict IPv4 octet bounds (`0-255`), terminating on invalid IP without executing `nft`; (d) validates `port` integer bounds `[1, 65535]`, terminating on invalid port. | | |
| TASK-009 | **[TDD — Green]** Rewrite `knockknock/PortOpener.py`: construct `nft add element` command with per-element timeout `{ sourceIP . port timeout {openDuration}s }`; implement strict IPv4 regex and port validation; remove `RuleTimer` import and usage. | | |
| TASK-010 | **[TDD — Red]** Write unit tests verifying `PortOpener.open()` writes `sourceIP\nport\n` to the stream and flushes, handling broken pipe exceptions with `os._exit(4)`. | | |
| TASK-011 | **[TDD — Green]** Ensure `PortOpener.open()` passes with strict typing and 100% branch coverage. | | |
| TASK-012 | **[Refactor]** Run `flake8 knockknock` and `mypy --strict knockknock`; achieve 0 warnings and 0 errors. | | |

### Implementation Phase 3: RuleTimer Subsystem Deletion

- GOAL-003: Completely remove `RuleTimer` source code, test suites, and imports.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-013 | Delete `knockknock/RuleTimer.py`. | | |
| TASK-014 | Delete `tests/unit/test_rule_timer.py`. | | |
| TASK-015 | Verify zero references to `RuleTimer` across the codebase using `grep -rn "RuleTimer" knockknock tests/`. | | |

### Implementation Phase 4: Blackbox Test Harness & Server Configuration Migration

- GOAL-004: Update blackbox container configuration, startup entrypoint, and documentation to use native `nftables`.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-016 | Update `tests/blackbox/Dockerfile.server`: replace `iptables` with `nftables`. | | |
| TASK-017 | Update `tests/blackbox/server_entrypoint.sh`: replace `iptables -F`, `iptables -N REJECTLOG`, and `iptables -A ...` with equivalent native `nftables` rules in table `inet filter` (creating `REJECTLOG` chain with `log prefix "REJECT " flags tcp sequence,options ip options` and rejecting knock/protected ports to generate logs for `knockknock-daemon`). | | |
| TASK-018 | Update `INSTALL`: replace legacy `iptables` configuration examples with modern `nftables` configuration rules. | | |

### Implementation Phase 5: Verification & Validation Meta-Loop Convergence

- GOAL-005: Execute the full verification-validation meta-loop, ensuring 100% coverage, 0 surviving gremlins, and clean blackbox tests.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-019 | Run `pytest --cov=knockknock --cov-branch --cov-report=term-missing --cov-report=annotate:cov_annotate --cov-fail-under=100`. Inspect `cov_annotate/` and resolve any missing statements or branches. | | |
| TASK-020 | Run `pytest --gremlins --gremlin-targets=knockknock --strict-pardons`. Eliminate all surviving mutants until `Survived: 0`. | | |
| TASK-021 | Run `python3 -m compileall -q knockknock` and `flake8 knockknock`. | | |
| TASK-022 | Run `pip install -e .` and verify CLI smoke tests. | | |
| TASK-023 | Execute inner code-review loop (`code-review-and-quality` skill) until 0 findings remain. | | |
| TASK-024 | Execute inner security-review loop (`security-review` skill) until 0 findings remain. | | |
| TASK-025 | Execute Docker Compose blackbox E2E test suite (`tests/blackbox/run_all.sh`) confirming full knock lifecycle over real `nftables` rules. | | |
| TASK-026 | Convergence check: If any modifications were made during tasks TASK-019 through TASK-025, reset and restart from TASK-019 until outer loop converges with 0 changes on final pass. | | |

## 3. Alternatives

- **ALT-001**: Retain `iptables` and rely on `iptables-nft` compatibility shim. Rejected: `iptables-nft` translation layers introduce subtle syntax quirks and do not benefit from native set element timeouts or atomic set updates.
- **ALT-002**: Retain `RuleTimer` threading with `nft delete element`. Rejected: kernel-level timed set elements eliminate race conditions, GIL contention, and threading leaks when child terminates.
- **ALT-003**: eBPF/XDP packet filter. Rejected: strictly prohibited by `README` (ll. 31, 33–34).
- **ALT-004**: Use `python-nftables` C-bindings. Rejected: introduces compilation and C-library ABI dependencies, whereas CLI `subprocess.call` preserves the established security isolation boundary.

## 4. Dependencies

- **DEP-001**: `nftables` package (`nft` CLI binary >= 0.9.3) installed on server and inside blackbox container.
- **DEP-002**: Linux kernel >= 4.1 supporting nftables named sets with `flags timeout`.
- **DEP-003**: Linux capability `CAP_NET_ADMIN` on server — unchanged from legacy `iptables`.
- **DEP-004**: `pycryptodome >= 3.20.0` — sole external runtime dependency.

## 5. Files

- **FILE-001**: `knockknock/NftSetup.py` — **New module**. Encapsulates `nft` binary discovery, table/set/chain/rule initialization, and teardown.
- **FILE-002**: `knockknock/PortOpener.py` — Rewritten to add timed set elements with strict IPv4 and port validation; `RuleTimer` deleted.
- **FILE-003**: `knockknock/RuleTimer.py` — **Deleted**.
- **FILE-004**: `knockknock-daemon.py` — Updated to manage `NftSetup` lifecycle within privileged child.
- **FILE-005**: `tests/unit/test_nft_setup.py` — **New test suite**. Unit tests for table, set, chain, and rule management.
- **FILE-006**: `tests/unit/test_port_opener.py` — Unit tests for timed set element insertion and input validation.
- **FILE-007**: `tests/unit/test_rule_timer.py` — **Deleted**.
- **FILE-008**: `tests/blackbox/Dockerfile.server` — Server container image; replaced `iptables` with `nftables`.
- **FILE-009**: `tests/blackbox/server_entrypoint.sh` — Server container entrypoint; updated firewall setup to `nftables`.
- **FILE-010**: `INSTALL` — Documentation updated with modern `nftables` firewall examples.

## 6. Testing

- **TEST-001**: Unit test suite asserting exact `nft` CLI argument vectors for table, set, chain, rule creation, and deletion.
- **TEST-002**: Unit test asserting `NftSetup` exits with code 3 if `nft` binary is missing from `PATH`.
- **TEST-003**: Unit test asserting `PortOpener.waitForRequests()` formats element syntax `{ <ip> . <port> timeout <duration>s }`.
- **TEST-004**: Unit test asserting strict IPv4 validation rejecting malformed IPs and preventing command injection.
- **TEST-005**: Unit test asserting port validation rejecting ports < 1 or > 65535.
- **TEST-006**: 100% statement and branch coverage across `knockknock/NftSetup.py` and `knockknock/PortOpener.py`.
- **TEST-007**: Mutation testing gate: 100% mutation slaughter rate with `pytest-gremlins` (`Survived: 0`).
- **TEST-008**: Full blackbox Docker Compose suite passing cleanly with real `nftables` dynamic open and auto-expire.

## 7. Risks & Assumptions

- **RISK-001**: Some older container base images lack `nftables` kernel modules if the host kernel is ancient. *Mitigation*: Modern standard host kernels (>= 4.19) support nftables sets natively.
- **RISK-002**: High concurrency knock requests to `PortOpener` could race on set updates. *Mitigation*: `nft add element` is an atomic netlink operation in kernel space.
- **ASSUMPTION-001**: Server host runs Linux with `CAP_NET_ADMIN`.
- **ASSUMPTION-002**: The kernel supports `inet` family tables and named sets with timeouts.

## 8. Related Specifications / Further Reading

- [hping3 Replacement Implementation Plan](file:///workspaces/knockknock/docs/plans/refactor-hping3-replacement-1.md)
- [Verification & Validation Rules](file:///workspaces/knockknock/.agents/rules/verification-validation-rules.md)
- [nftables Wiki – Sets](https://wiki.nftables.org/wiki-nftables/index.php/Sets)
- [nftables Wiki – Meters](https://wiki.nftables.org/wiki-nftables/index.php/Meters)
