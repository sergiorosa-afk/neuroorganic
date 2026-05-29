import os
import json
import uuid
import time
import requests
from datetime import date, timedelta

import fal_client
from google import genai
from google.genai import types
from flask import current_app

_GEMINI_FALLBACK_MODELS = ['gemini-2.5-flash', 'gemini-2.0-flash']


def _gemini_generate_with_retry(client, model, contents, config, max_retries=3):
    """Call generate_content with retry on 503 and model fallback.

    503 UNAVAILABLE → retry with backoff, then fallback model.
    429 RESOURCE_EXHAUSTED com 'limit: 0' → quota zerada, falha imediata.
    429 rate-limit normal → retry com backoff, sem fallback de modelo.
    """
    def _is_quota_zero(msg):
        return 'limit: 0' in msg or 'RESOURCE_EXHAUSTED' in msg and 'free_tier' in msg

    last_exc = None
    # Try primary model first with retries
    for retry in range(max_retries):
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as e:
            msg = str(e)
            if _is_quota_zero(msg):
                raise  # cota zerada — não adianta retry nem fallback
            if '503' in msg or 'UNAVAILABLE' in msg or '429' in msg:
                last_exc = e
                if retry < max_retries - 1:
                    time.sleep(2 ** retry)
                continue
            raise

    # Only fallback on transient unavailability (503), not quota issues
    if last_exc and ('503' in str(last_exc) or 'UNAVAILABLE' in str(last_exc)):
        for fallback in [m for m in _GEMINI_FALLBACK_MODELS if m != model]:
            try:
                return client.models.generate_content(
                    model=fallback, contents=contents, config=config
                )
            except Exception:
                continue

    raise last_exc

DIAS_MAP = {0: 'segunda', 1: 'terca', 2: 'quarta', 3: 'quinta', 4: 'sexta'}

# ── PromptLayout — montagem e seleção ─────────────────────────────────────────

_PALETA_MAP = {
    'marca':    'Use brand accent colors naturally integrated into the scene',
    'terroso':  'Earthy warm color palette: terracotta, ochre, sienna, warm browns',
    'vibrante': 'Vibrant saturated colors, high contrast, energetic palette',
    'pastel':   'Soft pastel color palette, gentle, dreamy and airy tones',
}

_INSTAGRAM_BASE = (
    "Vertical portrait 3:4 format (1080x1440px) optimized for Instagram feed. "
    "Clean negative space in the lower third for text overlay. "
    "No text, no letters, no typography in the image itself. "
    "Shallow depth of field, candid authentic emotion, 8K quality."
)


def montar_prompt_imagem(layout):
    """Assemble parametric fields into a Flux-compatible English image prompt."""
    parts = []

    estilo = (layout.estilo_visual or 'photorealistic').strip()
    parts.append(f"{estilo} photography, high production value, cinematic quality")

    if layout.iluminacao and layout.iluminacao.strip():
        parts.append(layout.iluminacao.strip())

    if layout.cenario and layout.cenario.strip():
        parts.append(f"Scene: {layout.cenario.strip()}")

    if layout.personagens and layout.personagens.strip():
        parts.append(f"Subject: {layout.personagens.strip()}")

    if layout.elementos_visuais and layout.elementos_visuais.strip():
        parts.append(f"Featuring: {layout.elementos_visuais.strip()}")

    if layout.humor and layout.humor.strip():
        parts.append(f"Mood: {layout.humor.strip()}")

    paleta_key = (layout.paleta or 'marca').strip()
    if paleta_key in _PALETA_MAP:
        parts.append(_PALETA_MAP[paleta_key])

    parts.append(_INSTAGRAM_BASE)

    if layout.restricoes and layout.restricoes.strip():
        parts.append(f"Avoid: {layout.restricoes.strip()}")

    return " ".join(p.rstrip('. ') + '.' for p in parts if p.strip())


def get_layout_ativo(cliente_id, data):
    """Return the best PromptLayout for a given client and date.

    Priority: exact date-range match → open-ended (no dates) → most recent.
    Returns None if no active layouts exist.
    """
    from models import PromptLayout

    layouts = PromptLayout.query.filter_by(cliente_id=cliente_id, ativo=True).all()
    if not layouts:
        return None

    # Priority 1: layout with date range that covers the target date
    ranged = [l for l in layouts if l.vigente_de or l.vigente_ate]
    for l in ranged:
        if l.vigente_para(data):
            return l

    # Priority 2: layout with no date restriction (always active)
    for l in layouts:
        if not l.vigente_de and not l.vigente_ate:
            return l

    # Priority 3: most recently created active layout
    return sorted(layouts, key=lambda l: l.criado_em, reverse=True)[0]


