#!/bin/bash
# ==============================================================
# Sage Clone — Full Stack Setup (Django + Angular + Neo4j + Docker)
# ==============================================================

set -e

echo "🚀 Setting up Sage Clone full stack..."

# -------------------------------
# 1️⃣ Folder structure
# -------------------------------
mkdir -p backend frontend docker
cd backend

# -------------------------------
# 2️⃣ Python virtual environment
# -------------------------------
echo "🐍 Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# -------------------------------
# 3️⃣ Install backend dependencies
# -------------------------------
echo "📦 Installing backend dependencies..."
cat <<EOT > requirements.txt
Django
djangorestframework
django-cors-headers
neomodel
neo4j-driver
python-decouple
gunicorn
EOT

pip install --upgrade pip
pip install -r requirements.txt

# -------------------------------
# 4️⃣ Create Django project & apps
# -------------------------------
echo "🧱 Creating Django project and apps..."
django-admin startproject config .
python manage.py startapp banks
python manage.py startapp accounts
python manage.py startapp reports

# -------------------------------
# 5️⃣ Environment variables
# -------------------------------
echo "🧩 Creating .env file..."
cat <<EOT > .env
DEBUG=True
SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(24))')
ALLOWED_HOSTS=*
NEO4J_BOLT_URL=bolt://neo4j:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=yourpassword
EOT

# -------------------------------
# 6️⃣ Settings configuration
# -------------------------------
echo "⚙️ Configuring Django settings..."
SETTINGS_FILE="config/settings.py"

cat <<'PYCODE' > $SETTINGS_FILE
from pathlib import Path
from decouple import config
from neomodel import config as neo_config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'banks',
    'accounts',
    'reports',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Neo4j config
neo_config.DATABASE_URL = config('NEO4J_BOLT_URL')

# CORS
CORS_ALLOW_ALL_ORIGINS = True
PYCODE

# -------------------------------
# 7️⃣ URLs + basic API endpoints
# -------------------------------
echo "🌐 Setting up URLs and sample APIs..."
cat <<'PYCODE' > config/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/banks/', include('banks.urls')),
    path('api/accounts/', include('accounts.urls')),
    path('api/reports/', include('reports.urls')),
]
PYCODE

for app in banks accounts reports; do
  cat <<PYCODE > $app/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='${app}_index'),
]
PYCODE

  cat <<PYCODE > $app/views.py
from django.http import JsonResponse

def index(request):
    return JsonResponse({"message": "Welcome to the ${app} API!"})
PYCODE
done

python manage.py migrate
python manage.py collectstatic --noinput
deactivate

cd ..

# -------------------------------
# 8️⃣ Backend Dockerfile
# -------------------------------
echo "🐳 Creating backend Dockerfile..."
cat <<'DOCKER' > docker/Dockerfile.backend
FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend /app

ENV PYTHONUNBUFFERED=1
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
DOCKER

# -------------------------------
# 9️⃣ Angular frontend setup
# -------------------------------
echo "🌍 Creating Angular frontend..."
cd frontend

if ! command -v npm &> /dev/null; then
  echo "❌ npm not found. Please install Node.js and npm."
  exit 1
fi

npm install @angular/cli@17 --save-dev
npx ng new sage-frontend --defaults --skip-git --routing=true --style=css
cd sage-frontend
npm install axios

mkdir -p src/app/services
cat <<'TS' > src/app/services/api.service.ts
import { Injectable } from '@angular/core';
import axios from 'axios';

@Injectable({ providedIn: 'root' })
export class ApiService {
  baseUrl = 'http://localhost:8000/api/';
  async getBanks() {
    const response = await axios.get(this.baseUrl + 'banks/');
    return response.data;
  }
}
TS

cd ../../

cat <<'DOCKER' > docker/Dockerfile.frontend
# Use Node with Debian for better ARM64 support
FROM node:20-bullseye

WORKDIR /app

# 1️⃣ Install Angular CLI globally
RUN npm install -g @angular/cli@17 --legacy-peer-deps

# 2️⃣ Copy only dependency files first
COPY frontend/sage-frontend/package*.json ./

# 3️⃣ Clean cache, remove lockfile & install dependencies
RUN npm cache clean --force \
    && rm -rf node_modules package-lock.json \
    && npm install --legacy-peer-deps --no-optional

# 4️⃣ Install rollup manually (forces JS fallback, avoids missing ARM binary)
RUN npm install rollup@4 --save-dev --force

# 5️⃣ Copy remaining source code
COPY frontend/sage-frontend/ .

# 6️⃣ Set environment variable to skip native Rollup binary
ENV ROLLUP_SKIP_NATIVE=true

EXPOSE 4200

# 7️⃣ Serve Angular app on all interfaces
CMD ["npx", "ng", "serve", "--host", "0.0.0.0"]
DOCKER

# -------------------------------
# 🔟 Docker Compose
# -------------------------------
echo "🧩 Creating docker-compose.yml..."
cat <<'YAML' > docker-compose.yml
version: "3.9"

services:
  backend:
    build:
      context: .
      dockerfile: docker/Dockerfile.backend
    container_name: django_backend
    env_file: backend/.env
    ports:
      - "8000:8000"
    depends_on:
      - neo4j

  frontend:
    build:
      context: .
      dockerfile: docker/Dockerfile.frontend
    container_name: angular_frontend
    ports:
      - "4200:4200"
    depends_on:
      - backend

  neo4j:
    image: neo4j:5
    container_name: neo4j_db
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/yourpassword
    volumes:
      - neo4j_data:/data

volumes:
  neo4j_data:
YAML

echo ""
echo "✅ Setup complete!"
echo "Run the full stack with:"
echo "  docker-compose up --build"
echo ""
echo "🌐 Access:"
echo "  Frontend → http://localhost:4200"
echo "  Backend API → http://localhost:8000/api/"
echo "  Neo4j Browser → http://localhost:7474"
