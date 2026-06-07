"""
servicio_inven.py — Servicio de Inventario / Núcleo Transaccional (nombre en bus: "inven")
SGID · RedSalud

Operaciones:
  - descontar          : descuenta stock inmediato con BEGIN IMMEDIATE (Flujo A, Clinico)
  - registrar_entrada  : suma stock al recibir insumos en bodega (Bodega, Admin)
  - listar_movimientos : historial filtrable de movimientos (Bodega, Admin)

NOTA: El descuento por aprobación de pedido (Flujo B) lo ejecuta servicio_pedid.py
internamente dentro de su propia transacción, sin pasar por este servicio,
para mantener la atomicidad de la operación completa de aprobación.

Uso: python servicio_inven.py
"""

import json
from soa_lib import connect_to_bus, send_message, receive_message
from db import get_conn, ok, error, server_error

SERVICE_NAME   = "inven"
ROLES_CLINICO  = {"Clinico"}
ROLES_BODEGA   = {"Bodega", "Admin"}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_rol(conn, id_usuario: int):
    cur = conn.cursor()
    cur.execute("SELECT rol FROM usuarios WHERE id_usuario = ?", (id_usuario,))
    row = cur.fetchone()
    return row["rol"] if row else None


# ─── Lógica de negocio ───────────────────────────────────────────────────────

def handle_descontar(payload: dict) -> str:
    """
    Descuenta stock de un insumo de manera inmediata y atómica (Flujo A).

    Implementación del bloqueo para concurrencia:
    ─────────────────────────────────────────────
    1. BEGIN IMMEDIATE → SQLite adquiere un bloqueo exclusivo de escritura
       desde el inicio de la transacción. Con modo WAL, los lectores (SELECT
       sin transacción activa) pueden operar concurrentemente; solo los
       escritores se serializan.
    2. SELECT del stock actual → valor garantizado y bloqueado.
    3. Validación en Python: si stock < cantidad → ROLLBACK y error 400.
    4. UPDATE stock_actual = stock_actual - cantidad (determinístico, no hay
       posibilidad de race condition porque el bloqueo serializa los writers).
    5. INSERT en movimientos_stock con tipo SALIDA e id_solicitud NULL.
    6. COMMIT → libera el bloqueo.

    Campos requeridos: id_insumo (int), cantidad (int > 0), id_usuario (int)
    Roles permitidos: Clinico
    """
    id_insumo  = payload.get("id_insumo")
    cantidad   = payload.get("cantidad")
    id_usuario = payload.get("id_usuario")

    # ── Validación de campos ──────────────────────────────────────────────────
    if id_insumo is None or cantidad is None or id_usuario is None:
        return error("Faltan campos obligatorios: id_insumo, cantidad, id_usuario.")
    if not isinstance(id_insumo, int) or not isinstance(id_usuario, int):
        return error("'id_insumo' e 'id_usuario' deben ser enteros.")
    if not isinstance(cantidad, int) or cantidad <= 0:
        return error("La cantidad debe ser un entero mayor a 0.")

    conn = None
    try:
        conn = get_conn()

        # ── Verificar rol ─────────────────────────────────────────────────────
        rol = _get_rol(conn, id_usuario)
        if rol is None:
            return error(f"El usuario con id {id_usuario} no existe.")
        if rol not in ROLES_CLINICO:
            return error(
                f"El rol '{rol}' no tiene permiso para descontar stock directamente. "
                "Solo el rol 'Clinico' puede realizar consumos rápidos de box.",
                code=403
            )

        # ── BEGIN IMMEDIATE ───────────────────────────────────────────────────
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()

        # Verificar existencia del insumo (dentro del bloqueo)
        cur.execute(
            "SELECT id_insumo, nombre, stock_actual FROM insumos WHERE id_insumo = ?",
            (id_insumo,)
        )
        insumo = cur.fetchone()
        if insumo is None:
            conn.rollback()
            return error(f"El insumo con id {id_insumo} no existe en el catálogo.")

        stock_actual  = insumo["stock_actual"]
        nombre_insumo = insumo["nombre"]

        # Verificar stock suficiente (con el valor bloqueado)
        if stock_actual < cantidad:
            conn.rollback()
            return error(
                f"No hay stock suficiente (Solicitó {cantidad}, Quedan {stock_actual})"
            )

        # Descontar y registrar
        nuevo_stock = stock_actual - cantidad
        cur.execute(
            "UPDATE insumos SET stock_actual = ? WHERE id_insumo = ?",
            (nuevo_stock, id_insumo)
        )
        cur.execute("""
            INSERT INTO movimientos_stock
                (id_insumo, id_usuario, id_solicitud, tipo_movimiento, cantidad, observacion)
            VALUES (?, ?, NULL, 'SALIDA', ?, 'Consumo directo en box')
        """, (id_insumo, id_usuario, cantidad))

        conn.commit()

        print(f"[inven] SALIDA: '{nombre_insumo}' -{cantidad} → stock={nuevo_stock} "
              f"(usuario={id_usuario})")
        return ok(
            f"Stock descontado. Quedan {nuevo_stock}.",
            nuevo_stock=nuevo_stock
        )

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[inven] Error en descontar: {e}")
        return server_error()
    finally:
        if conn:
            conn.close()


