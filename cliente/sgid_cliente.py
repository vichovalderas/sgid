"""
sgid_cliente.py - Cliente CLI para SGID sobre el bus SOA del curso.

Uso:
  python3 sgid_cliente.py
  python3 sgid_cliente.py --demo

Requiere que el bus este en localhost:5000 y los servicios SGID esten
registrados: authe, catal, inven y pedid.
"""

import argparse
import json
import os
import sys
from getpass import getpass


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICIOS_DIR = os.path.join(BASE_DIR, "servicios")
sys.path.insert(0, SERVICIOS_DIR)

from soa_lib import connect_to_bus, receive_message, send_message  # noqa: E402


class BusClient:
    def __init__(self):
        self.sock = connect_to_bus()

    def close(self):
        self.sock.close()

    def call(self, service_name, payload):
        send_message(self.sock, service_name, json.dumps(payload))
        raw = receive_message(self.sock)
        if not raw:
            raise RuntimeError("El bus cerro la conexion sin responder.")

        source = raw[:5].decode("utf-8", errors="replace")
        body = raw[5:].decode("utf-8")
        if body.startswith(("OK", "NK")):
            body = body[2:]
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Respuesta no JSON desde {source}: {body}") from exc

        data["_source"] = source
        return data


def print_response(res):
    prefix = "OK" if res.get("status") == "OK" else "ERROR"
    print(f"[{prefix}] {res.get('msg', 'Sin mensaje')}")


def ask_int(label, minimum=None, allow_empty=False):
    while True:
        value = input(label).strip()
        if allow_empty and value == "":
            return None
        try:
            parsed = int(value)
        except ValueError:
            print("Ingresa un numero entero.")
            continue
        if minimum is not None and parsed < minimum:
            print(f"El valor debe ser mayor o igual a {minimum}.")
            continue
        return parsed


def pause():
    input("\nPresiona Enter para continuar...")


def show_catalog(client):
    res = fetch_catalog(client)
    print_response(res)
    if res.get("status") != "OK":
        return

    print()
    print(f"{'ID':<4} {'Codigo':<10} {'Stock':>7} {'Critico':>8} {'Unidad':<10} Nombre")
    print("-" * 78)
    for item in res["insumos"]:
        mark = "!" if item["bajo_critico"] else " "
        print(
            f"{item['id_insumo']:<4} {item['codigo_interno']:<10} "
            f"{item['stock']:>7} {item['stock_critico']:>8} "
            f"{item['unidad_medida']:<10} {mark} {item['nombre']}"
        )


def fetch_catalog(client, page_size=4):
    insumos = []
    offset = 0
    total = None

    while total is None or offset < total:
        res = client.call(
            "catal",
            {"operacion": "listar_todos", "limite": page_size, "offset": offset},
        )
        if res.get("status") != "OK":
            return res

        page = res.get("insumos", [])
        total = res.get("total", offset + len(page))
        insumos.extend(page)
        if not page:
            break
        offset += len(page)

    return {
        "status": "OK",
        "code": 200,
        "msg": f"Catalogo cargado ({len(insumos)} insumo(s))",
        "insumos": insumos,
        "total": total,
    }


def login(client):
    print("\nInicio de sesion")
    user = input("Usuario: ").strip()
    password = getpass("Contrasena: ")
    res = client.call("authe", {"operacion": "login", "user": user, "pass": password})
    print_response(res)
    return res.get("data") if res.get("status") == "OK" else None


def direct_stock_discount(client, user):
    print("\nDescuento directo de stock")
    id_insumo = ask_int("ID insumo: ", minimum=1)
    cantidad = ask_int("Cantidad: ", minimum=1)
    res = client.call(
        "inven",
        {
            "operacion": "descontar",
            "id_insumo": id_insumo,
            "cantidad": cantidad,
            "id_usuario": user["id_usuario"],
        },
    )
    print_response(res)
    if "nuevo_stock" in res:
        print(f"Nuevo stock: {res['nuevo_stock']}")


