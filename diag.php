<?php
if (($_GET['token'] ?? '') !== 'neuro2026deploy') { die('403'); }
header('Content-Type: text/plain; charset=utf-8');

$DIR    = __DIR__;
$PYTHON = "$DIR/venv/bin/python3.9";

echo "=== Diagnóstico Python ===\n\n";

// Testa import do app
$script = <<<PY
import sys, os
sys.path.insert(0, '$DIR')
os.chdir('$DIR')

# Carrega .env
try:
    from dotenv import load_dotenv
    load_dotenv('$DIR/.env')
    print("dotenv: OK")
except Exception as e:
    print(f"dotenv: ERRO - {e}")

# Testa import do app
try:
    from app import app
    print("app import: OK")
except Exception as e:
    import traceback
    print("app import: ERRO")
    traceback.print_exc()
PY;

$tmp = tempnam('/tmp', 'diag_') . '.py';
file_put_contents($tmp, $script);
$out = shell_exec("cd $DIR && $PYTHON $tmp 2>&1");
unlink($tmp);

echo $out . "\n";
echo "=== Fim ===\n";
