"""
servicio_pedid.py — Servicio de Gestión de Pedidos (nombre en bus: "pedid")
SGID · RedSalud

Operaciones:
  - crear_pedido      : crea solicitud + ítems en transacción atómica (Flujo B)
  - listar_pendientes : lista pedidos en estado Pendiente (Bodega/Admin)
  - listar_por_usuario: lista pedidos de un usuario (Clinico/Bodega/Admin)
  - aprobar_pedido    : aprueba pedido y descuenta stock en una sola transacción (Bodega)
  - rechazar_pedido   : rechaza pedido sin tocar stock (Bodega)

Uso: python servicio_pedid.py
"""

import json
from soa_lib import connect_to_bus, send_message, receive_message
from db import get_conn, ok, error, server_error

SERVICE_NAME = "pedid"

# Roles autorizados por operación
ROLES_CREAR     = {"Clinico"}
ROLES_BODEGA    = {"Bodega", "Admin"}
ROLES_VER       = {"Clinico", "Bodega", "Admin"}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_rol(conn, id_usuario: int):
    """Retorna el rol del usuario o None si no existe."""
    cur = conn.cursor()
    cur.execute("SELECT rol FROM usuarios WHERE id_usuario = ?", (id_usuario,))
    row = cur.fetchone()
    return row["rol"] if row else None


# ─── Lógica de negocio ───────────────────────────────────────────────────────

def handle_crear_pedido(payload: dict) -> str:
    """
    Crea una solicitud con sus ítems en una transacción atómica.

    Garantía: si la inserción de cualquier ítem falla (insumo inexistente,
    cantidad inválida), se hace ROLLBACK completo: la solicitud no queda
    a medias en la base de datos.

    Campos requeridos: id_usuario (int), items (list de {id_insumo, cantidad})
    Respuesta OK:  {status, code, msg}  — msg incluye el número de pedido
    """
    id_usuario = payload.get("id_usuario")
    items      = payload.get("items")

    if id_usuario is None:
        return error("El campo 'id_usuario' es obligatorio.")
    if not isinstance(id_usuario, int):
        return error("El campo 'id_usuario' debe ser un entero.")
    if not items or not isinstance(items, list):
        return error("El pedido debe contener al menos un ítem en el campo 'items'.")

    conn = None
    try:
        conn = get_conn()

        # ── Verificar usuario y rol ──────────────────────────────────────────
        rol = _get_rol(conn, id_usuario)
        if rol is None:
            return error(f"El usuario con id {id_usuario} no existe.")
        if rol not in ROLES_CREAR:
            return error(
                f"El rol '{rol}' no tiene permiso para crear pedidos. Solo rol 'Clinico'.",
                code=403
            )

        # ── BEGIN: transacción atómica ───────────────────────────────────────
        conn.execute("BEGIN")
        cur = conn.cursor()

        # 1. Insertar encabezado de la solicitud
        cur.execute(
            "INSERT INTO solicitudes (id_usuario, estado) VALUES (?, 'Pendiente')",
            (id_usuario,)
        )
        id_solicitud = cur.lastrowid

        # 2. Insertar cada ítem; si algo falla → ROLLBACK
        for i, item in enumerate(items):
            item_id_insumo = item.get("id_insumo")
            item_cantidad  = item.get("cantidad")

            # Validación de estructura del ítem
            if item_id_insumo is None or item_cantidad is None:
                conn.rollback()
                return error(f"El ítem #{i+1} debe tener 'id_insumo' y 'cantidad'.")
            if not isinstance(item_cantidad, int) or item_cantidad <= 0:
                conn.rollback()
                return error(f"La cantidad del ítem #{i+1} debe ser un entero mayor a 0.")

            # Verificar que el insumo exista en el catálogo
            cur.execute(
                "SELECT id_insumo FROM insumos WHERE id_insumo = ?",
                (item_id_insumo,)
            )
            if cur.fetchone() is None:
                conn.rollback()
                return error(
                    f"El id_insumo {item_id_insumo} (ítem #{i+1}) no existe en el catálogo."
                )

            cur.execute(
                "INSERT INTO detalle_solicitud (id_solicitud, id_insumo, cantidad) VALUES (?,?,?)",
                (id_solicitud, item_id_insumo, item_cantidad)
            )

        conn.commit()
        print(f"[pedid] Pedido #{id_solicitud} creado por usuario {id_usuario} "
              f"con {len(items)} ítem(s).")
        return ok(f"Pedido N° {id_solicitud} creado (Pendiente)")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[pedid] Error en crear_pedido: {e}")
        return server_error()
    finally:
        if conn:
            conn.close()


