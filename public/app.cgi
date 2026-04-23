#!/home3/fionco36/neuroseller.com.br/neuroorganic/venv/bin/python3.9
import sys
import os
import traceback

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

LOG = os.path.join(APP_DIR, 'tmp', 'cgi_error.log')

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(APP_DIR, '.env'))

    from wsgiref.handlers import CGIHandler
    from app import app

    CGIHandler().run(app)

except Exception:
    os.makedirs(os.path.join(APP_DIR, 'tmp'), exist_ok=True)
    with open(LOG, 'w') as f:
        traceback.print_exc(file=f)
    print("Content-Type: text/plain\n")
    print("Erro interno. Verifique tmp/cgi_error.log")
