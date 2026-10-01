#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_DIR="$SCRIPT_DIR/shared"
SERVER_IP="172.28.0.10"
PROXY_IP="172.28.0.25"
PROXY_PORT="1080"
NETWORK="knock_net"
IMAGE_NAME="blackbox-knockknock-server"
PROXY_CONTAINER="knockknock-test-proxy-$$"

echo "=== Test 3: knockknock-proxy SOCKS5 Auto-Knocking E2E over Docker ==="

cleanup() {
    docker rm -f "$PROXY_CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# 1. Ensure client profile is prepared for SERVER_IP
mkdir -p "$SHARED_DIR/client_profiles/$SERVER_IP"
cp -r "$SHARED_DIR/testclient/"* "$SHARED_DIR/client_profiles/$SERVER_IP/"

# Reset counter to 0 on profile to ensure fresh knock
echo "0" > "$SHARED_DIR/client_profiles/$SERVER_IP/counter"

# 2. Verify port 8080 is blocked for the proxy IP initially
echo "Verifying port 8080 is initially blocked for $PROXY_IP..."
set +e
docker run --rm --network "$NETWORK" --ip "$PROXY_IP" "$IMAGE_NAME" \
    curl -s --connect-timeout 2 "http://$SERVER_IP:8080" >/dev/null 2>&1
CURL_STATUS=$?
set -e
if [ "$CURL_STATUS" -eq 0 ]; then
    echo "FAIL: Port 8080 was accessible before proxy knock!"
    exit 1
fi
echo "Verified port 8080 is blocked initially."

# 3. Start knockknock-proxy inside a container with static IP PROXY_IP
echo "Starting knockknock-proxy daemon on $PROXY_IP:$PROXY_PORT..."
docker run -d --name "$PROXY_CONTAINER" \
    --network "$NETWORK" --ip "$PROXY_IP" \
    --cap-add NET_RAW \
    -v "$SHARED_DIR/client_profiles:/root/.knockknock" \
    "$IMAGE_NAME" \
    sh -c "knockknock-proxy $PROXY_PORT && sleep 300"

# Wait for proxy socket to become ready
echo "Waiting for SOCKS5 proxy to listen on $PROXY_IP:$PROXY_PORT..."
READY=0
for i in $(seq 1 30); do
    if docker exec "$PROXY_CONTAINER" nc -z 127.0.0.1 "$PROXY_PORT" >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 0.5
done

if [ "$READY" -ne 1 ]; then
    echo "FAIL: SOCKS5 proxy failed to start listening on port $PROXY_PORT"
    docker logs "$PROXY_CONTAINER"
    exit 1
fi
echo "SOCKS5 proxy is ready and listening."

# 4. Perform proxied HTTP request with curl using SOCKS5
echo "Executing curl via SOCKS5 proxy (127.0.0.1:$PROXY_PORT) to http://$SERVER_IP:8080..."
set +e
HTTP_RESPONSE=$(docker exec "$PROXY_CONTAINER" \
    curl -v --connect-timeout 10 --socks5 "127.0.0.1:$PROXY_PORT" "http://$SERVER_IP:8080/" 2>&1)
CURL_STATUS=$?
set -e

echo "$HTTP_RESPONSE"

if [ "$CURL_STATUS" -ne 0 ]; then
    echo "FAIL: curl through SOCKS5 proxy failed (exit code $CURL_STATUS)"
    echo "--- Proxy Container Logs ---"
    docker logs "$PROXY_CONTAINER" || true
    echo "--- Server Container Logs ---"
    docker compose -f "$SCRIPT_DIR/docker-compose.yml" logs || true
    exit 1
fi

echo "All SOCKS5 auto-knocking and proxy tunneling tests passed successfully."
exit 0
