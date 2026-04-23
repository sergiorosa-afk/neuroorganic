import os
from flask import Flask, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config import Config
from models import db, Usuario, Cliente, PromptEstilo, Post, Configuracao, DIAS, DIAS_LABEL
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Faça login para continuar.'

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')
        usuario = Usuario.query.filter_by(email=email, ativo=True).first()

        if usuario and usuario.check_senha(senha):
            login_user(usuario)
            return redirect(url_for('dashboard'))

        flash('Email ou senha incorretos.', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ── Dashboard (cliente vê só os próprios posts) ───────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    posts = Post.query.filter_by(
        cliente_id=current_user.cliente_id
    ).order_by(Post.created_at.desc()).limit(20).all()

    contadores = {
        'pendente': Post.query.filter_by(cliente_id=current_user.cliente_id, status='pendente').count(),
        'aprovado': Post.query.filter_by(cliente_id=current_user.cliente_id, status='aprovado').count(),
        'publicado': Post.query.filter_by(cliente_id=current_user.cliente_id, status='publicado').count(),
        'reprovado': Post.query.filter_by(cliente_id=current_user.cliente_id, status='reprovado').count(),
    }

    from datetime import date as _date
    return render_template('dashboard.html', posts=posts, contadores=contadores,
                           DIAS_LABEL=DIAS_LABEL, today=_date.today().isoformat())


# ── Aprovação / Reprovação de posts ───────────────────────────────────────────

@app.route('/post/<int:post_id>/aprovar', methods=['POST'])
@login_required
def aprovar_post(post_id):
    post = Post.query.filter_by(id=post_id, cliente_id=current_user.cliente_id).first_or_404()
    post.status = 'aprovado'
    post.aprovado_por = current_user.id
    post.aprovado_em = datetime.utcnow()
    db.session.commit()

    cliente = post.cliente
    if cliente.make_webhook_url:
        from webhook import disparar_webhook
        try:
            disparar_webhook(cliente.make_webhook_url, post, request.url_root)
            post.status = 'publicado'
            post.publicado_em = datetime.utcnow()
            db.session.commit()
            flash('Post aprovado e enviado para publicação no Instagram!', 'success')
        except Exception as e:
            flash(f'Post aprovado, mas falha ao enviar ao Make.com: {e}', 'warning')
    else:
        flash('Post aprovado! Configure o webhook Make.com para publicar automaticamente.', 'success')

    return redirect(url_for('dashboard'))


@app.route('/post/<int:post_id>/reprovar', methods=['POST'])
@login_required
def reprovar_post(post_id):
    post = Post.query.filter_by(id=post_id, cliente_id=current_user.cliente_id).first_or_404()
    feedback = request.form.get('feedback', '').strip()
    post.status = 'reprovado'
    post.feedback = feedback
    db.session.commit()
    flash('Post reprovado. Feedback registrado.', 'warning')
    return redirect(url_for('dashboard'))


# ── Admin — Prompts por dia ───────────────────────────────────────────────────

@app.route('/admin/prompts')
@login_required
def admin_prompts():
    if not current_user.is_admin:
        abort(403)

    clientes = Cliente.query.filter_by(ativo=True).all()
    cliente_id = request.args.get('cliente_id', clientes[0].id if clientes else None, type=int)
    cliente_sel = Cliente.query.get_or_404(cliente_id)

    prompts = {p.dia_semana: p for p in PromptEstilo.query.filter_by(cliente_id=cliente_id).all()}

    return render_template('admin/prompts.html',
                           clientes=clientes,
                           cliente_sel=cliente_sel,
                           prompts=prompts,
                           DIAS=DIAS,
                           DIAS_LABEL=DIAS_LABEL)


@app.route('/admin/prompts/salvar', methods=['POST'])
@login_required
def salvar_prompt():
    if not current_user.is_admin:
        abort(403)

    cliente_id = request.form.get('cliente_id', type=int)
    dia = request.form.get('dia_semana')
    intencao = request.form.get('intencao', '').strip()
    prompt_imagem = request.form.get('prompt_imagem', '').strip()
    texto_subheadline = request.form.get('texto_subheadline', '').strip()
    texto_cta = request.form.get('texto_cta', '').strip()

    prompt = PromptEstilo.query.filter_by(cliente_id=cliente_id, dia_semana=dia).first()
    if prompt:
        prompt.intencao = intencao
        prompt.prompt_imagem = prompt_imagem
        prompt.texto_subheadline = texto_subheadline
        prompt.texto_cta = texto_cta
    else:
        prompt = PromptEstilo(cliente_id=cliente_id, dia_semana=dia,
                              intencao=intencao, prompt_imagem=prompt_imagem,
                              texto_subheadline=texto_subheadline, texto_cta=texto_cta)
        db.session.add(prompt)

    db.session.commit()
    flash(f'Prompt de {DIAS_LABEL[dia]} salvo com sucesso.', 'success')
    return redirect(url_for('admin_prompts', cliente_id=cliente_id))


# ── Admin — Planejamento ──────────────────────────────────────────────────────

@app.route('/admin/planejamento')
@login_required
def admin_planejamento():
    if not current_user.is_admin:
        abort(403)
    clientes = Cliente.query.filter_by(ativo=True).all()
    cliente_id = request.args.get('cliente_id', clientes[0].id if clientes else None, type=int)
    cliente_sel = Cliente.query.get_or_404(cliente_id)
    return render_template('admin/planejamento.html', clientes=clientes, cliente_sel=cliente_sel)


@app.route('/admin/planejamento/salvar', methods=['POST'])
@login_required
def salvar_planejamento():
    if not current_user.is_admin:
        abort(403)
    cliente_id = request.form.get('cliente_id', type=int)
    cliente = Cliente.query.get_or_404(cliente_id)
    cliente.planejamento_texto = request.form.get('planejamento_texto', '').strip()
    db.session.commit()
    flash('Planejamento salvo.', 'success')
    return redirect(url_for('admin_planejamento', cliente_id=cliente_id))


@app.route('/admin/planejamento/preview', methods=['POST'])
@login_required
def preview_planejamento():
    if not current_user.is_admin:
        abort(403)
    from generate import parsear_planejamento
    from datetime import datetime

    cliente_id = request.form.get('cliente_id', type=int)
    cliente = Cliente.query.get_or_404(cliente_id)
    texto = request.form.get('planejamento_texto', '').strip()

    if texto:
        cliente.planejamento_texto = texto
        db.session.commit()

    entries = parsear_planejamento(texto)
    DIAS_LABEL_MAP = {'segunda': 'Segunda', 'terca': 'Terça', 'quarta': 'Quarta',
                      'quinta': 'Quinta', 'sexta': 'Sexta', 'sabado': 'Sábado', 'domingo': 'Domingo'}
    DIAS_MAP = {0: 'segunda', 1: 'terca', 2: 'quarta', 3: 'quinta', 4: 'sexta', 5: 'sabado', 6: 'domingo'}

    preview = []
    for e in entries:
        dia = DIAS_MAP.get(e['data'].weekday(), '?')
        label = DIAS_LABEL_MAP.get(dia, dia)
        post_ativo = Post.query.filter(
            Post.cliente_id == cliente_id,
            Post.data_publicacao == e['data'],
            Post.status.in_(['pendente', 'aprovado', 'publicado']),
        ).first()
        fim_de_semana = e['data'].weekday() >= 5
        preview.append({
            'data': e['data'].strftime('%d/%m/%Y'),
            'dia': label,
            'titulo': e['titulo'],
            'legenda_curta': e['legenda'][:80] + '...' if len(e['legenda']) > 80 else e['legenda'],
            'ja_existe': bool(post_ativo),
            'fim_de_semana': fim_de_semana,
        })

    clientes = Cliente.query.filter_by(ativo=True).all()
    return render_template('admin/planejamento.html',
                           clientes=clientes, cliente_sel=cliente,
                           preview=preview)


@app.route('/admin/planejamento/gerar', methods=['POST'])
@login_required
def gerar_do_planejamento():
    if not current_user.is_admin:
        abort(403)
    import threading
    from generate import parsear_planejamento, gerar_do_planejamento as _gerar

    cliente_id = request.form.get('cliente_id', type=int)
    cliente = Cliente.query.get_or_404(cliente_id)
    texto = request.form.get('planejamento_texto', '').strip()

    if texto:
        cliente.planejamento_texto = texto
        db.session.commit()

    entries = parsear_planejamento(cliente.planejamento_texto or '')
    novos = [e for e in entries if e['data'].weekday() < 5]

    if not novos:
        flash('Nenhuma entrada válida encontrada.', 'error')
        return redirect(url_for('admin_planejamento', cliente_id=cliente_id))

    def _worker(app_ctx, entries, cliente_id):
        with app_ctx:
            from generate import gerar_do_planejamento as _g
            cliente_obj = Cliente.query.get(cliente_id)
            for entry in entries:
                try:
                    _g(cliente_obj, entry)
                    print(f"[bg] ✓ {entry['data']} — {entry['titulo'][:50]}")
                except Exception as e:
                    print(f"[bg] erro {entry['data']}: {e}")

    t = threading.Thread(target=_worker, args=(app.app_context(), novos, cliente_id), daemon=True)
    t.start()

    flash(f'Gerando {len(novos)} criativo(s) em segundo plano. Atualize o dashboard em instantes.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/admin/cliente/<int:cliente_id>/contexto', methods=['POST'])
@login_required
def salvar_contexto(cliente_id):
    if not current_user.is_admin:
        abort(403)
    cliente = Cliente.query.get_or_404(cliente_id)
    cliente.contexto = request.form.get('contexto', '').strip()
    db.session.commit()
    flash('Contexto da marca salvo com sucesso.', 'success')
    return redirect(url_for('admin_prompts', cliente_id=cliente_id))


@app.route('/admin/cliente/<int:cliente_id>/logo', methods=['POST'])
@login_required
def upload_logo(cliente_id):
    if not current_user.is_admin:
        abort(403)
    cliente = Cliente.query.get_or_404(cliente_id)
    f = request.files.get('logo')
    if not f or not f.filename:
        flash('Nenhum arquivo selecionado.', 'error')
        return redirect(url_for('admin_prompts', cliente_id=cliente_id))

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.svg'):
        flash('Formato inválido. Use PNG, JPG ou SVG.', 'error')
        return redirect(url_for('admin_prompts', cliente_id=cliente_id))

    logos_dir = os.path.join(app.root_path, 'static', 'uploads', 'logos')
    os.makedirs(logos_dir, exist_ok=True)
    filename = f'logo_{cliente_id}{ext}'
    f.save(os.path.join(logos_dir, filename))
    cliente.logo_url = f'/static/uploads/logos/{filename}'
    db.session.commit()
    flash('Logo salvo com sucesso.', 'success')
    return redirect(url_for('admin_prompts', cliente_id=cliente_id))


# ── Admin — Clientes ──────────────────────────────────────────────────────────

@app.route('/admin/clientes')
@login_required
def admin_clientes():
    if not current_user.is_admin:
        abort(403)
    clientes = Cliente.query.order_by(Cliente.nome).all()
    return render_template('admin/clientes.html', clientes=clientes)


@app.route('/admin/clientes/novo', methods=['GET', 'POST'])
@login_required
def novo_cliente():
    if not current_user.is_admin:
        abort(403)

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        instagram = request.form.get('instagram_handle', '').strip().lstrip('@')
        webhook = request.form.get('make_webhook_url', '').strip()
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '').strip()

        if not nome or not instagram or not email or not senha:
            flash('Preencha todos os campos obrigatórios.', 'error')
            return render_template('admin/novo_cliente.html')

        if Usuario.query.filter_by(email=email).first():
            flash('Este email já está cadastrado.', 'error')
            return render_template('admin/novo_cliente.html')

        cliente = Cliente(nome=nome, instagram_handle=instagram, make_webhook_url=webhook)
        db.session.add(cliente)
        db.session.flush()

        usuario = Usuario(cliente_id=cliente.id, nome=nome, email=email, role='cliente')
        usuario.set_senha(senha)
        db.session.add(usuario)
        db.session.commit()

        flash(f'Cliente {nome} criado com sucesso.', 'success')
        return redirect(url_for('admin_clientes'))

    return render_template('admin/novo_cliente.html')


