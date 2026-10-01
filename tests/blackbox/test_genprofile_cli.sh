#!/bin/bash
set -euo pipefail

echo "=== Test 1: knockknock-genprofile CLI Validation ==="

IMAGE_NAME="blackbox-knockknock-server"

# Wrapper to execute knockknock-genprofile in container
run_genprofile() {
    docker run --rm --entrypoint knockknock-genprofile "$IMAGE_NAME" "$@"
}

# 1. Test argument validation (Usage and Exit Code 3)
set +e
run_genprofile
EXIT_CODE=$?
set -e
if [ "$EXIT_CODE" -ne 3 ]; then
    echo "FAIL: Expected exit code 3 for missing arguments, got $EXIT_CODE"
    exit 1
fi

set +e
run_genprofile only_one_arg
EXIT_CODE=$?
set -e
if [ "$EXIT_CODE" -ne 3 ]; then
    echo "FAIL: Expected exit code 3 for 1 argument, got $EXIT_CODE"
    exit 1
fi

echo "Argument validation passed."

# 2. Test profile generation and filesystem structure
TEST_PROFILE="bbtest_$$"
TEST_PORT="9876"
TARGET_DIR="/etc/knockknock.d/profiles/$TEST_PROFILE"

echo "Testing profile generation inside container..."
CONTAINER_ID=$(docker run -d --rm --entrypoint sleep "$IMAGE_NAME" 60)

cleanup() {
    docker rm -f "$CONTAINER_ID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Generate profile
docker exec "$CONTAINER_ID" knockknock-genprofile "$TEST_PROFILE" "$TEST_PORT"

# Verify directory exists
if ! docker exec "$CONTAINER_ID" test -d "$TARGET_DIR"; then
    echo "FAIL: Profile directory $TARGET_DIR was not created"
    exit 1
fi

# Verify required files and 0600 permissions
for file in cipher.key mac.key counter config; do
    if ! docker exec "$CONTAINER_ID" test -f "$TARGET_DIR/$file"; then
        echo "FAIL: Missing expected file $TARGET_DIR/$file"
        exit 1
    fi
    PERMS=$(docker exec "$CONTAINER_ID" stat -c "%a" "$TARGET_DIR/$file" | tr -d '\r\n')
    if [ "$PERMS" != "600" ]; then
        echo "FAIL: Expected permissions 600 for $file, got $PERMS"
        exit 1
    fi
done

# Verify key decoding (16 bytes base64-encoded)
CIPHER_BYTES=$(docker exec "$CONTAINER_ID" sh -c "base64 -d $TARGET_DIR/cipher.key | wc -c" | tr -d '\r\n ')
if [ "$CIPHER_BYTES" -ne 16 ]; then
    echo "FAIL: Expected 16 decoded cipher key bytes, got $CIPHER_BYTES"
    exit 1
fi

MAC_BYTES=$(docker exec "$CONTAINER_ID" sh -c "base64 -d $TARGET_DIR/mac.key | wc -c" | tr -d '\r\n ')
if [ "$MAC_BYTES" -ne 16 ]; then
    echo "FAIL: Expected 16 decoded mac key bytes, got $MAC_BYTES"
    exit 1
fi

# Verify counter and config
COUNTER_VAL=$(docker exec "$CONTAINER_ID" cat "$TARGET_DIR/counter" | tr -d '\r\n ')
if [ "$COUNTER_VAL" != "0" ]; then
    echo "FAIL: Expected initial counter 0, got $COUNTER_VAL"
    exit 1
fi

CONFIG_PORT=$(docker exec "$CONTAINER_ID" sh -c "grep knock_port $TARGET_DIR/config | cut -d= -f2" | tr -d '\r\n ')
if [ "$CONFIG_PORT" != "$TEST_PORT" ]; then
    echo "FAIL: Expected knock_port $TEST_PORT in config, got $CONFIG_PORT"
    exit 1
fi

# 3. Test duplicate port conflict warning
echo "Testing port conflict warning on port $TEST_PORT..."
CONFLICT_OUTPUT=$(docker exec "$CONTAINER_ID" knockknock-genprofile "${TEST_PROFILE}_dup" "$TEST_PORT" 2>&1 || true)
if ! echo "$CONFLICT_OUTPUT" | grep -q "A profile already exists for knock port: $TEST_PORT"; then
    echo "FAIL: Expected port conflict warning, got: $CONFLICT_OUTPUT"
    exit 1
fi

# 4. Test re-creating existing profile
echo "Testing duplicate profile name handling..."
DUP_OUTPUT=$(docker exec "$CONTAINER_ID" knockknock-genprofile "$TEST_PROFILE" "$TEST_PORT" 2>&1 || true)
if ! echo "$DUP_OUTPUT" | grep -q "Profile already exists"; then
    echo "FAIL: Expected 'Profile already exists' message, got: $DUP_OUTPUT"
    exit 1
fi

echo "All knockknock-genprofile CLI validations passed successfully."
exit 0
