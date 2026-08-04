#!/usr/bin/env bash
# QuickJob runner — all dev and production commands in one place.
#
# FIRST TIME
#   ./run.sh setup      Copy .env files from examples, validate they are filled,
#                       build all containers and start the stack.
#                       Re-running is safe — skips copying if .env files already exist.
#
# DAY-TO-DAY
#   ./run.sh up         Production mode: nginx on :80, compiled images, detached.
#   ./run.sh dev        Dev mode: FastAPI --reload on :8000, Next.js dev server on :3000.
#                       No nginx. Source directories mounted for live changes.
#                       NOTE: uvicorn --reload may not detect file changes on Windows
#                       hosts with Docker Desktop (WSL2 inotify limitation). Run
#                       './run.sh restart api' to manually restart the container.
#
# OTHER
#   ./run.sh logs [svc] Tail logs. Scope to: api | nextjs | celery | redis | nginx | postgres
#   ./run.sh restart    Stop then start in production mode.
#   ./run.sh ps         Show container status and health checks.
#   ./run.sh shell [s]  Open a shell inside a container (default: api).
#   ./run.sh down       Stop all containers.
#   ./run.sh clean      Full wipe — containers + volumes (asks for confirmation).
#   ./run.sh help       Show this message.

set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
CMD="${1:-help}"

# ── Helpers ───────────────────────────────────────────────────────────────────

info()    { echo ""; echo "==> $*"; }
success() { echo ""; echo "    OK: $*"; }
abort()   { echo ""; echo "ERROR: $*" >&2; exit 1; }

# Check Docker daemon is reachable before doing anything.
_require_docker() {
  if ! docker info >/dev/null 2>&1; then
    abort "Docker is not running. Start Docker Desktop (or the daemon) and try again."
  fi
}

# Poll an endpoint until HTTP 200 or timeout.
# Usage: _wait_for_health <url> <label>
_wait_for_health() {
  local url="$1"
  local label="${2:-$url}"
  local timeout=90
  local interval=3
  local elapsed=0

  info "Waiting for ${label} to be healthy (timeout ${timeout}s)..."
  while [ "$elapsed" -lt "$timeout" ]; do
    if curl -sf "$url" >/dev/null 2>&1; then
      success "${label} is healthy"
      return 0
    fi
    sleep "$interval"
    elapsed=$((elapsed + interval))
    echo "    ... waiting (${elapsed}s)"
  done

  echo ""
  echo "ERROR: ${label} did not become healthy in ${timeout}s." >&2
  echo "       Run './run.sh logs' to investigate." >&2
  exit 1
}

# Validate that required env vars inside a file are non-empty or whitespace-only.
# Usage: _check_env_vars apps/api/.env SUPABASE_URL ANTHROPIC_API_KEY ...
_check_env_vars() {
  local file="$1"; shift
  local missing=()
  for var in "$@"; do
    # Match KEY= followed by nothing OR only whitespace (catches "KEY=   " too)
    if grep -qE "^${var}=[[:space:]]*$" "$file" 2>/dev/null; then
      missing+=("$var")
    fi
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    echo ""
    echo "ERROR: The following required variables are empty in ${file}:" >&2
    for v in "${missing[@]}"; do
      echo "         $v" >&2
    done
    echo ""
    echo "       Fill them in and run './run.sh setup' again." >&2
    exit 1
  fi
}

# ── Commands ──────────────────────────────────────────────────────────────────

cmd_setup() {
  _require_docker

  # Tear down anything already running to avoid port conflicts between
  # a previously started dev/prod stack and the one we are about to start.
  info "Stopping any existing containers..."
  docker compose down 2>/dev/null || true

  # ── Backend .env ───────────────────────────────────────────────
  if [ ! -f apps/api/.env ]; then
    if [ ! -f apps/api/.env.example ]; then
      abort "apps/api/.env.example not found. Cannot scaffold environment."
    fi
    cp apps/api/.env.example apps/api/.env
    echo ""
    echo "Created apps/api/.env from apps/api/.env.example."
    echo "Open it and fill in the required values, then run './run.sh setup' again."
    exit 0
  fi

  # ── Frontend .env.local ────────────────────────────────────────
  if [ ! -f apps/web/.env.local ]; then
    if [ ! -f apps/web/.env.example ]; then
      abort "apps/web/.env.example not found. Cannot scaffold environment."
    fi
    cp apps/web/.env.example apps/web/.env.local
    echo ""
    echo "Created apps/web/.env.local from apps/web/.env.example."
    echo "Open it and fill in the required values, then run './run.sh setup' again."
    exit 0
  fi

  # ── Validate required vars are filled ─────────────────────────
  info "Validating environment variables..."
  _check_env_vars apps/api/.env \
    SUPABASE_URL \
    SUPABASE_SERVICE_ROLE_KEY \
    SUPABASE_JWT_SECRET \
    UPSTASH_REDIS_REST_URL \
    UPSTASH_REDIS_REST_TOKEN \
    REDIS_PASSWORD

  _check_env_vars apps/web/.env.local \
    NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY

  success "Environment looks good."

  # ── Supabase schema reminder ───────────────────────────────────
  echo ""
  echo "  REMINDER: If this is your first time, apply the database schema:"
  echo "  Open supabase/schema.sql in the Supabase SQL editor and run it."
  echo ""
  read -r -p "  Have you applied the schema? [y/N] " schema_done
  if [ "$schema_done" != "y" ] && [ "$schema_done" != "Y" ]; then
    echo ""
    echo "  Apply the schema first, then run './run.sh setup' again."
    exit 0
  fi

  # ── Build and start ────────────────────────────────────────────
  info "Building and starting all containers..."
  docker compose up --build -d

  _wait_for_health "http://localhost/api/health" "QuickJob (nginx → FastAPI)"

  echo ""
  echo "  QuickJob is running!"
  echo ""
  echo "    App:    http://localhost"
  echo "    API:    http://localhost/api/health"
  echo ""
  echo "  Day-to-day:  ./run.sh up"
  echo "  Dev mode:    ./run.sh dev"
  echo "  Logs:        ./run.sh logs"
}

