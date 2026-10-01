#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_DIR="$SCRIPT_DIR/shared"
SERVER_IP="172.28.0.10"
CLIENT_IP="172.28.0.20"
NETWORK="knock_net"
IMAGE_NAME="blackbox-knockknock-server"

echo "=== Test 2: Knock and Firewall Dynamic Open/Close E2E over Docker ==="

# Helper to run commands from the designated client IP on knock_net
client_exec() {
    docker run --rm --network "$NETWORK" --ip "$CLIENT_IP" --cap-add NET_RAW \
        -v "$SHARED_DIR/client_profiles:/root/.knockknock" \
        "$IMAGE_NAME" "$@"
}

# 1. Setup client profile for target 172.28.0.10
echo "Preparing client profile for $SERVER_IP..."
mkdir -p "$SHARED_DIR/client_profiles/$SERVER_IP"
cp -r "$SHARED_DIR/testclient/"* "$SHARED_DIR/client_profiles/$SERVER_IP/"

# 2. Verify protected port 8080 is initially blocked
echo "Verifying port 8080 is initially blocked..."
set +e
client_exec curl -s --connect-timeout 2 "http://$SERVER_IP:8080" >/dev/null 2>&1
CURL_STATUS=$?
set -e
if [ "$CURL_STATUS" -eq 0 ]; then
    echo "FAIL: Port 8080 was accessible before knocking!"
    exit 1
fi
echo "Verified port 8080 is blocked initially (exit code $CURL_STATUS)."

# 3. Send knock from client to open port 8080
echo "Sending knock from $CLIENT_IP to $SERVER_IP:7000 to open port 8080..."
KNOCK_OUTPUT=$(client_exec knockknock -p 8080 "$SERVER_IP")
echo "$KNOCK_OUTPUT"
if ! echo "$KNOCK_OUTPUT" | grep -q "Knock sent."; then
    echo "FAIL: Knock was not sent successfully"
    exit 1
fi

# Give the daemon and iptables a moment to process the knock
sleep 1

# 4. Verify port 8080 is now OPEN for client
echo "Verifying port 8080 is now open..."
HTTP_RESPONSE=$(client_exec curl -s -f --connect-timeout 2 "http://$SERVER_IP:8080")
echo "HTTP Response received successfully: ${HTTP_RESPONSE:0:60}..."

# Verify counter advanced on client profile
NEW_COUNTER=$(cat "$SHARED_DIR/client_profiles/$SERVER_IP/counter" | tr -d '\r\n ')
if [ "$NEW_COUNTER" -lt 1 ]; then
    echo "FAIL: Client counter was not advanced after knock (counter=$NEW_COUNTER)"
    exit 1
fi
echo "Client counter successfully advanced to $NEW_COUNTER."

# 5. Wait for nftables set element timeout to automatically close the port (delay is 3s)
echo "Waiting 4s for port opening rule to expire..."
sleep 4

echo "Verifying port 8080 has automatically closed..."
set +e
client_exec curl -s --connect-timeout 2 "http://$SERVER_IP:8080" >/dev/null 2>&1
CURL_STATUS=$?
set -e
if [ "$CURL_STATUS" -eq 0 ]; then
    echo "FAIL: Port 8080 remained open after configured delay!"
    exit 1
fi
echo "Verified port 8080 automatically closed after expiration (exit code $CURL_STATUS)."

echo "All knock and firewall lifecycle tests passed successfully."
exit 0
