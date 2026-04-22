<?php
// NeuroOrganic — Deploy via Git pull + Passenger restart
// Acesso: https://seudominio.com.br/deploy.php?token=neuro2026deploy

$TOKEN     = 'neuro2026deploy';
$APP_DIR   = __DIR__;
$VENV_PIP  = $APP_DIR . '/venv/bin/pip';
$RESTART   = $APP_DIR . '/tmp/restart.txt';

// ── Auth ──────────────────────────────────────────────────────────────────────
if (($_GET['token'] ?? '') !== $TOKEN) {
    http_response_code(403);
    die('Acesso negado.');
}

header('Content-Type: text/plain; charset=utf-8');
echo "=== NeuroOrganic Deploy ===\n";
echo "Data: " . date('d/m/Y H:i:s') . "\n";
echo "Dir:  $APP_DIR\n\n";

// ── Função helper ─────────────────────────────────────────────────────────────
function run($cmd, $label) {
    echo ">>> $label\n";
    $output = []; $code = 0;
    exec("cd " . escapeshellarg($APP_DIR) . " && $cmd 2>&1", $output, $code);
    echo implode("\n", $output) . "\n";
    echo "Exit: $code\n\n";
    return $code;
}

// ── Git pull ──────────────────────────────────────────────────────────────────
run('git pull origin main 2>&1', 'Git Pull');

// ── Criar venv se não existir ─────────────────────────────────────────────────
$action = $_GET['action'] ?? '';
if ($action === 'full' || $action === 'pip') {
    if (!file_exists($VENV_PIP)) {
        echo ">>> Criando venv (primeira vez)\n";
        $py = trim(shell_exec('which python3.9 || which python3.8 || which python3 2>/dev/null'));
        echo "Python encontrado: $py\n";
        run("$py -m venv venv 2>&1", 'Criar venv');
    }
    run("$VENV_PIP install --upgrade pip 2>&1", 'Upgrade pip');
    run("$VENV_PIP install -r requirements.txt 2>&1", 'Pip Install');
}

// ── Restart Passenger ─────────────────────────────────────────────────────────
@mkdir(dirname($RESTART), 0755, true);
file_put_contents($RESTART, date('Y-m-d H:i:s'));
echo ">>> Passenger restart\n";
echo file_exists($RESTART) ? "✓ tmp/restart.txt atualizado\n" : "✗ Falha ao criar restart.txt\n";

echo "\n=== Deploy concluído ===\n";
echo "Acesse o sistema para verificar.\n";
