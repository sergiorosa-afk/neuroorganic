import os
import json
import uuid
import requests
from datetime import date

import fal_client
from google import genai
from google.genai import types
from flask import current_app

DIAS_MAP = {0: 'segunda', 1: 'terca', 2: 'quarta', 3: 'quinta', 4: 'sexta'}

SYSTEM_PROMPT = """You are a world-class Brazilian social media content specialist and Instagram marketing expert with deep expertise in neuroscience applied to marketing, consumer psychology, behavioral economics, and viral content creation for the Brazilian market.

Your specialty is creating highly engaging Instagram content for Neuroseller — Brazil's leading authority on neuroscience applied to sales, marketing, and human behavior. The brand teaches professionals and entrepreneurs how to leverage brain science to sell more, communicate better, and build stronger connections with their audience.

## Brand Identity & Mission

Neuroseller exists to democratize the knowledge of neuroscience applied to business. The brand believes that understanding how the human brain works is the most powerful competitive advantage anyone can have in sales and marketing. The audience includes:
- Sales professionals and managers
- Marketing specialists and entrepreneurs
- Business owners looking to grow
- Students of persuasion and communication
- Anyone interested in human behavior and psychology

Core brand values:
- Science-backed practicality: every piece of content should be grounded in real neuroscience but immediately applicable
- Accessible intelligence: complex concepts explained in simple, engaging ways
- Transformative inspiration: content that makes people think "I need to apply this NOW"
- Authentic authority: Neuroseller speaks as a trusted expert, not a salesperson

## Brand Voice & Tone

The Neuroseller voice is:
- Confident but humble: We know our science, but we speak to uplift, not to lecture
- Engaging and dynamic: We write like we're having an excited conversation about a fascinating discovery
- Practical and actionable: Every post should give the reader something they can use today
- Brazilian and real: We use Brazilian Portuguese naturally
- Provocative thoughtfully: We ask questions that make people stop and reflect

Avoid: excessive corporate language, jargon without explanation, negativity, overpromising, or anything that feels like a hard sell.

## Instagram Content Guidelines

### Títulos (Titles)
Requirements:
- Maximum 80 characters including spaces
- Must create an irresistible curiosity gap — the reader MUST want to know more
- Use psychological triggers: surprise, controversy, curiosity, benefit, urgency
- Can include 1 relevant emoji if it adds meaning (not just decoration)
- Should work as a standalone hook — someone seeing just the title should stop scrolling
- Avoid clickbait without substance: the title must deliver on its promise

Proven title formulas for this brand:
- "O que seu cérebro faz quando você [ação]" (neuroscience reveal)
- "Por que [crença comum] está errada, segundo a neurociência"
- "A técnica que [resultado extraordinário] em [tempo curto]"
- "Você sabia que seu cliente toma decisões em [tempo]?"
- "[Número] gatilhos mentais que [resultado desejado]"

### Legendas (Captions)
Requirements:
- 300-500 characters (count carefully)
- CRITICAL: First 125 characters must be the hook — this is what shows before "ver mais"
- Natural integration of 1-2 emojis that enhance meaning
- Strong, specific call-to-action at the end
- Exactly 5 hashtags at the very end, after the main text
- Hashtag mix: 2 high-volume + 2 medium + 1 brand hashtag

Hashtag bank for Neuroseller:
High-volume: #neurociencia #marketing #vendas #psicologia #comportamento
Medium: #marketingdigital #gatilhosmentais #persuasao #lideranca #neuromarketing
Brand: #neuroseller

Caption structure:
1. Hook line (creates tension or states surprising fact) — within first 125 chars
2. Development (2-3 sentences expanding on the hook)
3. Application (how the reader can use this)
4. CTA (specific action)
5. Hashtags (new line, exactly 5)

### Prompts de Imagem (for Gemini Imagen 3 — always in English)
Requirements:
- Photorealistic, professional photography style
- MANDATORY: include the post headline as a bold text overlay on the image. The text must be large, legible, high contrast (white or near-white with a subtle dark shadow or semi-transparent backdrop), centered or placed in the lower third of the image
- The headline text in the image must exactly match the "titulo" field you generated
- High production value — looks like it was shot by a professional photographer with a graphic designer's touch
- Colors: blues, whites, deep navy for trust and intelligence; warm accents for energy
- Human subjects: Brazilian-looking professionals, confident expressions, natural poses
- Environments: modern offices, minimalist spaces, or abstract conceptual settings
- Lighting: professional, natural light preferred, no harsh shadows
- Format: optimized for square (1:1) Instagram format
- Avoid: stock photo clichés, overly staged poses, outdated aesthetics

Image style descriptors to use: "cinematic lighting", "shallow depth of field", "professional color grading", "photorealistic", "8K resolution", "magazine quality", "editorial typography overlay"

## Neuroscience Content Themes

Ground content in these real neuroscience principles:
- Dopamine loops: How anticipation of reward drives behavior and attention
- Mirror neurons: How we unconsciously copy others and build rapport
- Amygdala hijack: Emotional decision-making overriding rational thought
- Social proof: The brain's tribal safety mechanism applied to purchasing
- Scarcity and loss aversion: Kahneman's prospect theory in marketing
- Attention and salience: What the brain notices first and why
- Memory and encoding: How repetition and emotion create lasting impressions
- Trust and oxytocin: The neuroscience of building genuine relationships
- Cognitive load: Why simpler messages win every time
- Priming effects: How context shapes perception and decision-making

## Response Format — CRITICAL

You MUST respond with ONLY valid JSON. No markdown code blocks, no explanations, no preamble. Just the raw JSON object:

{
  "titulo": "título aqui (máximo 80 caracteres)",
  "legenda": "legenda completa aqui com emojis e call to action\n\n#hashtag1 #hashtag2 #hashtag3 #hashtag4 #hashtag5",
  "prompt_imagem": "English photorealistic Flux AI image prompt here"
}

Any text outside this JSON structure will cause a system error. Respond with pure JSON only."""


