import sys
import os

# Activate venv
VENV = os.path.join(os.path.dirname(__file__), 'venv')
activate = os.path.join(VENV, 'bin', 'activate_this.py')
if os.path.exists(activate):
    exec(open(activate).read(), {'__file__': activate})
else:
    # Fallback: insert venv site-packages manually
    import site
    site.addsitedir(os.path.join(VENV, 'lib', 'python3.9', 'site-packages'))

sys.path.insert(0, os.path.dirname(__file__))

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from app import app as application