def handle_registrar_entrada(payload: dict) -> str:
    """
    Registra el ingreso de insumos a bodega (reposición / compra).
    Incrementa stock_actual y registra el movimiento con tipo ENTRADA.

    Campos requeridos: id_insumo (int), cantidad (int > 0), id_usuario (int)
    Campos opcionales: observacion (str) — ej: 'Compra OC-2024-001'
    Roles permitidos: Bodega, Admin
    """
    id_insumo   = payload.get("id_insumo")
    cantidad    = payload.get("cantidad")
    id_usuario  = payload.get("id_usuario")
    observacion = payload.get("observacion", "Entrada de insumos")

    if id_insumo is None or cantidad is None or id_usuario is None:
        return error("Faltan campos obligatorios: id_insumo, cantidad, id_usuario.")
    if not isinstance(id_insumo, int) or not isinstance(id_usuario, int):
        return error("'id_insumo' e 'id_usuario' deben ser enteros.")
    if not isinstance(cantidad, int) or cantidad <= 0:
        return error("La cantidad debe ser un entero mayor a 0.")

    conn = None
    try:
        conn = get_conn()

        rol = _get_rol(conn, id_usuario)
        if rol is None:
            return error(f"El usuario con id {id_usuario} no existe.")
        if rol not in ROLES_BODEGA:
            return error(
                f"El rol '{rol}' no tiene permiso para registrar entradas de stock. "
                "Solo 'Bodega' o 'Admin'.",
                code=403
            )

        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()

        cur.execute(
            "SELECT id_insumo, nombre, stock_actual FROM insumos WHERE id_insumo = ?",
            (id_insumo,)
        )
        insumo = cur.fetchone()
        if insumo is None:
            conn.rollback()
            return error(f"El insumo con id {id_insumo} no existe en el catálogo.")

        nuevo_stock = insumo["stock_actual"] + cantidad
        cur.execute(
            "UPDATE insumos SET stock_actual = ? WHERE id_insumo = ?",
            (nuevo_stock, id_insumo)
        )
        cur.execute("""
            INSERT INTO movimientos_stock
                (id_insumo, id_usuario, id_solicitud, tipo_movimiento, cantidad, observacion)
            VALUES (?, ?, NULL, 'ENTRADA', ?, ?)
        """, (id_insumo, id_usuario, cantidad, observacion))

        conn.commit()

        print(f"[inven] ENTRADA: '{insumo['nombre']}' +{cantidad} → stock={nuevo_stock} "
              f"(usuario={id_usuario})")
        return ok(
            f"Entrada registrada. Stock de '{insumo['nombre']}': {nuevo_stock}.",
            nuevo_stock=nuevo_stock
        )

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[inven] Error en registrar_entrada: {e}")
        return server_error()
    finally:
        if conn:
            conn.close()


