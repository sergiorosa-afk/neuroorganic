<?php
// NeuroOrganic — Deploy via Git pull + Passenger restart
// Uso: https://seudominio.com.br/neuroorganic/deploy.php?token=neuro2026deploy&action=full

$TOKEN   = 'neuro2026deploy';
$DIR     = __DIR__;
$VENV    = "$DIR/venv";
$PIP     = "$VENV/bin/pip";
$PYTHON  = "$VENV/bin/python3";
$FLASK   = "$VENV/bin/flask";
$RESTART = "$DIR/tmp/restart.txt";

if (($_GET['token'] ?? '') !== $TOKEN) {
    http_response_code(403);
    die('Acesso negado.');
}

header('Content-Type: text/plain; charset=utf-8');

function cmd($label, $command) {
    echo ">>> $label\n";
    $out = []; $code = 0;
    exec($command . ' 2>&1', $out, $code);
    echo implode("\n", $out) . "\n";
    echo "Exit: $code\n\n";
    return $code;
}

echo "=== NeuroOrganic Deploy ===\n";
echo "Data: " . date('d/m/Y H:i:s') . "\n";
echo "Dir:  $DIR\n\n";

$action = $_GET['action'] ?? 'pull';

// ── Criar .env em produção ────────────────────────────────────────────────────
if ($action === 'setup-env') {
    $env_file = "$DIR/.env";

    // Lê .env existente ou começa do padrão
    $defaults = [
        'DATABASE_URL'      => 'mysql+pymysql://fionco36_neuroorganic:12345%40Mudar@localhost:3306/fionco36_neuroorganic',
        'SECRET_KEY'        => 'neuro-secret-2026-xK9mP',
        'GEMINI_API_KEY'    => '',
        'FAL_KEY'           => '',
        'CRON_SECRET'       => 'neuro-cron-2026',
        'REQUEST_BASE_URL'  => 'https://neuroorganic.neuroseller.com.br',
    ];

    // Carrega valores existentes do .env
    $current = $defaults;
    if (file_exists($env_file)) {
        foreach (file($env_file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
            if (strpos($line, '=') !== false && $line[0] !== '#') {
                [$k, $v] = explode('=', $line, 2);
                $current[trim($k)] = trim($v);
            }
        }
    }

    // Sobrescreve apenas os parâmetros passados na URL
    if (isset($_GET['gemini']) && $_GET['gemini'] !== '') $current['GEMINI_API_KEY'] = $_GET['gemini'];
    if (isset($_GET['fal'])    && $_GET['fal']    !== '') $current['FAL_KEY']        = $_GET['fal'];
    if (isset($_GET['cron'])   && $_GET['cron']   !== '') $current['CRON_SECRET']    = $_GET['cron'];

    $lines = [];
    foreach ($current as $k => $v) {
        $lines[] = "$k=$v";
    }
    file_put_contents($env_file, implode("\n", $lines) . "\n");
    echo file_exists($env_file) ? "✓ .env atualizado com sucesso\n" : "✗ Falha ao salvar .env\n";
    echo "\nChaves configuradas:\n";
    echo "  GEMINI_API_KEY : " . ($current['GEMINI_API_KEY'] ? '✓ presente' : '✗ vazia') . "\n";
    echo "  FAL_KEY        : " . ($current['FAL_KEY']        ? '✓ presente' : '✗ vazia') . "\n";
    echo "\n=== Concluído ===\n";
    exit;
}

// ── Listar modelos Gemini disponíveis ─────────────────────────────────────────
if ($action === 'list-models') {
    $env_file = "$DIR/.env";
    $script = <<<PY
import os
from dotenv import load_dotenv
load_dotenv('$env_file')
from google import genai
client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
for m in client.models.list():
    if 'generateContent' in (m.supported_actions or []):
        print(m.name)
PY;
    $tmp = tempnam('/tmp', 'gmodels_') . '.py';
    file_put_contents($tmp, $script);
    $out = shell_exec("$PYTHON $tmp 2>&1");
    unlink($tmp);
    echo $out;
    echo "\n=== Concluído ===\n";
    exit;
}

// ── Migração: adiciona colunas novas sem recriar tabelas ─────────────────────
if ($action === 'migrate') {
    $env_file = "$DIR/.env";
    $script = <<<PY
import os, sys
sys.path.insert(0, '$DIR')
from dotenv import load_dotenv
load_dotenv('$env_file')
from app import app
from models import db

migrations = [
    "ALTER TABLE clientes ADD COLUMN contexto MEDIUMTEXT",
    "CREATE TABLE IF NOT EXISTS configuracoes (chave VARCHAR(50) PRIMARY KEY, valor VARCHAR(255) NOT NULL)",
]

with app.app_context():
    for sql in migrations:
        try:
            db.session.execute(db.text(sql))
            db.session.commit()
            print(f"OK: {sql[:60]}")
        except Exception as e:
            db.session.rollback()
            print(f"Skip: {e}")
PY;
    $tmp = tempnam('/tmp', 'migrate_') . '.py';
    file_put_contents($tmp, $script);
    $out = shell_exec("cd $DIR && $PYTHON $tmp 2>&1");
    unlink($tmp);
    echo $out;
    echo "\n=== Migração concluída ===\n";
    exit;
}

// ── Inicializar banco de dados ────────────────────────────────────────────────
if ($action === 'init') {
    if (!file_exists("$DIR/.env")) {
        echo "AVISO: .env não encontrado — rode action=setup-env primeiro\n\n";
    }

    $env_line = "set -a && source $DIR/.env && set +a";

    cmd('flask init-db', "bash -c '$env_line && FLASK_APP=$DIR/app.py $FLASK --app $DIR/app.py init-db'");
    cmd('flask criar-admin', "bash -c '$env_line && FLASK_APP=$DIR/app.py $FLASK --app $DIR/app.py criar-admin'");

    echo "=== Banco inicializado ===\n";
    echo "Login: admin@neuroorganic.com / Admin@2026\n";

    // restart
    @mkdir("$DIR/tmp", 0755, true);
    file_put_contents($RESTART, date('Y-m-d H:i:s'));
    echo "✓ Passenger reiniciado\n";
    exit;
}

// ── Git pull ──────────────────────────────────────────────────────────────────
cmd('Git Reset', "cd $DIR && git checkout -- . && git clean -fd");
cmd('Git Pull', "cd $DIR && git pull origin main");
cmd('chmod app.cgi', "chmod 755 $DIR/public/app.cgi");

// ── Setup venv + dependências ─────────────────────────────────────────────────
if ($action === 'full' || $action === 'pip') {

    if (!file_exists($PIP)) {
        echo ">>> Criar venv\n";
        $py3 = trim(shell_exec("which python3.9 2>/dev/null || which python3.8 2>/dev/null || which python3 2>/dev/null"));
        echo "Python: $py3\n\n";
        cmd('python -m venv', "cd $DIR && $py3 -m venv venv");
    }

    cmd('Pip upgrade', "$PIP install --upgrade pip");
    cmd('Pip install', "$PIP install -r $DIR/requirements.txt");
}

// ── Restart Passenger ─────────────────────────────────────────────────────────
@mkdir("$DIR/tmp", 0755, true);
file_put_contents($RESTART, date('Y-m-d H:i:s'));
echo ">>> Passenger restart\n";
echo file_exists($RESTART) ? "✓ tmp/restart.txt atualizado\n\n" : "✗ Falha\n\n";

echo "=== Concluído ===\n";
