<?php
// Ponto de entrada do deploy via browser.
// Fica em public/ para ser servido pelo Apache (fora do Passenger WSGI).
// O deploy.php real está na raiz do projeto — __DIR__ lá resolve corretamente.
include dirname(__DIR__) . '/deploy.php';
