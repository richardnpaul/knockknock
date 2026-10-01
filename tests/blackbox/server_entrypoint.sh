#!/bin/bash
set -e

# If arguments are passed, execute them directly (e.g. for client containers)
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

echo "=== Initializing Knockknock Server Container ==="

# 1. Setup kern.log streaming
mkdir -p /var/log
touch /var/log/kern.log

# Start userspace packet logger to ensure logs are captured even if dmesg is restricted
python3 /app/tests/blackbox/packet_logger.py &
LOGGER_PID=$!

# Also try dmesg in background (may fail harmlessly if dmesg_restrict is on)
dmesg -w >> /var/log/kern.log 2>&1 &
DMESG_PID=$!

# 2. Setup mock HTTP protected service on port 8080
echo "Starting mock protected service on port 8080..."
python3 -m http.server 8080 --directory /tmp &
HTTP_PID=$!

# 3. Setup knockknock profile for knockPort 7000
echo "Generating test profile on knock port 7000..."
knockknock-genprofile testclient 7000

# Setup daemon configuration with 3s delay for fast test verification
cat << 'EOF' > /etc/knockknock.d/config
[main]
delay = 3
error_window = 20
EOF

# 4. Copy profile to shared volume for client if available
if [ -d "/shared" ]; then
    mkdir -p /shared/testclient
    cp -r /etc/knockknock.d/profiles/testclient/* /shared/testclient/
    chmod -R 777 /shared/testclient
    echo "Exported profile to /shared/testclient"
fi

# 5. Apply iptables firewall rules
echo "Applying minimal firewall rules..."
iptables -F || true
iptables -X || true

iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT

iptables -N REJECTLOG
iptables -A REJECTLOG -j LOG --log-level debug --log-tcp-sequence --log-tcp-options --log-ip-options --log-prefix "REJECT "
iptables -A REJECTLOG -p tcp -j REJECT --reject-with tcp-reset
iptables -A REJECTLOG -j REJECT

# Route knock port (7000) and protected service (8080) to REJECTLOG
iptables -A INPUT -p tcp --dport 7000 -j REJECTLOG
iptables -A INPUT -p tcp --dport 8080 -j REJECTLOG

echo "Firewall active. Starting knockknock-daemon..."
knockknock-daemon

echo "Knockknock-daemon running. Tailing log file..."
trap "kill $LOGGER_PID $DMESG_PID $HTTP_PID 2>/dev/null || true; exit 0" SIGTERM SIGINT

tail -f /var/log/kern.log