# ── Admin — Configurações ─────────────────────────────────────────────────────

PROVEDORES_IMAGEM = [
    ('pollinations', 'Pollinations.ai (Flux)', 'Gratuito, sem chave API', None),
    ('fal_flux',     'Flux Realism (fal.ai)',  'Melhor qualidade — requer FAL_KEY', 'FAL_KEY'),
    ('imagen3',      'Imagen 3 (Google)',       'Alta qualidade — requer GEMINI_API_KEY + billing', 'GEMINI_API_KEY'),
]


@app.route('/admin/configuracoes', methods=['GET', 'POST'])
@login_required
def admin_configuracoes():
    if not current_user.is_admin:
        abort(403)

    if request.method == 'POST':
        provedor = request.form.get('provedor_imagem', 'pollinations')
        if provedor not in [p[0] for p in PROVEDORES_IMAGEM]:
            flash('Provedor inválido.', 'error')
        else:
            Configuracao.set('provedor_imagem', provedor)
            db.session.commit()
            flash('Configuração salva com sucesso.', 'success')
        return redirect(url_for('admin_configuracoes'))

    provedor_atual = Configuracao.get('provedor_imagem', 'pollinations')
    chaves_presentes = {k: bool(os.environ.get(k)) for k in ['GEMINI_API_KEY', 'FAL_KEY']}

    return render_template('admin/configuracoes.html',
                           provedores=PROVEDORES_IMAGEM,
                           provedor_atual=provedor_atual,
                           chaves=chaves_presentes)