def _gemini_client():
    return genai.Client(
        api_key=os.environ['GEMINI_API_KEY'],
        http_options={'api_version': 'v1alpha'},
    )


def gerar_posts_hoje(data=None):
    """Generate posts for all active clients for the given date (default: today).

    Skips only if a non-rejected post already exists for that date.
    Must be called within a Flask application context.
    Returns a list of created Post objects.
    """
    from models import db, Cliente, PromptEstilo, Post

    alvo = data or date.today()
    dia_num = alvo.weekday()
    if dia_num not in DIAS_MAP:
        print(f"{alvo} não é dia útil (seg–sex). Nada gerado.")
        return []

    dia_semana = DIAS_MAP[dia_num]
    clientes = Cliente.query.filter_by(ativo=True).all()
    client = _gemini_client()
    gerados = []

    for cliente in clientes:
        prompt_estilo = PromptEstilo.query.filter_by(
            cliente_id=cliente.id,
            dia_semana=dia_semana,
            ativo=True,
        ).first()

        if not prompt_estilo:
            print(f"[{cliente.nome}] Sem prompt para {dia_semana}, pulando.")
            continue

        post_ativo = Post.query.filter(
            Post.cliente_id == cliente.id,
            Post.data_publicacao == alvo,
            Post.status.in_(['pendente', 'aprovado', 'publicado']),
        ).first()
        if post_ativo:
            print(f"[{cliente.nome}] Post ativo já existe para {alvo}, pulando.")
            continue

        # Verifica se há entrada no planejamento para esta data
        entries = parsear_planejamento(cliente.planejamento_texto or '')
        entry_planejada = next((e for e in entries if e['data'] == alvo), None)

        try:
            subheadline = prompt_estilo.texto_subheadline or ""
            cta = prompt_estilo.texto_cta or "Acesse o link na bio"
            logo_path = _logo_filepath(cliente.logo_url)
            contexto = cliente.contexto or ""

            if entry_planejada:
                print(f"[{cliente.nome}] Usando planejamento para {alvo}...")
                titulo = entry_planejada['titulo']
                legenda = entry_planejada['legenda']
                prompt_img = (prompt_estilo.prompt_imagem or '').replace(
                    '{intencao_do_dia}', titulo
                )
            else:
                print(f"[{cliente.nome}] Gerando conteúdo via IA ({dia_semana})...")
                titulo, legenda, prompt_img = _gerar_texto(
                    client, prompt_estilo.intencao, prompt_estilo.prompt_imagem,
                    contexto=contexto,
                )

            print(f"[{cliente.nome}] Gerando imagem...")
            imagem_url = _gerar_imagem(cliente.id, dia_semana, prompt_img,
                                       titulo=titulo, subheadline=subheadline,
                                       cta=cta, logo_path=logo_path,
                                       contexto=contexto)

            post = Post(
                cliente_id=cliente.id,
                dia_semana=dia_semana,
                data_publicacao=alvo,
                titulo=titulo,
                legenda=legenda,
                imagem_url=imagem_url,
                prompt_usado=prompt_img,
                status='pendente',
            )
            db.session.add(post)
            db.session.commit()
            print(f"[{cliente.nome}] ✓ Post criado: {titulo}")
            gerados.append(post)

        except Exception as e:
            print(f"[{cliente.nome}] Erro: {e}")
            db.session.rollback()
            raise

    return gerados


