FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies needed for compiling python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create a non-root user and change ownership of app files
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

# Expose port 5000
EXPOSE 5000

# Define env variables
ENV PORT=5000
ENV ANONYMUS_LOG_LEVEL=info
ENV ANONYMUS_PRODUCTION=True

# Run with Granian Rust ASGI server
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "5000", "transports.p2p.app_v3:app"]