# ── Geração de conteúdo ──────────────────────────────────────────────────────

@app.route('/admin/gerar', methods=['POST'])
@login_required
def admin_gerar():
    if not current_user.is_admin:
        abort(403)
    from datetime import date as _date
    from generate import gerar_posts_hoje
    data_str = request.form.get('data_publicacao', '').strip()
    try:
        alvo = _date.fromisoformat(data_str) if data_str else _date.today()
    except ValueError:
        flash('Data inválida.', 'error')
        return redirect(url_for('dashboard'))
    try:
        posts = gerar_posts_hoje(data=alvo)
        if posts:
            flash(f'{len(posts)} post(s) gerado(s) para {alvo.strftime("%d/%m/%Y")}!', 'success')
        else:
            flash(
                f'Nenhum post gerado para {alvo.strftime("%d/%m/%Y")}. '
                'Verifique se a data é dia útil e se já não existe um post ativo para esse dia.',
                'warning',
            )
    except Exception as e:
        flash(f'Erro ao gerar post: {e}', 'error')
    return redirect(url_for('dashboard'))


@app.route('/post/<int:post_id>/regerar', methods=['POST'])
@login_required
def regerar_post(post_id):
    post = Post.query.filter_by(id=post_id, cliente_id=current_user.cliente_id).first_or_404()
    if post.status not in ('pendente', 'reprovado'):
        flash('Só é possível regerar posts pendentes ou reprovados.', 'error')
        return redirect(url_for('dashboard'))
    from generate import regerar_post as _regerar
    try:
        _regerar(post)
        flash('Novo post gerado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao regerar post: {e}', 'error')
    return redirect(url_for('dashboard'))


