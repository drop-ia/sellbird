#!/bin/sh
# Container entry for Dokploy: the Access check on 127.0.0.1:5556, the Caddy
# front on :8080 and, by default, the dashboard on 127.0.0.1:5555. Any argument
# runs that Sellbird command instead (for example `setup` or `gmail auth`),
# without the front.
set -eu

if [ "$#" -gt 0 ] && [ "$1" != "dashboard" ]; then
  exec python -m sellbird "$@"
fi

python /usr/local/lib/sellbird/access_auth.py &
auth_pid=$!

caddy run --config /etc/caddy/Caddyfile --adapter caddyfile &
caddy_pid=$!

python -m sellbird dashboard &
sellbird_pid=$!

# Stop all three when any one exits, so Dokploy restarts the container.
trap 'kill "$auth_pid" "$caddy_pid" "$sellbird_pid" 2>/dev/null || true' INT TERM
while kill -0 "$auth_pid" 2>/dev/null && kill -0 "$caddy_pid" 2>/dev/null \
  && kill -0 "$sellbird_pid" 2>/dev/null; do
  sleep 5
done
kill "$auth_pid" "$caddy_pid" "$sellbird_pid" 2>/dev/null || true
wait || true
exit 1
