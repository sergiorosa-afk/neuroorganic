-- ============================================
-- NEUROORGANIC — Schema Multi-tenant
-- Banco: fionco36_neuroorganic
-- ============================================

-- Clientes (cada cliente = uma marca/Instagram)
CREATE TABLE clientes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    instagram_handle VARCHAR(50) NOT NULL,
    make_webhook_url MEDIUMTEXT,
    logo_url MEDIUMTEXT,
    planejamento_texto MEDIUMTEXT,
    contexto MEDIUMTEXT,
    ativo TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Usuários (login — cada usuário pertence a um cliente)
CREATE TABLE usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    senha_hash VARCHAR(255) NOT NULL,
    role ENUM('admin','cliente') DEFAULT 'cliente',
    ativo TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);

-- Prompts de estilo por dia da semana por cliente
CREATE TABLE prompts_estilo (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    dia_semana ENUM('segunda','terca','quarta','quinta','sexta') NOT NULL,
    intencao MEDIUMTEXT COMMENT 'O que o post quer comunicar nesse dia',
    prompt_imagem MEDIUMTEXT COMMENT 'Prompt completo para geração da imagem',
    texto_subheadline VARCHAR(120) DEFAULT '',
    texto_cta VARCHAR(80) DEFAULT 'Acesse o link na bio',
    ativo TINYINT(1) DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id),
    UNIQUE KEY uq_cliente_dia (cliente_id, dia_semana)
);

-- Posts gerados (título, legenda, imagem)
CREATE TABLE posts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    dia_semana ENUM('segunda','terca','quarta','quinta','sexta'),
    data_publicacao DATE,
    titulo VARCHAR(255),
    legenda MEDIUMTEXT,
    imagem_url MEDIUMTEXT,
    prompt_usado MEDIUMTEXT,
    status ENUM('pendente','aprovado','reprovado','publicado') DEFAULT 'pendente',
    feedback MEDIUMTEXT COMMENT 'Feedback quando reprovado',
    aprovado_por INT NULL,
    aprovado_em TIMESTAMP NULL,
    publicado_em TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id),
    FOREIGN KEY (aprovado_por) REFERENCES usuarios(id)
);

-- Configurações globais da plataforma (chave-valor)
CREATE TABLE configuracoes (
    chave VARCHAR(50) PRIMARY KEY,
    valor VARCHAR(255) NOT NULL
);

-- ============================================
-- DADOS INICIAIS
-- ============================================

-- Cliente: Neuroseller
INSERT INTO clientes (nome, instagram_handle) VALUES
('Neuroseller', 'neuroseller1');

-- Admin master (senha: Admin@2026 — troque após primeiro login)
INSERT INTO usuarios (cliente_id, nome, email, senha_hash, role) VALUES
(1, 'Admin', 'admin@neuroorganic.com',
 '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TiqrCiHMFfF1mER0wFb1.3.3.3.3.',
 'admin');

