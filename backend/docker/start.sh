#!/usr/bin/env bash

set -Eeuo pipefail

render_port="${PORT:-8000}"
celery_pid=""
api_pid=""
shutdown_status=0

terminate_children() {
    local signal="${1:-TERM}"

    if [[ -n "${api_pid}" ]] && kill -0 "${api_pid}" 2>/dev/null; then
        kill "-${signal}" "${api_pid}" 2>/dev/null || true
    fi

    if [[ -n "${celery_pid}" ]] && kill -0 "${celery_pid}" 2>/dev/null; then
        kill "-${signal}" "${celery_pid}" 2>/dev/null || true
    fi
}

handle_sigterm() {
    shutdown_status=143
    terminate_children TERM
}

handle_sigint() {
    shutdown_status=130
    terminate_children INT
}

trap handle_sigterm TERM
trap handle_sigint INT

celery -A app.core.celery_app worker \
    --loglevel=INFO \
    --pool=solo \
    --concurrency=1 &
celery_pid=$!

uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${render_port}" \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips="*" &
api_pid=$!

exited_pid=""
set +e
wait -n -p exited_pid "${api_pid}" "${celery_pid}"
first_status=$?
set -e

if (( shutdown_status != 0 )); then
    set +e
    wait "${api_pid}" 2>/dev/null
    wait "${celery_pid}" 2>/dev/null
    set -e
    exit "${shutdown_status}"
fi

if [[ "${exited_pid}" == "${api_pid}" ]]; then
    terminate_children TERM
    set +e
    wait "${celery_pid}" 2>/dev/null
    set -e

    if (( first_status == 0 )); then
        exit 1
    fi

    exit "${first_status}"
fi

# Celery is critical for document indexing. Stop the API so Render restarts the
# whole service instead of leaving a healthy-looking API without a worker.
terminate_children TERM
set +e
wait "${api_pid}" 2>/dev/null
set -e

if (( first_status == 0 )); then
    exit 1
fi

exit "${first_status}"
