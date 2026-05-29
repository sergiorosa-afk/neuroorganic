import os
from flask import Flask, render_template, redirect, url_for, flash, request, abort, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config import Config
from models import db, Usuario, Cliente, PromptEstilo, Post, PromptLayout, Configuracao, DIAS, DIAS_LABEL
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


# ── Helpers multi-tenant ──────────────────────────────────────────────────────

def _require_admin_cliente():
    """For admin routes: returns (cliente_id, None) or (None, redirect_response)."""
    cid = session.get('admin_cliente_id')
    if not cid:
        flash('Selecione uma empresa primeiro.', 'warning')
        return None, redirect(url_for('admin_empresas'))
    cliente = Cliente.query.get(cid)
    if not cliente:
        session.pop('admin_cliente_id', None)
        flash('Empresa não encontrada. Selecione novamente.', 'warning')
        return None, redirect(url_for('admin_empresas'))
    return cid, None


def _get_cliente_id():
    """Returns (cliente_id, None) or (None, redirect_response) for admin+cliente routes."""
    if current_user.is_admin:
        return _require_admin_cliente()
    return current_user.cliente_id, None


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_empresas'))
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')
        usuario = Usuario.query.filter_by(email=email, ativo=True).first()

        if usuario and usuario.check_senha(senha):
            login_user(usuario)
            if usuario.is_admin:
                return redirect(url_for('admin_empresas'))
            return redirect(url_for('dashboard'))

        flash('Email ou senha incorretos.', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    session.pop('admin_cliente_id', None)
    logout_user()
    return redirect(url_for('login'))


# ── Admin — Seletor de Empresa ────────────────────────────────────────────────

@app.route('/admin/empresas')
@login_required
def admin_empresas():
    if not current_user.is_admin:
        abort(403)
    clientes = Cliente.query.filter_by(ativo=True).order_by(Cliente.nome).all()
    selected_id = session.get('admin_cliente_id')
    return render_template('admin/empresas.html', clientes=clientes, selected_id=selected_id)


@app.route('/admin/selecionar-empresa', methods=['POST'])
@login_required
def selecionar_empresa():
    if not current_user.is_admin:
        abort(403)
    cliente_id = request.form.get('cliente_id', type=int)
    cliente = Cliente.query.get_or_404(cliente_id)
    session['admin_cliente_id'] = cliente_id
    flash(f'Empresa {cliente.nome} selecionada.', 'success')
    return redirect(url_for('dashboard'))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin:
        cliente_id, redir = _require_admin_cliente()
        if redir:
            return redir
    else:
        cliente_id = current_user.cliente_id

    posts = Post.query.filter_by(
        cliente_id=cliente_id
    ).order_by(Post.created_at.desc()).limit(20).all()

    contadores = {
        'pendente': Post.query.filter_by(cliente_id=cliente_id, status='pendente').count(),
        'aprovado': Post.query.filter_by(cliente_id=cliente_id, status='aprovado').count(),
        'publicado': Post.query.filter_by(cliente_id=cliente_id, status='publicado').count(),
        'reprovado': Post.query.filter_by(cliente_id=cliente_id, status='reprovado').count(),
    }

    from datetime import date as _date
    cliente_sel = Cliente.query.get(cliente_id)
    layouts_disponiveis = PromptLayout.query.filter_by(
        cliente_id=cliente_id, ativo=True
    ).order_by(PromptLayout.nome).all()
    return render_template('dashboard.html', posts=posts, contadores=contadores,
                           DIAS_LABEL=DIAS_LABEL, today=_date.today().isoformat(),
                           cliente_sel=cliente_sel, layouts=layouts_disponiveis)


# ── Aprovação / Reprovação de posts ───────────────────────────────────────────

@app.route('/post/<int:post_id>/aprovar', methods=['POST'])
@login_required
def aprovar_post(post_id):
    if current_user.is_admin:
        post = Post.query.get_or_404(post_id)
    else:
        post = Post.query.filter_by(id=post_id, cliente_id=current_user.cliente_id).first_or_404()
    post.status = 'aprovado'
    post.aprovado_por = current_user.id
    post.aprovado_em = datetime.utcnow()
    db.session.commit()
    flash('Post aprovado! Será publicado automaticamente no dia agendado.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/post/<int:post_id>/reprovar', methods=['POST'])
@login_required
def reprovar_post(post_id):
    if current_user.is_admin:
        post = Post.query.get_or_404(post_id)
    else:
        post = Post.query.filter_by(id=post_id, cliente_id=current_user.cliente_id).first_or_404()
    feedback = request.form.get('feedback', '').strip()
    post.status = 'reprovado'
    post.feedback = feedback
    db.session.commit()
    flash('Post reprovado. Feedback registrado.', 'warning')
    return redirect(url_for('dashboard'))


# ── Prompts por dia ───────────────────────────────────────────────────────────

@app.route('/prompts')
@login_required
def admin_prompts():
    if current_user.is_admin:
        cid_param = request.args.get('cliente_id', type=int)
        if cid_param:
            session['admin_cliente_id'] = cid_param
    cliente_id, redir = _get_cliente_id()
    if redir:
        return redir
    cliente_sel = Cliente.query.get_or_404(cliente_id)
    prompts = {p.dia_semana: p for p in PromptEstilo.query.filter_by(cliente_id=cliente_id).all()}
    return render_template('admin/prompts.html',
                           cliente_sel=cliente_sel,
                           prompts=prompts,
                           DIAS=DIAS,
                           DIAS_LABEL=DIAS_LABEL)


@app.route('/prompts/salvar', methods=['POST'])
@login_required
def salvar_prompt():
    cliente_id, redir = _get_cliente_id()
    if redir:
        return redir

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
    return redirect(url_for('admin_prompts'))


# ── Planejamento ──────────────────────────────────────────────────────────────

@app.route('/planejamento')
@login_required
def admin_planejamento():
    cliente_id, redir = _get_cliente_id()
    if redir:
        return redir
    cliente_sel = Cliente.query.get_or_404(cliente_id)
    return render_template('admin/planejamento.html', cliente_sel=cliente_sel)


@app.route('/planejamento/salvar', methods=['POST'])
@login_required
def salvar_planejamento():
    cliente_id, redir = _get_cliente_id()
    if redir:
        return redir
    cliente = Cliente.query.get_or_404(cliente_id)
    cliente.planejamento_texto = request.form.get('planejamento_texto', '').strip()
    db.session.commit()
    flash('Planejamento salvo.', 'success')
    return redirect(url_for('admin_planejamento'))


@app.route('/planejamento/preview', methods=['POST'])
@login_required
def preview_planejamento():
    from generate import parsear_planejamento

    cliente_id, redir = _get_cliente_id()
    if redir:
        return redir
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

    return render_template('admin/planejamento.html', cliente_sel=cliente, preview=preview)


@app.route('/planejamento/gerar-ia', methods=['POST'])
@login_required
def gerar_planejamento_ia():
    from datetime import date as _date, timedelta
    from generate import gerar_planejamento_ia as _gerar

    cliente_id, redir = _get_cliente_id()
    if redir:
        return jsonify(error='Empresa não selecionada'), 400

    cliente = Cliente.query.get_or_404(cliente_id)

    data_str = request.form.get('segunda_feira', '').strip()
    try:
        if data_str:
            segunda = _date.fromisoformat(data_str)
            if segunda.weekday() != 0:
                from datetime import timedelta as _td
                segunda = segunda - _td(days=segunda.weekday())
        else:
            hoje = _date.today()
            dias_ate_segunda = (7 - hoje.weekday()) % 7 or 7
            segunda = hoje + timedelta(days=dias_ate_segunda)
    except ValueError:
        return jsonify(error='Data inválida'), 400

    try:
        texto = _gerar(cliente, segunda)
        return jsonify(ok=True, texto=texto)
    except Exception as e:
        return jsonify(error=str(e)), 500



@app.route('/cliente/<int:cliente_id>/contexto', methods=['POST'])
@login_required
def salvar_contexto(cliente_id):
    if not current_user.is_admin and current_user.cliente_id != cliente_id:
        abort(403)
    cliente = Cliente.query.get_or_404(cliente_id)
    cliente.contexto = request.form.get('contexto', '').strip()
    db.session.commit()
    flash('Contexto da marca salvo com sucesso.', 'success')
    return redirect(url_for('admin_prompts'))


@app.route('/cliente/<int:cliente_id>/cores', methods=['POST'])
@login_required
def salvar_cores(cliente_id):
    if not current_user.is_admin and current_user.cliente_id != cliente_id:
        abort(403)
    cliente = Cliente.query.get_or_404(cliente_id)
    cliente.cor_primaria = request.form.get('cor_primaria', '').strip() or None
    cliente.cor_secundaria = request.form.get('cor_secundaria', '').strip() or None
    db.session.commit()
    flash('Cores da marca salvas com sucesso.', 'success')
    return redirect(url_for('admin_prompts'))


@app.route('/cliente/<int:cliente_id>/logo-img')
def serve_logo(cliente_id):
    import base64
    from flask import Response
    cliente = Cliente.query.get_or_404(cliente_id)
    if not cliente.logo_data:
        abort(404)
    mime, b64 = cliente.logo_data.split(',', 1)
    mime_type = mime.split(':')[1].split(';')[0]
    return Response(base64.b64decode(b64), mimetype=mime_type)


@app.route('/cliente/<int:cliente_id>/logo', methods=['POST'])
@login_required
def upload_logo(cliente_id):
    import base64
    if not current_user.is_admin and current_user.cliente_id != cliente_id:
        abort(403)
    cliente = Cliente.query.get_or_404(cliente_id)
    f = request.files.get('logo')
    if not f or not f.filename:
        flash('Nenhum arquivo selecionado.', 'error')
        return redirect(url_for('admin_prompts'))

    ext = os.path.splitext(f.filename)[1].lower()
    mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml'}
    if ext not in mime_map:
        flash('Formato inválido. Use PNG, JPG ou SVG.', 'error')
        return redirect(url_for('admin_prompts'))

    data = f.read()
    b64 = base64.b64encode(data).decode('utf-8')
    cliente.logo_data = f'data:{mime_map[ext]};base64,{b64}'
    cliente.logo_url = url_for('serve_logo', cliente_id=cliente_id)
    db.session.commit()
    flash('Logo salvo com sucesso.', 'success')
    return redirect(url_for('admin_prompts'))


# ── Temas Visuais (PromptLayout) ─────────────────────────────────────────────

@app.route('/layouts')
@login_required
def admin_layouts():
    cliente_id, redir = _get_cliente_id()
    if redir:
        return redir
    cliente_sel = Cliente.query.get_or_404(cliente_id)
    layouts = PromptLayout.query.filter_by(cliente_id=cliente_id)\
        .order_by(PromptLayout.criado_em.desc()).all()
    edit_id = request.args.get('edit', type=int)
    edit_layout = PromptLayout.query.get(edit_id) if edit_id else None
    if edit_layout and edit_layout.cliente_id != cliente_id:
        edit_layout = None
    return render_template('admin/layouts.html',
                           cliente_sel=cliente_sel,
                           layouts=layouts,
                           edit_layout=edit_layout)


@app.route('/layouts/salvar', methods=['POST'])
@login_required
def salvar_layout():
    from generate import montar_prompt_imagem

    cliente_id, redir = _get_cliente_id()
    if redir:
        return redir

    layout_id = request.form.get('layout_id', type=int)
    if layout_id:
        layout = PromptLayout.query.get_or_404(layout_id)
        if layout.cliente_id != cliente_id:
            abort(403)
    else:
        layout = PromptLayout(cliente_id=cliente_id)
        db.session.add(layout)

    layout.nome = request.form.get('nome', '').strip()
    layout.descricao = request.form.get('descricao', '').strip()

    vde = request.form.get('vigente_de', '').strip()
    vate = request.form.get('vigente_ate', '').strip()
    try:
        layout.vigente_de = datetime.strptime(vde, '%Y-%m-%d').date() if vde else None
        layout.vigente_ate = datetime.strptime(vate, '%Y-%m-%d').date() if vate else None
    except ValueError:
        layout.vigente_de = None
        layout.vigente_ate = None

    layout.cenario = request.form.get('cenario', '').strip()
    layout.estilo_visual = request.form.get('estilo_visual', 'photorealistic').strip()
    layout.personagens = request.form.get('personagens', '').strip()
    layout.iluminacao = request.form.get('iluminacao', '').strip()
    layout.elementos_visuais = request.form.get('elementos_visuais', '').strip()
    layout.humor = request.form.get('humor', '').strip()
    layout.paleta = request.form.get('paleta', 'marca').strip()
    layout.restricoes = request.form.get('restricoes', '').strip()
    layout.ativo = 'ativo' in request.form

    layout.prompt_gerado = montar_prompt_imagem(layout)

    db.session.commit()
    flash(f'Tema "{layout.nome}" salvo com sucesso.', 'success')
    return redirect(url_for('admin_layouts'))


@app.route('/layouts/<int:layout_id>/toggle', methods=['POST'])
@login_required
def toggle_layout(layout_id):
    cliente_id, redir = _get_cliente_id()
    if redir:
        return jsonify(error='Empresa não selecionada'), 400
    layout = PromptLayout.query.get_or_404(layout_id)
    if layout.cliente_id != cliente_id:
        abort(403)
    layout.ativo = not layout.ativo
    db.session.commit()
    return jsonify(ok=True, ativo=layout.ativo, label='Ativo' if layout.ativo else 'Inativo')


@app.route('/layouts/<int:layout_id>/deletar', methods=['POST'])
@login_required
def deletar_layout(layout_id):
    cliente_id, redir = _get_cliente_id()
    if redir:
        return redir
    layout = PromptLayout.query.get_or_404(layout_id)
    if layout.cliente_id != cliente_id:
        abort(403)
    nome = layout.nome
    db.session.delete(layout)
    db.session.commit()
    flash(f'Tema "{nome}" excluído.', 'success')
    return redirect(url_for('admin_layouts'))


@app.route('/layouts/ia-preencher', methods=['POST'])
@login_required
def layouts_ia_preencher():
    from generate import preencher_campos_ia

    cliente_id, redir = _get_cliente_id()
    if redir:
        return jsonify(error='Empresa não selecionada'), 400
    cliente = Cliente.query.get_or_404(cliente_id)

    data = request.get_json(silent=True) or {}
    descricao = data.get('descricao', '').strip()
    if not descricao:
        return jsonify(error='Descrição não informada'), 400

    try:
        campos = preencher_campos_ia(descricao, gemini_api_key=cliente.gemini_api_key)
        return jsonify(ok=True, campos=campos)
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/layouts/preview-prompt', methods=['POST'])
@login_required
def layouts_preview_prompt():
    from generate import montar_prompt_imagem

    class _TempLayout:
        pass

    l = _TempLayout()
    data = request.get_json(silent=True) or {}
    l.cenario = data.get('cenario', '')
    l.estilo_visual = data.get('estilo_visual', 'photorealistic')
    l.personagens = data.get('personagens', '')
    l.iluminacao = data.get('iluminacao', '')
    l.elementos_visuais = data.get('elementos_visuais', '')
    l.humor = data.get('humor', '')
    l.paleta = data.get('paleta', 'marca')
    l.restricoes = data.get('restricoes', '')

    return jsonify(ok=True, prompt=montar_prompt_imagem(l))


# ── Copia Tema ────────────────────────────────────────────────────────────────

@app.route('/copia-tema')
@login_required
def copia_tema():
    cliente_id, redir = _get_cliente_id()
    if redir:
        return redir
    cliente_sel = Cliente.query.get_or_404(cliente_id)
    return render_template('admin/copia_tema.html', cliente_sel=cliente_sel)


@app.route('/copia-tema/analisar', methods=['POST'])
@login_required
def copia_tema_analisar():
    from generate import analisar_imagem_para_prompt

    cliente_id, redir = _get_cliente_id()
    if redir:
        return jsonify(error='Empresa não selecionada'), 400
    cliente = Cliente.query.get_or_404(cliente_id)

    file = request.files.get('imagem')
    if not file or not file.filename:
        return jsonify(error='Nenhuma imagem enviada'), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        return jsonify(error='Formato inválido. Use JPG, PNG ou WebP'), 400

    upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'tmp')
    os.makedirs(upload_dir, exist_ok=True)
    tmp_path = os.path.join(upload_dir, f'copia_{uuid.uuid4().hex}{ext}')
    file.save(tmp_path)

    try:
        prompt = analisar_imagem_para_prompt(tmp_path, gemini_api_key=cliente.gemini_api_key)
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return jsonify(ok=True, prompt=prompt)