-- Prompt padrão para todos os dias (Neuroseller)
INSERT INTO prompts_estilo (cliente_id, dia_semana, intencao, prompt_imagem) VALUES
(1, 'segunda',  'Motivação e início de semana — energia e propósito', 'Ultra realistic cinematic editorial image of a Brazilian person (25–40 years old), natural beauty, relatable and humanized appearance, not a model, representing a real professional.\n\nFacial expression emotionally driven, subtle micro-expressions, deep eye connection with camera, conveying authenticity, trust and transformation.\n\nSkin extremely realistic with visible pores, texture, natural imperfections, no plastic smoothing, no artificial retouching.\n\nLighting cinematic and premium:\nsoft directional light, volumetric light rays, high dynamic range (HDR), natural highlights and shadows, studio-quality diffusion, soft contrast.\n\nColor grading:\nhigh-end editorial color grading, warm tones (beige, gold, soft brown), balanced with subtle cool tones when needed, Netflix/Apple commercial look.\n\nLens and composition:\n85mm lens look, shallow depth of field, ultra sharp focus on eyes, background softly blurred, waist-up framing, centered or rule of thirds composition.\n\nEnvironment:\nclean, minimal, modern and aesthetic professional environment, realistic and not exaggerated, softly blurred.\n\nMood:\nemotional storytelling, aspirational but grounded, realistic transformation feeling, cinematic atmosphere.\n\nStyle:\nluxury editorial photography, Vogue-level, Apple/Nike campaign quality, premium commercial look.\n\nTechnical:\n8K resolution, ultra detailed, high fidelity, depth, subtle film grain.\n\nScene concept:\n{intencao_do_dia}\n\nLayout composition for Instagram post:\nleave clean negative space on LEFT and/or RIGHT side for text overlay\nbalanced composition allowing headline readability\nsubject positioned slightly off-center for design usage\n\nTypography placeholder (do not render text, just leave space):\narea reserved for:\n- main headline (top or left)\n- supporting line (middle)\n- CTA (bottom)\n\nNO:\nno logos, no text rendered, no artificial beauty, no overediting, no cartoon look, no stock image feeling'),
(1, 'terca',   'Educação e conteúdo técnico — autoridade e conhecimento', 'Ultra realistic cinematic editorial image of a Brazilian person (25–40 years old), natural beauty, relatable and humanized appearance, not a model, representing a real professional.\n\nFacial expression emotionally driven, subtle micro-expressions, deep eye connection with camera, conveying authenticity, trust and transformation.\n\nSkin extremely realistic with visible pores, texture, natural imperfections, no plastic smoothing, no artificial retouching.\n\nLighting cinematic and premium:\nsoft directional light, volumetric light rays, high dynamic range (HDR), natural highlights and shadows, studio-quality diffusion, soft contrast.\n\nColor grading:\nhigh-end editorial color grading, warm tones (beige, gold, soft brown), balanced with subtle cool tones when needed, Netflix/Apple commercial look.\n\nLens and composition:\n85mm lens look, shallow depth of field, ultra sharp focus on eyes, background softly blurred, waist-up framing, centered or rule of thirds composition.\n\nEnvironment:\nclean, minimal, modern and aesthetic professional environment, realistic and not exaggerated, softly blurred.\n\nMood:\nemotional storytelling, aspirational but grounded, realistic transformation feeling, cinematic atmosphere.\n\nStyle:\nluxury editorial photography, Vogue-level, Apple/Nike campaign quality, premium commercial look.\n\nTechnical:\n8K resolution, ultra detailed, high fidelity, depth, subtle film grain.\n\nScene concept:\n{intencao_do_dia}\n\nLayout composition for Instagram post:\nleave clean negative space on LEFT and/or RIGHT side for text overlay\nbalanced composition allowing headline readability\nsubject positioned slightly off-center for design usage\n\nTypography placeholder (do not render text, just leave space):\narea reserved for:\n- main headline (top or left)\n- supporting line (middle)\n- CTA (bottom)\n\nNO:\nno logos, no text rendered, no artificial beauty, no overediting, no cartoon look, no stock image feeling'),
(1, 'quarta',  'Prova social e depoimentos — confiança e resultados', 'Ultra realistic cinematic editorial image of a Brazilian person (25–40 years old), natural beauty, relatable and humanized appearance, not a model, representing a real professional.\n\nFacial expression emotionally driven, subtle micro-expressions, deep eye connection with camera, conveying authenticity, trust and transformation.\n\nSkin extremely realistic with visible pores, texture, natural imperfections, no plastic smoothing, no artificial retouching.\n\nLighting cinematic and premium:\nsoft directional light, volumetric light rays, high dynamic range (HDR), natural highlights and shadows, studio-quality diffusion, soft contrast.\n\nColor grading:\nhigh-end editorial color grading, warm tones (beige, gold, soft brown), balanced with subtle cool tones when needed, Netflix/Apple commercial look.\n\nLens and composition:\n85mm lens look, shallow depth of field, ultra sharp focus on eyes, background softly blurred, waist-up framing, centered or rule of thirds composition.\n\nEnvironment:\nclean, minimal, modern and aesthetic professional environment, realistic and not exaggerated, softly blurred.\n\nMood:\nemotional storytelling, aspirational but grounded, realistic transformation feeling, cinematic atmosphere.\n\nStyle:\nluxury editorial photography, Vogue-level, Apple/Nike campaign quality, premium commercial look.\n\nTechnical:\n8K resolution, ultra detailed, high fidelity, depth, subtle film grain.\n\nScene concept:\n{intencao_do_dia}\n\nLayout composition for Instagram post:\nleave clean negative space on LEFT and/or RIGHT side for text overlay\nbalanced composition allowing headline readability\nsubject positioned slightly off-center for design usage\n\nTypography placeholder (do not render text, just leave space):\narea reserved for:\n- main headline (top or left)\n- supporting line (middle)\n- CTA (bottom)\n\nNO:\nno logos, no text rendered, no artificial beauty, no overediting, no cartoon look, no stock image feeling'),
(1, 'quinta',  'Oferta e conversão — desejo e urgência', 'Ultra realistic cinematic editorial image of a Brazilian person (25–40 years old), natural beauty, relatable and humanized appearance, not a model, representing a real professional.\n\nFacial expression emotionally driven, subtle micro-expressions, deep eye connection with camera, conveying authenticity, trust and transformation.\n\nSkin extremely realistic with visible pores, texture, natural imperfections, no plastic smoothing, no artificial retouching.\n\nLighting cinematic and premium:\nsoft directional light, volumetric light rays, high dynamic range (HDR), natural highlights and shadows, studio-quality diffusion, soft contrast.\n\nColor grading:\nhigh-end editorial color grading, warm tones (beige, gold, soft brown), balanced with subtle cool tones when needed, Netflix/Apple commercial look.\n\nLens and composition:\n85mm lens look, shallow depth of field, ultra sharp focus on eyes, background softly blurred, waist-up framing, centered or rule of thirds composition.\n\nEnvironment:\nclean, minimal, modern and aesthetic professional environment, realistic and not exaggerated, softly blurred.\n\nMood:\nemotional storytelling, aspirational but grounded, realistic transformation feeling, cinematic atmosphere.\n\nStyle:\nluxury editorial photography, Vogue-level, Apple/Nike campaign quality, premium commercial look.\n\nTechnical:\n8K resolution, ultra detailed, high fidelity, depth, subtle film grain.\n\nScene concept:\n{intencao_do_dia}\n\nLayout composition for Instagram post:\nleave clean negative space on LEFT and/or RIGHT side for text overlay\nbalanced composition allowing headline readability\nsubject positioned slightly off-center for design usage\n\nTypography placeholder (do not render text, just leave space):\narea reserved for:\n- main headline (top or left)\n- supporting line (middle)\n- CTA (bottom)\n\nNO:\nno logos, no text rendered, no artificial beauty, no overediting, no cartoon look, no stock image feeling'),
(1, 'sexta',   'Bastidores e humanização — conexão e identidade', 'Ultra realistic cinematic editorial image of a Brazilian person (25–40 years old), natural beauty, relatable and humanized appearance, not a model, representing a real professional.\n\nFacial expression emotionally driven, subtle micro-expressions, deep eye connection with camera, conveying authenticity, trust and transformation.\n\nSkin extremely realistic with visible pores, texture, natural imperfections, no plastic smoothing, no artificial retouching.\n\nLighting cinematic and premium:\nsoft directional light, volumetric light rays, high dynamic range (HDR), natural highlights and shadows, studio-quality diffusion, soft contrast.\n\nColor grading:\nhigh-end editorial color grading, warm tones (beige, gold, soft brown), balanced with subtle cool tones when needed, Netflix/Apple commercial look.\n\nLens and composition:\n85mm lens look, shallow depth of field, ultra sharp focus on eyes, background softly blurred, waist-up framing, centered or rule of thirds composition.\n\nEnvironment:\nclean, minimal, modern and aesthetic professional environment, realistic and not exaggerated, softly blurred.\n\nMood:\nemotional storytelling, aspirational but grounded, realistic transformation feeling, cinematic atmosphere.\n\nStyle:\nluxury editorial photography, Vogue-level, Apple/Nike campaign quality, premium commercial look.\n\nTechnical:\n8K resolution, ultra detailed, high fidelity, depth, subtle film grain.\n\nScene concept:\n{intencao_do_dia}\n\nLayout composition for Instagram post:\nleave clean negative space on LEFT and/or RIGHT side for text overlay\nbalanced composition allowing headline readability\nsubject positioned slightly off-center for design usage\n\nTypography placeholder (do not render text, just leave space):\narea reserved for:\n- main headline (top or left)\n- supporting line (middle)\n- CTA (bottom)\n\nNO:\nno logos, no text rendered, no artificial beauty, no overediting, no cartoon look, no stock image feeling');
