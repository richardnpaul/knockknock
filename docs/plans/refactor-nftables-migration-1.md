---
goal: Replace iptables with nftables and eliminate the RuleTimer threading subsystem
version: 1.0
date_created: 2026-10-01
last_updated: 2026-10-01
owner: Architecture & Engineering
status: Planned
tags: [refactoring, modernisation, nftables, firewall, iptables, threading]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

This plan specifies the migration of `knockknock-daemon`'s firewall management layer from
the legacy `iptables` userspace tool to `nftables`.  The change covers two modules:
[`knockknock/PortOpener.py`](file:///workspaces/knockknock/knockknock/PortOpener.py) and
[`knockknock/RuleTimer.py`](file:///workspaces/knockknock/knockknock/RuleTimer.py).

`nftables` is the Linux kernel's official successor to `iptables` and is the default
firewall backend on Debian 11+, Ubuntu 20.04+, and RHEL 8+.  Its native **timed set
elements** (`timeout` keyword) allow the kernel itself to retire an allow-rule after the
configured open duration elapses, making the `threading.Thread`-based `RuleTimer` class
redundant.  Eliminating `RuleTimer` removes the only daemon thread from the child process,
reducing concurrency surface and simplifying the privilege-separated root child.

The approach is intentionally conservative: the `nft` CLI tool is invoked via
`subprocess.call(shell=False)` — the same pattern already used for `iptables` — so the
privilege model, security boundary, and test doubles remain identical.

## 1. Requirements & Constraints

- **REQ-001**: Replace all `iptables` CLI invocations in `PortOpener.py` and `RuleTimer.py` with equivalent `nft` invocations that maintain identical firewall semantics: insert a per-source TCP accept rule scoped to a single destination port, and remove it after `openDuration` seconds.
- **REQ-002**: On daemon startup (`knockknock-daemon.py`), initialise a dedicated `nftables` table (`inet knockknock`) containing a named set (`open_ports`) typed `ipv4_addr . inet_service` with `flags timeout` enabled.  The set must not already exist; startup must be idempotent (re-entrant safe if the daemon is restarted).
- **REQ-003**: Eliminate `knockknock/RuleTimer.py` entirely.  Rule expiry must be delegated to the kernel via the `timeout` attribute on individual set elements added by `PortOpener`.
- **REQ-004**: Implement a `teardown` path in `knockknock-daemon.py` (triggered on `SIGTERM`/`SIGINT`) that flushes and deletes the `inet knockknock` table so no stale rules persist after the daemon exits.
- **REQ-005**: The `nft` binary must be located via `PATH` lookup at runtime; the path must not be hardcoded.  If `nft` is absent, the daemon must exit with code 3 and a descriptive error message.
- **REQ-006**: All `nft` invocations must use `subprocess.call(command_list, shell=False)` — no shell interpolation, no string-building that accepts untrusted input without validation.
- **SEC-001**: Source IP addresses received from the IPC pipe must be validated against a strict IPv4/IPv6 regex before being interpolated into any `nft` command argument to prevent command injection via a compromised parent process.
- **SEC-002**: Port numbers received from the IPC pipe must be validated as integers in range `[1, 65535]` before use.
- **CON-001**: Wire compatibility: the firewall rules must preserve the existing rate-limit semantics (`limit rate 1/minute burst 1 packets`) applied to the per-source accept rule so that a single approved connection can proceed and subsequent attempts are dropped until the rule expires.
- **CON-002**: All existing quality gates must continue to pass: 100% statement and branch coverage (`--cov-fail-under=100`), 0 surviving gremlins (`pytest --gremlins --strict-pardons`), `flake8` clean, `mypy --strict` clean.
- **CON-003**: All Docker Compose blackbox E2E tests (`tests/blackbox/run_all.sh`) must pass without modification to the test harness.  The blackbox Dockerfile (`tests/blackbox/Dockerfile.server`) must install `nftables` in place of `iptables`.
- **CON-004**: `RuleTimer` must be fully deleted (source file and all imports); no dead code may remain.
- **GUD-001**: Apply TDD — write a failing unit test for each new behaviour before writing the production implementation (`tdd-rules.md`).
- **GUD-002**: Apply the full Verification & Validation meta-loop (`verification-validation-rules.md`) before declaring this plan complete.
- **PAT-001**: Retain the existing subprocess list-argument pattern (`command_list = [...]`, `subprocess.call(command_list, shell=False)`) for all `nft` invocations.
- **PAT-002**: Locate the `nft` binary using `shutil.which`; store the resolved path at class initialisation time.

## 2. Implementation Steps

### Implementation Phase 1: nft Table Initialisation

- GOAL-001: Add daemon startup logic that creates the `inet knockknock` table and `open_ports` set with timeout support, and a teardown path that removes it on exit.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | **[TDD — Red]** Write a failing unit test in `tests/unit/test_nft_setup.py` asserting that `NftSetup.initialise()` calls `subprocess.call` with exactly `["nft", "add", "table", "inet", "knockknock"]` then `["nft", "add", "set", "inet", "knockknock", "open_ports", "{ type ipv4_addr . inet_service; flags timeout; }"]`, using `unittest.mock.patch("subprocess.call")`. | | |
| TASK-002 | **[TDD — Red]** Add a failing test in `tests/unit/test_nft_setup.py` asserting that `NftSetup.teardown()` calls `subprocess.call` with `["nft", "delete", "table", "inet", "knockknock"]`. | | |
| TASK-003 | **[TDD — Red]** Add a failing test asserting that `NftSetup.__init__` raises `SystemExit(3)` when `nft` is not found on `PATH` (patch `shutil.which` to return `None`). | | |
| TASK-004 | **[TDD — Green]** Create `knockknock/NftSetup.py` implementing `class NftSetup` with `__init__(self)` (resolves `nft` path via `shutil.which`, exits 3 if absent), `initialise(self) -> None` (issues table and set creation commands), and `teardown(self) -> None` (deletes the table). Make all three tests pass. | | |
| TASK-005 | **[TDD — Green]** Wire `NftSetup` into `knockknock-daemon.py`: call `NftSetup().initialise()` in the privileged child before entering `PortOpener.waitForRequests()`, and register `NftSetup().teardown()` via `signal.signal(signal.SIGTERM, ...)` and `atexit.register(...)`. | | |
| TASK-006 | **[Refactor]** Run `flake8 knockknock` and `mypy --strict knockknock`; resolve all findings. | | |

### Implementation Phase 2: Replace PortOpener iptables Calls

- GOAL-002: Rewrite `PortOpener.py` to insert timed `nftables` set elements instead of calling `iptables -I`.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-007 | **[TDD — Red]** Write failing unit tests in `tests/unit/test_port_opener.py` for the updated `PortOpener` class: (a) `waitForRequests` reads `sourceIP` + `port` from stream and calls `subprocess.call` with `["nft", "add", "element", "inet", "knockknock", "open_ports", "{ 1.2.3.4 . 22 timeout 30s }"]`; (b) an empty `sourceIP` or `port` causes `os._exit(4)`; (c) a `sourceIP` failing IPv4 validation causes `os._exit(4)` without calling `subprocess.call`; (d) a port outside `[1, 65535]` causes `os._exit(4)`. | | |
| TASK-008 | **[TDD — Green]** Rewrite `knockknock/PortOpener.py`: replace the `iptables -I` command construction with `["nft", "add", "element", "inet", "knockknock", "open_ports", f"{{ {sourceIP} . {port} timeout {self.openDuration}s }}"]`.  Add IPv4 regex validation (`re.fullmatch`) and port range validation before constructing the command.  Remove all references to `RuleTimer`. | | |
| TASK-009 | **[TDD — Red]** Write a failing unit test asserting that `PortOpener.open()` writes `sourceIP\nport\n` to `self.stream` and flushes, and that an `IOError` on write causes `os._exit(4)`. | | |
| TASK-010 | **[TDD — Green]** Confirm `PortOpener.open()` tests pass with the rewritten implementation; add type annotations and verify coverage. | | |
| TASK-011 | **[Refactor]** Run `flake8 knockknock` and `mypy --strict knockknock`; resolve all findings. | | |

### Implementation Phase 3: Delete RuleTimer

- GOAL-003: Remove `RuleTimer` from the codebase entirely — source file, imports, and all test doubles.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | Delete `knockknock/RuleTimer.py`. | | |
| TASK-013 | Remove `from .RuleTimer import RuleTimer` from `knockknock/__init__.py` (if present) and any other module that imports it. | | |
| TASK-014 | Delete `tests/unit/test_rule_timer.py` (the existing unit test file for the now-deleted class).  Confirm `pytest` still collects and passes all remaining tests. | | |
| TASK-015 | Run `grep -r "RuleTimer" /workspaces/knockknock` and confirm zero hits. | | |

### Implementation Phase 4: Update Blackbox Harness

- GOAL-004: Replace `iptables` with `nftables` in the Docker-based blackbox test environment.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-016 | In `tests/blackbox/Dockerfile.server`, replace `RUN apt-get install -y iptables` with `RUN apt-get install -y nftables` (or the equivalent for the base image's package manager). | | |
| TASK-017 | In `tests/blackbox/docker-compose.yml`, verify `cap_add: [NET_ADMIN]` is present on the server service definition (already required for `iptables`; now required for `nft` table manipulation). Add it if absent. | | |
| TASK-018 | Run `tests/blackbox/run_all.sh` against the updated image and confirm all scenarios pass end-to-end (knock → connect → port-closes). | | |

### Implementation Phase 5: Verification & Validation Convergence

- GOAL-005: Execute the full outer meta-loop until convergence with zero changes on the final pass.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-019 | Run `pytest --cov=knockknock --cov-branch --cov-report=term-missing --cov-report=annotate:cov_annotate --cov-fail-under=100`. Inspect `cov_annotate/` for any `!`-prefixed lines and add targeted tests to achieve 100% statement and branch coverage. | | |
| TASK-020 | Run `pytest --gremlins --gremlin-targets=knockknock --strict-pardons`. For any surviving gremlin, use `pytest --gremlins --gremlin-explain=<id>` to diagnose and add a targeted assertion or simplify the production branch to kill it. | | |
| TASK-021 | Run `python3 -m compileall -q knockknock` and `flake8 knockknock`; confirm 0 errors. | | |
| TASK-022 | Run `pip install -e .` and verify CLI smoke tests: `knockknock` exits 2, `knockknock-genprofile` exits 3, `knockknock-daemon` exits 3, `knockknock-proxy` exits 3. | | |
| TASK-023 | Execute the inner code-review loop (`code-review-and-quality` skill) until 0 findings remain; set `changes_made = true` for each finding addressed. | | |
| TASK-024 | Execute the inner security-review loop (`security-review` skill) until 0 findings remain; set `changes_made = true` for each finding addressed. | | |
| TASK-025 | Perform the outer convergence check: if any tasks TASK-019 through TASK-024 required code or test changes, restart from TASK-019.  Declare convergence only when a full pass completes with zero changes. | | |

## 3. Alternatives

- **ALT-001**: Keep `iptables` and add a compatibility shim (`iptables-legacy` or `iptables-nft`). Rejected — both shims invoke the deprecated netfilter API; `nftables` is the canonical forward-compatible interface on all supported distributions.
- **ALT-002**: Use `python-nftables` (the official Python bindings that embed `libnftables`). Rejected — introduces a C extension dependency, complicates packaging, and provides no testability advantage over the `nft` CLI subprocess pattern already established in the codebase.
- **ALT-003**: Retain `RuleTimer` threading and call `nft delete element` after `openDuration` seconds. Rejected — kernel-native timeouts are strictly more reliable (persist across Python thread deaths, GIL contention, and daemon restarts) and eliminating `RuleTimer` is a net simplification.
- **ALT-004**: eBPF/XDP packet filtering. Rejected — explicitly violates the project constraint "I don't want something that runs in the kernel" (`README` l.31).

## 4. Dependencies

- **DEP-001**: `nftables` package (`nft` CLI binary) — must be installed on the server host and inside the blackbox Docker image.  Runtime version requirement: `nft >= 0.9.3` (timed set elements stable since kernel 4.1 / nft 0.6.0; `0.9.3` chosen for reliable `inet` dual-stack support on Debian 11+ / Ubuntu 20.04+).
- **DEP-002**: Linux kernel `>= 4.1` — minimum for nftables timed set support.  Effectively already satisfied by the existing `iptables` dependency on any modern distribution.
- **DEP-003**: `CAP_NET_ADMIN` capability — already required for `iptables`; no change to privilege model.
- **DEP-004**: `pycryptodome >= 3.20.0` — unchanged sole external Python runtime dependency.

## 5. Files

- **FILE-001**: `knockknock/PortOpener.py` — Rewritten to issue `nft add element` with per-element timeout; `RuleTimer` import removed; IPv4 and port validation added.
- **FILE-002**: `knockknock/RuleTimer.py` — **Deleted**.
- **FILE-003**: `knockknock/NftSetup.py` — **New file**. Encapsulates `nft` binary discovery, table/set initialisation, and teardown.
- **FILE-004**: `knockknock-daemon.py` — Updated to call `NftSetup().initialise()` on startup and `NftSetup().teardown()` on `SIGTERM`/exit.
- **FILE-005**: `tests/unit/test_nft_setup.py` — **New file**. Unit tests for `NftSetup` initialisation, teardown, and missing-binary exit.
- **FILE-006**: `tests/unit/test_port_opener.py` — Updated unit tests covering `nft` command construction, IP validation, port validation, and `os._exit(4)` paths.
- **FILE-007**: `tests/unit/test_rule_timer.py` — **Deleted** (class removed).
- **FILE-008**: `tests/blackbox/Dockerfile.server` — Updated to install `nftables` instead of `iptables`.
- **FILE-009**: `tests/blackbox/docker-compose.yml` — Verified/updated `cap_add: [NET_ADMIN]` for server service.

## 6. Testing

- **TEST-001**: Unit tests for `NftSetup.__init__` — `nft` binary resolved correctly from `PATH`; `SystemExit(3)` raised when absent.
- **TEST-002**: Unit tests for `NftSetup.initialise()` — asserts exact subprocess argument lists for table creation and set creation commands.
- **TEST-003**: Unit tests for `NftSetup.teardown()` — asserts exact subprocess argument list for table deletion command.
- **TEST-004**: Unit tests for `PortOpener.waitForRequests()` — asserts `nft add element` command constructed correctly; asserts `os._exit(4)` on empty stream; asserts `os._exit(4)` on invalid IP; asserts `os._exit(4)` on out-of-range port.
- **TEST-005**: Unit tests for `PortOpener.open()` — asserts IPC stream writes and flush; asserts `os._exit(4)` on `IOError`.
- **TEST-006**: Coverage gate — `pytest --cov=knockknock --cov-branch --cov-report=annotate:cov_annotate --cov-fail-under=100` passes with 0 uncovered lines.
- **TEST-007**: Mutation gate — `pytest --gremlins --gremlin-targets=knockknock --strict-pardons` reports `Survived: 0`.
- **TEST-008**: Blackbox E2E — `tests/blackbox/run_all.sh` passes all scenarios end-to-end with the `nftables`-backed Docker image.

## 7. Risks & Assumptions

- **RISK-001**: Some CI environments and container base images still ship with `iptables` as default and `nftables` may not be installed.  *Mitigation*: `Dockerfile.server` explicitly installs `nftables`; `NftSetup.__init__` provides a clear `SystemExit(3)` with an actionable error message if `nft` is missing.
- **RISK-002**: The timed set element syntax (`{ ip . port timeout Xs }`) differs between older `nft` versions.  *Mitigation*: Specify `nft >= 0.9.3` in `INSTALL` and `DEP-001`; blackbox image pins the package version.
- **RISK-003**: The kernel removes the timed element slightly before `openDuration` seconds under high-load conditions.  *Mitigation*: This is the same race that existed with `RuleTimer.sleep()`; the `nftables` kernel path is strictly more accurate.
- **ASSUMPTION-001**: The deployment kernel is `>= 4.1` (timed set support).  This is satisfied by all distributions listed in `DEP-001`.
- **ASSUMPTION-002**: The `nft` CLI argument syntax for `add element` with timeout is stable across `nft >= 0.9.3` and does not change in a backwards-incompatible way.

## 8. Related Specifications / Further Reading

- [Existing Modernisation Plan (Step 3)](file:///workspaces/knockknock/docs/plans/refactor-modernise-codebase-1.md)
- [hping3 Replacement Plan](file:///workspaces/knockknock/docs/plans/refactor-hping3-replacement-1.md)
- [Verification & Validation Rules](file:///workspaces/knockknock/.agents/rules/verification-validation-rules.md)
- [nftables wiki — sets with timeouts](https://wiki.nftables.org/wiki-nftables/index.php/Sets)
- [nftables wiki — rate limiting](https://wiki.nftables.org/wiki-nftables/index.php/Rate_limiting_matchings)