def build_items():
    items = []
    print("Agrega items al pedido. Deja el ID vacio para terminar.")
    while True:
        id_insumo = ask_int("ID insumo: ", minimum=1, allow_empty=True)
        if id_insumo is None:
            break
        cantidad = ask_int("Cantidad: ", minimum=1)
        items.append({"id_insumo": id_insumo, "cantidad": cantidad})
    return items


def create_order(client, user):
    print("\nCrear pedido")
    items = build_items()
    if not items:
        print("No se creo el pedido porque no agregaste items.")
        return
    res = client.call(
        "pedid",
        {"operacion": "crear_pedido", "id_usuario": user["id_usuario"], "items": items},
    )
    print_response(res)


def show_orders(res):
    print_response(res)
    if res.get("status") != "OK":
        return

    solicitudes = res.get("solicitudes", [])
    for sol in solicitudes:
        print()
        print(
            f"Pedido #{sol['id_solicitud']} | {sol['estado']} | "
            f"{sol.get('fecha_creacion', '')}"
        )
        if sol.get("solicitante"):
            print(f"Solicitante: {sol['solicitante']} ({sol['email_solicitante']})")
        for item in sol["items"]:
            nombre = item.get("nombre_insumo", f"Insumo {item['id_insumo']}")
            stock = item.get("stock_disponible")
            stock_txt = f" | stock: {stock}" if stock is not None else ""
            print(f"  - {nombre}: {item['cantidad']}{stock_txt}")


def list_my_orders(client, user):
    res = client.call(
        "pedid",
        {"operacion": "listar_por_usuario", "id_usuario": user["id_usuario"]},
    )
    show_orders(res)


def list_pending(client, user):
    res = client.call(
        "pedid",
        {"operacion": "listar_pendientes", "id_usuario": user["id_usuario"]},
    )
    show_orders(res)


def approve_or_reject(client, user, action):
    label = "aprobar" if action == "aprobar_pedido" else "rechazar"
    id_solicitud = ask_int(f"ID pedido a {label}: ", minimum=1)
    res = client.call(
        "pedid",
        {
            "operacion": action,
            "id_solicitud": id_solicitud,
            "id_usuario_bodega": user["id_usuario"],
        },
    )
    print_response(res)


def register_entry(client, user):
    print("\nRegistrar entrada de stock")
    id_insumo = ask_int("ID insumo: ", minimum=1)
    cantidad = ask_int("Cantidad: ", minimum=1)
    observacion = input("Observacion: ").strip() or "Entrada registrada desde cliente SGID"
    res = client.call(
        "inven",
        {
            "operacion": "registrar_entrada",
            "id_insumo": id_insumo,
            "cantidad": cantidad,
            "id_usuario": user["id_usuario"],
            "observacion": observacion,
        },
    )
    print_response(res)


def list_movements(client, user):
    res = client.call(
        "inven",
        {"operacion": "listar_movimientos", "id_usuario": user["id_usuario"], "limite": 20},
    )
    print_response(res)
    if res.get("status") != "OK":
        return
    for mov in res["movimientos"]:
        print(
            f"#{mov['id_movimiento']} {mov['tipo_movimiento']:<7} "
            f"{mov['cantidad']:>4} | {mov['nombre_insumo']} | "
            f"{mov['fecha_movimiento']} | {mov.get('observacion') or ''}"
        )


def admin_create_user(client, user):
    print("\nCrear usuario")
    nombre = input("Nombre: ").strip()
    email = input("Usuario/email: ").strip()
    password = getpass("Contrasena: ")
    rol = input("Rol (Clinico/Bodega/Admin): ").strip()
    res = client.call(
        "authe",
        {
            "operacion": "crear_usuario",
            "id_usuario_admin": user["id_usuario"],
            "nombre": nombre,
            "email": email,
            "pass": password,
            "rol": rol,
        },
    )
    print_response(res)


