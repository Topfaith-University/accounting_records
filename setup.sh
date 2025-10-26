#!/bin/bash
set -e

echo "🏗️ Setting up Django + Neo4j + Docker project (Banks, Accounts, Reports)..."

# Create project structure
mkdir -p backend
mkdir -p docker

cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Django and Neo4j libraries
pip install django neomodel gunicorn

# Freeze dependencies
pip freeze > requirements.txt

# Create Django project
django-admin startproject core .

# Create apps
python manage.py startapp banks
python manage.py startapp accounts
python manage.py startapp reports

# Add apps to INSTALLED_APPS (works on macOS and Linux)
if [[ "$OSTYPE" == "darwin"* ]]; then
  sed -i '' "/INSTALLED_APPS = \[/a\\
    \ \ \ \ 'banks',\\
    \ \ \ \ 'accounts',\\
    \ \ \ \ 'reports',\\
    \ \ \ \ 'neomodel',
  " core/settings.py
else
  sed -i "/INSTALLED_APPS = \[/a\ \ \ \ 'banks',\n    'accounts',\n    'reports',\n    'neomodel'," core/settings.py
fi

# Add Neo4j configuration to settings
cat >> core/settings.py <<'EOF'

# Neo4j Database Configuration
from neomodel import config
import os
config.DATABASE_URL = os.getenv("NEO4J_BOLT_URL", "bolt://neo4j:password@neo4j:7687")
EOF

# Create static directory
mkdir -p static

# Create .env file
cat > .env <<EOF
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=admin123
SECRET_KEY=$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
DEBUG=True
NEO4J_BOLT_URL=bolt://neo4j:password@neo4j:7687
EOF

deactivate
cd ..

# Create Dockerfile
cat > docker/Dockerfile <<'EOF'
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

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
EOF

# Create entrypoint.sh
cat > docker/entrypoint.sh <<'EOF'
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

echo "🌍 Running Django server on 0.0.0.0:8000..."
exec python manage.py runserver 0.0.0.0:8000
EOF

# Create docker-compose.yml
cat > docker-compose.yml <<'EOF'
version: "3.9"

services:
  web:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: django_web
    volumes:
      - ./backend:/app
    ports:
      - "8000:8000"
    env_file:
      - backend/.env
    environment:
      - PYTHONUNBUFFERED=1
    depends_on:
      - neo4j

  neo4j:
    image: neo4j:5.21
    container_name: django_neo4j
    environment:
      - NEO4J_AUTH=neo4j/password
    ports:
      - "7474:7474"
      - "7687:7687"
EOF

echo "✅ Django + Neo4j + Docker setup complete!"
echo "-------------------------------------------"
echo "Next steps:"
echo "1. cd <your-repo-root>"
echo "2. chmod +x setup.sh"
echo "3. ./setup.sh"
echo "4. docker-compose up --build"
echo ""
echo "Visit: http://localhost:8000"
echo "Login: admin / admin123"
echo "-------------------------------------------"
