import sys
import os
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(APP_DIR, 'venv')
LOG = os.path.join(APP_DIR, 'tmp', 'passenger_error.log')

def _log(msg):
    try:
        os.makedirs(os.path.join(APP_DIR, 'tmp'), exist_ok=True)
        with open(LOG, 'a') as f:
            f.write(msg + '\n')
    except:
        pass

_log('=== passenger_wsgi starting ===')

# Inject venv site-packages
try:
    site_packages = os.path.join(VENV, 'lib', 'python3.9', 'site-packages')
    sys.path.insert(0, site_packages)
    sys.path.insert(0, APP_DIR)
    _log(f'sys.path OK: {site_packages}')
except Exception as e:
    _log(f'sys.path ERROR: {e}')

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(APP_DIR, '.env'))
    _log('dotenv OK')
except Exception as e:
    _log(f'dotenv ERROR: {e}')

# Import app
try:
    os.chdir(APP_DIR)
    from app import app as application
    _log('app import OK')
except Exception as e:
    err = traceback.format_exc()
    _log(f'app import ERROR:\n{err}')

    def application(environ, start_response):
        start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
        return [f'STARTUP ERROR:\n{err}'.encode()]
