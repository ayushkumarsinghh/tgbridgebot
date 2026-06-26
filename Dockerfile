FROM python:3.10-slim

# Prevent python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DOCKER_ENV=true

WORKDIR /app

# Install system core utilities, Xvfb for browser support, and Google Chrome stable
RUN apt-get update && apt-get install -y \
    xvfb \
    xauth \
    wget \
    gnupg \
    curl \
    unzip \
    --no-install-recommends && \
    wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get install -y ./google-chrome-stable_current_amd64.deb --no-install-recommends && \
    rm google-chrome-stable_current_amd64.deb && \
    rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Run the bridge bot script
CMD ["python", "-u", "bridge_bot.py"]