def handle_listar_pendientes(payload: dict) -> str:
    """
    Retorna todas las solicitudes en estado 'Pendiente' con sus ítems.
    Solo accesible para roles Bodega y Admin.

    Campos requeridos: id_usuario (int) — para verificar el rol
    """
    id_usuario = payload.get("id_usuario")
    if id_usuario is None or not isinstance(id_usuario, int):
        return error("El campo 'id_usuario' es obligatorio y debe ser un entero.")

    conn = None
    try:
        conn = get_conn()
        rol = _get_rol(conn, id_usuario)
        if rol is None:
            return error(f"El usuario con id {id_usuario} no existe.")
        if rol not in ROLES_BODEGA:
            return error(
                "Solo los roles 'Bodega' y 'Admin' pueden listar pedidos pendientes.",
                code=403
            )

        cur = conn.cursor()

        # Obtener solicitudes pendientes con datos del solicitante
        cur.execute("""
            SELECT s.id_solicitud, s.fecha_creacion, s.estado,
                   u.nombre AS nombre_solicitante, u.email AS email_solicitante
            FROM solicitudes s
            JOIN usuarios u ON s.id_usuario = u.id_usuario
            WHERE s.estado = 'Pendiente'
            ORDER BY s.fecha_creacion ASC
        """)
        solicitudes = cur.fetchall()

        resultado = []
        for sol in solicitudes:
            # Obtener ítems de cada solicitud
            cur.execute("""
                SELECT d.id_insumo, i.nombre AS nombre_insumo,
                       d.cantidad, i.stock_actual AS stock_disponible
                FROM detalle_solicitud d
                JOIN insumos i ON d.id_insumo = i.id_insumo
                WHERE d.id_solicitud = ?
            """, (sol["id_solicitud"],))
            items = [dict(row) for row in cur.fetchall()]

            resultado.append({
                "id_solicitud":      sol["id_solicitud"],
                "fecha_creacion":    sol["fecha_creacion"],
                "estado":            sol["estado"],
                "solicitante":       sol["nombre_solicitante"],
                "email_solicitante": sol["email_solicitante"],
                "items":             items
            })

        return ok(f"{len(resultado)} solicitud(es) pendiente(s).", solicitudes=resultado)

    except Exception as e:
        print(f"[pedid] Error en listar_pendientes: {e}")
        return server_error()
    finally:
        if conn:
            conn.close()