@app.route('/cron/gerar', methods=['POST'])
def cron_gerar():
    """HTTP endpoint for scheduled post generation.

    Requires X-Cron-Token header matching CRON_SECRET env var.
    Called by cron services (cron-job.org, EasyCron, etc.) or cron_gerar.py.
    """
    token = os.environ.get('CRON_SECRET', '')
    if not token or request.headers.get('X-Cron-Token') != token:
        abort(403)
    from generate import gerar_posts_hoje
    posts = gerar_posts_hoje()
    return jsonify({'gerados': len(posts), 'post_ids': [p.id for p in posts]})


@app.cli.command('gerar-posts')
def gerar_posts_cmd():
    """Gera posts para todos os clientes ativos para o dia de hoje."""
    from generate import gerar_posts_hoje
    posts = gerar_posts_hoje()
    print(f'{len(posts)} post(s) gerado(s).')


# ── API para Make.com ─────────────────────────────────────────────────────────

def _check_token():
    token = request.args.get('token') or request.headers.get('X-Token')
    if token != os.environ.get('CRON_SECRET', 'token123'):
        abort(401, 'Token inválido.')

def _base_url():
    """Public base URL — uses REQUEST_BASE_URL env var in production."""
    return os.environ.get('REQUEST_BASE_URL', request.host_url.rstrip('/'))


