"""
servicio_authe.py — Servicio de Autenticación (nombre en bus: "authe")
SGID · RedSalud

Operaciones:
  - login: valida credenciales y devuelve id_usuario + rol

Uso: python servicio_authe.py
"""

import json
import bcrypt
from soa_lib import connect_to_bus, send_message, receive_message
from db import get_conn, ok, error, server_error

SERVICE_NAME = "authe"


# ─── Lógica de negocio ───────────────────────────────────────────────────────

def handle_login(payload: dict) -> str:
    """
    Valida las credenciales de un usuario.

    Campos requeridos: user (email), pass
    Respuesta OK:  {status, code, msg, data: {id_usuario, rol}}
    Respuesta NK:  {status, code: 401, msg}
    """
    user_email = payload.get("user", "").strip()
    password   = payload.get("pass", "")

    if not user_email or not password:
        return error("Los campos 'user' y 'pass' son obligatorios.", code=400)

    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id_usuario, nombre, password_hash, rol FROM usuarios WHERE email = ?",
            (user_email,)
        )
        row = cur.fetchone()
        conn.close()
    except Exception as e:
        print(f"[authe] Error BD en login: {e}")
        return server_error()

    # Usuario no encontrado → mismo mensaje que contraseña incorrecta (seguridad)
    if row is None:
        return error("Credenciales incorrectas.", code=401)

    # Verificar contraseña con bcrypt
    password_ok = bcrypt.checkpw(password.encode(), row["password_hash"].encode())
    if not password_ok:
        return error("Credenciales incorrectas.", code=401)

    return ok(
        f"Bienvenido {user_email}",
        data={
            "id_usuario": row["id_usuario"],
            "rol":        row["rol"],
            "nombre":     row["nombre"]
        }
    )


# ─── Dispatcher ──────────────────────────────────────────────────────────────

ROLES_ADMIN = {"Admin"}


def handle_crear_usuario(payload: dict) -> str:
    id_solicitante = payload.get("id_usuario_admin")
    nombre   = payload.get("nombre", "").strip()
    email    = payload.get("email", "").strip()
    password = payload.get("pass", "")
    rol      = payload.get("rol", "")

    if not all([id_solicitante, nombre, email, password, rol]):
        return error("Faltan campos: id_usuario_admin, nombre, email, pass, rol.")
    if rol not in ("Clinico", "Bodega", "Admin"):
        return error("El campo 'rol' debe ser 'Clinico', 'Bodega' o 'Admin'.")

    try:
        conn = get_conn()
        rol_solicitante = None
        cur = conn.cursor()
        cur.execute("SELECT rol FROM usuarios WHERE id_usuario = ?", (id_solicitante,))
        row = cur.fetchone()
        if row:
            rol_solicitante = row["rol"]
        if rol_solicitante not in ROLES_ADMIN:
            conn.close()
            return error("Solo el rol 'Admin' puede crear usuarios.", code=403)

        cur.execute("SELECT id_usuario FROM usuarios WHERE email = ?", (email,))
        if cur.fetchone():
            conn.close()
            return error(f"Ya existe un usuario con el email '{email}'.")

        hashed = __import__("bcrypt").hashpw(password.encode(), __import__("bcrypt").gensalt()).decode()
        cur.execute(
            "INSERT INTO usuarios (nombre, email, password_hash, rol) VALUES (?,?,?,?)",
            (nombre, email, hashed, rol)
        )
        conn.commit()
        nuevo_id = cur.lastrowid
        conn.close()
        return ok(f"Usuario '{email}' creado correctamente.", data={"id_usuario": nuevo_id})
    except Exception as e:
        print(f"[authe] Error en crear_usuario: {e}")
        return server_error()


