#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
export SECRET_KEY=dev-local
export CRON_SECRET=token123
export FLASK_APP=app.py
exec "$DIR/venv/bin/flask" run --port 5050
