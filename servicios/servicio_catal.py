"""
servicio_catal.py — Servicio de Catálogo de Insumos (nombre en bus: "catal")
SGID · RedSalud

Operaciones:
  - listar_todos    : retorna catálogo completo con indicador bajo_critico (todos los roles)
  - crear_insumo    : registra nuevo insumo (Bodega, Admin)
  - actualizar_insumo: modifica datos de un insumo existente (Bodega, Admin)

Uso: python servicio_catal.py
"""

import json
from soa_lib import connect_to_bus, send_message, receive_message
from db import get_conn, ok, error, server_error

SERVICE_NAME = "catal"
ROLES_ESCRITURA = {"Bodega", "Admin"}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_rol(conn, id_usuario: int):
    cur = conn.cursor()
    cur.execute("SELECT rol FROM usuarios WHERE id_usuario = ?", (id_usuario,))
    row = cur.fetchone()
    return row["rol"] if row else None


# ─── Lógica de negocio ───────────────────────────────────────────────────────

def handle_listar_todos(payload: dict = None) -> str:
    """
    Retorna el catálogo completo de insumos ordenados por nombre.
    El campo calculado bajo_critico = (stock_actual <= stock_critico).
    Accesible para todos los roles (no requiere id_usuario).

    Respuesta OK: {status, code, msg, insumos: [...]}
    """
    payload = payload or {}
    limite = payload.get("limite")
    offset = payload.get("offset", 0)

    if limite is not None and (not isinstance(limite, int) or limite <= 0):
        return error("El campo 'limite' debe ser un entero mayor a 0.")
    if not isinstance(offset, int) or offset < 0:
        return error("El campo 'offset' debe ser un entero >= 0.")

    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("SELECT COUNT(*) AS total FROM insumos")
        total = cur.fetchone()["total"]

        sql = """
            SELECT id_insumo, nombre, stock_actual AS stock,
                   stock_critico, unidad_medida, codigo_interno
            FROM insumos
            ORDER BY nombre ASC
        """
        params = []
        if limite is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limite, offset])

        cur.execute(sql, params)
        filas = cur.fetchall()
        conn.close()
    except Exception as e:
        print(f"[catal] Error BD en listar_todos: {e}")
        return server_error()

    insumos = [
        {
            "id_insumo":      fila["id_insumo"],
            "nombre":         fila["nombre"],
            "stock":          fila["stock"],
            "stock_critico":  fila["stock_critico"],
            "unidad_medida":  fila["unidad_medida"],
            "codigo_interno": fila["codigo_interno"],
            # Campo calculado: el cliente debe resaltar estos insumos en la UI
            "bajo_critico":   fila["stock"] <= fila["stock_critico"]
        }
        for fila in filas
    ]

    return ok("Catálogo cargado", insumos=insumos, total=total, offset=offset, limite=limite)


def handle_crear_insumo(payload: dict) -> str:
    """
    Registra un nuevo insumo en el catálogo.
    Valida que el codigo_interno no exista previamente (UNIQUE en BD).
    No permite modificar stock_actual directamente (eso es responsabilidad de inven).

    Campos requeridos: id_usuario (int), codigo_interno, nombre
    Campos opcionales: stock_actual (default 0), stock_critico (default 10),
                       unidad_medida (default 'unidad')
    Roles permitidos: Bodega, Admin
    """
    id_usuario      = payload.get("id_usuario")
    codigo_interno  = payload.get("codigo_interno", "").strip()
    nombre          = payload.get("nombre", "").strip()
    stock_actual    = payload.get("stock_actual", 0)
    stock_critico   = payload.get("stock_critico", 10)
    unidad_medida   = payload.get("unidad_medida", "unidad").strip()

    if not id_usuario or not isinstance(id_usuario, int):
        return error("El campo 'id_usuario' es obligatorio y debe ser un entero.")
    if not codigo_interno:
        return error("El campo 'codigo_interno' es obligatorio.")
    if not nombre:
        return error("El campo 'nombre' es obligatorio.")
    if not isinstance(stock_actual, int) or stock_actual < 0:
        return error("El campo 'stock_actual' debe ser un entero >= 0.")
    if not isinstance(stock_critico, int) or stock_critico < 0:
        return error("El campo 'stock_critico' debe ser un entero >= 0.")

    conn = None
    try:
        conn = get_conn()

        # Verificar rol
        rol = _get_rol(conn, id_usuario)
        if rol is None:
            return error(f"El usuario con id {id_usuario} no existe.")
        if rol not in ROLES_ESCRITURA:
            return error(
                f"El rol '{rol}' no tiene permiso para crear insumos. Solo 'Bodega' o 'Admin'.",
                code=403
            )

        cur = conn.cursor()

        # Verificar unicidad del código interno
        cur.execute(
            "SELECT id_insumo FROM insumos WHERE codigo_interno = ?",
            (codigo_interno,)
        )
        if cur.fetchone():
            return error(f"Ya existe un insumo con el código interno '{codigo_interno}'.")

        cur.execute("""
            INSERT INTO insumos (codigo_interno, nombre, stock_actual, stock_critico, unidad_medida)
            VALUES (?, ?, ?, ?, ?)
        """, (codigo_interno, nombre, stock_actual, stock_critico, unidad_medida))
        conn.commit()
        nuevo_id = cur.lastrowid

        print(f"[catal] Insumo creado: id={nuevo_id}, codigo={codigo_interno}, nombre={nombre}")
        return ok(
            f"Insumo '{nombre}' creado correctamente.",
            data={"id_insumo": nuevo_id, "codigo_interno": codigo_interno}
        )

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[catal] Error en crear_insumo: {e}")
        return server_error()
    finally:
        if conn:
            conn.close()


