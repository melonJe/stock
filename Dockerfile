# Build stage
FROM python:3.10-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.10-slim

# Set timezone
ENV TZ="Asia/Seoul"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Copy only necessary files from builder
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Copy application code
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0"]
