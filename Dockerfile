# Use a lightweight python image
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
ENV FLASK_DEBUG=False
ENV DISABLE_SSL=False

# Run with Gunicorn eventlet worker
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "-b", "0.0.0.0:5000", "server:app"]