def handle_actualizar_insumo(payload: dict) -> str:
    """
    Modifica los datos de un insumo existente.
    NO permite modificar stock_actual (eso ocurre exclusivamente a través de inven).
    Campos modificables: nombre, stock_critico, unidad_medida.

    Campos requeridos: id_usuario (int), id_insumo (int)
    Roles permitidos: Bodega, Admin
    """
    id_usuario = payload.get("id_usuario")
    id_insumo  = payload.get("id_insumo")
    nombre         = payload.get("nombre")
    stock_critico  = payload.get("stock_critico")
    unidad_medida  = payload.get("unidad_medida")

    if not id_usuario or not isinstance(id_usuario, int):
        return error("El campo 'id_usuario' es obligatorio y debe ser un entero.")
    if not id_insumo or not isinstance(id_insumo, int):
        return error("El campo 'id_insumo' es obligatorio y debe ser un entero.")

    # Detectar si intentan modificar stock_actual directamente
    if "stock_actual" in payload:
        return error(
            "No se permite modificar 'stock_actual' directamente desde el catálogo. "
            "Use el servicio 'inven' para registrar movimientos de stock."
        )

    conn = None
    try:
        conn = get_conn()

        rol = _get_rol(conn, id_usuario)
        if rol is None:
            return error(f"El usuario con id {id_usuario} no existe.")
        if rol not in ROLES_ESCRITURA:
            return error(
                f"El rol '{rol}' no tiene permiso para actualizar insumos.",
                code=403
            )

        cur = conn.cursor()
        cur.execute("SELECT id_insumo FROM insumos WHERE id_insumo = ?", (id_insumo,))
        if not cur.fetchone():
            return error(f"El insumo con id {id_insumo} no existe.")

        updates, params = [], []
        if nombre is not None:
            if not isinstance(nombre, str) or not nombre.strip():
                return error("El campo 'nombre' no puede estar vacío.")
            updates.append("nombre = ?"); params.append(nombre.strip())
        if stock_critico is not None:
            if not isinstance(stock_critico, int) or stock_critico < 0:
                return error("El campo 'stock_critico' debe ser un entero >= 0.")
            updates.append("stock_critico = ?"); params.append(stock_critico)
        if unidad_medida is not None:
            if not isinstance(unidad_medida, str) or not unidad_medida.strip():
                return error("El campo 'unidad_medida' no puede estar vacío.")
            updates.append("unidad_medida = ?"); params.append(unidad_medida.strip())

        if not updates:
            return error(
                "Debe especificar al menos un campo a actualizar: "
                "nombre, stock_critico o unidad_medida."
            )

        params.append(id_insumo)
        cur.execute(
            f"UPDATE insumos SET {', '.join(updates)} WHERE id_insumo = ?",
            params
        )
        conn.commit()

        print(f"[catal] Insumo {id_insumo} actualizado: {updates}")
        return ok(f"Insumo {id_insumo} actualizado correctamente.")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[catal] Error en actualizar_insumo: {e}")
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
        "listar_todos":      handle_listar_todos,
        "crear_insumo":      handle_crear_insumo,
        "actualizar_insumo": handle_actualizar_insumo,
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