cmd_up() {
  _require_docker
  info "Starting QuickJob (production mode)..."
  docker compose up --build -d
  _wait_for_health "http://localhost/api/health" "QuickJob (nginx → FastAPI)"
  echo ""
  echo "  App: http://localhost | API: http://localhost/api/health"
}

cmd_dev() {
  _require_docker

  if [ ! -f apps/api/.env ] || [ ! -f apps/web/.env.local ]; then
    abort "Environment files missing. Run './run.sh setup' first."
  fi

  # Tear down any existing stack (prod or dev) to avoid port conflicts.
  info "Stopping any existing containers..."
  docker compose down 2>/dev/null || true

  info "Starting QuickJob (dev mode — hot reload, no nginx)..."
  docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d

  # Poll FastAPI directly — no nginx in dev mode.
  _wait_for_health "http://localhost:8000/api/health" "FastAPI"

  echo ""
  echo "  FastAPI:  http://localhost:8000        (hot reload)"
  echo "  Swagger:  http://localhost:8000/docs"
  echo "  Next.js:  http://localhost:3000        (Next.js dev server)"
  echo ""
  echo "  Source changes are picked up instantly — no rebuild needed."
  echo "  NOTE: On Windows, uvicorn --reload may not detect changes."
  echo "        Use './run.sh restart api' if a change is missed."
}

cmd_logs() {
  # $1 is the optional service name (passed from dispatch as "${2:-}")
  local service="${1:-}"
  if [ -n "$service" ]; then
    docker compose logs -f "$service"
  else
    docker compose logs -f
  fi
}

cmd_restart() {
  _require_docker
  info "Restarting QuickJob..."
  docker compose down
  docker compose up --build -d
  _wait_for_health "http://localhost/api/health" "QuickJob (nginx → FastAPI)"
}

cmd_ps() {
  docker compose ps
}

cmd_shell() {
  # $1 is the optional service name (passed from dispatch as "${2:-api}")
  local service="${1:-api}"
  info "Opening shell in ${service}..."
  docker compose exec "$service" /bin/sh
}

cmd_down() {
  info "Stopping all containers..."
  docker compose down
  success "All containers stopped."
}

cmd_clean() {
  echo ""
  echo "WARNING: This will delete all containers AND the Redis data volume."
  echo "         Your Supabase data is unaffected (it lives in the cloud)."
  echo ""
  read -r -p "  Type 'yes' to confirm: " confirm
  if [ "$confirm" != "yes" ]; then
    abort "Cancelled."
  fi
  docker compose down -v
  success "Wiped. Run './run.sh setup' to start fresh."
}

cmd_help() {
  cat <<'EOF'

  QuickJob — available commands

    ./run.sh setup          First-time init: scaffold .env files, validate config,
                            build containers, start the stack. Safe to re-run.

    ./run.sh up             Production mode — nginx on :80, compiled images.
    ./run.sh dev            Dev mode — FastAPI hot-reload on :8000, Next.js on :3000.
                            Source directories mounted. No nginx.

    ./run.sh logs [service] Tail logs. Scope to: api | nextjs | celery | redis | nginx | postgres
    ./run.sh restart        Stop then start in production mode.
    ./run.sh ps             Show container status and health.
    ./run.sh shell [svc]    Shell into a container (default: api).
    ./run.sh down           Stop all containers.
    ./run.sh clean          Full wipe — containers + volumes (asks for confirmation).
    ./run.sh help           Show this message.

  First time:    ./run.sh setup
  Day-to-day:    ./run.sh up       →  http://localhost
  Development:   ./run.sh dev      →  http://localhost:8000 + http://localhost:3000

EOF
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
# Pass only the service/subarg (${2:-}) to functions that need it,
# rather than the full "$@", so functions don't need to know their
# position in the argument list.

case "$CMD" in
  setup)   cmd_setup              ;;
  up)      cmd_up                 ;;
  dev)     cmd_dev                ;;
  logs)    cmd_logs    "${2:-}"   ;;
  restart) cmd_restart            ;;
  ps)      cmd_ps                 ;;
  shell)   cmd_shell   "${2:-}"   ;;
  down)    cmd_down               ;;
  clean)   cmd_clean              ;;
  help|*)  cmd_help               ;;
esac
