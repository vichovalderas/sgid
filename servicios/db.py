"""
db.py — Helpers de base de datos compartidos por todos los servicios.
Provee conexión thread-safe a SQLite y funciones de respuesta estandarizadas.
"""

import sqlite3
import json

DB_PATH = "sgid.db"


def get_conn():
    """
    Abre y retorna una conexión SQLite con foreign keys activadas.
    check_same_thread=False permite usar la misma conexión desde el thread
    del servicio (que no es el thread principal).
    isolation_level=None → autocommit desactivado; usamos BEGIN/COMMIT manual
    para las transacciones críticas.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row          # permite acceder columnas por nombre
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")   # WAL: mejor concurrencia lecturas/escrituras
    return conn


# ─── Helpers de respuesta ─────────────────────────────────────────────────────

def ok(msg: str, **extra) -> str:
    """Respuesta de éxito serializada a JSON. Acepta campos extra."""
    return json.dumps({"status": "OK", "code": 200, "msg": msg, **extra})


def error(msg: str, code: int = 400) -> str:
    """Respuesta de error serializada a JSON."""
    return json.dumps({"status": "NK", "code": code, "msg": msg})


def server_error(msg: str = "Error interno del servidor.") -> str:
    return error(msg, code=500)