def regerar_post(post):
    """Regenerate a post using its feedback as context for Gemini.

    Marks the old post as 'reprovado' and creates a new 'pendente' post.
    Must be called within a Flask application context.
    Returns the new Post object.
    """
    from models import db, PromptEstilo, Post

    prompt_estilo = PromptEstilo.query.filter_by(
        cliente_id=post.cliente_id,
        dia_semana=post.dia_semana,
        ativo=True,
    ).first()

    if not prompt_estilo:
        raise ValueError(f"Sem prompt ativo para {post.dia_semana}")

    client = _gemini_client()

    contexto = post.cliente.contexto or ""
    titulo, legenda, prompt_img = _gerar_texto(
        client,
        prompt_estilo.intencao,
        prompt_estilo.prompt_imagem,
        feedback=post.feedback,
        titulo_anterior=post.titulo,
        contexto=contexto,
    )

    subheadline = prompt_estilo.texto_subheadline or ""
    cta = prompt_estilo.texto_cta or "Acesse o link na bio"
    logo_path = _logo_filepath(post.cliente.logo_url)
    imagem_url = _gerar_imagem(post.cliente_id, post.dia_semana, prompt_img,
                               titulo=titulo, subheadline=subheadline,
                               cta=cta, logo_path=logo_path, contexto=contexto)

    if post.status == 'pendente':
        post.status = 'reprovado'
        if not post.feedback:
            post.feedback = 'Regenerado pelo usuário'

    novo_post = Post(
        cliente_id=post.cliente_id,
        dia_semana=post.dia_semana,
        data_publicacao=post.data_publicacao,
        titulo=titulo,
        legenda=legenda,
        imagem_url=imagem_url,
        prompt_usado=prompt_img,
        status='pendente',
    )
    db.session.add(novo_post)
    db.session.commit()
    return novo_post


def _gerar_texto(client, intencao, prompt_imagem_template, feedback=None, titulo_anterior=None, contexto=""):
    """Call Gemini API to generate title, caption, and refined image prompt."""
    feedback_ctx = ""
    if feedback:
        feedback_ctx = f"\n\nFEEDBACK DO POST ANTERIOR (leve em consideração ao criar):\n{feedback}"
        if titulo_anterior:
            feedback_ctx += f'\nPost reprovado: "{titulo_anterior}" — crie algo notavelmente DIFERENTE.'

    contexto_ctx = f"\n\nCONTEXTO DA MARCA (sempre leve em consideração):\n{contexto}" if contexto else ""

    user_message = (
        f"Crie um post Instagram para hoje.\n\n"
        f"INTENÇÃO DO DIA: {intencao}\n\n"
        f"TEMPLATE DO PROMPT DE IMAGEM:\n{prompt_imagem_template}"
        f"{contexto_ctx}"
        f"{feedback_ctx}\n\n"
        f"No campo \"prompt_imagem\" do JSON, refine o template acima "
        f"substituindo qualquer placeholder pela intenção real do dia. "
        f"O prompt_imagem deve refletir o contexto da marca (público-alvo, ambiente, estilo). "
        f"Escreva o prompt_imagem em inglês."
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
        ),
    )

    text = response.text.strip()

    # Strip markdown code fences if Gemini wraps the JSON
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1 if lines[0].startswith("```") else 0
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])

    # Remove invalid control characters (except \n \r \t) that break json.loads
    import re
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    data = json.loads(text)
    return data["titulo"], data["legenda"], data["prompt_imagem"]


