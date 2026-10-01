#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
SHARED_DIR="$SCRIPT_DIR/shared"

echo "TAP version 13"
echo "1..3"

cleanup() {
    echo "# Cleaning up Docker containers and temporary files..."
    docker compose -f "$COMPOSE_FILE" down -v --remove-orphans >/dev/null 2>&1 || true
    rm -rf "$SHARED_DIR"
}

trap cleanup EXIT

# Clean old shared data
rm -rf "$SHARED_DIR"
mkdir -p "$SHARED_DIR"

# Test 1: Local CLI profile generation
echo "# Running Test 1: knockknock-genprofile CLI"
if bash "$SCRIPT_DIR/test_genprofile_cli.sh"; then
    echo "ok 1 - knockknock-genprofile CLI validation passed"
else
    echo "not ok 1 - knockknock-genprofile CLI validation failed"
    exit 1
fi

# Build and start server container
echo "# Starting server container via Docker Compose..."
docker compose -f "$COMPOSE_FILE" up -d --build

# Wait for server readiness
echo "# Waiting for server readiness..."
MAX_WAIT=30
WAITED=0
while [ ! -f "$SHARED_DIR/testclient/config" ]; do
    sleep 1
    WAITED=$((WAITED + 1))
    if [ "$WAITED" -ge "$MAX_WAIT" ]; then
        echo "# Timeout waiting for knockknock-server container to initialize"
        docker compose -f "$COMPOSE_FILE" logs
        exit 1
    fi
done
echo "# Server initialized and profile exported."

# Test 2: Knock & Firewall Lifecycle over Docker Bridge Network
echo "# Running Test 2: Knock and Firewall E2E over Docker"
if bash "$SCRIPT_DIR/test_knock_and_firewall_docker.sh"; then
    echo "ok 2 - knock and firewall dynamic open/close passed"
else
    echo "not ok 2 - knock and firewall dynamic open/close failed"
    exit 1
fi

# Test 3: SOCKS Proxy auto-knocking over Docker
echo "# Running Test 3: knockknock-proxy SOCKS5 tunneling"
if bash "$SCRIPT_DIR/test_socks_proxy_docker.sh"; then
    echo "ok 3 - knockknock-proxy SOCKS5 auto-knocking passed"
else
    echo "not ok 3 - knockknock-proxy SOCKS5 auto-knocking failed"
    exit 1
fi

echo "# All blackbox tests completed successfully!"
