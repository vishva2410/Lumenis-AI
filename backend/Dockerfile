# ============================================================
# Lumenis AI — Backend Dockerfile (Multi-Stage Build)
# ============================================================
# Stage 1: Builder — install Python dependencies in a venv
# Stage 2: Runtime — slim image with only what's needed
# ============================================================

# --------------- Stage 1: Builder ---------------
FROM python:3.11-slim AS builder

# Prevent Python from writing .pyc files & enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install build-time system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment so we can copy it cleanly
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /tmp/requirements.txt


# --------------- Stage 2: Runtime ---------------
FROM python:3.11-slim AS runtime

LABEL maintainer="Lumenis AI Team" \
      description="Lumenis AI Backend — Medical Image Analysis API" \
      version="1.0.0"

# Prevent Python from writing .pyc files & enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install runtime-only system dependencies
#   - libpq5: PostgreSQL client library (runtime counterpart of libpq-dev)
#   - libgl1-mesa-glx + libglib2.0-0: required by OpenCV (cv2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the pre-built virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create a non-root user for security
RUN groupadd --gid 1000 lumenis \
    && useradd --uid 1000 --gid lumenis --shell /bin/bash --create-home lumenis

# Set working directory
WORKDIR /app

# Copy application source code
COPY --chown=lumenis:lumenis . /app

# Switch to non-root user
USER lumenis

# Expose the API port
EXPOSE 8000

# Health check — hit the /health endpoint every 30s
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
