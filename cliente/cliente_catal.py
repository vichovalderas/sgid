"""
cliente_catal.py — Cliente interactivo del servicio de Catálogo
SGID · RedSalud

Operaciones disponibles:
  1. listar_todos      (todos los roles)
  2. crear_insumo      (Bodega, Admin)
  3. actualizar_insumo (Bodega, Admin)

Uso: python cliente_catal.py
"""

import json
from soa_lib import connect_to_bus, send_message, receive_message

SERVICIO = "catal"

# ─── Helper de comunicación ───────────────────────────────────────────────────

def llamar(payload: dict) -> dict:
    sock = connect_to_bus()
    try:
        send_message(sock, SERVICIO, json.dumps(payload))
        raw = receive_message(sock)
        if not raw:
            return {"status": "NK", "code": 500, "msg": "Sin respuesta del bus."}
        return json.loads(raw[5:].decode())
    finally:
        sock.close()

def mostrar(r: dict):
    estado = "✓" if r["status"] == "OK" else "✗"
    print(f"\n  {estado} [{r['code']}] {r['msg']}")

def pedir(campo: str, default: str = "") -> str:
    sufijo = f" (Enter = '{default}')" if default else ""
    valor = input(f"  {campo}{sufijo}: ").strip()
    return valor if valor else default

def separador(ancho=70):
    print("  " + "─" * ancho)

# ─── Operaciones ──────────────────────────────────────────────────────────────

def op_listar_todos():
    print("\n── CATÁLOGO DE INSUMOS ────────────────────────")
    r = llamar({"operacion": "listar_todos"})
    mostrar(r)
    if r["status"] == "OK":
        insumos = r["insumos"]
        separador()
        print(f"  {'ID':<5} {'Código':<10} {'Nombre':<28} {'Stock':>6} {'Crítico':>8} {'Unidad':<10} {'Alerta'}")
        separador()
        for i in insumos:
            alerta = "⚠ BAJO" if i["bajo_critico"] else ""
            print(f"  {i['id_insumo']:<5} {i['codigo_interno']:<10} "
                  f"{i['nombre'][:27]:<28} {i['stock']:>6} "
                  f"{i['stock_critico']:>8} {i['unidad_medida']:<10} {alerta}")
        separador()
        print(f"  Total: {len(insumos)} insumo(s)")
        bajos = [i for i in insumos if i["bajo_critico"]]
        if bajos:
            print(f"  ⚠  {len(bajos)} insumo(s) bajo stock crítico:")
            for i in bajos:
                print(f"     - {i['nombre']} (stock={i['stock']}, crítico={i['stock_critico']})")


def op_crear_insumo():
    print("\n── CREAR INSUMO (Bodega / Admin) ──────────────")
    id_usuario     = pedir("Tu ID de usuario")
    codigo_interno = pedir("Código interno (ej: INS-011)")
    nombre         = pedir("Nombre del insumo")
    stock_actual   = pedir("Stock inicial", "0")
    stock_critico  = pedir("Stock crítico (umbral de alerta)", "10")
    unidad_medida  = pedir("Unidad de medida", "unidad")

    r = llamar({
        "operacion":      "crear_insumo",
        "id_usuario":     int(id_usuario),
        "codigo_interno": codigo_interno,
        "nombre":         nombre,
        "stock_actual":   int(stock_actual),
        "stock_critico":  int(stock_critico),
        "unidad_medida":  unidad_medida,
    })
    mostrar(r)
    if r["status"] == "OK":
        print(f"  ID asignado      : {r['data']['id_insumo']}")
        print(f"  Código interno   : {r['data']['codigo_interno']}")


def op_actualizar_insumo():
    print("\n── ACTUALIZAR INSUMO (Bodega / Admin) ─────────")
    print("  NOTA: No se puede modificar stock_actual desde aquí.")
    print("        Para eso usa el cliente de INVEN.")
    id_usuario = pedir("Tu ID de usuario")
    id_insumo  = pedir("ID del insumo a modificar")
    print("  Deja en blanco los campos que no quieras cambiar.")
    nombre        = pedir("Nuevo nombre (Enter para omitir)")
    stock_critico = pedir("Nuevo stock crítico (Enter para omitir)")
    unidad_medida = pedir("Nueva unidad de medida (Enter para omitir)")

    payload = {
        "operacion":  "actualizar_insumo",
        "id_usuario": int(id_usuario),
        "id_insumo":  int(id_insumo),
    }
    if nombre:        payload["nombre"]        = nombre
    if stock_critico: payload["stock_critico"] = int(stock_critico)
    if unidad_medida: payload["unidad_medida"] = unidad_medida

    r = llamar(payload)
    mostrar(r)


# ─── Menú principal ───────────────────────────────────────────────────────────

MENU = {
    "1": ("Listar todos los insumos",   op_listar_todos),
    "2": ("Crear insumo",               op_crear_insumo),
    "3": ("Actualizar insumo",          op_actualizar_insumo),
}

def main():
    print("=" * 50)
    print("  SGID · Cliente — Servicio CATAL")
    print("  Catálogo de insumos dentales")
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
            except ValueError:
                print("\n  [!] Ingresa un número válido donde se pida un ID o cantidad.")
            except Exception as e:
                print(f"\n  [ERROR] {e}")
        else:
            print("  Opción no válida.")

if __name__ == "__main__":
    main()