def handle_listar_movimientos(payload: dict) -> str:
    """
    Retorna el historial de movimientos con filtros opcionales.

    Campos requeridos: id_usuario (int) — para verificar rol
    Filtros opcionales:
      - id_insumo (int)    : filtrar por insumo específico
      - tipo (str)         : 'ENTRADA' o 'SALIDA'
      - limite (int)       : máximo de registros (default 100)
    Roles permitidos: Bodega, Admin
    """
    id_usuario = payload.get("id_usuario")
    id_insumo  = payload.get("id_insumo")
    tipo       = payload.get("tipo")
    limite     = payload.get("limite", 100)

    if not id_usuario or not isinstance(id_usuario, int):
        return error("El campo 'id_usuario' es obligatorio y debe ser un entero.")
    if tipo and tipo not in ("ENTRADA", "SALIDA"):
        return error("El campo 'tipo' debe ser 'ENTRADA' o 'SALIDA'.")
    if not isinstance(limite, int) or limite <= 0:
        return error("El campo 'limite' debe ser un entero mayor a 0.")

    conn = None
    try:
        conn = get_conn()

        rol = _get_rol(conn, id_usuario)
        if rol is None:
            return error(f"El usuario con id {id_usuario} no existe.")
        if rol not in ROLES_BODEGA:
            return error(
                "Solo los roles 'Bodega' y 'Admin' pueden consultar el historial.",
                code=403
            )

        cur = conn.cursor()

        # Construir query dinámica con filtros
        where_clauses = []
        params = []

        if id_insumo:
            where_clauses.append("m.id_insumo = ?")
            params.append(id_insumo)
        if tipo:
            where_clauses.append("m.tipo_movimiento = ?")
            params.append(tipo)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        params.append(limite)

        cur.execute(f"""
            SELECT m.id_movimiento, m.tipo_movimiento, m.cantidad,
                   m.fecha_movimiento, m.observacion,
                   i.nombre AS nombre_insumo, i.id_insumo,
                   u.nombre AS nombre_usuario, u.email AS email_usuario,
                   m.id_solicitud
            FROM movimientos_stock m
            JOIN insumos  i ON m.id_insumo  = i.id_insumo
            JOIN usuarios u ON m.id_usuario = u.id_usuario
            {where_sql}
            ORDER BY m.fecha_movimiento DESC
            LIMIT ?
        """, params)

        movimientos = [dict(row) for row in cur.fetchall()]
        return ok(
            f"{len(movimientos)} movimiento(s) encontrado(s).",
            movimientos=movimientos
        )

    except Exception as e:
        print(f"[inven] Error en listar_movimientos: {e}")
        return server_error()
    finally:
        if conn:
            conn.close()


# ─── Dispatcher ──────────────────────────────────────────────────────────────

def dispatch(payload_raw: str) -> str:
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        return error("El cuerpo de la petición no es JSON válido.", code=400)

    operacion = payload.get("operacion", "")
    ops = {
        "descontar":           handle_descontar,
        "registrar_entrada":   handle_registrar_entrada,
        "listar_movimientos":  handle_listar_movimientos,
    }
    handler = ops.get(operacion)
    if handler is None:
        return error(
            f"Operación desconocida: '{operacion}'. "
            f"Opciones: {', '.join(ops.keys())}.",
            code=400
        )
    return handler(payload)


# ─── Loop principal del servicio ─────────────────────────────────────────────

def main():
    sock = connect_to_bus()
    try:
        print(f"[{SERVICE_NAME}] Registrando servicio en el bus...")
        send_message(sock, "sinit", SERVICE_NAME)
        init_data = receive_message(sock)
        print(f"[{SERVICE_NAME}] Confirmación del bus: {init_data!r}")
        print(f"[{SERVICE_NAME}] Servicio listo para recibir peticiones.\n")

        while True:
            data = receive_message(sock)
            if not data:
                print(f"[{SERVICE_NAME}] Conexión cerrada por el bus.")
                break
            payload_raw = data[5:].decode("utf-8")
            print(f"[{SERVICE_NAME}] Petición recibida: {payload_raw}")
            respuesta = dispatch(payload_raw)
            print(f"[{SERVICE_NAME}] Respuesta enviada:  {respuesta}\n")
            send_message(sock, SERVICE_NAME, respuesta)

    except KeyboardInterrupt:
        print(f"\n[{SERVICE_NAME}] Detenido por el usuario.")
    except Exception as e:
        print(f"[{SERVICE_NAME}] Error inesperado: {e}")
    finally:
        print(f"[{SERVICE_NAME}] Cerrando socket.")
        sock.close()


if __name__ == "__main__":
    main()
