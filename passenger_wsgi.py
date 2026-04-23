import sys
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(APP_DIR, 'venv')

# Inject venv site-packages
sys.path.insert(0, os.path.join(VENV, 'lib', 'python3.9', 'site-packages'))
sys.path.insert(0, APP_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(APP_DIR, '.env'))
except Exception as e:
    pass  # dotenv optional — env vars may already be set

try:
    from app import app as application
except Exception as e:
    import traceback
    error_msg = traceback.format_exc()

    def application(environ, start_response):
        start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
        return [f'STARTUP ERROR:\n{error_msg}'.encode()]
