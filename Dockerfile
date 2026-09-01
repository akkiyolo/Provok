FROM python:3.12-slim

WORKDIR /app

# System dependencies for PostgreSQL and building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy the entire project (backend and frontend)
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# Expose port 8000 for Render
EXPOSE 8000

# Run Uvicorn in production mode (without --reload)
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
