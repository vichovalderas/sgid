"""
cliente_authe.py — Cliente interactivo del servicio de Autenticación
SGID · RedSalud

Operaciones disponibles:
  1. login
  2. crear_usuario   (requiere Admin)
  3. listar_usuarios (requiere Admin)
  4. actualizar_usuario (requiere Admin)

Uso: python cliente_authe.py
"""

import json
from soa_lib import connect_to_bus, send_message, receive_message

SERVICIO = "authe"

# ─── Helper de comunicación ───────────────────────────────────────────────────

def llamar(payload: dict) -> dict:
    """Abre conexión, envía, recibe y cierra. Una conexión por llamada.
    
    El bus devuelve: SSSSSRR{json}
      SSSSS = nombre del servicio (5 bytes)
      RR    = resultado del bus, "OK" o "NK" (2 bytes)
      {json} = respuesta del servicio
    En total hay que saltar 7 bytes para llegar al JSON.
    """
    sock = connect_to_bus()
    try:
        send_message(sock, SERVICIO, json.dumps(payload))
        raw = receive_message(sock)
        if not raw:
            return {"status": "NK", "code": 500, "msg": "Sin respuesta del bus."}
        try:
            # Saltar 7 bytes: 5 del nombre del servicio + 2 del resultado del bus (OK/NK)
            return json.loads(raw[7:].decode())
        except json.JSONDecodeError as e:
            print(f"[DEBUG] raw recibido: {raw!r}")
            return {"status": "NK", "code": 500, "msg": f"Respuesta del bus no es JSON válido: {e}"}
    except OSError as e:
        return {"status": "NK", "code": 500, "msg": f"Error de conexión al bus: {e}"}
    finally:
        sock.close()

def mostrar(r: dict):
    estado = "✓" if r["status"] == "OK" else "✗"
    print(f"\n  {estado} [{r['code']}] {r['msg']}")

def pedir(campo: str, oculto=False) -> str:
    if oculto:
        import getpass
        return getpass.getpass(f"  {campo}: ")
    return input(f"  {campo}: ").strip()

def separador():
    print("  " + "─" * 46)

# ─── Operaciones ──────────────────────────────────────────────────────────────

def op_login():
    print("\n─ LOGIN ──────────────────────────────────────")
    user = pedir("Email (ej: juan.perez)")
    pw   = pedir("Contraseña", oculto=True)
    r = llamar({"operacion": "login", "user": user, "pass": pw})
    mostrar(r)
    if r["status"] == "OK":
        d = r["data"]
        print(f"  Nombre  : {d['nombre']}")
        print(f"  Rol     : {d['rol']}")
        print(f"  ID      : {d['id_usuario']}")
        print(f"\n  ► Guarda tu ID de usuario: {d['id_usuario']}")
    return r


def op_crear_usuario():
    print("\n─ CREAR USUARIO (solo Admin) ─────────────────")
    id_admin = pedir("Tu ID de usuario Admin")
    nombre   = pedir("Nombre completo del nuevo usuario")
    email    = pedir("Email del nuevo usuario")
    pw       = pedir("Contraseña", oculto=True)
    print("  Roles disponibles: Clinico / Bodega / Admin")
    rol      = pedir("Rol")
    r = llamar({
        "operacion":       "crear_usuario",
        "id_usuario_admin": int(id_admin),
        "nombre":          nombre,
        "email":           email,
        "pass":            pw,
        "rol":             rol,
    })
    mostrar(r)
    if r["status"] == "OK":
        print(f"  Nuevo ID de usuario: {r['data']['id_usuario']}")


def op_listar_usuarios():
    print("\n── LISTAR USUARIOS (solo Admin) ───────────────")
    id_admin = pedir("Tu ID de usuario Admin")
    r = llamar({
        "operacion":        "listar_usuarios",
        "id_usuario_admin": int(id_admin),
    })
    mostrar(r)
    if r["status"] == "OK":
        separador()
        print(f"  {'ID':<5} {'Nombre':<22} {'Email':<22} {'Rol'}")
        separador()
        for u in r["usuarios"]:
            print(f"  {u['id_usuario']:<5} {u['nombre']:<22} {u['email']:<22} {u['rol']}")
        separador()


def op_actualizar_usuario():
    print("\n── ACTUALIZAR USUARIO (solo Admin) ────────────")
    id_admin  = pedir("Tu ID de usuario Admin")
    id_target = pedir("ID del usuario a modificar")
    print("  Deja en blanco los campos que no quieras cambiar.")
    nombre = pedir("Nuevo nombre (Enter para omitir)")
    print("  Roles: Clinico / Bodega / Admin")
    rol    = pedir("Nuevo rol (Enter para omitir)")
    pw     = pedir("Nueva contraseña (Enter para omitir)", oculto=True)

    payload = {
        "operacion":        "actualizar_usuario",
        "id_usuario_admin": int(id_admin),
        "id_usuario":       int(id_target),
    }
    if nombre: payload["nombre"] = nombre
    if rol:    payload["rol"]    = rol
    if pw:     payload["pass"]   = pw

    r = llamar(payload)
    mostrar(r)


# ─── Menú principal ───────────────────────────────────────────────────────────

MENU = {
    "1": ("Login",                  op_login),
    "2": ("Crear usuario",          op_crear_usuario),
    "3": ("Listar usuarios",        op_listar_usuarios),
    "4": ("Actualizar usuario",     op_actualizar_usuario),
}

def main():
    print("=" * 50)
    print("  SGID · Cliente — Servicio AUTHE")
    print("  Autenticación y gestión de usuarios")
    print("=" * 50)

    while True:
        print("\n  Operaciones disponibles:")
        for k, (nombre, _) in MENU.items():
            print(f"    [{k}] {nombre}")
        print("    [0] Salir")

        opcion = input("\n  Selecciona una opción: ").strip()

        if opcion == "0":
            print("\n  Hasta luego.\n")
            break
        elif opcion in MENU:
            try:
                MENU[opcion][1]()
            except KeyboardInterrupt:
                print("\n  (operación cancelada)")
            except Exception as e:
                print(f"\n  [ERROR] {type(e).__name__}: {e}")
        else:
            print("  Opción no válida.")

if __name__ == "__main__":
    main()
