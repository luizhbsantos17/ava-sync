#!/usr/bin/env bash
# Adiciona ao crontab: 07:10 e 19:10 todos os dias
DIR="$(cd "$(dirname "$0")/.." && pwd)"
LINHA="10 7,19 * * * cd \"$DIR\" && python3 -m avasync tudo >> \"$DIR/agendador_saida.log\" 2>&1"
( crontab -l 2>/dev/null | grep -v "avasync tudo"; echo "$LINHA" ) | crontab -
echo "Agendado: $LINHA"
