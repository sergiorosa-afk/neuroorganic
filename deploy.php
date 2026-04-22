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
