#!/bin/sh
set -e

echo "Applying fix for docker-in-docker /tmp mount..."
if [ -f /usr/local/share/docker-init.sh ]; then
    sed -i 's|mount -t tmpfs none /tmp|true|g' /usr/local/share/docker-init.sh
    echo "Successfully patched /usr/local/share/docker-init.sh"
else
    echo "Warning: /usr/local/share/docker-init.sh not found to patch"
fi