def preencher_campos_ia(descricao, gemini_api_key=None):
    """Parse a natural language description and return parametric fields as dict.

    Uses Gemini to extract visual parameters, returns them in English
    ready to fill the PromptLayout form.
    """
    client = _gemini_client(api_key=gemini_api_key)

    system = """You are an expert visual art director specializing in Instagram content for the Brazilian market.

Given a creative brief (in any language), extract visual style parameters and return them as JSON.
Translate ALL descriptive values to English for the image generation AI.

Return ONLY this JSON structure, no other text:
{
  "cenario": "setting/environment in English (empty string if unclear)",
  "estilo_visual": "exactly one of: photorealistic, cinematic, editorial, lifestyle, documentary",
  "personagens": "subject/people description in English (empty string if none)",
  "iluminacao": "exactly one of: natural soft light, golden hour, studio lighting, dramatic lighting, night festive lighting",
  "elementos_visuais": "specific props and visual elements in English (empty string if none)",
  "humor": "mood and emotion descriptors in English",
  "paleta": "exactly one of: marca, terroso, vibrante, pastel",
  "restricoes": "what to avoid in English (empty string if none)"
}

Rules:
- "paleta: marca" when brand colors are mentioned or implied
- "paleta: terroso" for rustic, earthy, natural, festive June party themes
- "paleta: vibrante" for energetic, colorful, festive themes
- "paleta: pastel" for soft, romantic, delicate themes
- For June party (Festa Junina): paleta=terroso, iluminacao=night festive lighting
- For Valentine's Day: paleta=pastel or vibrante, humor=romantic loving
- Always use "natural soft light" as default iluminacao if not specified"""

    response = _gemini_generate_with_retry(
        client,
        model='gemini-2.5-flash',
        contents=f"Extract visual parameters from this creative brief:\n\n{descricao}",
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.2,
        ),
    )

    return json.loads(_fix_json(response.text.strip()))

BASE_SYSTEM_PROMPT = """You are a world-class Brazilian social media content specialist and Instagram marketing expert with deep expertise in consumer psychology, behavioral economics, and viral content creation for the Brazilian market.

Your role is to create highly engaging Instagram content that resonates authentically with the brand's specific audience. You MUST follow the brand context provided — it defines who the audience is, what they look like, what they feel, and what visual style fits them.

## Instagram Content Guidelines

### Títulos (Titles)
- Maximum 80 characters including spaces
- Create an irresistible curiosity gap — the reader MUST want to know more
- Use psychological triggers: surprise, curiosity, transformation, benefit, urgency
- Can include 1 relevant emoji if it adds meaning (not just decoration)
- Should work as a standalone hook — someone seeing just the title should stop scrolling
- Avoid clickbait without substance: the title must deliver on its promise

### Legendas (Captions)
- 800–1200 characters total (Instagram rewards longer captions for engagement)
- CRITICAL: First 125 characters must be the unmissable hook — this is ALL that shows before "ver mais"
- USE LINE BREAKS between every section — Instagram captions must breathe. Use \n\n between paragraphs.
- USE EMOJIS GENEROUSLY: 6–10 emojis distributed throughout the text (hook, transitions, CTA, hashtag line). Emojis must match the emotion and brand tone.
- Strong, specific call-to-action in the last line before hashtags
- Exactly 5 hashtags on a SEPARATE line at the very end
- Hashtag mix: 2 high-volume + 2 medium + 1 brand hashtag relevant to the brand context

Caption structure (each section separated by \n\n):
1. 🔥 Hook line — surprising fact, tension, or bold statement (first 125 chars, ends with emoji)
2. Development — 2–3 sentences expanding the hook, with 1–2 emojis mid-text
3. Application — how this matters to the reader / what they gain, with 1 emoji
4. CTA — direct action line ending with emoji (👇 ✅ 🔗 etc.)
5. Hashtags — on a new line, exactly 5

Example of correct format:
"Hook irresistível que para o scroll 🔥\n\nDesenvolvimento do tema em 2–3 frases que aprofundam a ideia e criam conexão emocional com o leitor. ✨\n\nO que você pode fazer com isso hoje? Aqui está o caminho mais simples para começar. 💡\n\nClique no link da bio e dê o primeiro passo agora. 👇\n\n#hashtag1 #hashtag2 #hashtag3 #hashtag4 #hashtag5"

### Prompts de Imagem (always in English)
- Photorealistic photography style, high production value
- The image must visually represent the brand's real audience — follow the brand context strictly: their social class, appearance, environment, emotion
- Do NOT default to executives, suits, offices, or aspirational lifestyles unless the brand context specifies it
- Lighting: natural, warm, authentic — avoid overly polished corporate aesthetics
- Format: vertical portrait 3:4 (1080x1440) — Instagram feed format. The image must be taller than wide.
- Negative space: leave clean area on the lower portion for text overlay
- No text, letters, or typography in the image itself
- Style descriptors: "cinematic lighting", "shallow depth of field", "photorealistic", "8K", "candid emotion", "authentic Brazilian people"

## Response Format — CRITICAL

You MUST respond with ONLY valid JSON. No markdown code blocks, no explanations, no preamble. Just the raw JSON object:

{
  "titulo": "título aqui (máximo 80 caracteres)",
  "legenda": "Hook irresistível que para o scroll 🔥\n\nDesenvolvimento em 2–3 frases com conexão emocional. ✨\n\nO que o leitor ganha com isso. 💡\n\nCTA direto aqui. 👇\n\n#hashtag1 #hashtag2 #hashtag3 #hashtag4 #hashtag5",
  "prompt_imagem": "English photorealistic image prompt here"
}

Any text outside this JSON structure will cause a system error. Respond with pure JSON only."""


