#!/home3/fionco36/neuroseller.com.br/neuroorganic/venv/bin/python3.9
import sys
import os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(APP_DIR, '.env'))

from wsgiref.handlers import CGIHandler
from app import app

CGIHandler().run(app)