def run_menu(client, user):
    while True:
        print()
        print(f"SGID - {user['nombre']} ({user['rol']})")
        print("1. Ver catalogo")
        print("2. Crear pedido")
        print("3. Mis pedidos")
        print("4. Descontar stock directo")
        print("5. Pedidos pendientes")
        print("6. Aprobar pedido")
        print("7. Rechazar pedido")
        print("8. Registrar entrada de stock")
        print("9. Historial de movimientos")
        print("10. Crear usuario")
        print("0. Salir")

        option = input("Opcion: ").strip()
        if option == "1":
            show_catalog(client)
        elif option == "2":
            create_order(client, user)
        elif option == "3":
            list_my_orders(client, user)
        elif option == "4":
            direct_stock_discount(client, user)
        elif option == "5":
            list_pending(client, user)
        elif option == "6":
            approve_or_reject(client, user, "aprobar_pedido")
        elif option == "7":
            approve_or_reject(client, user, "rechazar_pedido")
        elif option == "8":
            register_entry(client, user)
        elif option == "9":
            list_movements(client, user)
        elif option == "10":
            admin_create_user(client, user)
        elif option == "0":
            break
        else:
            print("Opcion no valida.")

        pause()


def demo_call(client, title, service, payload):
    print(f"\n== {title}")
    print(f"-> {service}: {json.dumps(payload, ensure_ascii=False)}")
    res = client.call(service, payload)
    print(f"<- {json.dumps({k: v for k, v in res.items() if k != '_source'}, ensure_ascii=False)}")
    if res.get("status") != "OK":
        raise RuntimeError(f"Fallo la demo en: {title}")
    return res


def run_demo(client):
    print("Demo SGID por bus SOA")
    clinico = demo_call(
        client,
        "Login Clinico",
        "authe",
        {"operacion": "login", "user": "juan.perez", "pass": "clave123"},
    )["data"]
    bodega = demo_call(
        client,
        "Login Bodega",
        "authe",
        {"operacion": "login", "user": "pedro.bodega", "pass": "bodega2024"},
    )["data"]
    print("\n== Listar catalogo paginado")
    catalogo = fetch_catalog(client)
    print(f"<- {json.dumps(catalogo, ensure_ascii=False)}")
    if catalogo.get("status") != "OK":
        raise RuntimeError("Fallo la demo al listar catalogo")
    id_insumo = next(i["id_insumo"] for i in catalogo["insumos"] if i["stock"] >= 2)

    pedido = demo_call(
        client,
        "Crear pedido clinico",
        "pedid",
        {
            "operacion": "crear_pedido",
            "id_usuario": clinico["id_usuario"],
            "items": [{"id_insumo": id_insumo, "cantidad": 2}],
        },
    )
    id_solicitud = int(pedido["msg"].split("N°")[1].split("creado")[0].strip())

    demo_call(
        client,
        "Listar pendientes bodega",
        "pedid",
        {"operacion": "listar_pendientes", "id_usuario": bodega["id_usuario"]},
    )
    demo_call(
        client,
        "Aprobar pedido y descontar stock",
        "pedid",
        {
            "operacion": "aprobar_pedido",
            "id_solicitud": id_solicitud,
            "id_usuario_bodega": bodega["id_usuario"],
        },
    )
    demo_call(
        client,
        "Consultar movimientos",
        "inven",
        {"operacion": "listar_movimientos", "id_usuario": bodega["id_usuario"], "limite": 5},
    )
    print("\n== Catalogo posterior paginado")
    catalogo_final = fetch_catalog(client)
    print(f"<- {json.dumps(catalogo_final, ensure_ascii=False)}")
    if catalogo_final.get("status") != "OK":
        raise RuntimeError("Fallo la demo al listar catalogo posterior")
    print("\nDemo finalizada correctamente.")


def main():
    parser = argparse.ArgumentParser(description="Cliente SGID para bus SOA")
    parser.add_argument("--demo", action="store_true", help="ejecuta un flujo automatico")
    args = parser.parse_args()

    client = BusClient()
    try:
        if args.demo:
            run_demo(client)
            return

        user = None
        while user is None:
            user = login(client)
        run_menu(client, user)
    finally:
        client.close()


if __name__ == "__main__":
    main()