def _build_system_prompt(contexto=""):
    if not contexto:
        return BASE_SYSTEM_PROMPT
    return (
        BASE_SYSTEM_PROMPT
        + f"\n\n## Brand Context — HIGHEST PRIORITY\n\n"
        + "Everything you create — titles, captions, image prompts — MUST reflect this brand context. "
        + "It overrides any generic assumption about audience, tone, or visual style.\n\n"
        + contexto
    )


def _gemini_client(api_key=None):
    key = api_key or os.environ['GEMINI_API_KEY']
    return genai.Client(
        api_key=key,
        http_options={'api_version': 'v1alpha'},
    )


def gerar_posts_hoje(data=None, cliente_id=None, prompt_layout_id=None):
    """Generate posts for active clients for the given date (default: today).

    If cliente_id is given, generates only for that client.
    If prompt_layout_id is given, uses that specific layout instead of auto-detecting.
    Returns a list of created Post objects.
    """
    from models import db, Cliente, PromptEstilo, Post, PromptLayout

    alvo = data or date.today()
    dia_num = alvo.weekday()
    if dia_num >= 5:
        print(f"{alvo} é fim de semana. Nada gerado.")
        return []

    dia_semana = DIAS_MAP[dia_num]
    if cliente_id:
        c = Cliente.query.get(cliente_id)
        clientes = [c] if c and c.ativo else []
    else:
        clientes = Cliente.query.filter_by(ativo=True).all()
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
            cta = prompt_estilo.texto_cta or ""
            logo_path = _logo_filepath(cliente.logo_data or cliente.logo_url)
            contexto = cliente.contexto or ""
            gemini_client = _gemini_client(api_key=cliente.gemini_api_key)

            # Seleciona o layout visual: explícito > automático por data > fallback legacy
            if prompt_layout_id:
                layout = PromptLayout.query.get(prompt_layout_id)
            else:
                layout = get_layout_ativo(cliente.id, alvo)

            template_visual = (
                layout.prompt_gerado if layout and layout.prompt_gerado
                else (prompt_estilo.prompt_imagem or '')
            )
            layout_info = f" via layout '{layout.nome}'" if layout else " (prompt direto)"

            if entry_planejada:
                print(f"[{cliente.nome}] Usando planejamento para {alvo}{layout_info}...")
                titulo = entry_planejada['titulo']
                legenda = entry_planejada['legenda']
                prompt_img = template_visual.replace('{intencao_do_dia}', titulo)
            else:
                print(f"[{cliente.nome}] Gerando conteúdo via IA ({dia_semana}{layout_info})...")
                titulo, legenda, prompt_img = _gerar_texto(
                    gemini_client, prompt_estilo.intencao, template_visual,
                    contexto=contexto,
                    layout=layout,
                )

            print(f"[{cliente.nome}] Gerando imagem...")
            imagem_url = _gerar_imagem(cliente.id, dia_semana, prompt_img,
                                       titulo=titulo, subheadline=subheadline,
                                       cta=cta, logo_path=logo_path,
                                       contexto=contexto,
                                       api_key=cliente.gemini_api_key,
                                       cor_primaria=cliente.cor_primaria)

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


