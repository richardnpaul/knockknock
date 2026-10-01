---
goal: Modernise Codebase Architecture, pyproject.toml Packaging, Asyncio Proxy, and CI Pipeline
version: 1.0
date_created: 2026-10-01
last_updated: 2026-10-01
owner: Architecture & Engineering
status: Complete
tags: [refactoring, modernisation, pyproject, asyncio, ci, github-actions, mypy, typing]
---

# Introduction

![Status: Complete](https://img.shields.io/badge/status-Complete-brightgreen)

This implementation plan specifies the architecture and execution tasks for **Step 3** of the `knockknock` project roadmap: modernising the codebase. Building on the foundational Python 3.14 compatibility established in Step 1 and the comprehensive test framework established in Step 2, this step modernises project packaging, testing workflows, protocol concurrency, and software architecture:

1. **Packaging & Configuration Modernisation**: Adopting PEP 517/518/621 declarative configuration via `pyproject.toml`, consolidating project metadata, dependencies, scripts, and tool configs (`pytest`, `coverage`, `mypy`), while eliminating legacy `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, and `.coveragerc`.
2. **Continuous Integration (CI)**: Implementing an automated multi-job GitHub Actions workflow (`.github/workflows/ci.yml`) enforcing static analysis, strict typing, 100% statement and branch coverage, zero surviving gremlins via `pytest-gremlins`, and Docker Compose blackbox E2E verification on every pull request and push.
3. **Core Modernisation**: Integrating modern cryptographic safety (constant-time `hmac.compare_digest` to prevent timing attacks), filesystem abstraction via `pathlib.Path`, clean resource management (`with open(...)`), modern CLI argument parsing with `argparse` preserving exact legacy exit code contracts, and comprehensive static type annotations (`mypy --strict`).
4. **Asyncio Concurrency Migration**: Migrating the SOCKS5 proxy subsystem (`knockknock/proxy/`) from legacy `asyncore`/`asynchat` event loops to Python 3's native `asyncio` streams and protocols, eliminating obsolete external dependencies (`pyasyncore`, `pyasynchat`) and leaving `pycryptodome` as the sole external runtime dependency.

## 1. Requirements & Constraints

- **REQ-001**: Migrate all packaging, dependencies, and tool configurations into a single declarative `pyproject.toml` adhering to PEP 517, PEP 518, and PEP 621, deprecating `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, and `.coveragerc`.
- **REQ-002**: Implement an automated GitHub Actions CI workflow in `.github/workflows/ci.yml` running linting, typechecking, 100% coverage tests, mutation testing, and containerized blackbox E2E tests.
- **REQ-003**: Refactor the SOCKS5 proxy architecture (`knockknock/proxy/`) from legacy `asyncore` and `asynchat` to Python 3 standard library `asyncio` (`asyncio.start_server`, `asyncio.open_connection`, `StreamReader`, `StreamWriter`), removing `pyasyncore` and `pyasynchat` dependencies.
- **REQ-004**: Add full type annotations across all modules in `knockknock/` and provide a PEP 561 `py.typed` marker, achieving zero errors under `mypy --strict`.
- **REQ-005**: Upgrade MAC verification in `knockknock/CryptoEngine.py` to use `hmac.compare_digest` for constant-time comparison to protect against timing attacks.
- **REQ-006**: Modernize CLI parsing in `knockknock.py`, `knockknock-genprofile.py`, `knockknock-daemon.py`, and `knockknock-proxy.py` using `argparse`, strictly preserving existing CLI argument flags, error messages, and legacy exit codes (2 for client errors, 3 for daemon/genprofile/proxy errors).
- **REQ-007**: Modernize file path handling and persistence using `pathlib.Path` with explicit context managers (`with` blocks) for all file descriptors.
- **SEC-001**: Cryptographic MAC comparison must use constant-time comparison (`hmac.compare_digest`) to eliminate side-channel timing attack vectors.
- **SEC-002**: CLI arguments must be validated and sanitized through structured `argparse` type validators to prevent unexpected type coercion or parameter injection.
- **SEC-003**: Key and profile file generation must continue enforcing strict user-only read/write permissions (`stat.S_IRUSR | stat.S_IWUSR` / `0600`) via `pathlib.Path.chmod`.
- **CON-001**: Strict wire and protocol compatibility must be maintained; packet formats, crypto counters, sliding window logic, and firewall rules must remain 100% compatible.
- **CON-002**: Code coverage baseline must remain at 100% statement and 100% branch coverage across all modules (`--cov-fail-under=100`).
- **CON-003**: Mutation testing with `pytest-gremlins` must maintain a 100.00% mutation score with zero surviving gremlins (`--strict-pardons`).
- **CON-004**: All existing blackbox Docker E2E tests (`tests/blackbox/run_all.sh`) must pass cleanly without modification to external test contracts.
- **GUD-001**: Apply Test-Driven Development (TDD) and the Transformation Priority Premise (TPP) during all refactoring tasks.
- **GUD-002**: Follow the Verification and Test Suite Validation rules (`verification-validation-rules.md`) to achieve outer loop convergence.
- **GUD-003**: Cleanly separate socket orchestration from protocol framing in `asyncio` proxy components.
- **PAT-001**: PEP 621 declarative metadata and dependency table pattern in `pyproject.toml`.
- **PAT-002**: Asyncio streaming protocol and bidirectional pipe forwarding pattern (`asyncio.create_task` with `stream.read` and `stream.write`).
- **PAT-003**: Matrix and parallel pipeline CI pattern in GitHub Actions.

## 2. Implementation Steps

### Implementation Phase 1: Packaging Modernisation & pyproject.toml Consolidation

- GOAL-001: Modernise package architecture, metadata, dependencies, and tool settings using a unified `pyproject.toml`.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Create modern `pyproject.toml` with `[build-system]` (setuptools>=69.0), PEP 621 `[project]`, `dependencies`, `[project.optional-dependencies]` (`dev`), `[project.scripts]`, `[tool.pytest.ini_options]`, `[tool.coverage.*]`, and `[tool.mypy]`. | [x] | 2026-10-01 |
| TASK-002 | Deprecate and remove redundant legacy config files (`requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `.coveragerc`) and update `.gitignore` accordingly. | [x] | 2026-10-01 |
| TASK-003 | Validate editable installation (`pip install -e .[dev]`), dependency consistency (`pip check`), and verify pytest and coverage discovery from `pyproject.toml`. | [x] | 2026-10-01 |

### Implementation Phase 2: Continuous Integration (CI) Setup

- GOAL-002: Implement an automated multi-stage GitHub Actions CI workflow.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Create `.github/workflows/ci.yml` configuring jobs for: (a) Static Analysis & Type Checking (`compileall`, `flake8`, `mypy`), (b) Unit & Integration Tests (100% coverage enforcement), (c) Mutation Testing Gate (`pytest-gremlins`), and (d) Package Build & CLI Smoke Tests. | [x] | 2026-10-01 |
| TASK-005 | Configure containerized Blackbox E2E test job in `.github/workflows/ci.yml` running Docker Compose and `tests/blackbox/run_all.sh`. | [x] | 2026-10-01 |
| TASK-006 | Validate CI workflow YAML schema integrity and test local execution of CI commands. | [x] | 2026-10-01 |


### Implementation Phase 3: Core Modernisation (Crypto, Pathlib, Argparse, Type Hints)

- GOAL-003: Modernise core utilities, cryptographic comparisons, file handling, CLI parsing, and static typing.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-007 | Update `knockknock/CryptoEngine.py` to use `hmac.compare_digest` for constant-time MAC verification and add strict type annotations. | [x] | 2026-10-01 |
| TASK-008 | Refactor `knockknock/Profile.py` and `knockknock/Profiles.py` using `pathlib.Path`, context managers for counter file persistence, and complete type annotations. | [x] | 2026-10-01 |
| TASK-009 | Modernise `knockknock/LogEntry.py`, `knockknock/LogFile.py`, `knockknock/DaemonConfiguration.py`, `knockknock/RuleTimer.py`, `knockknock/PortOpener.py`, and `knockknock/daemonize.py` with type annotations and modern idioms. | [x] | 2026-10-01 |
| TASK-010 | Refactor CLI entrypoints (`knockknock.py`, `knockknock-genprofile.py`, `knockknock-daemon.py`, `knockknock-proxy.py`) using `argparse`, preserving exact exit codes (2 for client errors, 3 for daemon/genprofile/proxy errors) and error output format. | [x] | 2026-10-01 |
| TASK-011 | Add `knockknock/py.typed` marker (PEP 561) and verify complete static type checking pass via `mypy --strict knockknock`. | [x] | 2026-10-01 |

### Implementation Phase 4: Asyncio Migration for SOCKS5 Proxy Subsystem

- GOAL-004: Migrate the SOCKS5 proxy architecture to modern Python `asyncio` and eliminate legacy `asyncore`/`asynchat` dependencies.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | Refactor `knockknock/proxy/EndpointConnection.py` and `knockknock/proxy/KnockingEndpointConnection.py` to use `asyncio.open_connection` with `StreamReader` and `StreamWriter`. | [x] | 2026-10-01 |
| TASK-013 | Refactor `knockknock/proxy/SocksRequestHandler.py` to an asyncio stream protocol handling SOCKS5 handshakes, address parsing, and asynchronous bidirectional streaming. | [x] | 2026-10-01 |
| TASK-014 | Modernise `knockknock-proxy.py` (`ProxyServer`) to utilize `asyncio.start_server` and `asyncio.run()`. | [x] | 2026-10-01 |
| TASK-015 | Remove `pyasyncore` and `pyasynchat` from `pyproject.toml` dependencies, leaving `pycryptodome` as the sole external runtime dependency, and verify with `pip check`. | [x] | 2026-10-01 |
| TASK-016 | Update proxy unit and integration tests in `tests/unit/test_proxy_endpoints.py`, `tests/unit/test_socks_request_handler.py`, and `tests/integration/test_proxy_pipeline.py` to test asyncio streams cleanly without `asyncore.socket_map`. | [x] | 2026-10-01 |

### Implementation Phase 5: Verification, Mutation Testing & Validation Convergence

- GOAL-005: Execute the full verification-validation meta-loop, ensuring 100% coverage, 0 surviving gremlins, and clean blackbox tests.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-017 | Update `tests/blackbox/Dockerfile.server` to install the package using `pip install .` without referencing removed requirements files. | [x] | 2026-10-01 |
| TASK-018 | Execute the full Verification & Validation meta-loop: all 5 Quality Gates (unit tests, 100% coverage, 0 surviving gremlins, flake8/mypy, package installation & CLI smoke tests), inner code review, inner security review, and blackbox test runner (`tests/blackbox/run_all.sh`), ensuring outer loop convergence. | [x] | 2026-10-01 |

## 3. Alternatives

- **ALT-001**: Retain `requirements.txt` as a wrapper pointing to `pyproject.toml`. Rejected in favor of modern PEP 621 declarative packaging where `pyproject.toml` is the sole source of truth for dependencies.
- **ALT-002**: Migrate build backend to `poetry` or `flit`. Rejected in favor of standard `setuptools` (PEP 517/621) which is natively supported by pip, requires no additional third-party tools, and keeps the build stack lightweight.
- **ALT-003**: Keep `pyasyncore` and `pyasynchat` backports instead of rewriting proxy in `asyncio`. Rejected because `asyncore` and `asynchat` were removed from Python standard library in 3.12, whereas `asyncio` is the modern standard, offering superior performance, native concurrency primitives, and zero external dependencies.

## 4. Dependencies

- **DEP-001**: `setuptools>=69.0.0` & `wheel` (PEP 517/518/621 build backend)
- **DEP-002**: `pycryptodome>=3.20.0` (Core cryptographic cipher and HMAC engine; sole external runtime dependency)
- **DEP-003**: `pytest>=8.0.0` & `pytest-cov>=5.0.0` (Unit/integration test execution and 100% coverage measurement)
- **DEP-004**: `pytest-gremlins>=1.9.0` (Mutation testing framework for gremlin slaughter)
- **DEP-005**: `flake8>=7.0.0` & `mypy>=1.10.0` (Linter and strict static type checker)
- **DEP-006**: `docker` & `docker compose` (Isolated containerized blackbox E2E test harness)

## 5. Files

- **FILE-001**: `pyproject.toml` — Modern unified project metadata, dependencies, entry points, and tool configurations.
- **FILE-002**: `.github/workflows/ci.yml` — Multi-stage GitHub Actions CI workflow specification.
- **FILE-003**: `knockknock/py.typed` — PEP 561 marker declaring type hints are available.
- **FILE-004**: `knockknock/CryptoEngine.py` — Modernized crypto engine with `hmac.compare_digest` and type hints.
- **FILE-005**: `knockknock/Profile.py` — Modernized profile persistence with `pathlib.Path` and type hints.
- **FILE-006**: `knockknock/Profiles.py` — Modernized profiles collection with `pathlib.Path` and type hints.
- **FILE-007**: `knockknock/proxy/SocksRequestHandler.py` — Asyncio SOCKS5 protocol handler.
- **FILE-008**: `knockknock/proxy/EndpointConnection.py` — Asyncio stream endpoint connection.
- **FILE-009**: `knockknock/proxy/KnockingEndpointConnection.py` — Asyncio stream knocking endpoint connection.
- **FILE-010**: `knockknock-proxy.py` — Asyncio proxy server daemon.
- **FILE-011**: `knockknock.py` — Client CLI entry point with `argparse`.
- **FILE-012**: `knockknock-genprofile.py` — Profile generator CLI entry point with `argparse`.
- **FILE-013**: `knockknock-daemon.py` — Daemon CLI entry point with `argparse`.
- **FILE-014**: `tests/blackbox/Dockerfile.server` — Updated server Dockerfile installing from `pyproject.toml`.

## 6. Testing

- **TEST-001**: Static typing check via `mypy --strict knockknock`.
- **TEST-002**: Coverage gate via `pytest --cov=knockknock --cov-branch --cov-report=annotate:cov_annotate --cov-fail-under=100`.
- **TEST-003**: Mutation testing gate via `pytest --gremlins --gremlin-targets=knockknock --strict-pardons`.
- **TEST-004**: CLI smoke tests asserting exact exit codes (`knockknock`: 2, `knockknock-genprofile`: 3, `knockknock-daemon`: 3, `knockknock-proxy`: 3).
- **TEST-005**: Language-agnostic Docker Compose blackbox E2E suite via `tests/blackbox/run_all.sh` (TAP-13 output).

## 7. Risks & Assumptions

- **RISK-001**: Switching SOCKS5 proxy to `asyncio` could subtly alter connection close or buffer flush timing. *Mitigation*: Integration tests and live blackbox curl proxy tests validate that all bytes stream through and connection closes cleanly.
- **RISK-002**: `argparse` standard error messages default to exit code 2, whereas legacy daemons returned exit code 3 on argument errors. *Mitigation*: Override `error()` method in custom `ArgumentParser` subclass to return exact exit code 3.
- **ASSUMPTION-001**: Python standard library `asyncio` is fully available and functional across all target deployment environments.
- **ASSUMPTION-002**: GitHub Actions Linux runners have Docker and Docker Compose preinstalled for running containerized blackbox E2E tests.

## 8. Related Specifications / Further Reading

- [Step 1 Migration Plan: Python 3.14 Compatibility](file:///home/vscode/.gemini/antigravity-ide/brain/adbdf2f6-3cec-4f6b-ab7b-a72ebde91ada/step_one_python3_migration_plan.md)
- [Step 2 Test Framework Implementation Plan](file:///workspaces/knockknock/docs/plans/feature-test-framework-1.md)
- [Verification & Test Suite Validation Rules](file:///workspaces/knockknock/.agents/rules/verification-validation-rules.md)
- [PEP 517 – A build-system independent format for source trees](https://peps.python.org/pep-0517/)
- [PEP 621 – Storing project metadata in pyproject.toml](https://peps.python.org/pep-0621/)
- [PEP 561 – Distributing and Packaging Type Information](https://peps.python.org/pep-0561/)
