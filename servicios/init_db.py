"""
init_db.py — Inicialización de la base de datos SGID
Crea las tablas y carga datos de prueba.
Ejecutar UNA VEZ antes de levantar los servicios.

Uso: python init_db.py
"""

import sqlite3
import bcrypt
import os

DB_PATH = "sgid.db"


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init():
    # Borrar base anterior si existe (para empezar limpio en desarrollo)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"[init_db] Base anterior eliminada.")

    conn = get_conn()
    cur = conn.cursor()

    # ─── PRAGMA: integridad referencial ───────────────────────────────────────
    cur.execute("PRAGMA foreign_keys = ON")

    # ─── TABLA: usuarios ──────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE usuarios (
            id_usuario   INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre       TEXT    NOT NULL,
            email        TEXT    UNIQUE NOT NULL,
            password_hash TEXT   NOT NULL,
            rol          TEXT    NOT NULL CHECK(rol IN ('Clinico', 'Bodega', 'Admin'))
        )
    """)

    # ─── TABLA: insumos ───────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE insumos (
            id_insumo       INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_interno  TEXT    UNIQUE NOT NULL,
            nombre          TEXT    NOT NULL,
            stock_actual    INTEGER NOT NULL DEFAULT 0 CHECK(stock_actual >= 0),
            stock_critico   INTEGER NOT NULL DEFAULT 10,
            unidad_medida   TEXT    NOT NULL DEFAULT 'unidad'
        )
    """)

    # ─── TABLA: solicitudes ───────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE solicitudes (
            id_solicitud   INTEGER PRIMARY KEY AUTOINCREMENT,
            id_usuario     INTEGER NOT NULL REFERENCES usuarios(id_usuario),
            fecha_creacion TEXT    NOT NULL DEFAULT (datetime('now')),
            estado         TEXT    NOT NULL DEFAULT 'Pendiente'
                               CHECK(estado IN ('Pendiente', 'Aprobada', 'Rechazada'))
        )
    """)

    # ─── TABLA: detalle_solicitud ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE detalle_solicitud (
            id_detalle   INTEGER PRIMARY KEY AUTOINCREMENT,
            id_solicitud INTEGER NOT NULL REFERENCES solicitudes(id_solicitud),
            id_insumo    INTEGER NOT NULL REFERENCES insumos(id_insumo),
            cantidad     INTEGER NOT NULL CHECK(cantidad > 0)
        )
    """)

    # ─── TABLA: movimientos_stock ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE movimientos_stock (
            id_movimiento   INTEGER PRIMARY KEY AUTOINCREMENT,
            id_insumo       INTEGER NOT NULL REFERENCES insumos(id_insumo),
            id_usuario      INTEGER NOT NULL REFERENCES usuarios(id_usuario),
            id_solicitud    INTEGER REFERENCES solicitudes(id_solicitud),
            tipo_movimiento TEXT    NOT NULL CHECK(tipo_movimiento IN ('ENTRADA', 'SALIDA')),
            cantidad        INTEGER NOT NULL CHECK(cantidad > 0),
            fecha_movimiento TEXT   NOT NULL DEFAULT (datetime('now')),
            observacion     TEXT
        )
    """)

    conn.commit()
    print("[init_db] Tablas creadas.")

    # ─── DATOS DE PRUEBA ──────────────────────────────────────────────────────

    # Usuarios (contraseña = nombre de usuario para testing)
    usuarios = [
        ("Juan Pérez",    "juan.perez",    "clave123",    "Clinico"),
        ("María González","maria.gonzalez","clave123",    "Clinico"),
        ("Pedro Bodega",  "pedro.bodega",  "bodega2024",  "Bodega"),
        ("Admin Sistema", "admin",         "admin2024",   "Admin"),
    ]
    for nombre, email, clave, rol in usuarios:
        hashed = bcrypt.hashpw(clave.encode(), bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO usuarios (nombre, email, password_hash, rol) VALUES (?,?,?,?)",
            (nombre, email, hashed, rol)
        )

    # Insumos dentales con stock variado
    insumos = [
        ("INS-001", "Jeringa 5ml",              100, 20, "unidad"),
        ("INS-002", "Guantes nitrilo (caja)",    50,  10, "caja"),
        ("INS-003", "Mascarilla quirúrgica",      30,  15, "unidad"),
        ("INS-004", "Algodón dental (rollo)",     80,  10, "rollo"),
        ("INS-005", "Anestesia Lidocaína 2%",     25,   5, "cartucho"),
        ("INS-006", "Hilo dental profesional",    60,  10, "rollo"),
        ("INS-007", "Eyector de saliva",           0,   5, "unidad"),  # sin stock
        ("INS-008", "Babero desechable (100u)",   15,  20, "paquete"),  # bajo stock crítico
        ("INS-009", "Explorador dental",          40,   5, "unidad"),
        ("INS-010", "Cemento de ionómero",        12,   8, "frasco"),
    ]
    for row in insumos:
        cur.execute(
            "INSERT INTO insumos (codigo_interno, nombre, stock_actual, stock_critico, unidad_medida) VALUES (?,?,?,?,?)",
            row
        )

    conn.commit()
    conn.close()

    print("[init_db] Datos de prueba cargados.")
    print()
    print("  Usuarios de prueba:")
    print("  ─────────────────────────────────────────────────────")
    print("  email               | contraseña  | rol")
    print("  ─────────────────────────────────────────────────────")
    for nombre, email, clave, rol in usuarios:
        print(f"  {email:<20}| {clave:<12}| {rol}")
    print()
    print("[init_db] Base de datos lista en:", os.path.abspath(DB_PATH))


if __name__ == "__main__":
    init()