def gerar_texto_carrossel(intencao, template_visual, num_frames, contexto="", gemini_api_key=None):
    """Generate carousel content: title, one Instagram caption, and per-frame text+prompt.

    Returns (titulo_carrossel, legenda, frames) where frames is a list of dicts:
    [{titulo, texto_frame, prompt_imagem}, ...]
    """
    client = _gemini_client(api_key=gemini_api_key)

    frame_roles = {
        2: [
            "Frame 1 — GANCHO: Headline de impacto que para o scroll. Visual de abertura forte.",
            "Frame 2 — REVELAÇÃO + CTA: Desenvolvimento + chamada para ação clara. Visual de encerramento.",
        ],
        3: [
            "Frame 1 — GANCHO: Headline de impacto que para o scroll. Visual de abertura forte.",
            "Frame 2 — DESENVOLVIMENTO: Aprofunda o conteúdo, cria conexão emocional.",
            "Frame 3 — CONCLUSÃO + CTA: Fechamento poderoso + chamada para ação. Visual de encerramento.",
        ],
    }
    roles_txt = "\n".join(f"  {r}" for r in frame_roles.get(num_frames, frame_roles[2]))

    user_message = (
        f"Crie um CARROSSEL do Instagram com {num_frames} frames.\n\n"
        f"INTENÇÃO DO CONTEÚDO: {intencao}\n\n"
        f"TEMPLATE VISUAL BASE:\n{template_visual}\n\n"
        f"ESTRUTURA DOS FRAMES:\n{roles_txt}\n\n"
        f"Retorne APENAS JSON válido com esta estrutura exata:\n"
        '{\n'
        '  "titulo_carrossel": "Título geral do carrossel (máx 80 chars, gancho irresistível)",\n'
        '  "legenda": "Legenda única do Instagram (800-1200 chars, \\n\\n entre seções, 6-10 emojis, CTA + 5 hashtags no final)",\n'
        '  "frames": [\n'
        '    {\n'
        '      "titulo": "Texto overlay desta imagem (máx 52 chars, impacto máximo)",\n'
        '      "texto_frame": "Texto de apoio curto (máx 110 chars, complementa o título)",\n'
        '      "prompt_imagem": "English Flux prompt — UNIQUE scene for this specific frame"\n'
        '    }\n'
        '  ]\n'
        '}\n\n'
        'RULES:\n'
        '- Each frame has a DIFFERENT visual scene (unique prompt_imagem per frame)\n'
        '- Frame titles: short, punchy, different from each other\n'
        '- All prompt_imagem values in English, refine the template visual for that frame role\n'
        '- Caption (legenda) guides the reader through all frames as a story arc\n'
        f'- Return exactly {num_frames} frames (no more, no less)'
    )

    response = _gemini_generate_with_retry(
        client,
        model="gemini-2.5-flash",
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=_build_system_prompt(contexto),
            temperature=0.7,
        ),
    )

    data = json.loads(_fix_json(response.text.strip()))
    frames = data.get("frames", [])[:num_frames]
    return data["titulo_carrossel"], data["legenda"], frames


def gerar_frame_carrossel(post, frame_index):
    """Generate a single carousel frame image and update post.frames_json.

    Must be called within Flask app context.
    Returns the image URL for the generated frame.
    """
    import json as _json
    from models import db

    frames = _json.loads(post.frames_json or '[]')
    if frame_index >= len(frames):
        raise ValueError(f"Frame {frame_index} não existe (total: {len(frames)})")

    frame = frames[frame_index]
    cliente = post.cliente
    logo_path = _logo_filepath(cliente.logo_data or cliente.logo_url)

    imagem_url = _gerar_imagem(
        cliente.id,
        f"cr{frame_index}",
        frame['prompt_imagem'],
        titulo=frame['titulo'],
        subheadline=frame.get('texto_frame', ''),
        cta="",
        logo_path=logo_path,
        contexto=cliente.contexto or "",
        api_key=cliente.gemini_api_key,
        cor_primaria=cliente.cor_primaria,
    )

    frames[frame_index]['imagem_url'] = imagem_url
    post.frames_json = _json.dumps(frames, ensure_ascii=False)

    if all(f.get('imagem_url') for f in frames):
        post.status = 'pendente'
        post.imagem_url = frames[0]['imagem_url']
        post.prompt_usado = " | ".join(f['prompt_imagem'] for f in frames)

    db.session.commit()
    return imagem_url


