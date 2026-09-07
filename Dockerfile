# ==============================================================================
# DOCKERFILE - FASTAPI COGNITIVE BRAIN SERVICE (SLIM BUILD)
# ==============================================================================

FROM python:3.11-slim

# Prevent python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Step 1: Install CPU-only PyTorch FIRST (small ~300 MB vs 2 GB GPU version)
# This prevents sentence-transformers from pulling the GPU torch automatically
RUN pip install --no-cache-dir \
    torch==2.2.2 \
    --index-url https://download.pytorch.org/whl/cpu

# Step 2: Install remaining app dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 3: Copy source code
COPY . .

# Expose FastAPI server port
EXPOSE 8000

# Start server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