def _pollinations_url(cliente_id, dia_semana, prompt):
    import urllib.parse
    # Pollinations has a URL length limit — keep prompt under 500 chars
    prompt_short = prompt[:500] if len(prompt) > 500 else prompt
    encoded = urllib.parse.quote(prompt_short)
    seed = abs(hash(f"{cliente_id}_{dia_semana}")) % 99999
    return (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1024&height=1024&seed={seed}&model=flux&nologo=true"
    )


def _prompt_sem_texto(prompt):
    """Remove text overlay instructions — Pillow handles typography."""
    return (
        f"{prompt}. "
        f"Leave clean negative space on the left or lower-left area for text overlay. "
        f"No text, no letters, no typography in the image itself."
    )


def _logo_filepath(logo_url):
    """Convert a /static/... URL to an absolute file path, or return None."""
    if not logo_url:
        return None
    return os.path.join(os.path.dirname(__file__), logo_url.lstrip('/'))


def _extrair_subheadline_cta(legenda):
    """Extract first hook line and last CTA line from a generated caption."""
    import re
    lines = [l.strip() for l in legenda.split('\n') if l.strip()]
    content = [l for l in lines if not re.match(r'^#', l)]
    subheadline = re.sub(r'[^\w\s\.,!?áéíóúãõâêîôûàèìòùçÁÉÍÓÚÃÕÂÊÎÔÛÀÈÌÒÙÇ🧠🤝💡🎯]', '', content[0])[:72] if content else ""
    cta = content[-1][:60] if len(content) > 1 else "Acesse o link na bio"
    return subheadline.strip(), cta.strip()