def regerar_post(post):
    """Regenerate a post using its feedback as context for Gemini.

    Marks the old post as 'reprovado' and creates a new 'pendente' post.
    Must be called within a Flask application context.
    Returns the new Post object.
    """
    from models import db, PromptEstilo, Post, PromptLayout

    prompt_estilo = PromptEstilo.query.filter_by(
        cliente_id=post.cliente_id,
        dia_semana=post.dia_semana,
        ativo=True,
    ).first()

    if not prompt_estilo:
        raise ValueError(f"Sem prompt ativo para {post.dia_semana}")

    contexto = post.cliente.contexto or ""
    subheadline = prompt_estilo.texto_subheadline or ""

    layout = get_layout_ativo(post.cliente_id, post.data_publicacao)
    template_visual = (
        layout.prompt_gerado if layout and layout.prompt_gerado
        else (prompt_estilo.prompt_imagem or '')
    )

    # Se há entrada no planejamento para esta data, mantém título e legenda
    entries = parsear_planejamento(post.cliente.planejamento_texto or '')
    entry_planejada = next((e for e in entries if e['data'] == post.data_publicacao), None)

    if entry_planejada:
        titulo = post.titulo
        legenda = post.legenda
        prompt_img = template_visual.replace('{intencao_do_dia}', titulo)
    else:
        client = _gemini_client(api_key=post.cliente.gemini_api_key)
        titulo, legenda, prompt_img = _gerar_texto(
            client,
            prompt_estilo.intencao,
            template_visual,
            feedback=post.feedback,
            titulo_anterior=post.titulo,
            contexto=contexto,
            layout=layout,
        )

    subheadline = prompt_estilo.texto_subheadline or ""
    cta = prompt_estilo.texto_cta or ""
    logo_path = _logo_filepath(post.cliente.logo_data or post.cliente.logo_url)
    imagem_url = _gerar_imagem(post.cliente_id, post.dia_semana, prompt_img,
                               titulo=titulo, subheadline=subheadline,
                               cta=cta, logo_path=logo_path, contexto=contexto,
                               api_key=post.cliente.gemini_api_key,
                               cor_primaria=post.cliente.cor_primaria)

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


def _fix_json(text):
    """Escape literal control characters inside JSON string values."""
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1 if lines[0].startswith("```") else 0
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])

    result = []
    in_string = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\' and in_string:
            result.append(c)
            i += 1
            if i < len(text):
                result.append(text[i])
            i += 1
            continue
        if c == '"':
            in_string = not in_string
            result.append(c)
        elif in_string and c == '\n':
            result.append('\\n')
        elif in_string and c == '\r':
            result.append('\\r')
        elif in_string and ord(c) < 0x20 and c != '\t':
            pass  # drop other control chars
        else:
            result.append(c)
        i += 1
    return ''.join(result)


def _gerar_texto(client, intencao, prompt_imagem_template, feedback=None, titulo_anterior=None, contexto="", layout=None):
    """Call Gemini API to generate title, caption, and refined image prompt."""
    feedback_ctx = ""
    if feedback:
        feedback_ctx = f"\n\nFEEDBACK DO POST ANTERIOR (leve em consideração ao criar):\n{feedback}"
        if titulo_anterior:
            feedback_ctx += f'\nPost reprovado: "{titulo_anterior}" — crie algo notavelmente DIFERENTE.'

    tema_ctx = ""
    if layout:
        nome_tema = layout.nome or ""
        desc_tema = layout.descricao or ""
        tema_ctx = (
            f"\n\n## TEMA ATIVO: {nome_tema}\n"
            + (f"Descrição: {desc_tema}\n" if desc_tema else "")
            + "\nIMPORTANTE: O título e a legenda DEVEM incorporar o espírito e vocabulário deste tema de forma criativa e autêntica. "
            + "Adapte o tom, as metáforas, os emojis e o estilo narrativo ao tema — não use o padrão genérico de sempre. "
            + "Exemplo para 'Festa Junina': use expressões regionais, referências à tradição, clima festivo, calor humano da festa. "
            + "Mantenha a regra do headline (máx 80 chars, gancho irresistível que para o scroll)."
        )

    user_message = (
        f"Crie um post Instagram para hoje.\n\n"
        f"INTENÇÃO DO DIA: {intencao}"
        f"{tema_ctx}\n\n"
        f"TEMPLATE DO PROMPT DE IMAGEM:\n{prompt_imagem_template}"
        f"{feedback_ctx}\n\n"
        f"No campo \"prompt_imagem\" do JSON, refine o template acima "
        f"substituindo qualquer placeholder pela intenção real do dia. "
        f"O prompt_imagem deve refletir fielmente o público-alvo e estilo visual do Brand Context. "
        f"Escreva o prompt_imagem em inglês."
    )

    response = _gemini_generate_with_retry(
        client,
        model="gemini-2.5-flash",
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=_build_system_prompt(contexto),
            temperature=0.85 if layout else 0.7,
        ),
    )

    text = response.text.strip()
    data = json.loads(_fix_json(text))
    return data["titulo"], data["legenda"], data["prompt_imagem"]


def _pollinations_url(cliente_id, dia_semana, prompt):
    import urllib.parse
    # Pollinations has a URL length limit — keep prompt under 500 chars
    prompt_short = prompt[:500] if len(prompt) > 500 else prompt
    encoded = urllib.parse.quote(prompt_short)
    seed = abs(hash(f"{cliente_id}_{dia_semana}")) % 99999
    return (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1024&height=1365&seed={seed}&model=flux&nologo=true"
    )