def handle_listar_por_usuario(payload: dict) -> str:
    """
    Retorna los pedidos de un usuario específico con su estado.
    Accesible para todos los roles (el Clínico solo ve sus propios pedidos).

    Campos requeridos: id_usuario (int)
    """
    id_usuario = payload.get("id_usuario")
    if id_usuario is None or not isinstance(id_usuario, int):
        return error("El campo 'id_usuario' es obligatorio y debe ser un entero.")

    conn = None
    try:
        conn = get_conn()
        if _get_rol(conn, id_usuario) is None:
            return error(f"El usuario con id {id_usuario} no existe.")

        cur = conn.cursor()
        cur.execute("""
            SELECT s.id_solicitud, s.fecha_creacion, s.estado
            FROM solicitudes s
            WHERE s.id_usuario = ?
            ORDER BY s.fecha_creacion DESC
        """, (id_usuario,))
        solicitudes = cur.fetchall()

        resultado = []
        for sol in solicitudes:
            cur.execute("""
                SELECT d.id_insumo, i.nombre AS nombre_insumo, d.cantidad
                FROM detalle_solicitud d
                JOIN insumos i ON d.id_insumo = i.id_insumo
                WHERE d.id_solicitud = ?
            """, (sol["id_solicitud"],))
            items = [dict(row) for row in cur.fetchall()]

            resultado.append({
                "id_solicitud":   sol["id_solicitud"],
                "fecha_creacion": sol["fecha_creacion"],
                "estado":         sol["estado"],
                "items":          items
            })

        return ok(f"{len(resultado)} pedido(s) encontrado(s).", solicitudes=resultado)

    except Exception as e:
        print(f"[pedid] Error en listar_por_usuario: {e}")
        return server_error()
    finally:
        if conn:
            conn.close()


def handle_aprobar_pedido(payload: dict) -> str:
    """
    Aprueba un pedido y descuenta el stock de cada ítem en la MISMA transacción.

    Garantía de atomicidad:
    1. BEGIN IMMEDIATE → bloqueo exclusivo de escritura.
    2. Verificar que la solicitud existe y está en estado 'Pendiente'.
    3. Para cada ítem: verificar stock suficiente (si alguno falla → ROLLBACK).
    4. Para cada ítem: UPDATE stock_actual e INSERT en movimientos_stock.
    5. UPDATE solicitudes SET estado = 'Aprobada'.
    6. COMMIT → libera el bloqueo.

    El cliente de bodega NO debe llamar a inven después de aprobar.

    Campos requeridos: id_solicitud (int), id_usuario_bodega (int)
    """
    id_solicitud    = payload.get("id_solicitud")
    id_usuario_bod  = payload.get("id_usuario_bodega")

    if id_solicitud is None or id_usuario_bod is None:
        return error("Los campos 'id_solicitud' e 'id_usuario_bodega' son obligatorios.")
    if not isinstance(id_solicitud, int) or not isinstance(id_usuario_bod, int):
        return error("'id_solicitud' e 'id_usuario_bodega' deben ser enteros.")

    conn = None
    try:
        conn = get_conn()

        # ── Verificar rol del usuario de bodega ──────────────────────────────
        rol = _get_rol(conn, id_usuario_bod)
        if rol is None:
            return error(f"El usuario con id {id_usuario_bod} no existe.")
        if rol not in ROLES_BODEGA:
            return error(
                f"El rol '{rol}' no tiene permiso para aprobar pedidos. Solo 'Bodega' o 'Admin'.",
                code=403
            )

        # ── BEGIN IMMEDIATE: bloqueo exclusivo ───────────────────────────────
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()

        # Verificar que la solicitud existe y está Pendiente
        cur.execute(
            "SELECT id_solicitud, estado FROM solicitudes WHERE id_solicitud = ?",
            (id_solicitud,)
        )
        solicitud = cur.fetchone()

        if solicitud is None:
            conn.rollback()
            return error(f"La solicitud N° {id_solicitud} no existe.")
        if solicitud["estado"] != "Pendiente":
            conn.rollback()
            return error(
                f"La solicitud N° {id_solicitud} no está en estado Pendiente "
                f"(estado actual: {solicitud['estado']})."
            )

        # Obtener todos los ítems del pedido
        cur.execute("""
            SELECT d.id_insumo, d.cantidad, i.nombre, i.stock_actual
            FROM detalle_solicitud d
            JOIN insumos i ON d.id_insumo = i.id_insumo
            WHERE d.id_solicitud = ?
        """, (id_solicitud,))
        items = cur.fetchall()

        # ── Fase 1: verificar stock de TODOS los ítems antes de modificar nada
        for item in items:
            if item["stock_actual"] < item["cantidad"]:
                conn.rollback()
                return error(
                    f"No se puede aprobar. Falta stock para el ítem "
                    f"'{item['nombre']}' (ID {item['id_insumo']}): "
                    f"se necesitan {item['cantidad']}, hay {item['stock_actual']}."
                )

        # ── Fase 2: aplicar descuentos y registrar movimientos ───────────────
        for item in items:
            nuevo_stock = item["stock_actual"] - item["cantidad"]

            cur.execute(
                "UPDATE insumos SET stock_actual = ? WHERE id_insumo = ?",
                (nuevo_stock, item["id_insumo"])
            )
            cur.execute("""
                INSERT INTO movimientos_stock
                    (id_insumo, id_usuario, id_solicitud, tipo_movimiento, cantidad, observacion)
                VALUES (?, ?, ?, 'SALIDA', ?, ?)
            """, (
                item["id_insumo"],
                id_usuario_bod,
                id_solicitud,
                item["cantidad"],
                f"Aprobación pedido N° {id_solicitud}"
            ))

        # ── Fase 3: actualizar estado de la solicitud ────────────────────────
        cur.execute(
            "UPDATE solicitudes SET estado = 'Aprobada' WHERE id_solicitud = ?",
            (id_solicitud,)
        )

        conn.commit()
        print(f"[pedid] Pedido #{id_solicitud} aprobado por usuario {id_usuario_bod}. "
              f"Stock descontado para {len(items)} ítem(s).")
        return ok(f"Pedido N° {id_solicitud} aprobado. Stock descontado correctamente.")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[pedid] Error en aprobar_pedido: {e}")
        return server_error()
    finally:
        if conn:
            conn.close()


