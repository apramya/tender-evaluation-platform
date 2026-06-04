# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY backend/requirements.txt .
COPY backend/requirements-ml.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --user --no-cache-dir -r requirements.txt \
    && pip install --user --no-cache-dir --retries 10 --timeout 120 -r requirements-ml.txt

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies (including Tesseract for OCR)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Set environment variables
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Copy application code
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/alembic.ini ./alembic.ini
COPY backend/migrations ./migrations

# Create upload and logs directories
RUN mkdir -p uploads logs temp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/health')" || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