def _prompt_sem_texto(prompt):
    """Remove text overlay instructions — Pillow handles typography."""
    return (
        f"{prompt}. "
        f"Leave clean negative space on the left or lower-left area for text overlay. "
        f"No text, no letters, no typography in the image itself."
    )


def _crop_portrait(filepath, ratio=(3, 4)):
    """Crop image to portrait ratio from center. Default 3:4 for Instagram."""
    from PIL import Image
    img = Image.open(filepath)
    w, h = img.size
    target_w = int(h * ratio[0] / ratio[1])
    if target_w < w:
        left = (w - target_w) // 2
        img = img.crop((left, 0, left + target_w, h))
    elif h < int(w * ratio[1] / ratio[0]):
        target_h = int(w * ratio[1] / ratio[0])
        top = (h - target_h) // 2
        img = img.crop((0, max(top, 0), w, max(top, 0) + target_h))
    img.save(filepath, "JPEG", quality=93)


def _logo_filepath(logo_url_or_data):
    """Return absolute path to logo file, decoding from DB base64 if needed."""
    if not logo_url_or_data:
        return None
    if logo_url_or_data.startswith('data:'):
        import base64, tempfile
        mime, b64 = logo_url_or_data.split(',', 1)
        ext = '.png' if 'png' in mime else '.jpg'
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=os.path.join(current_app.root_path, 'tmp'))
        tmp.write(base64.b64decode(b64))
        tmp.close()
        return tmp.name
    return os.path.join(current_app.root_path, logo_url_or_data.lstrip('/'))


def _extrair_subheadline_cta(legenda):
    """Extract first hook line and last CTA line from a generated caption."""
    import re
    lines = [l.strip() for l in legenda.split('\n') if l.strip()]
    content = [l for l in lines if not re.match(r'^#', l)]
    subheadline = re.sub(r'[^\w\s\.,!?áéíóúãõâêîôûàèìòùçÁÉÍÓÚÃÕÂÊÎÔÛÀÈÌÒÙÇ🧠🤝💡🎯]', '', content[0])[:72] if content else ""
    cta = content[-1][:60] if len(content) > 1 else ""
    return subheadline.strip(), cta.strip()


def _hex_to_rgba(hex_color, alpha=255):
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4)) + (alpha,)


def _strip_emoji(text):
    """Remove emoji characters that Oswald/Montserrat fonts cannot render (would show as □)."""
    import re
    emoji_re = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F700-\U0001F77F"  # alchemical symbols
        "\U0001F780-\U0001F7FF"  # geometric shapes extended
        "\U0001F800-\U0001F8FF"  # supplemental arrows-c
        "\U0001F900-\U0001F9FF"  # supplemental symbols & pictographs
        "\U0001FA00-\U0001FA6F"  # chess symbols
        "\U0001FA70-\U0001FAFF"  # symbols & pictographs extended-a
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"
        "\U0001F1E0-\U0001F1FF"  # flags
        "☀-⛿"          # miscellaneous symbols
        "✀-➿"          # dingbats block
        "︀-️"          # variation selectors
        "‍"                  # zero-width joiner
        "]+",
        flags=re.UNICODE,
    )
    return emoji_re.sub('', text).strip()


def compor_texto_na_imagem(filepath, titulo, subheadline="", cta="", logo_path=None, cor_primaria=None):
    """Premium Pillow text overlay — Apple/Nike editorial style."""
    from PIL import Image, ImageDraw, ImageFont

    base = os.path.dirname(__file__)
    font_oswald = os.path.join(base, "static", "fonts", "Oswald.ttf")
    font_mont  = os.path.join(base, "static", "fonts", "Montserrat.ttf")

    GOLD      = _hex_to_rgba(cor_primaria) if cor_primaria else (245, 166, 35, 255)
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
    titulo_limpo = _strip_emoji(titulo)
    hl_lines, current = [], ""
    for word in titulo_limpo.upper().split():
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
            "image_size": "portrait_4_3",
            "num_images": 1,
            "enable_safety_checker": False,
        },
    )
    image_url = result["images"][0]["url"]
    resp = requests.get(image_url, timeout=120)
    resp.raise_for_status()
    return resp.content


def _gerar_imagem_imagen3(prompt, api_key=None):
    """Generate image via Gemini image model. Uses client API key if provided."""
    client = genai.Client(
        api_key=api_key or os.environ['GEMINI_API_KEY'],
        http_options={'api_version': 'v1alpha'},
    )
    portrait_prompt = f"{prompt} Portrait orientation, 3:4 aspect ratio (taller than wide), optimized for Instagram feed post."
    response = client.models.generate_content(
        model='gemini-2.5-flash-image',
        contents=portrait_prompt,
        config=types.GenerateContentConfig(
            response_modalities=['IMAGE'],
        ),
    )
    for part in response.candidates[0].content.parts:
        if getattr(part, 'inline_data', None) is not None:
            return part.inline_data.data
    raise ValueError('Nenhuma imagem retornada pelo modelo')


