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
    $gemini_key = $_GET['gemini'] ?? '';
    $cron_secret = $_GET['cron'] ?? 'neuro-cron-2026';

    if (!$gemini_key) {
        die("ERRO: passe ?gemini=SUA_CHAVE na URL\n");
    }

    $env = <<<ENV
DATABASE_URL=mysql+pymysql://fionco36_neuroorganic:12345%40Mudar@localhost:3306/fionco36_neuroorganic
SECRET_KEY=neuro-secret-2026-xK9mP
GEMINI_API_KEY=$gemini_key
CRON_SECRET=$cron_secret
REQUEST_BASE_URL=https://neuroseller.com.br/neuroorganic
ENV;

    file_put_contents("$DIR/.env", $env);
    echo file_exists("$DIR/.env") ? "✓ .env criado com sucesso\n" : "✗ Falha ao criar .env\n";
    echo "\n=== Concluído ===\n";
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
cmd('Git Pull', "cd $DIR && git pull origin main");

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
