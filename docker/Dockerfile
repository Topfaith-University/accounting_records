FROM python:3.11-slim

WORKDIR /app

# Copy requirements first (for Docker caching)
COPY backend/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy Django backend code
COPY backend .

# Copy entrypoint script
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8002

ENTRYPOINT ["/entrypoint.sh"]
