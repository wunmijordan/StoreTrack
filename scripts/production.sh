#!/usr/bin/env bash
set -Eeuo pipefail

run_build() {
  python -m pip install --disable-pip-version-check -r requirements.txt
  python manage.py collectstatic --noinput
  python manage.py check
}

run_release() {
  python manage.py migrate --noinput
  python manage.py run_scheduled_jobs
}

run_server() {
  exec daphne \
    --bind 0.0.0.0 \
    --port "${PORT:-10000}" \
    --http-timeout "${DAPHNE_HTTP_TIMEOUT:-120}" \
    --ping-interval "${DAPHNE_PING_INTERVAL:-30}" \
    --ping-timeout "${DAPHNE_PING_TIMEOUT:-20}" \
    --websocket-max-message-size "${DAPHNE_WEBSOCKET_MAX_MESSAGE_SIZE:-16384}" \
    --proxy-headers \
    --access-log - \
    storetrack.asgi:application
}

case "${1:-}" in
  build)
    run_build
    ;;
  jobs)
    python manage.py run_scheduled_jobs
    ;;
  release)
    run_release
    ;;
  serve)
    run_release
    run_server
    ;;
  deploy)
    run_build
    run_release
    ;;
  *)
    echo "Usage: $0 {build|jobs|release|serve|deploy}" >&2
    exit 2
    ;;
esac
