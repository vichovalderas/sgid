#!/bin/bash
# start_services.sh — Levanta todos los servicios SGID en terminales separadas
# Uso: bash start_services.sh
#
# Requisito previo: el bus ESB debe estar corriendo en localhost:5000
#   docker run -d -p 5000:5000 jrgiadach/soabus:v1

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$SCRIPT_DIR/sgid.db"

echo "═══════════════════════════════════════════════════"
echo "  SGID — Sistema de Gestión de Insumos Dentales"
echo "  RedSalud · Arranque de Servicios SOA"
echo "═══════════════════════════════════════════════════"
echo ""

# ── 1. Verificar base de datos ───────────────────────────────────────────────
if [ ! -f "$DB" ]; then
    echo "[init] Base de datos no encontrada. Inicializando..."
    cd "$SCRIPT_DIR"
    python3 init_db.py
    echo ""
fi

# ── 2. Verificar que el bus está disponible ──────────────────────────────────
echo "[check] Verificando conexión al bus ESB (localhost:5000)..."
if ! python3 -c "
import socket, sys
try:
    s = socket.create_connection(('localhost', 5000), timeout=2)
    s.close()
    print('[check] Bus ESB disponible.')
except Exception:
    print('[ERROR] No se puede conectar al bus en localhost:5000')
    print('        Ejecuta: docker run -d -p 5000:5000 jrgiadach/soabus:v1')
    sys.exit(1)
"; then
    exit 1
fi

echo ""
echo "[start] Levantando servicios..."
echo "        Cada servicio se ejecuta en segundo plano."
echo "        Logs en: sgid_authe.log, sgid_catal.log, sgid_inven.log, sgid_pedid.log"
echo ""

cd "$SCRIPT_DIR"

# ── 3. Levantar los 4 servicios ──────────────────────────────────────────────
nohup python3 -u servicio_authe.py > sgid_authe.log 2>&1 &
PID_AUTHE=$!
echo "  [authe] PID $PID_AUTHE → sgid_authe.log"
sleep 0.5

nohup python3 -u servicio_catal.py > sgid_catal.log 2>&1 &
PID_CATAL=$!
echo "  [catal] PID $PID_CATAL → sgid_catal.log"
sleep 0.5

nohup python3 -u servicio_inven.py > sgid_inven.log 2>&1 &
PID_INVEN=$!
echo "  [inven] PID $PID_INVEN → sgid_inven.log"
sleep 0.5

nohup python3 -u servicio_pedid.py > sgid_pedid.log 2>&1 &
PID_PEDID=$!
echo "  [pedid] PID $PID_PEDID → sgid_pedid.log"
sleep 1

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Todos los servicios levantados."
echo ""
echo "  Para detener todos:"
echo "    kill $PID_AUTHE $PID_CATAL $PID_INVEN $PID_PEDID"
echo ""
echo "  Para ver logs en tiempo real:"
echo "    tail -f sgid_authe.log sgid_catal.log sgid_inven.log sgid_pedid.log"
echo "═══════════════════════════════════════════════════"
echo ""
echo "PIDs: authe=$PID_AUTHE catal=$PID_CATAL inven=$PID_INVEN pedid=$PID_PEDID" > sgid_pids.txt
echo "[ok] PIDs guardados en sgid_pids.txt"
