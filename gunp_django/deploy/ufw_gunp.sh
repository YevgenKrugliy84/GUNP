#!/usr/bin/env bash
# Opens port 8095 (the GUNP nginx vhost) in ufw, scoped to the same internal
# subnets already used for the other УІАП service (5051/tcp) on this host,
# instead of allowing "Anywhere". Must be run with sudo; one-time setup, not
# invoked by install.sh since firewall changes are security-sensitive enough
# to warrant a separate, explicit step.
set -euo pipefail

for subnet in 10.111.16.0/24 10.111.24.0/24 10.111.21.0/24; do
    ufw allow from "$subnet" to any port 8095 proto tcp comment 'GUNP portal'
done

ufw reload

echo "Done. Current 8095 rules:"
ufw status | grep 8095