def _gerar_imagem(cliente_id, dia_semana, prompt, titulo="", subheadline="", cta="", logo_path=None, contexto="", api_key=None, cor_primaria=None):
    """Generate image using configured provider, then compose text overlay."""
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"{cliente_id}_{dia_semana}_{uuid.uuid4().hex[:8]}.jpg"
    filepath = os.path.join(upload_dir, filename)

    clean_prompt = _prompt_sem_texto(prompt)
    if contexto:
        clean_prompt = f"{clean_prompt} Brand context: {contexto}"
    if cor_primaria:
        clean_prompt = f"{clean_prompt} Use brand color palette with dominant color {cor_primaria} as accent in the scene."
    provedor = _get_provedor()

    if provedor == 'imagen3':
        image_bytes = _gerar_imagem_imagen3(clean_prompt, api_key=api_key)
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

    _crop_portrait(filepath)

    if titulo:
        compor_texto_na_imagem(filepath, titulo, subheadline=subheadline, cta=cta or "", logo_path=logo_path, cor_primaria=cor_primaria)

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
    if dia_num >= 5:
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

    logo_path = _logo_filepath(cliente.logo_data or cliente.logo_url)
    imagem_url = _gerar_imagem(
        cliente.id, dia_semana,
        prompt_img,
        titulo=entry['titulo'],
        logo_path=logo_path,
        api_key=cliente.gemini_api_key,
        cor_primaria=cliente.cor_primaria,
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


# ── Geração de planejamento semanal via IA ────────────────────────────────────

_MESES_BR = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro',
}

_DIAS_NOME_BR = {
    0: 'Segunda-feira', 1: 'Terça-feira', 2: 'Quarta-feira',
    3: 'Quinta-feira', 4: 'Sexta-feira',
}

_CALENDARIO_BR = """
Janeiro: Confraternização Universal (1/jan), preparação para Carnaval
Fevereiro/Março: Carnaval (data variável — terça gorda e quarta de cinzas), Dia Internacional da Mulher (8/mar)
Abril: Páscoa (variável — domingo), Tiradentes (21/abr), véspera do Dia do Trabalho
Maio: Dia do Trabalho (1/mai), Dia das Mães (2º domingo de maio), Dia do Estudante (11/mai)
Junho: Corpus Christi (variável), Dia dos Namorados (12/jun), Festas Juninas (todo o mês), Dia do Meio Ambiente (5/jun)
Julho: Férias escolares (julho inteiro), Dia do Amigo (20/jul)
Agosto: Dia dos Pais (2º domingo de agosto), Dia dos Solteiros (15/ago), Dia do Folclore (22/ago)
Setembro: Independência do Brasil (7/set), Dia do Cliente (15/set), Início da Primavera (22 ou 23/set)
Outubro: Dia das Crianças (12/out), Dia dos Professores (15/out), Halloween (31/out)
Novembro: Finados (2/nov), Proclamação da República (15/nov), Consciência Negra (20/nov), Black Friday (última sexta de novembro)
Dezembro: Natal (25/dez), Réveillon (31/dez), festas e confraternizações de fim de ano (todo dezembro)
"""


