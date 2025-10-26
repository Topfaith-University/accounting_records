#!/bin/sh
set -e

echo "🚀 Starting Django + Neo4j app..."

# Apply migrations (for relational parts, if added later)
echo "📦 Applying migrations..."
python manage.py migrate --noinput || true

# Collect static files
echo "🎨 Collecting static files..."
python manage.py collectstatic --noinput

# Create default superuser (if not exists)
echo "👤 Checking for default superuser..."
python manage.py shell <<EOF2
import os
from django.contrib.auth import get_user_model
User = get_user_model()
username = os.getenv("DJANGO_SUPERUSER_USERNAME", "admin")
email = os.getenv("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "admin123")

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f"✅ Superuser created: {username}")
else:
    print(f"ℹ️ Superuser already exists: {username}")
EOF2

# Wait for Neo4j to be ready
echo "⏳ Waiting for Neo4j to start..."
sleep 10

echo "🌍 Running Django server on 0.0.0.0:8002..."
exec python manage.py runserver 0.0.0.0:8002
