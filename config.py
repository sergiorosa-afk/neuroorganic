import os

# Em produção (HostGator), defina a variável DATABASE_URL com a senha URL-encoded:
# mysql+pymysql://fionco36_neuroorganic:12345%40Mudar@localhost:3306/fionco36_neuroorganic
_default_db = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'dev.db')}"

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'troque-esta-chave-em-producao')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', _default_db)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
