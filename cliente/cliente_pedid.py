"""
cliente_pedid.py — Cliente interactivo del servicio de Pedidos
SGID · RedSalud

Operaciones disponibles:
  1. crear_pedido       — solicitud a bodega con múltiples ítems (Clinico)
  2. listar_pendientes  — ver pedidos en espera de aprobación (Bodega, Admin)
  3. listar_por_usuario — ver mis pedidos (todos)
  4. aprobar_pedido     — aprobar y descontar stock automáticamente (Bodega)
  5. rechazar_pedido    — rechazar sin tocar stock (Bodega)

Uso: python cliente_pedid.py
"""

import json
from soa_lib import connect_to_bus, send_message, receive_message

SERVICIO = "pedid"

# ─── Helper de comunicación ───────────────────────────────────────────────────

def llamar(payload: dict) -> dict:
    """Abre conexión, envía, recibe y cierra. Una conexión por llamada."""
    sock = connect_to_bus()
    try:
        send_message(sock, SERVICIO, json.dumps(payload))
        raw = receive_message(sock)
        if not raw:
            return {"status": "NK", "code": 500, "msg": "Sin respuesta del bus."}
        try:
            return json.loads(raw[5:].decode())
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

def pedir(campo: str, default: str = "") -> str:
    sufijo = f" (Enter = '{default}')" if default else ""
    valor = input(f"  {campo}{sufijo}: ").strip()
    return valor if valor else default

def separador(ancho=72):
    print("  " + "─" * ancho)

def mostrar_items(items: list):
    """Muestra la tabla de ítems de un pedido."""
    print(f"    {'ID ins.':<8} {'Nombre':<28} {'Cantidad':>8} {'Stock actual':>12}")
    print("    " + "─" * 58)
    for it in items:
        stock_str = str(it.get("stock_disponible", "—"))
        print(f"    {it['id_insumo']:<8} {it['nombre_insumo'][:27]:<28} "
              f"{it['cantidad']:>8} {stock_str:>12}")

def mostrar_solicitudes(solicitudes: list, mostrar_stock=False):
    """Muestra una lista de solicitudes con sus ítems."""
    if not solicitudes:
        print("  (No hay solicitudes)")
        return
    for sol in solicitudes:
        separador()
        solicitante = sol.get("solicitante", f"usuario {sol.get('id_solicitud','?')}")
        print(f"  Pedido N°{sol['id_solicitud']}  |  Estado: {sol['estado']}  "
              f"|  Fecha: {sol['fecha_creacion'][:16]}")
        if "solicitante" in sol:
            print(f"  Solicitante: {sol['solicitante']} ({sol.get('email_solicitante','')})")
        print(f"  Ítems:")
        mostrar_items(sol["items"])
    separador()

# ─── Operaciones ──────────────────────────────────────────────────────────────

def op_crear_pedido():
    print("\n── CREAR PEDIDO A BODEGA (Flujo B) ────────────")
    print("  Solo para rol Clinico.")
    print("  Tip: usa el cliente de CATAL para ver los IDs de insumos.")
    id_usuario = pedir("Tu ID de usuario (Clinico)")

    items = []
    print("\n  Agrega los ítems del pedido (Enter en ID para terminar):")
    while True:
        id_insumo = pedir(f"  ID del insumo (ítem #{len(items)+1})")
        if not id_insumo:
            if not items:
                print("  [!] Debes agregar al menos un ítem.")
                continue
            break
        cantidad = pedir(f"  Cantidad para insumo {id_insumo}")
        try:
            items.append({"id_insumo": int(id_insumo), "cantidad": int(cantidad)})
            print(f"  ✓ Ítem agregado: id_insumo={id_insumo}, cantidad={cantidad}")
        except ValueError:
            print("  [!] ID y cantidad deben ser números enteros.")

    print(f"\n  Resumen del pedido ({len(items)} ítem(s)):")
    for it in items:
        print(f"    id_insumo={it['id_insumo']}, cantidad={it['cantidad']}")

    confirmar = pedir("\n  ¿Confirmar pedido? (s/n)", "s").lower()
    if confirmar != "s":
        print("  Pedido cancelado.")
        return

    r = llamar({
        "operacion":  "crear_pedido",
        "id_usuario": int(id_usuario),
        "items":      items,
    })
    mostrar(r)


def op_listar_pendientes():
    print("\n── PEDIDOS PENDIENTES (Bodega / Admin) ────────")
    print("  Muestra solicitudes que esperan aprobación o rechazo.")
    id_usuario = pedir("Tu ID de usuario (Bodega o Admin)")

    r = llamar({"operacion": "listar_pendientes", "id_usuario": int(id_usuario)})
    mostrar(r)
    if r["status"] == "OK":
        mostrar_solicitudes(r["solicitudes"], mostrar_stock=True)
        if r["solicitudes"]:
            print("  Tip: usa Aprobar o Rechazar pedido con el N° de pedido.")


def op_listar_por_usuario():
    print("\n── MIS PEDIDOS ────────────────────────────────")
    id_usuario = pedir("Tu ID de usuario")

    r = llamar({"operacion": "listar_por_usuario", "id_usuario": int(id_usuario)})
    mostrar(r)
    if r["status"] == "OK":
        mostrar_solicitudes(r["solicitudes"])


def op_aprobar_pedido():
    print("\n── APROBAR PEDIDO (Bodega) ─────────────────────")
    print("  Al aprobar, el servidor descuenta el stock de cada ítem")
    print("  automáticamente. Si falta stock en algún ítem, se cancela todo.")
    id_bodega    = pedir("Tu ID de usuario (Bodega)")
    id_solicitud = pedir("N° del pedido a aprobar")

    confirmar = pedir(f"\n  ¿Aprobar pedido N°{id_solicitud}? (s/n)", "s").lower()
    if confirmar != "s":
        print("  Operación cancelada.")
        return

    r = llamar({
        "operacion":        "aprobar_pedido",
        "id_solicitud":     int(id_solicitud),
        "id_usuario_bodega": int(id_bodega),
    })
    mostrar(r)


def op_rechazar_pedido():
    print("\n── RECHAZAR PEDIDO (Bodega) ────────────────────")
    print("  Rechazar no modifica el stock.")
    id_bodega    = pedir("Tu ID de usuario (Bodega)")
    id_solicitud = pedir("N° del pedido a rechazar")

    confirmar = pedir(f"\n  ¿Rechazar pedido N°{id_solicitud}? (s/n)", "s").lower()
    if confirmar != "s":
        print("  Operación cancelada.")
        return

    r = llamar({
        "operacion":         "rechazar_pedido",
        "id_solicitud":      int(id_solicitud),
        "id_usuario_bodega": int(id_bodega),
    })
    mostrar(r)


# ─── Menú principal ───────────────────────────────────────────────────────────

MENU = {
    "1": ("Crear pedido a bodega  [Clinico]",          op_crear_pedido),
    "2": ("Ver pedidos pendientes [Bodega/Admin]",     op_listar_pendientes),
    "3": ("Ver mis pedidos        [todos]",            op_listar_por_usuario),
    "4": ("Aprobar pedido         [Bodega]",           op_aprobar_pedido),
    "5": ("Rechazar pedido        [Bodega]",           op_rechazar_pedido),
}

def main():
    print("=" * 50)
    print("  SGID · Cliente — Servicio PEDID")
    print("  Gestión de pedidos (Flujo B)")
    print("=" * 50)
    print("  FLUJO B:")
    print("    Clinico crea pedido → queda Pendiente (sin tocar stock)")
    print("    Bodega aprueba → stock descontado automáticamente")

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
