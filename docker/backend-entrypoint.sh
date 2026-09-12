#!/bin/sh
set -eu

case "${AUTH_REQUIRED:-false}" in
  1|true|TRUE|yes|YES)
    if [ -z "${DATA_ENCRYPTION_KEY:-}" ]; then
      echo "DATA_ENCRYPTION_KEY is required when AUTH_REQUIRED=true." >&2
      exit 1
    fi
    if [ -z "${JWT_SECRET:-}" ] || [ "${JWT_SECRET}" = "loanlens-development-secret-change-me" ]; then
      echo "Set a non-default JWT_SECRET when AUTH_REQUIRED=true." >&2
      exit 1
    fi
    if [ "${POSTGRES_PASSWORD:-}" = "loanlens-dev-only" ]; then
      echo "Set a non-default POSTGRES_PASSWORD when AUTH_REQUIRED=true." >&2
      exit 1
    fi
    ;;
esac

exec "$@"