@app.route('/api/posts/publicar')
def api_posts_publicar():
    """Return approved posts for a given date (default: today).

    Make.com calls this daily. Query params:
      ?token=SEU_TOKEN&data=22/04/2026   (optional — defaults to today)
    """
    _check_token()
    from datetime import date as date_cls

    data_str = request.args.get('data')
    if data_str:
        try:
            alvo = datetime.strptime(data_str, '%d/%m/%Y').date()
        except ValueError:
            return jsonify(error='Formato de data inválido. Use DD/MM/AAAA.'), 400
    else:
        alvo = date_cls.today()

    posts = Post.query.filter_by(status='aprovado', data_publicacao=alvo).all()

    base = _base_url()
    result = []
    for p in posts:
        result.append({
            'id': p.id,
            'titulo': p.titulo,
            'legenda': p.legenda,
            'imagem_url': f"{base}{p.imagem_url}" if p.imagem_url else None,
            'instagram_handle': p.cliente.instagram_handle,
            'data_publicacao': p.data_publicacao.strftime('%d/%m/%Y'),
            'marcar_publicado_url': f"{base}/api/posts/{p.id}/publicado?token={os.environ.get('CRON_SECRET', 'token123')}",
        })

    return jsonify(total=len(result), data=alvo.strftime('%d/%m/%Y'), posts=result)


@app.route('/api/posts/<int:post_id>/publicado', methods=['POST', 'GET'])
def api_marcar_publicado(post_id):
    """Mark a post as published. Make.com calls this after posting to Instagram."""
    _check_token()
    post = Post.query.get_or_404(post_id)
    if post.status == 'aprovado':
        post.status = 'publicado'
        db.session.commit()
    return jsonify(ok=True, post_id=post_id, status=post.status)


# ── Init BD ───────────────────────────────────────────────────────────────────

@app.cli.command('init-db')
def init_db():
    db.create_all()
    print('Tabelas criadas.')


@app.cli.command('criar-admin')
def criar_admin():
    from models import Cliente, Usuario
    cliente = Cliente.query.first()
    if not cliente:
        cliente = Cliente(nome='Neuroseller', instagram_handle='neuroseller1')
        db.session.add(cliente)
        db.session.flush()

    if not Usuario.query.filter_by(email='admin@neuroorganic.com').first():
        admin = Usuario(cliente_id=cliente.id, nome='Admin',
                        email='admin@neuroorganic.com', role='admin')
        admin.set_senha('Admin@2026')
        db.session.add(admin)
        db.session.commit()
        print('Admin criado: admin@neuroorganic.com / Admin@2026')
    else:
        print('Admin já existe.')


@app.cli.command('aplicar-texto-imagens')
def aplicar_texto_imagens():
    """AVISO: só use em imagens recém-geradas (sem overlay anterior) para evitar gradiente duplo."""
    from generate import compor_texto_na_imagem, _logo_filepath
    posts = Post.query.filter(Post.imagem_url.isnot(None)).all()
    ok = 0
    for post in posts:
        filepath = os.path.join(app.root_path, post.imagem_url.lstrip('/'))
        if not os.path.exists(filepath):
            print(f'  [skip] arquivo não encontrado: {filepath}')
            continue
        try:
            pe = post.cliente.prompts  # list
            prompt_dia = next((p for p in pe if p.dia_semana == post.dia_semana and p.ativo), None)
            subheadline = prompt_dia.texto_subheadline if prompt_dia else ""
            cta = prompt_dia.texto_cta if prompt_dia else "Acesse o link na bio"
            logo_path = _logo_filepath(post.cliente.logo_url)
            compor_texto_na_imagem(filepath, post.titulo, subheadline=subheadline, cta=cta, logo_path=logo_path)
            print(f'  ✓ {post.titulo[:60]}')
            ok += 1
        except Exception as e:
            print(f'  [erro] post {post.id}: {e}')
    print(f'\nConcluído: {ok}/{len(posts)} imagens atualizadas.')


if __name__ == '__main__':
    app.run(debug=True)