def handle_rechazar_pedido(payload: dict) -> str:
    """
    Rechaza un pedido sin modificar el stock.

    Campos requeridos: id_solicitud (int), id_usuario_bodega (int)
    """
    id_solicitud   = payload.get("id_solicitud")
    id_usuario_bod = payload.get("id_usuario_bodega")

    if id_solicitud is None or id_usuario_bod is None:
        return error("Los campos 'id_solicitud' e 'id_usuario_bodega' son obligatorios.")
    if not isinstance(id_solicitud, int) or not isinstance(id_usuario_bod, int):
        return error("'id_solicitud' e 'id_usuario_bodega' deben ser enteros.")

    conn = None
    try:
        conn = get_conn()

        rol = _get_rol(conn, id_usuario_bod)
        if rol is None:
            return error(f"El usuario con id {id_usuario_bod} no existe.")
        if rol not in ROLES_BODEGA:
            return error(
                f"El rol '{rol}' no tiene permiso para rechazar pedidos.",
                code=403
            )

        cur = conn.cursor()
        cur.execute(
            "SELECT estado FROM solicitudes WHERE id_solicitud = ?",
            (id_solicitud,)
        )
        solicitud = cur.fetchone()

        if solicitud is None:
            return error(f"La solicitud N° {id_solicitud} no existe.")
        if solicitud["estado"] != "Pendiente":
            return error(
                f"La solicitud N° {id_solicitud} no está en estado Pendiente "
                f"(estado actual: {solicitud['estado']})."
            )

        cur.execute(
            "UPDATE solicitudes SET estado = 'Rechazada' WHERE id_solicitud = ?",
            (id_solicitud,)
        )
        conn.commit()

        print(f"[pedid] Pedido #{id_solicitud} rechazado por usuario {id_usuario_bod}.")
        return ok(f"Pedido N° {id_solicitud} rechazado correctamente.")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[pedid] Error en rechazar_pedido: {e}")
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
        "crear_pedido":      handle_crear_pedido,
        "listar_pendientes": handle_listar_pendientes,
        "listar_por_usuario":handle_listar_por_usuario,
        "aprobar_pedido":    handle_aprobar_pedido,
        "rechazar_pedido":   handle_rechazar_pedido,
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