@app.route('/copia-tema/salvar', methods=['POST'])
@login_required
def copia_tema_salvar():
    cliente_id, redir = _get_cliente_id()
    if redir:
        return redir
    cliente = Cliente.query.get_or_404(cliente_id)

    nome = request.form.get('nome', '').strip()
    prompt = request.form.get('prompt_gerado', '').strip()
    if not nome or not prompt:
        flash('Nome e prompt são obrigatórios.', 'danger')
        return redirect(url_for('copia_tema'))

    # Append brand palette instruction so generated images use brand colors
    paleta_instrucao = 'Use brand accent colors naturally integrated into the scene'
    if paleta_instrucao not in prompt:
        prompt_final = prompt.rstrip('. ') + f'. {paleta_instrucao}.'
    else:
        prompt_final = prompt

    layout = PromptLayout(cliente_id=cliente_id)
    layout.nome = nome
    layout.descricao = request.form.get('descricao', '').strip()
    layout.prompt_gerado = prompt_final
    # Mark parametric fields as empty — prompt_gerado is used directly
    layout.cenario = ''
    layout.estilo_visual = 'photorealistic'
    layout.personagens = ''
    layout.iluminacao = ''
    layout.elementos_visuais = ''
    layout.humor = ''
    layout.paleta = 'marca'
    layout.restricoes = ''
    layout.ativo = True

    vde = request.form.get('vigente_de', '').strip()
    vate = request.form.get('vigente_ate', '').strip()
    try:
        layout.vigente_de = datetime.strptime(vde, '%Y-%m-%d').date() if vde else None
        layout.vigente_ate = datetime.strptime(vate, '%Y-%m-%d').date() if vate else None
    except ValueError:
        layout.vigente_de = None
        layout.vigente_ate = None

    db.session.add(layout)
    db.session.commit()
    flash(f'Tema "{nome}" salvo com sucesso.', 'success')
    return redirect(url_for('admin_layouts'))


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
        gemini_api_key = request.form.get('gemini_api_key', '').strip()

        if not nome or not instagram or not email or not senha:
            flash('Preencha todos os campos obrigatórios.', 'error')
            return render_template('admin/novo_cliente.html')

        if Usuario.query.filter_by(email=email).first():
            flash('Este email já está cadastrado.', 'error')
            return render_template('admin/novo_cliente.html')

        cliente = Cliente(nome=nome, instagram_handle=instagram,
                         make_webhook_url=webhook, gemini_api_key=gemini_api_key or None)
        db.session.add(cliente)
        db.session.flush()

        usuario = Usuario(cliente_id=cliente.id, nome=nome, email=email, role='cliente')
        usuario.set_senha(senha)
        db.session.add(usuario)
        db.session.commit()

        flash(f'Cliente {nome} criado com sucesso.', 'success')
        return redirect(url_for('admin_clientes'))

    return render_template('admin/novo_cliente.html')


