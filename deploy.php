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

// ── Pip install (só se requirements mudou) ────────────────────────────────────
$action = $_GET['action'] ?? '';
if ($action === 'full' || $action === 'pip') {
    run("$VENV_PIP install -r requirements.txt 2>&1", 'Pip Install');
}

// ── Restart Passenger ─────────────────────────────────────────────────────────
@mkdir(dirname($RESTART), 0755, true);
file_put_contents($RESTART, date('Y-m-d H:i:s'));
echo ">>> Passenger restart\n";
echo file_exists($RESTART) ? "✓ tmp/restart.txt atualizado\n" : "✗ Falha ao criar restart.txt\n";

echo "\n=== Deploy concluído ===\n";
echo "Acesse o sistema para verificar.\n";
