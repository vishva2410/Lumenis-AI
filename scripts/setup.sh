#!/usr/bin/env bash
# ============================================================
# Lumenis AI — One-Command Setup Script
# ============================================================
# Usage:  chmod +x scripts/setup.sh && ./scripts/setup.sh
# ============================================================

set -euo pipefail

# ---- Colors ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ---- Banner ----
echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════╗"
echo "║       Lumenis AI — Development Setup         ║"
echo "║   Medical Image Analysis Platform            ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# ---- Prerequisite Checks ----
info "Checking prerequisites..."

# Docker
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version | head -1)
    success "Docker found: ${DOCKER_VERSION}"
else
    error "Docker is not installed. Please install Docker Desktop: https://docs.docker.com/get-docker/"
fi

# Docker Compose (v2 plugin)
if docker compose version &> /dev/null; then
    COMPOSE_VERSION=$(docker compose version --short)
    success "Docker Compose found: v${COMPOSE_VERSION}"
else
    error "Docker Compose v2 is not available. Please update Docker Desktop."
fi

# Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    success "Python found: ${PYTHON_VERSION}"
else
    warn "Python 3 is not installed. It is required for local development (not needed for Docker)."
fi

# Node.js
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    success "Node.js found: ${NODE_VERSION}"
else
    warn "Node.js is not installed. It will be required for the frontend in later phases."
fi

echo ""

# ---- Environment File ----
info "Setting up environment file..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ -f "${PROJECT_ROOT}/.env" ]; then
    warn ".env file already exists — skipping copy."
else
    if [ -f "${PROJECT_ROOT}/.env.example" ]; then
        cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
        success "Copied .env.example → .env"
    else
        warn ".env.example not found. Creating a minimal .env file..."
        cat > "${PROJECT_ROOT}/.env" <<'ENVEOF'
# ============================================================
# Lumenis AI — Environment Variables
# ============================================================

# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/lumenis
POSTGRES_DB=lumenis
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Redis
REDIS_URL=redis://redis:6379/0

# Qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# App
APP_ENV=development
SECRET_KEY=change-me-in-production
DEBUG=true
ENVEOF
        success "Created .env with default development values."
    fi
fi

echo ""

# ---- Build & Start Services ----
info "Building and starting Docker services..."
cd "${PROJECT_ROOT}"
docker compose up --build -d

echo ""

# ---- Wait for Services ----
info "Waiting for services to become healthy..."

wait_for_service() {
    local service_name="$1"
    local url="$2"
    local max_retries="${3:-30}"
    local retry=0

    while [ $retry -lt $max_retries ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            success "${service_name} is ready!"
            return 0
        fi
        retry=$((retry + 1))
        sleep 2
    done
    warn "${service_name} did not become ready within $((max_retries * 2))s — check logs with 'make logs'"
    return 1
}

# Wait for PostgreSQL via Docker health check
info "Waiting for PostgreSQL..."
RETRIES=0
MAX_RETRIES=30
while [ $RETRIES -lt $MAX_RETRIES ]; do
    PG_STATUS=$(docker inspect --format='{{.State.Health.Status}}' lumenis-postgres 2>/dev/null || echo "missing")
    if [ "$PG_STATUS" = "healthy" ]; then
        success "PostgreSQL is healthy!"
        break
    fi
    RETRIES=$((RETRIES + 1))
    sleep 2
done
if [ $RETRIES -ge $MAX_RETRIES ]; then
    warn "PostgreSQL did not become healthy in time."
fi

# Wait for Redis
info "Waiting for Redis..."
RETRIES=0
while [ $RETRIES -lt $MAX_RETRIES ]; do
    REDIS_STATUS=$(docker inspect --format='{{.State.Health.Status}}' lumenis-redis 2>/dev/null || echo "missing")
    if [ "$REDIS_STATUS" = "healthy" ]; then
        success "Redis is healthy!"
        break
    fi
    RETRIES=$((RETRIES + 1))
    sleep 2
done

# Wait for Backend
wait_for_service "Backend API" "http://localhost:8000/health" 30 || true

# Wait for Frontend
wait_for_service "Next.js Frontend" "http://localhost:3000" 45 || true

# Wait for Qdrant
wait_for_service "Qdrant" "http://localhost:6333/healthz" 20 || true

echo ""

# ---- Run Migrations ----
info "Running database migrations..."
if docker compose exec -T backend alembic upgrade head 2>/dev/null; then
    success "Database migrations completed!"
else
    warn "Migrations skipped (this is normal on first run before models are defined)."
fi

echo ""

# ---- Done! ----
echo -e "${BOLD}${GREEN}"
echo "╔══════════════════════════════════════════════╗"
echo "║         ✅  Setup Complete!                  ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "  ${BOLD}Service URLs:${NC}"
echo -e "  ─────────────────────────────────────────"
echo -e "  🌐 Frontend Web UI: ${CYAN}http://localhost:3000${NC}"
echo -e "  🚀 Backend API:    ${CYAN}http://localhost:8000${NC}"
echo -e "  📖 API Docs:       ${CYAN}http://localhost:8000/docs${NC}"
echo -e "  🐘 PostgreSQL:     ${CYAN}localhost:5432${NC}"
echo -e "  🔴 Redis:          ${CYAN}localhost:6379${NC}"
echo -e "  🧠 Qdrant REST:    ${CYAN}http://localhost:6333${NC}"
echo -e "  🧠 Qdrant gRPC:    ${CYAN}localhost:6334${NC}"
echo ""
echo -e "  ${BOLD}Useful Commands:${NC}"
echo -e "  ─────────────────────────────────────────"
echo -e "  make logs           Follow service logs"
echo -e "  make backend-shell  Shell into backend"
echo -e "  make down           Stop all services"
echo -e "  make test           Run tests"
echo ""
