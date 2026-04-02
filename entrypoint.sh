#!/bin/sh

# Wait for DB to be ready (Standard in Docker Compose)
echo "Waiting for PostgreSQL at $DATABASE_HOST:$DATABASE_PORT..."
while ! nc -z $DATABASE_HOST $DATABASE_PORT; do
  sleep 1
done
echo "PostgreSQL is up and running!"

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate --no-input

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --no-input

# Start the application using Daphne (ASGI) for WebSockets support
echo "Starting Daphne server (ASGI)..."
daphne -b 0.0.0.0 -p 8000 app.asgi:application