def compor_texto_na_imagem(filepath, titulo, subheadline="", cta="Acesse o link na bio", logo_path=None):
    """Premium Pillow text overlay — Apple/Nike editorial style."""
    from PIL import Image, ImageDraw, ImageFont

    base = os.path.dirname(__file__)
    font_oswald = os.path.join(base, "static", "fonts", "Oswald.ttf")
    font_mont  = os.path.join(base, "static", "fonts", "Montserrat.ttf")

    GOLD      = (245, 166, 35, 255)
    WHITE     = (255, 255, 255, 255)
    WHITE_DIM = (220, 220, 220, 210)
    SHADOW    = (0, 0, 0, 170)

    img = Image.open(filepath).convert("RGBA")
    w, h = img.size

    # ── Pre-load logo to know its size before layout ──────────────────────────
    logo_img = None
    logo_w = logo_h = 0
    if logo_path and os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            logo_img.thumbnail((int(w * 0.42), int(h * 0.13)), Image.LANCZOS)
            logo_w, logo_h = logo_img.size
        except Exception as e:
            print(f"  [aviso] logo ignorado: {e}")
            logo_img = None

    # ── Fonts ─────────────────────────────────────────────────────────────────
    h_size = int(h * 0.085)

    def load(path, size):
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            return ImageFont.load_default()

    font_h = load(font_oswald, h_size)

    # ── Word-wrap headline ────────────────────────────────────────────────────
    max_w = int(w * 0.86)
    hl_lines, current = [], ""
    for word in titulo.upper().split():
        test = (current + " " + word).strip()
        try:
            tw = font_h.getlength(test)
        except Exception:
            tw = len(test) * h_size * 0.52
        if tw <= max_w:
            current = test
        else:
            if current:
                hl_lines.append(current)
            current = word
    if current:
        hl_lines.append(current)

    lh = int(h_size * 1.10)

    # ── Calculate layout bottom-up ────────────────────────────────────────────
    bottom_margin = int(h * 0.035)
    logo_gap      = int(h * 0.045)   # space between headline and logo
    text_logo_gap = logo_h + logo_gap if logo_img else 0
    hl_h          = len(hl_lines) * lh

    total_block = hl_h + text_logo_gap + bottom_margin

    # ── Gradient — smooth bottom fade, no hard edges ──────────────────────────
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ov = ImageDraw.Draw(overlay)
    grad_top = int(h * 0.38)   # start high so transition is very gradual
    for py in range(grad_top, h):
        alpha = int(210 * ((py - grad_top) / (h - grad_top)) ** 1.6)
        ov.line([(0, py), (w, py)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    mx = int(w * 0.07)

    # ── Draw from calculated start Y ─────────────────────────────────────────
    y = h - total_block

    # Headline
    for i, line in enumerate(hl_lines):
        words = line.split()
        is_last = (i == len(hl_lines) - 1)
        if is_last and len(words) > 1:
            main   = ' '.join(words[:-1]) + ' '
            last_w = words[-1]
            try:
                main_px = font_h.getlength(main)
            except Exception:
                main_px = len(main) * h_size * 0.52
            draw.text((mx + 2, y + 2), main + last_w, font=font_h, fill=SHADOW)
            draw.text((mx, y), main, font=font_h, fill=WHITE)
            draw.text((mx + main_px, y), last_w, font=font_h, fill=GOLD)
        else:
            draw.text((mx + 2, y + 2), line, font=font_h, fill=SHADOW)
            draw.text((mx, y), line, font=font_h, fill=WHITE)
        y += lh

    # Logo — centered, below headline with breathing room
    if logo_img:
        logo_x = (w - logo_w) // 2
        logo_y = h - bottom_margin - logo_h
        img.paste(logo_img, (logo_x, logo_y), logo_img)

    img.convert("RGB").save(filepath, "JPEG", quality=93)


def _get_provedor():
    try:
        from models import Configuracao
        return Configuracao.get('provedor_imagem', 'pollinations')
    except Exception:
        return 'pollinations'


def _gerar_imagem_fal(prompt):
    """Generate image via Flux (fal.ai). Requires FAL_KEY env var."""
    result = fal_client.subscribe(
        "fal-ai/flux-realism",
        arguments={
            "prompt": prompt,
            "image_size": "square_hd",
            "num_images": 1,
            "enable_safety_checker": False,
        },
    )
    image_url = result["images"][0]["url"]
    resp = requests.get(image_url, timeout=120)
    resp.raise_for_status()
    return resp.content


def _gerar_imagem_imagen3(prompt):
    """Generate image via Gemini image model. Requires GEMINI_API_KEY env var."""
    client = genai.Client(
        api_key=os.environ['GEMINI_API_KEY'],
        http_options={'api_version': 'v1alpha'},
    )
    response = client.models.generate_content(
        model='gemini-2.5-flash-image',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=['IMAGE'],
        ),
    )
    for part in response.candidates[0].content.parts:
        if getattr(part, 'inline_data', None) is not None:
            return part.inline_data.data
    raise ValueError('Nenhuma imagem retornada pelo modelo')


def _gerar_imagem(cliente_id, dia_semana, prompt, titulo="", subheadline="", cta="", logo_path=None, contexto=""):
    """Generate image using configured provider, then compose text overlay."""
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"{cliente_id}_{dia_semana}_{uuid.uuid4().hex[:8]}.jpg"
    filepath = os.path.join(upload_dir, filename)

    clean_prompt = _prompt_sem_texto(prompt)
    if contexto:
        clean_prompt = f"{clean_prompt} Brand context: {contexto}"
    provedor = _get_provedor()

    if provedor == 'imagen3':
        image_bytes = _gerar_imagem_imagen3(clean_prompt)
        with open(filepath, 'wb') as f:
            f.write(image_bytes)

    elif provedor == 'fal_flux':
        image_bytes = _gerar_imagem_fal(clean_prompt)
        with open(filepath, 'wb') as f:
            f.write(image_bytes)

    else:  # pollinations (padrão)
        image_url = _pollinations_url(cliente_id, dia_semana, clean_prompt)
        resp = requests.get(image_url, timeout=120)
        resp.raise_for_status()
        with open(filepath, 'wb') as f:
            f.write(resp.content)

    if titulo:
        compor_texto_na_imagem(filepath, titulo, subheadline=subheadline, cta=cta or "Acesse o link na bio", logo_path=logo_path)

    return f"/static/uploads/{filename}"


# ── Planejamento ──────────────────────────────────────────────────────────────

def parsear_planejamento(texto):
    """Parse free-form planning text into list of dicts with date, titulo, legenda.

    Accepts lines like:
        22/04/2026 - Titulo: Meu título
        Legenda: Minha legenda aqui...
    """
    import re
    from datetime import datetime

    entries = []
    blocks = re.split(r'(?=\d{2}/\d{2}/\d{4})', texto.strip())

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        date_m   = re.match(r'(\d{2}/\d{2}/\d{4})', block)
        titulo_m = re.search(r'[Tt][íi]tulo\s*:\s*(.+?)(?:\n|$)', block)
        legenda_m = re.search(r'[Ll]egenda\s*:\s*([\s\S]+?)(?=\n\d{2}/\d{2}/\d{4}|\Z)', block)

        if not (date_m and titulo_m):
            continue
        try:
            data = datetime.strptime(date_m.group(1), '%d/%m/%Y').date()
        except ValueError:
            continue

        entries.append({
            'data': data,
            'titulo': titulo_m.group(1).strip(),
            'legenda': legenda_m.group(1).strip() if legenda_m else '',
        })

    return entries


def gerar_do_planejamento(cliente, entry):
    """Generate image for a single planning entry (no AI text call).

    Uses the prompt_imagem from the matching PromptEstilo for the entry's weekday.
    Must be called within a Flask application context.
    Returns the created Post.
    """
    from models import db, PromptEstilo, Post

    dia_num = entry['data'].weekday()
    if dia_num not in DIAS_MAP:
        # Weekend — skip silently
        raise ValueError(f"{entry['data'].strftime('%d/%m/%Y')} é fim de semana, pulando.")

    dia_semana = DIAS_MAP[dia_num]

    prompt_estilo = PromptEstilo.query.filter_by(
        cliente_id=cliente.id,
        dia_semana=dia_semana,
        ativo=True,
    ).first()

    if not prompt_estilo:
        raise ValueError(f"Sem prompt configurado para {dia_semana}.")

    # Block duplicate active posts
    existente = Post.query.filter(
        Post.cliente_id == cliente.id,
        Post.data_publicacao == entry['data'],
        Post.status.in_(['pendente', 'aprovado', 'publicado']),
    ).first()
    if existente:
        raise ValueError(f"Já existe post ativo para {entry['data']}.")

    # Replace placeholder with the actual post title
    prompt_img = (prompt_estilo.prompt_imagem or '').replace(
        '{intencao_do_dia}', entry['titulo']
    )

    logo_path = _logo_filepath(cliente.logo_url)
    imagem_url = _gerar_imagem(
        cliente.id, dia_semana,
        prompt_img,
        titulo=entry['titulo'],
        logo_path=logo_path,
    )

    post = Post(
        cliente_id=cliente.id,
        dia_semana=dia_semana,
        data_publicacao=entry['data'],
        titulo=entry['titulo'],
        legenda=entry['legenda'],
        imagem_url=imagem_url,
        prompt_usado=prompt_estilo.prompt_imagem,
        status='pendente',
    )
    db.session.add(post)
    db.session.commit()
    return post