def gerar_planejamento_ia(cliente, segunda_feira):
    """Generate a Mon–Fri weekly content plan using Gemini AI.

    Args:
        cliente: Cliente model instance
        segunda_feira: date object for Monday of the target week

    Returns:
        str — formatted planejamento text ready to paste into the editor
    """
    from models import PromptEstilo

    dias = []
    for i in range(5):
        dia = segunda_feira + timedelta(days=i)
        dia_key = DIAS_MAP[dia.weekday()]
        pe = PromptEstilo.query.filter_by(
            cliente_id=cliente.id, dia_semana=dia_key, ativo=True
        ).first()
        dias.append({
            'data': dia,
            'nome': _DIAS_NOME_BR[dia.weekday()],
            'intencao': pe.intencao if pe else None,
        })

    mes_nome = _MESES_BR[segunda_feira.month]
    ano = segunda_feira.year
    contexto = cliente.contexto or ''

    dias_txt = ''
    for d in dias:
        intencao_str = f'\n    Intenção configurada: {d["intencao"]}' if d['intencao'] else ''
        dias_txt += f'  • {d["nome"]} — {d["data"].strftime("%d/%m/%Y")}{intencao_str}\n'

    system_prompt = f"""Você é especialista em planejamento de conteúdo para Instagram no mercado brasileiro.

## Contexto da empresa (PRIORIDADE MÁXIMA — siga rigorosamente)
{contexto if contexto else 'Empresa sem contexto definido — crie conteúdo profissional e envolvente.'}

## Calendário brasileiro de datas comemorativas e sazonalidade
{_CALENDARIO_BR}

## Regras de criação
- Analise o mês e os dias solicitados — verifique datas comemorativas e sazonalidade
- Se houver data relevante para a marca naquele dia, incorpore-a naturalmente
- Se não houver, siga a intenção configurada ou crie conteúdo alinhado ao contexto da empresa
- Títulos: máximo 80 caracteres, gancho irresistível, psicologia de persuasão, 1 emoji se agregar sentido
- Legendas: 800–1200 caracteres, formato Instagram real com quebras de linha entre cada seção (\n\n), 6–10 emojis distribuídos ao longo do texto
- Estrutura da legenda: Hook (primeiros 125 chars) → Desenvolvimento → Aplicação → CTA → Hashtags (linha separada, exatamente 5)
- Mantenha a voz, o estilo e o público definidos no contexto da empresa

## FORMATO DE SAÍDA — retorne EXATAMENTE assim, sem nenhum texto antes ou depois:
DD/MM/AAAA - Titulo: Título aqui
Legenda: Legenda completa aqui...

DD/MM/AAAA - Titulo: Próximo título
Legenda: Próxima legenda...

(5 entradas no total, uma por linha, separadas por linha em branco)"""

    user_message = (
        f"Crie o planejamento da semana de {segunda_feira.strftime('%d/%m/%Y')} "
        f"({mes_nome}/{ano}).\n\n"
        f"Dias a preencher:\n{dias_txt}\n"
        f"Retorne exatamente 5 posts no formato especificado."
    )

    client = _gemini_client(api_key=cliente.gemini_api_key)
    response = _gemini_generate_with_retry(
        client,
        model='gemini-2.5-flash',
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.85,
        ),
    )
    return response.text.strip()


# ── Copia Tema — análise de imagem ────────────────────────────────────────────

def analisar_imagem_para_prompt(filepath, gemini_api_key=None):
    """Analyse a reference image and return a Flux-compatible image generation prompt.

    The prompt describes composition, lighting, mood, and style without
    referencing specific brand elements (colors, logos) from the source image,
    so the caller can apply the target brand palette on top.
    """
    from PIL import Image as PILImage

    client = _gemini_client(api_key=gemini_api_key)

    img = PILImage.open(filepath)
    # Keep aspect ratio, cap at 1024px longest side for API efficiency
    img.thumbnail((1024, 1024), PILImage.LANCZOS)

    system = """You are an expert AI art director specializing in Instagram content generation. Your task is to reverse-engineer a reference Instagram post image and produce a rich, detailed image generation prompt compatible with Flux (a photorealistic text-to-image AI model).

Analyse the image carefully and describe in detail:
1. PHOTOGRAPHIC STYLE — e.g. editorial, lifestyle, cinematic, documentary, product, portrait
2. COMPOSITION — framing, subject placement, rule of thirds, foreground/background layers, depth of field
3. LIGHTING — quality (hard/soft), direction, color temperature, shadows, highlights, any special effects (lens flare, bokeh, etc.)
4. MOOD & ATMOSPHERE — emotional tone, energy level, feeling evoked
5. SETTING & ENVIRONMENT — location type, time of day, indoor/outdoor, background elements
6. SUBJECT — type of person or object (no names, no brands), pose, expression, clothing style, skin tone if relevant
7. VISUAL DETAILS — textures, materials, props, decorative elements, negative space

Rules (strict):
- Write entirely in English
- Do NOT mention any text, typography, words, or captions visible in the source image — ignore them completely
- Do NOT mention any specific brand name, logo, or identifiable brand colors from the source image
- Do NOT include color palette instructions — brand colors will be appended separately
- The image must have a clean, uncluttered area (lower third or bottom 30%) left empty for text overlay
- End EVERY prompt with exactly this sentence: "Vertical portrait 3:4 format (1080x1440px) optimized for Instagram feed. Clean negative space in the lower third for text overlay. No text, no letters, no typography in the image itself."
- Output a single cohesive paragraph of 150–220 words
- Be specific and concrete — avoid vague words like "beautiful" or "nice"; use precise visual descriptors

Return ONLY the prompt paragraph, no preamble, no explanation."""

    response = _gemini_generate_with_retry(
        client,
        model='gemini-2.5-flash',
        contents=[img, "Analyse this reference Instagram image thoroughly and produce the detailed Flux image generation prompt as instructed. Remember: ignore all text/captions in the image, describe only the visual composition and style."],
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.25,
        ),
    )
    return response.text.strip()