def handle_listar_usuarios(payload: dict) -> str:
    id_solicitante = payload.get("id_usuario_admin")
    if not id_solicitante:
        return error("El campo 'id_usuario_admin' es obligatorio.")

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT rol FROM usuarios WHERE id_usuario = ?", (id_solicitante,))
        row = cur.fetchone()
        if not row or row["rol"] not in ROLES_ADMIN:
            conn.close()
            return error("Solo el rol 'Admin' puede listar usuarios.", code=403)

        cur.execute("SELECT id_usuario, nombre, email, rol FROM usuarios ORDER BY nombre")
        usuarios = [dict(u) for u in cur.fetchall()]
        conn.close()
        return ok(f"{len(usuarios)} usuario(s) encontrado(s).", usuarios=usuarios)
    except Exception as e:
        print(f"[authe] Error en listar_usuarios: {e}")
        return server_error()


def handle_actualizar_usuario(payload: dict) -> str:
    id_solicitante = payload.get("id_usuario_admin")
    id_objetivo    = payload.get("id_usuario")
    nombre  = payload.get("nombre")
    rol     = payload.get("rol")
    password = payload.get("pass")

    if not id_solicitante or not id_objetivo:
        return error("Los campos 'id_usuario_admin' e 'id_usuario' son obligatorios.")
    if rol and rol not in ("Clinico", "Bodega", "Admin"):
        return error("El campo 'rol' debe ser 'Clinico', 'Bodega' o 'Admin'.")

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT rol FROM usuarios WHERE id_usuario = ?", (id_solicitante,))
        row = cur.fetchone()
        if not row or row["rol"] not in ROLES_ADMIN:
            conn.close()
            return error("Solo el rol 'Admin' puede actualizar usuarios.", code=403)

        cur.execute("SELECT id_usuario FROM usuarios WHERE id_usuario = ?", (id_objetivo,))
        if not cur.fetchone():
            conn.close()
            return error(f"El usuario con id {id_objetivo} no existe.")

        updates, params = [], []
        if nombre:
            updates.append("nombre = ?"); params.append(nombre)
        if rol:
            updates.append("rol = ?"); params.append(rol)
        if password:
            hashed = __import__("bcrypt").hashpw(password.encode(), __import__("bcrypt").gensalt()).decode()
            updates.append("password_hash = ?"); params.append(hashed)

        if not updates:
            conn.close()
            return error("Debe especificar al menos un campo a actualizar: nombre, rol o pass.")

        params.append(id_objetivo)
        cur.execute(f"UPDATE usuarios SET {', '.join(updates)} WHERE id_usuario = ?", params)
        conn.commit()
        conn.close()
        return ok(f"Usuario {id_objetivo} actualizado correctamente.")
    except Exception as e:
        print(f"[authe] Error en actualizar_usuario: {e}")
        return server_error()


def dispatch(payload_raw: str) -> str:
    """Recibe el JSON crudo, determina la operación y la ejecuta."""
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        return error("El cuerpo de la petición no es JSON válido.", code=400)

    operacion = payload.get("operacion", "")
    ops = {
        "login":              handle_login,
        "crear_usuario":      handle_crear_usuario,
        "listar_usuarios":    handle_listar_usuarios,
        "actualizar_usuario": handle_actualizar_usuario,
    }
    handler = ops.get(operacion)
    if handler is None:
        return error(
            f"Operación desconocida: '{operacion}'. Opciones: {', '.join(ops.keys())}.",
            code=400
        )
    return handler(payload)


# ─── Loop principal del servicio ─────────────────────────────────────────────

def main():
    sock = connect_to_bus()

    try:
        # 1. Registro en el bus
        print(f"[{SERVICE_NAME}] Registrando servicio en el bus...")
        send_message(sock, "sinit", SERVICE_NAME)

        init_data = receive_message(sock)
        print(f"[{SERVICE_NAME}] Confirmación del bus: {init_data!r}")
        print(f"[{SERVICE_NAME}] Servicio listo para recibir peticiones.\n")

        # 2. Bucle de atención
        while True:
            data = receive_message(sock)
            if not data:
                print(f"[{SERVICE_NAME}] Conexión cerrada por el bus.")
                break

            # Los primeros 5 bytes son el nombre del servicio que el bus añade;
            # el payload JSON viene a partir del byte 5.
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