@app.route('/admin/clientes/<int:cliente_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_cliente(cliente_id):
    if not current_user.is_admin:
        abort(403)

    cliente = Cliente.query.get_or_404(cliente_id)
    usuario = Usuario.query.filter_by(cliente_id=cliente_id, role='cliente').first()

    if request.method == 'POST':
        cliente.nome = request.form.get('nome', '').strip()
        cliente.instagram_handle = request.form.get('instagram_handle', '').strip().lstrip('@')
        cliente.make_webhook_url = request.form.get('make_webhook_url', '').strip()
        gemini_key = request.form.get('gemini_api_key', '').strip()
        cliente.gemini_api_key = gemini_key or None
        cliente.ativo = 'ativo' in request.form

        novo_email = request.form.get('email', '').strip().lower()
        nova_senha = request.form.get('senha', '').strip()

        if usuario:
            if novo_email and novo_email != usuario.email:
                conflito = Usuario.query.filter_by(email=novo_email).first()
                if conflito and conflito.id != usuario.id:
                    flash('Este email já está em uso por outro usuário.', 'error')
                    return render_template('admin/editar_cliente.html', cliente=cliente, usuario=usuario)
                usuario.email = novo_email
            if nova_senha:
                usuario.set_senha(nova_senha)
        elif novo_email and nova_senha:
            conflito = Usuario.query.filter_by(email=novo_email).first()
            if conflito:
                flash('Este email já está em uso por outro usuário.', 'error')
                return render_template('admin/editar_cliente.html', cliente=cliente, usuario=None)
            usuario = Usuario(cliente_id=cliente.id, nome=cliente.nome, email=novo_email, role='cliente')
            usuario.set_senha(nova_senha)
            db.session.add(usuario)
        elif not usuario:
            flash('Preencha email e senha para criar o acesso do cliente.', 'error')
            return render_template('admin/editar_cliente.html', cliente=cliente, usuario=None)

        db.session.commit()
        flash(f'Cliente {cliente.nome} atualizado com sucesso.', 'success')
        return redirect(url_for('admin_clientes'))

    return render_template('admin/editar_cliente.html', cliente=cliente, usuario=usuario)


# ── Configurações (admin + cliente) ──────────────────────────────────────────

PROVEDORES_IMAGEM = [
    ('pollinations', 'Pollinations.ai (Flux)', 'Gratuito, sem chave API', None),
    ('fal_flux',     'Flux Realism (fal.ai)',  'Melhor qualidade — requer FAL_KEY', 'FAL_KEY'),
    ('imagen3',      'Imagen 3 (Google)',       'Alta qualidade — requer GEMINI_API_KEY + billing', 'GEMINI_API_KEY'),
]


@app.route('/configuracoes', methods=['GET', 'POST'])
@login_required
def admin_configuracoes():
    cliente_id, redir = _get_cliente_id()
    if redir:
        return redir

    cliente_sel = Cliente.query.get_or_404(cliente_id)

    if request.method == 'POST':
        # Chave Gemini do cliente
        gemini_key = request.form.get('gemini_api_key', '').strip()
        cliente_sel.gemini_api_key = gemini_key or None
        db.session.commit()

        # Provedor de imagem — só admin altera
        if current_user.is_admin:
            provedor = request.form.get('provedor_imagem', 'pollinations')
            if provedor in [p[0] for p in PROVEDORES_IMAGEM]:
                Configuracao.set('provedor_imagem', provedor)
                db.session.commit()

        flash('Configurações salvas com sucesso.', 'success')
        return redirect(url_for('admin_configuracoes'))

    provedor_atual = Configuracao.get('provedor_imagem', 'pollinations')
    chaves_presentes = {k: bool(os.environ.get(k)) for k in ['GEMINI_API_KEY', 'FAL_KEY']}

    return render_template('admin/configuracoes.html',
                           provedores=PROVEDORES_IMAGEM,
                           provedor_atual=provedor_atual,
                           chaves=chaves_presentes,
                           cliente_sel=cliente_sel)


# ── Geração de conteúdo ──────────────────────────────────────────────────────

@app.route('/admin/gerar', methods=['POST'])
@login_required
def admin_gerar():
    if current_user.is_admin:
        cliente_id, redir = _require_admin_cliente()
        if redir:
            return redir
    else:
        cliente_id = current_user.cliente_id

    from datetime import date as _date
    from generate import gerar_posts_hoje
    data_str = request.form.get('data_publicacao', '').strip()
    try:
        alvo = _date.fromisoformat(data_str) if data_str else _date.today()
    except ValueError:
        flash('Data inválida.', 'error')
        return redirect(url_for('dashboard'))
    prompt_layout_id = request.form.get('prompt_layout_id', type=int) or None
    try:
        posts = gerar_posts_hoje(data=alvo, cliente_id=cliente_id, prompt_layout_id=prompt_layout_id)
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
    if current_user.is_admin:
        post = Post.query.get_or_404(post_id)
    else:
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


@app.route('/admin/gerar-carrossel', methods=['POST'])
@login_required
def admin_gerar_carrossel():
    import json as _json
    from datetime import date as _date
    from generate import gerar_texto_carrossel, get_layout_ativo, DIAS_MAP

    if current_user.is_admin:
        cliente_id, redir = _require_admin_cliente()
        if redir:
            return jsonify(error='Empresa não selecionada'), 400
    else:
        cliente_id = current_user.cliente_id

    cliente = Cliente.query.get_or_404(cliente_id)

    data_str = request.form.get('data_publicacao', '').strip()
    num_frames = request.form.get('num_frames', type=int) or 2
    num_frames = max(2, min(3, num_frames))
    prompt_layout_id = request.form.get('prompt_layout_id', type=int) or None

    try:
        alvo = _date.fromisoformat(data_str) if data_str else _date.today()
    except ValueError:
        return jsonify(error='Data inválida'), 400

    dia_num = alvo.weekday()
    if dia_num >= 5:
        return jsonify(error='Fim de semana — escolha um dia útil.'), 400

    dia_semana = DIAS_MAP[dia_num]

    prompt_estilo = PromptEstilo.query.filter_by(
        cliente_id=cliente_id, dia_semana=dia_semana, ativo=True
    ).first()
    if not prompt_estilo:
        return jsonify(error=f'Sem prompt configurado para {dia_semana}. Configure em Prompts.'), 400

    if prompt_layout_id:
        layout = PromptLayout.query.get(prompt_layout_id)
    else:
        layout = get_layout_ativo(cliente_id, alvo)

    template_visual = (
        layout.prompt_gerado if layout and layout.prompt_gerado
        else (prompt_estilo.prompt_imagem or '')
    )

    try:
        titulo_carrossel, legenda, frames = gerar_texto_carrossel(
            intencao=prompt_estilo.intencao,
            template_visual=template_visual,
            num_frames=num_frames,
            contexto=cliente.contexto or '',
            gemini_api_key=cliente.gemini_api_key,
        )
    except Exception as e:
        return jsonify(error=f'Erro ao gerar roteiro: {e}'), 500

    frames_data = [
        {
            'titulo': f.get('titulo', f'Frame {i + 1}'),
            'texto_frame': f.get('texto_frame', ''),
            'prompt_imagem': f.get('prompt_imagem', template_visual),
            'imagem_url': None,
        }
        for i, f in enumerate(frames[:num_frames])
    ]

    post = Post(
        cliente_id=cliente_id,
        tipo='carrossel',
        dia_semana=dia_semana,
        data_publicacao=alvo,
        titulo=titulo_carrossel,
        legenda=legenda,
        imagem_url=None,
        prompt_usado=None,
        status='gerando',
        frames_json=_json.dumps(frames_data, ensure_ascii=False),
    )
    db.session.add(post)
    db.session.commit()

    return jsonify(ok=True, post_id=post.id, frames=[
        {'titulo': f['titulo'], 'texto_frame': f['texto_frame']}
        for f in frames_data
    ])


@app.route('/api/gerar-frame/<int:post_id>/<int:frame_index>', methods=['POST'])
@login_required
def api_gerar_frame(post_id, frame_index):
    if current_user.is_admin:
        post = Post.query.get_or_404(post_id)
    else:
        post = Post.query.filter_by(id=post_id, cliente_id=current_user.cliente_id).first_or_404()

    if post.tipo != 'carrossel':
        return jsonify(error='Post não é um carrossel'), 400

    from generate import gerar_frame_carrossel
    try:
        imagem_url = gerar_frame_carrossel(post, frame_index)
        return jsonify(ok=True, imagem_url=imagem_url, status=post.status)
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/cron/gerar', methods=['POST'])
def cron_gerar():
    """HTTP endpoint for scheduled post generation."""
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
    return os.environ.get('REQUEST_BASE_URL', request.host_url.rstrip('/'))



@app.route('/api/posts/publicar')
def api_posts_publicar():
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

    cliente_handle = request.args.get('cliente')
    if cliente_handle:
        cliente_obj = Cliente.query.filter_by(instagram_handle=cliente_handle).first()
        if not cliente_obj:
            return jsonify(error=f'Cliente "{cliente_handle}" não encontrado.'), 404
        posts = Post.query.filter_by(status='aprovado', data_publicacao=alvo, cliente_id=cliente_obj.id).all()
    else:
        posts = Post.query.filter_by(status='aprovado', data_publicacao=alvo).all()

    base = _base_url()
    result = []
    for p in posts:
        token = os.environ.get('CRON_SECRET', 'token123')
        marcar_url = f"{base}/api/posts/{p.id}/publicado?token={token}"

        if p.tipo == 'carrossel':
            frames = p.frames
            imagens = [f"{base}{f['imagem_url']}" for f in frames if f.get('imagem_url')]
            if not imagens:
                continue
            result.append({
                'id': p.id,
                'tipo': 'carrossel',
                'titulo': p.titulo,
                'legenda': p.legenda,
                'imagem_url': imagens[0],
                'imagens': imagens,
                'instagram_handle': p.cliente.instagram_handle,
                'data_publicacao': p.data_publicacao.strftime('%d/%m/%Y'),
                'marcar_publicado_url': marcar_url,
            })
        else:
            if not p.imagem_url:
                continue
            result.append({
                'id': p.id,
                'tipo': 'post',
                'titulo': p.titulo,
                'legenda': p.legenda,
                'imagem_url': f"{base}{p.imagem_url}",
                'instagram_handle': p.cliente.instagram_handle,
                'data_publicacao': p.data_publicacao.strftime('%d/%m/%Y'),
                'marcar_publicado_url': marcar_url,
            })

    return jsonify(result)


@app.route('/api/posts/<int:post_id>/publicado', methods=['POST', 'GET'])
def api_marcar_publicado(post_id):
    _check_token()
    post = Post.query.get_or_404(post_id)
    if post.status == 'aprovado':
        post.status = 'publicado'
        post.publicado_em = datetime.utcnow()
        db.session.commit()
    return jsonify(ok=True, post_id=post_id, status=post.status)


# ── Init BD ───────────────────────────────────────────────────────────────────

@app.cli.command('init-db')
def init_db():
    db.create_all()
    print('Tabelas criadas.')


@app.cli.command('migrar-layouts')
def migrar_layouts():
    """Cria a tabela prompt_layouts (nova funcionalidade de temas visuais)."""
    db.create_all()
    print('Tabela prompt_layouts criada (ou já existia).')


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
            pe = post.cliente.prompts
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
