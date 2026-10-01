---
goal: Comprehensive Multi-Tier Testing Framework (Unit, Integration, Docker Blackbox E2E)
version: 1.1
date_created: 2026-10-01
last_updated: 2026-10-01
owner: Quality Engineering
status: Complete
tags: [testing, pytest, pytest-gremlins, docker, docker-compose, blackbox, e2e, integration, unit]
---

# Introduction

![Status: Complete](https://img.shields.io/badge/status-Complete-brightgreen)

This implementation plan specifies the architecture and execution tasks for **Step 2** of the `knockknock` project roadmap: building a multi-tiered test framework. The framework encompasses unit tests with 100% statement and branch coverage, component integration tests, and a fully decoupled, language-agnostic blackbox end-to-end (E2E) test harness powered by Docker Compose. The blackbox harness deploys `knockknock-daemon` inside an isolated container with its own firewall stack, allowing the test suite to validate the system strictly from the outside over an isolated network bridge using standard CLI tools, network clients (`curl`, `nc`, `hping3`), and POSIX shell scripts without being tied to Python.

## 1. Requirements & Constraints

- **REQ-001**: Unit tests must cover 100% of statements and 100% of branches across all modules in the `knockknock` package (`knockknock/` and `knockknock/proxy/`).
- **REQ-002**: Mutation testing using `pytest-gremlins` must achieve a 100.00% mutation score with zero surviving gremlins (`--strict-pardons`).
- **REQ-003**: Integration tests must validate multi-component interaction pipelines without mocking internal domain boundaries (e.g. `KnockWatcher` -> `LogFile` -> `Profile` -> `PortOpener`).
- **REQ-004**: Blackbox end-to-end tests must be completely language-agnostic and executable via POSIX shell/Bash scripts without importing Python packages or depending on Python test runners.
- **REQ-005**: Blackbox tests must deploy `knockknock-daemon` and a protected backend service inside a container via Docker Compose with `NET_ADMIN` and `SYSLOG` capabilities, isolating all iptables rules from the host system.
- **REQ-006**: Blackbox tests must interact with the system strictly from outside the container across the Docker bridge network via public CLI entry points (`knockknock`, `knockknock-proxy`), kernel knock packets, and standard network clients (`curl`, `nc` / `netcat`, `hping3`).
- **REQ-007**: Test execution must support automated reporting adhering to standard Test Anything Protocol (TAP) or exit codes for CI/CD integration.
- **SEC-001**: Tests must verify cryptographic integrity, counter synchronization, replay attack sliding window enforcement, and rejection of tampered HMACs.
- **SEC-002**: Tests must verify privilege separation and dropping (`os.setuid`, `os.setgid` to `nobody:adm`) in daemon routines.
- **SEC-003**: Tests must verify file permissions for cryptographic keys and configuration directories (`stat.S_IRUSR | stat.S_IWUSR` / `0600`).
- **SEC-004**: Tests must audit subprocess argument sanitization to ensure no shell injection vectors exist when generating `iptables` or `hping3` commands.
- **CON-001**: Production code changes during Step 2 must be strictly prohibited unless required to fix uncovered bugs discovered during test development, adhering strictly to TDD rules.
- **CON-002**: Unit and integration test suites must execute under Python 3.14.7.
- **CON-003**: Blackbox test scripts must require only POSIX shell utilities, `bash`, `docker`, `docker compose`, `iptables`, `hping3`, `curl`, and `netcat`.
- **CON-004**: All tests must clean up ephemeral files, containers, networks, volumes, and background processes upon completion or premature failure.
- **GUD-001**: Adhere to the Transformation Priority Premise (TPP) and TDD rules (`tdd-rules.md`) when creating tests and killing mutation gremlins.
- **GUD-002**: Follow the `pytest-coverage` skill (`.agents/skills/pytest-coverage/SKILL.md`) to inspect annotated source files in `cov_annotate/` and resolve all missing coverage indicators (`!`).
- **GUD-003**: Structure test directories cleanly: `tests/unit/` for isolated unit tests, `tests/integration/` for component workflows, and `tests/blackbox/` for Docker-driven E2E tests.
- **PAT-001**: Fixture-based dependency injection for mocking external subprocess calls (`subprocess.call`), file system operations, and system clocks in unit tests.
- **PAT-002**: Docker Compose isolated bridge network pattern (`knock_net`) connecting the outside test runner to containerized `knockknock-server` for safe, isolated firewall blackbox testing.
- **PAT-003**: Containerized kernel log streaming pattern (`dmesg -w > /var/log/kern.log` with `SYSLOG` capability) for capturing `iptables -j LOG` packets without host kernel log dependencies.

## 2. Implementation Steps

### Implementation Phase 1: Test Infrastructure & Fixtures

- GOAL-001: Establish the test directory structure, pytest configuration, shared unit test fixtures, and Docker Compose blackbox test environment.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Configure `pyproject.toml` or `pytest.ini` with test discovery paths, coverage flags (`--cov=knockknock --cov-branch`), and gremlin target definitions. | [x] | 2026-10-01 |
| TASK-002 | Create `tests/conftest.py` providing reusable pytest fixtures: temporary profile directories, sample cryptographic keys, mock subprocess executors, and synthesized kernel log streams. | [x] | 2026-10-01 |
| TASK-003 | Create `tests/blackbox/Dockerfile.server` and `tests/blackbox/docker-compose.yml` defining the containerized server environment with `NET_ADMIN` / `SYSLOG` capabilities, mock protected service (HTTP echo on port 8080), iptables logging, and `knockknock-daemon`. | [x] | 2026-10-01 |
| TASK-004 | Create `tests/blackbox/run_all.sh` as the master language-agnostic test runner orchestrating container lifecycle (`docker compose up/down`), executing blackbox test scenarios, and emitting TAP-compatible summaries. | [x] | 2026-10-01 |

### Implementation Phase 2: Comprehensive Unit Test Suite

- GOAL-002: Build high-fidelity unit tests achieving 100% statement and branch coverage across all modules in `knockknock/` and `knockknock/proxy/`.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | Implement `tests/unit/test_crypto_engine.py` testing `CryptoEngine`: AES-CTR encryption, MAC calculation, MAC verification, exception raising, byte XOR logic, counter increments, and sliding window boundaries. | [x] | 2026-10-01 |
| TASK-006 | Implement `tests/unit/test_profile.py` and `tests/unit/test_profiles.py` testing `Profile` and `Profiles`: key serialization/deserialization (`cipher.key`, `mac.key`, `counter`, `config`), permissions (`0600`), port queries, IP queries, and DNS hostname resolution. | [x] | 2026-10-01 |
| TASK-007 | Implement `tests/unit/test_log_entry.py` and `tests/unit/test_log_file.py` testing `LogEntry` token parsing, header extraction (`ID`, `SEQ`, `ACK`, `WINDOW`), binary packing, `LogFile` end-seeking, tailing, and file rotation handling. | [x] | 2026-10-01 |
| TASK-008 | Implement `tests/unit/test_daemon_config.py` and `tests/unit/test_rule_timer.py` testing `DaemonConfiguration` defaults and parser errors, and `RuleTimer` thread execution and iptables deletion command invocation. | [x] | 2026-10-01 |
| TASK-009 | Implement `tests/unit/test_port_opener.py` and `tests/unit/test_daemonize.py` testing `PortOpener` request processing, parent process EOF termination, iptables rule construction, and `daemonize` fork/session creation logic. | [x] | 2026-10-01 |
| TASK-010 | Implement `tests/unit/test_knock_watcher.py` testing `KnockWatcher` tail processing, profile matching, decryption error recovery, and syslog notification formatting. | [x] | 2026-10-01 |
| TASK-011 | Implement `tests/unit/test_proxy_endpoints.py` testing `EndpointConnection` and `KnockingEndpointConnection`: connection lifecycle, buffering, socket creation, retry thresholds, and knock packet construction via hping3. | [x] | 2026-10-01 |
| TASK-012 | Implement `tests/unit/test_socks_request_handler.py` testing `SocksRequestHandler`: SOCKS5 handshake, authentication negotiation, command filtering, IPv4/domain address parsing, port decoding, response codes, and buffer streaming. | [x] | 2026-10-01 |

### Implementation Phase 3: Component Integration Tests

- GOAL-003: Implement integration tests validating interconnected component pipelines and end-to-end protocol workflows in Python without network mocks.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-013 | Implement `tests/integration/test_knock_pipeline.py`: connect client `knockknock.py` knock generator -> synthesized kernel log line -> `LogFile` -> `KnockWatcher` -> `PortOpener`, asserting dynamic iptables command execution and counter advance. | [x] | 2026-10-01 |
| TASK-014 | Implement `tests/integration/test_proxy_pipeline.py`: run `ProxyServer` on a test port, connect standard socket client requesting connection to host with profile, verify `KnockingEndpointConnection` knock packet dispatch, and verify two-way data streaming. | [x] | 2026-10-01 |

### Implementation Phase 4: Language-Agnostic Docker Blackbox E2E Test Suite

- GOAL-004: Create self-contained, shell-driven end-to-end blackbox tests executing from outside the Docker container against containerized `knockknock-daemon`.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-015 | Implement `tests/blackbox/test_genprofile_cli.sh`: execute `knockknock-genprofile` binary locally, assert directory structure created, file permissions match `0600`, key files are 16 bytes base64-encoded, and duplicate port conflicts are rejected with proper exit codes. | [x] | 2026-10-01 |
| TASK-016 | Implement `tests/blackbox/test_knock_and_firewall_docker.sh`: spin up `knockknock-server` container via Docker Compose, assert protected port (8080) is initially blocked via `curl`/`nc`, send knock from host using `knockknock` CLI, assert port dynamically opens with HTTP 200 response, and verify port automatically closes after configured delay. | [x] | 2026-10-01 |
| TASK-017 | Implement `tests/blackbox/test_socks_proxy_docker.sh`: start `knockknock-proxy` binary on host, execute standard `curl --socks5-hostname` against firewalled container service, verify auto-knock occurs and proxied HTTP/TCP request completes successfully. | [x] | 2026-10-01 |

### Implementation Phase 5: Mutation Testing & Coverage Validation Gate

- GOAL-005: Execute all verification gates, validate 100% statement and branch coverage via `pytest-cov`, and achieve a 100.00% mutation score via `pytest-gremlins`.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-018 | Execute `pytest --cov=knockknock --cov-branch --cov-report=annotate:cov_annotate --cov-fail-under=100`, inspect `cov_annotate/` per `pytest-coverage`, run `pytest --gremlins --gremlin-targets=knockknock --strict-pardons`, eliminate any surviving gremlins, and run `tests/blackbox/run_all.sh`. | [x] | 2026-10-01 |


## 3. Alternatives

- **ALT-001**: Implement blackbox tests using Python `pytest-subprocess` and Python test clients. Rejected because the user explicitly specified that blackbox tests must not be tied to Python, ensuring tests remain a durable verification harness if components are ever rewritten in C, Go, or Rust.
- **ALT-002**: Run blackbox firewall tests directly on the host network interface. Rejected because modifying host firewall rules can break container connectivity and developer SSH sessions; Docker Compose isolates all firewall rules completely in a disposable container network namespace.
- **ALT-003**: Use bare Linux network namespaces (`ip netns`) instead of Docker containers. Rejected in favor of Docker Compose because Docker containers provide cleaner process isolation, reproducible service packaging, and zero host network state contamination.

## 4. Dependencies

- **DEP-001**: `pytest>=8.0.0` (Python unit and integration test runner)
- **DEP-002**: `pytest-cov>=5.0.0` (Code coverage measurement and branch analysis)
- **DEP-003**: `pytest-gremlins>=1.9.0` (Mutation testing framework for pytest)
- **DEP-004**: `hping3` (CLI packet generator required for client knocks)
- **DEP-005**: `netcat-openbsd` & `curl` (Standard network client utilities used by blackbox test scripts)
- **DEP-006**: `docker` & `docker compose` (Container runtime and multi-container orchestration for isolated blackbox server testing)

## 5. Files

- **FILE-001**: `pyproject.toml` or `pytest.ini` — Pytest configuration, coverage thresholds, and gremlin target rules.
- **FILE-002**: `tests/conftest.py` — Shared pytest fixtures, temporary file generators, and mock factories.
- **FILE-003**: `tests/unit/test_crypto_engine.py` — Unit tests for AES-CTR encryption, HMAC authentication, and sliding window verification.
- **FILE-004**: `tests/unit/test_profile.py` — Unit tests for Profile serialization, deserialization, and permissions.
- **FILE-005**: `tests/unit/test_log_entry.py` — Unit tests for kernel log line parsing and packet reconstruction.
- **FILE-006**: `tests/unit/test_port_opener.py` — Unit tests for firewall rule generation and IPC pipe handling.
- **FILE-007**: `tests/unit/test_socks_request_handler.py` — Unit tests for SOCKS5 state machine and byte protocol framing.
- **FILE-008**: `tests/integration/test_knock_pipeline.py` — Integration test for client knock generation through daemon processing.
- **FILE-009**: `tests/integration/test_proxy_pipeline.py` — Integration test for SOCKS proxy server handling and knock dispatch.
- **FILE-010**: `tests/blackbox/Dockerfile.server` — Dockerfile packaging `knockknock-daemon`, iptables, and mock backend service.
- **FILE-011**: `tests/blackbox/docker-compose.yml` — Compose orchestration defining isolated bridge network, server container, and security capabilities.
- **FILE-012**: `tests/blackbox/test_knock_and_firewall_docker.sh` — Language-agnostic shell script validating full port-knocking and firewall opening lifecycle against the Docker container.
- **FILE-013**: `tests/blackbox/test_socks_proxy_docker.sh` — Language-agnostic shell script validating SOCKS proxy tunneling against the Docker container.
- **FILE-014**: `tests/blackbox/run_all.sh` — Master shell test runner orchestrating Docker Compose and executing all blackbox test scripts with TAP summaries.

## 6. Testing

- **TEST-001**: Unit test suite execution via `pytest tests/unit/` verifying all individual module methods.
- **TEST-002**: Coverage enforcement via `pytest --cov=knockknock --cov-branch --cov-report=annotate:cov_annotate --cov-fail-under=100`.
- **TEST-003**: Mutation testing verification via `pytest --gremlins --gremlin-targets=knockknock --strict-pardons` confirming 0 surviving gremlins.
- **TEST-004**: Integration test suite execution via `pytest tests/integration/` validating cross-module pipelines.
- **TEST-005**: Blackbox profile generation verification via `tests/blackbox/test_genprofile_cli.sh`.
- **TEST-006**: Blackbox Docker Compose knock and proxy verification via `tests/blackbox/test_knock_and_firewall_docker.sh` and `tests/blackbox/test_socks_proxy_docker.sh`.

## 7. Risks & Assumptions

- **RISK-001**: Container `iptables` and `dmesg` logging require `NET_ADMIN` and `SYSLOG` capabilities in Docker Compose. *Mitigation*: Confirmed that Docker-in-Docker in this devcontainer supports `cap_add: [NET_ADMIN, SYSLOG]` without errors.
- **RISK-002**: Timing issues with `RuleTimer` causing slow test execution. *Mitigation*: Unit tests will mock or supply short duration timeouts (`openDuration=0.05`), while Docker blackbox tests will use small delay parameters (`delay=2`).
- **RISK-003**: Mutation testing with `pytest-gremlins` on crypto and socket routines may uncover unasserted branches. *Mitigation*: Tests will assert exact error messages, return types, counter mutations, and exception states.
- **ASSUMPTION-001**: Docker daemon is active and accessible via `/var/run/docker.sock` in this environment.
- **ASSUMPTION-002**: Standard POSIX utilities (`sh`, `bash`, `nc`, `curl`, `hping3`) remain available in the host environment for executing blackbox tests against the container.
- **ASSUMPTION-003**: The blackbox tests can run independently of whether `knockknock` is installed in editable mode or installed as a binary in `/usr/local/bin`.

## 8. Related Specifications / Further Reading

- [Step 1 Migration Plan: Python 3.14 Compatibility](file:///home/vscode/.gemini/antigravity-ide/brain/adbdf2f6-3cec-4f6b-ab7b-a72ebde91ada/step_one_python3_migration_plan.md)
- [Verification & Test Suite Validation Rules](file:///workspaces/knockknock/.agents/rules/verification-validation-rules.md)
- [Command Execution and Terminal Rules](file:///workspaces/knockknock/.agents/rules/command-execution-rules.md)
- [Pytest Coverage Skill](file:///workspaces/knockknock/.agents/skills/pytest-coverage/SKILL.md)
- [Spec-Driven Development Skill](file:///workspaces/knockknock/.agents/skills/spec-driven-development/SKILL.md)
