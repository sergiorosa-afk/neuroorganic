#!/usr/bin/env python3
"""Standalone script for automatic daily post generation (Sprint 5).

── HostGator cPanel Cron ────────────────────────────────────────────────────
Run Monday–Friday at 8:00 AM BRT (11:00 UTC). In cPanel → Cron Jobs:

  Minute  Hour  Day  Month  Weekday
    0      11    *     *     1-5

Command (adjust paths to your account):
  /home/fionco36/virtualenv/neuroorganic/3.9/bin/python \
  /home/fionco36/public_html/neuroorganic/cron_gerar.py \
  >> /home/fionco36/logs/neuroorganic_cron.log 2>&1

── HTTP Trigger (alternative) ───────────────────────────────────────────────
Set CRON_SECRET in your environment, then call from any cron service:

  curl -s -X POST https://your-domain.com/cron/gerar \
       -H "X-Cron-Token: <CRON_SECRET>"

─────────────────────────────────────────────────────────────────────────────
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env if present (local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app import app
from generate import gerar_posts_hoje

if __name__ == '__main__':
    with app.app_context():
        posts = gerar_posts_hoje()
        print(f'[cron_gerar] {len(posts)} post(s) gerado(s).')
        for p in posts:
            print(f'  → #{p.id} {p.titulo}')
