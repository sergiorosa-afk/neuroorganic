from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class Cliente(db.Model):
    __tablename__ = 'clientes'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    instagram_handle = db.Column(db.String(50), nullable=False)
    make_webhook_url = db.Column(db.Text)
    logo_url = db.Column(db.Text)
    planejamento_texto = db.Column(db.Text, default='')
    ativo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    usuarios = db.relationship('Usuario', backref='cliente', lazy=True)
    prompts = db.relationship('PromptEstilo', backref='cliente', lazy=True)
    posts = db.relationship('Post', backref='cliente', lazy=True)

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('admin', 'cliente'), default='cliente')
    ativo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha, method='pbkdf2:sha256')

    def check_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

    @property
    def is_admin(self):
        return self.role == 'admin'

DIAS = ['segunda', 'terca', 'quarta', 'quinta', 'sexta']
DIAS_LABEL = {
    'segunda': 'Segunda-feira',
    'terca': 'Terça-feira',
    'quarta': 'Quarta-feira',
    'quinta': 'Quinta-feira',
    'sexta': 'Sexta-feira',
}

# MEDIUMTEXT (16 MB) no MySQL; TEXT ilimitado no SQLite
_BIGTEXT = db.Text(16777215)

class PromptEstilo(db.Model):
    __tablename__ = 'prompts_estilo'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    dia_semana = db.Column(db.Enum(*DIAS), nullable=False)
    intencao = db.Column(_BIGTEXT)
    prompt_imagem = db.Column(_BIGTEXT)
    texto_subheadline = db.Column(db.String(120), default='')
    texto_cta = db.Column(db.String(80), default='Acesse o link na bio')
    ativo = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'dia_semana', name='uq_cliente_dia'),
    )

class Post(db.Model):
    __tablename__ = 'posts'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    dia_semana = db.Column(db.Enum(*DIAS))
    data_publicacao = db.Column(db.Date)
    titulo = db.Column(db.String(255))
    legenda = db.Column(_BIGTEXT)
    imagem_url = db.Column(_BIGTEXT)
    prompt_usado = db.Column(_BIGTEXT)
    status = db.Column(db.Enum('pendente', 'aprovado', 'reprovado', 'publicado'), default='pendente')
    feedback = db.Column(_BIGTEXT)
    aprovado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    aprovado_em = db.Column(db.DateTime, nullable=True)
    publicado_em = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
