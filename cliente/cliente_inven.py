"""
cliente_inven.py — Cliente interactivo del servicio de Inventario
SGID · RedSalud

Operaciones disponibles:
  1. descontar         — consumo directo en box (Clinico)
  2. registrar_entrada — ingreso de insumos a bodega (Bodega, Admin)
  3. listar_movimientos — historial de movimientos (Bodega, Admin)

Uso: python cliente_inven.py
"""

import json
from soa_lib import connect_to_bus, send_message, receive_message

SERVICIO = "inven"

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

def pedir(campo: str, default: str = "") -> str:
    sufijo = f" (Enter = '{default}')" if default else ""
    valor = input(f"  {campo}{sufijo}: ").strip()
    return valor if valor else default

def separador(ancho=72):
    print("  " + "─" * ancho)

# ─── Operaciones ──────────────────────────────────────────────────────────────

def op_descontar():
    print("\n── CONSUMO RÁPIDO DE BOX (Flujo A) ────────────")
    print("  Solo para rol Clinico. Descuenta stock de forma inmediata.")
    print("  Tip: usa el cliente de CATAL para ver los IDs de insumos.")
    id_usuario = pedir("Tu ID de usuario (Clinico)")
    id_insumo  = pedir("ID del insumo a descontar")
    cantidad   = pedir("Cantidad a descontar")

    r = llamar({
        "operacion":  "descontar",
        "id_insumo":  int(id_insumo),
        "cantidad":   int(cantidad),
        "id_usuario": int(id_usuario),
    })
    mostrar(r)
    if r["status"] == "OK":
        print(f"  Nuevo stock disponible: {r['nuevo_stock']}")


def op_registrar_entrada():
    print("\n── REGISTRAR ENTRADA DE INSUMOS (Bodega / Admin) ─")
    print("  Registra la recepción de insumos en bodega.")
    id_usuario  = pedir("Tu ID de usuario (Bodega o Admin)")
    id_insumo   = pedir("ID del insumo recibido")
    cantidad    = pedir("Cantidad recibida")
    observacion = pedir("Observación (ej: Compra OC-2024-001)", "Entrada de insumos")

    r = llamar({
        "operacion":   "registrar_entrada",
        "id_insumo":   int(id_insumo),
        "cantidad":    int(cantidad),
        "id_usuario":  int(id_usuario),
        "observacion": observacion,
    })
    mostrar(r)
    if r["status"] == "OK":
        print(f"  Nuevo stock disponible: {r['nuevo_stock']}")


def op_listar_movimientos():
    print("\n── HISTORIAL DE MOVIMIENTOS (Bodega / Admin) ──")
    id_usuario = pedir("Tu ID de usuario (Bodega o Admin)")
    print("  Filtros opcionales (Enter para omitir):")
    id_insumo = pedir("ID de insumo a filtrar")
    print("  Tipos: ENTRADA / SALIDA")
    tipo      = pedir("Tipo de movimiento").upper()
    limite    = pedir("Límite de resultados", "20")

    payload = {
        "operacion":  "listar_movimientos",
        "id_usuario": int(id_usuario),
        "limite":     int(limite),
    }
    if id_insumo: payload["id_insumo"] = int(id_insumo)
    if tipo in ("ENTRADA", "SALIDA"): payload["tipo"] = tipo

    r = llamar(payload)
    mostrar(r)

    if r["status"] == "OK" and r["movimientos"]:
        separador()
        print(f"  {'ID':<5} {'Tipo':<8} {'Cant':>5} {'Insumo':<25} {'Usuario':<18} {'Fecha':<20} Observación")
        separador()
        for m in r["movimientos"]:
            print(f"  {m['id_movimiento']:<5} "
                  f"{m['tipo_movimiento']:<8} "
                  f"{m['cantidad']:>5} "
                  f"{m['nombre_insumo'][:24]:<25} "
                  f"{m['nombre_usuario'][:17]:<18} "
                  f"{m['fecha_movimiento'][:19]:<20} "
                  f"{(m['observacion'] or '')[:30]}")
        separador()
        print(f"  Total: {len(r['movimientos'])} movimiento(s)")


# ─── Menú principal ───────────────────────────────────────────────────────────

MENU = {
    "1": ("Descontar stock (Flujo A — box)",       op_descontar),
    "2": ("Registrar entrada de insumos",          op_registrar_entrada),
    "3": ("Ver historial de movimientos",          op_listar_movimientos),
}

def main():
    print("=" * 50)
    print("  SGID · Cliente — Servicio INVEN")
    print("  Inventario y movimientos de stock")
    print("=" * 50)
    print("  FLUJO A: usa 'Descontar stock' para consumo directo en box.")
    print("  FLUJO B: usa el cliente de PEDID para solicitudes a bodega.")

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
