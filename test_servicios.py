"""
test_servicios.py — Pruebas de integración para todos los servicios SGID
Ejecuta los dispatchers directamente (sin bus ni sockets) para verificar
la lógica de negocio y la base de datos.

Uso: python test_servicios.py
     (requiere que init_db.py haya sido ejecutado antes)
"""

import json
import sys
import os

# Asegurar que los imports encuentren los módulos
sys.path.insert(0, os.path.dirname(__file__))

from servicio_authe import dispatch as authe
from servicio_catal import dispatch as catal
from servicio_inven import dispatch as inven
from servicio_pedid import dispatch as pedid


# ─── Helpers ─────────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0

def req(servicio_dispatch, payload: dict) -> dict:
    return json.loads(servicio_dispatch(json.dumps(payload)))

def check(nombre: str, resultado: dict, esperado_status: str, esperado_code: int = None):
    global PASS, FAIL
    ok = resultado["status"] == esperado_status
    if esperado_code:
        ok = ok and resultado["code"] == esperado_code
    estado = "✓" if ok else "✗"
    if ok:
        PASS += 1
    else:
        FAIL += 1
        print(f"  {estado} FAIL [{nombre}]")
        print(f"       Esperado: status={esperado_status}, code={esperado_code}")
        print(f"       Obtenido: {resultado}")
        return
    print(f"  {estado} OK   [{nombre}] → {resultado['msg']}")


# ─── Tests ───────────────────────────────────────────────────────────────────

def test_authe():
    print("\n── authe ─────────────────────────────────────────────")

    # Login exitoso
    r = req(authe, {"operacion": "login", "user": "juan.perez", "pass": "clave123"})
    check("login OK", r, "OK", 200)
    assert r["data"]["rol"] == "Clinico", f"Rol esperado Clinico, obtenido {r['data']['rol']}"
    id_clinico = r["data"]["id_usuario"]

    # Login con clave incorrecta
    r = req(authe, {"operacion": "login", "user": "juan.perez", "pass": "mala"})
    check("login - clave incorrecta", r, "NK", 401)

    # Login usuario inexistente
    r = req(authe, {"operacion": "login", "user": "nadie@nada.com", "pass": "x"})
    check("login - usuario inexistente", r, "NK", 401)

    # Login admin
    r = req(authe, {"operacion": "login", "user": "admin", "pass": "admin2024"})
    check("login admin OK", r, "OK", 200)
    id_admin = r["data"]["id_usuario"]

    # Crear usuario (solo Admin)
    r = req(authe, {"operacion": "crear_usuario", "id_usuario_admin": id_admin,
                    "nombre": "Nuevo Test", "email": "nuevo@test.com",
                    "pass": "test1234", "rol": "Clinico"})
    check("crear_usuario OK", r, "OK", 200)

    # Crear usuario duplicado
    r = req(authe, {"operacion": "crear_usuario", "id_usuario_admin": id_admin,
                    "nombre": "Duplicado", "email": "nuevo@test.com",
                    "pass": "test1234", "rol": "Clinico"})
    check("crear_usuario - email duplicado", r, "NK", 400)

    # Crear usuario sin permiso (Clinico)
    r = req(authe, {"operacion": "crear_usuario", "id_usuario_admin": id_clinico,
                    "nombre": "X", "email": "x@x.com", "pass": "x", "rol": "Clinico"})
    check("crear_usuario - sin permiso", r, "NK", 403)

    # Listar usuarios
    r = req(authe, {"operacion": "listar_usuarios", "id_usuario_admin": id_admin})
    check("listar_usuarios OK", r, "OK", 200)

    return id_clinico, id_admin


def test_catal(id_clinico, id_admin):
    print("\n── catal ─────────────────────────────────────────────")

    # Listar todos
    r = req(catal, {"operacion": "listar_todos"})
    check("listar_todos OK", r, "OK", 200)
    assert len(r["insumos"]) > 0, "No hay insumos en el catálogo"
    id_insumo_1 = r["insumos"][0]["id_insumo"]

    # Verificar campo bajo_critico en INS-007 (stock=0, critico=5)
    sin_stock = [i for i in r["insumos"] if i["stock"] == 0]
    assert sin_stock, "Debería haber al menos un insumo sin stock"
    assert sin_stock[0]["bajo_critico"] == True, "bajo_critico debe ser True cuando stock=0"
    check("bajo_critico correcto en insumo sin stock", {"status":"OK","code":200,"msg":"bajo_critico=True"}, "OK")

    # Crear insumo (Bodega) — usar código único basado en timestamp
    import time as _time
    codigo_test = f"INS-T{int(_time.time()) % 100000}"
    r_login = req(authe, {"operacion": "login", "user": "pedro.bodega", "pass": "bodega2024"})
    id_bodega = r_login["data"]["id_usuario"]
    r = req(catal, {"operacion": "crear_insumo", "id_usuario": id_bodega,
                    "codigo_interno": codigo_test, "nombre": "Insumo de Prueba",
                    "stock_actual": 50, "stock_critico": 5, "unidad_medida": "unidad"})
    check("crear_insumo OK", r, "OK", 200)
    id_nuevo = r["data"]["id_insumo"] if r["status"] == "OK" else None
    if id_nuevo is None:
        # Fallback: buscar el insumo creado en el catálogo
        cat = req(catal, {"operacion": "listar_todos"})
        match = [i for i in cat["insumos"] if i["codigo_interno"] == codigo_test]
        id_nuevo = match[0]["id_insumo"] if match else id_insumo_1

    # Crear insumo duplicado
    r = req(catal, {"operacion": "crear_insumo", "id_usuario": id_bodega,
                    "codigo_interno": codigo_test, "nombre": "Duplicado", "stock_actual": 10})
    check("crear_insumo - código duplicado", r, "NK", 400)

    # Crear insumo sin permiso (Clinico)
    r = req(catal, {"operacion": "crear_insumo", "id_usuario": id_clinico,
                    "codigo_interno": "INS-X", "nombre": "X"})
    check("crear_insumo - sin permiso", r, "NK", 403)

    # Actualizar insumo
    r = req(catal, {"operacion": "actualizar_insumo", "id_usuario": id_bodega,
                    "id_insumo": id_nuevo, "stock_critico": 10, "nombre": "Insumo Test Actualizado"})
    check("actualizar_insumo OK", r, "OK", 200)

    # Intentar modificar stock_actual directamente (debe fallar)
    r = req(catal, {"operacion": "actualizar_insumo", "id_usuario": id_bodega,
                    "id_insumo": id_nuevo, "stock_actual": 999})
    check("actualizar_insumo - stock_actual bloqueado", r, "NK", 400)

    return id_insumo_1, id_nuevo, id_bodega


def test_inven(id_clinico, id_bodega, id_insumo_1, id_insumo_nuevo):
    print("\n── inven ─────────────────────────────────────────────")

    # Descontar stock OK
    r = req(inven, {"operacion": "descontar", "id_insumo": id_insumo_1,
                    "cantidad": 5, "id_usuario": id_clinico})
    check("descontar OK", r, "OK", 200)
    stock_post_descuento = r["nuevo_stock"]

    # Descontar - cantidad inválida
    r = req(inven, {"operacion": "descontar", "id_insumo": id_insumo_1,
                    "cantidad": 0, "id_usuario": id_clinico})
    check("descontar - cantidad=0", r, "NK", 400)

    # Descontar - sin permiso (Bodega)
    r = req(inven, {"operacion": "descontar", "id_insumo": id_insumo_1,
                    "cantidad": 1, "id_usuario": id_bodega})
    check("descontar - sin permiso (Bodega)", r, "NK", 403)

    # Descontar - insumo inexistente
    r = req(inven, {"operacion": "descontar", "id_insumo": 9999,
                    "cantidad": 1, "id_usuario": id_clinico})
    check("descontar - insumo inexistente", r, "NK", 400)

    # Descontar - stock insuficiente (INS-007 tiene stock=0)
    r = req(catal, {"operacion": "listar_todos"})
    sin_stock = [i for i in r["insumos"] if i["stock"] == 0]
    if sin_stock:
        r = req(inven, {"operacion": "descontar", "id_insumo": sin_stock[0]["id_insumo"],
                        "cantidad": 1, "id_usuario": id_clinico})
        check("descontar - stock insuficiente", r, "NK", 400)

    # Registrar entrada (Bodega)
    r = req(inven, {"operacion": "registrar_entrada", "id_insumo": id_insumo_nuevo,
                    "cantidad": 100, "id_usuario": id_bodega,
                    "observacion": "Reposición compra OC-TEST"})
    check("registrar_entrada OK", r, "OK", 200)

    # Registrar entrada - sin permiso (Clinico)
    r = req(inven, {"operacion": "registrar_entrada", "id_insumo": id_insumo_1,
                    "cantidad": 10, "id_usuario": id_clinico})
    check("registrar_entrada - sin permiso", r, "NK", 403)

    # Listar movimientos
    r = req(inven, {"operacion": "listar_movimientos", "id_usuario": id_bodega,
                    "tipo": "SALIDA", "limite": 10})
    check("listar_movimientos OK", r, "OK", 200)

    return stock_post_descuento


def test_pedid(id_clinico, id_bodega, id_insumo_1, id_insumo_nuevo):
    print("\n── pedid ─────────────────────────────────────────────")

    # Crear pedido OK
    r = req(pedid, {"operacion": "crear_pedido", "id_usuario": id_clinico,
                    "items": [{"id_insumo": id_insumo_1, "cantidad": 3},
                              {"id_insumo": id_insumo_nuevo, "cantidad": 10}]})
    check("crear_pedido OK", r, "OK", 200)
    # Extraer N° de pedido del mensaje
    id_solicitud = int(r["msg"].split("N°")[1].split("creado")[0].strip())

    # Crear pedido - items vacíos
    r = req(pedid, {"operacion": "crear_pedido", "id_usuario": id_clinico, "items": []})
    check("crear_pedido - items vacíos", r, "NK", 400)

    # Crear pedido - sin permiso (Bodega)
    r = req(pedid, {"operacion": "crear_pedido", "id_usuario": id_bodega,
                    "items": [{"id_insumo": id_insumo_1, "cantidad": 1}]})
    check("crear_pedido - sin permiso (Bodega)", r, "NK", 403)

    # Crear pedido - insumo inexistente
    r = req(pedid, {"operacion": "crear_pedido", "id_usuario": id_clinico,
                    "items": [{"id_insumo": 9999, "cantidad": 1}]})
    check("crear_pedido - insumo inexistente", r, "NK", 400)

    # Listar pendientes (Bodega)
    r = req(pedid, {"operacion": "listar_pendientes", "id_usuario": id_bodega})
    check("listar_pendientes OK", r, "OK", 200)
    assert any(s["id_solicitud"] == id_solicitud for s in r["solicitudes"]), \
        f"El pedido {id_solicitud} debería estar en pendientes"

    # Listar pendientes - sin permiso (Clinico)
    r = req(pedid, {"operacion": "listar_pendientes", "id_usuario": id_clinico})
    check("listar_pendientes - sin permiso", r, "NK", 403)

    # Listar por usuario
    r = req(pedid, {"operacion": "listar_por_usuario", "id_usuario": id_clinico})
    check("listar_por_usuario OK", r, "OK", 200)

    # Aprobar pedido OK
    r = req(pedid, {"operacion": "aprobar_pedido",
                    "id_solicitud": id_solicitud, "id_usuario_bodega": id_bodega})
    check("aprobar_pedido OK", r, "OK", 200)

    # Intentar aprobar el mismo pedido de nuevo (ya está Aprobada)
    r = req(pedid, {"operacion": "aprobar_pedido",
                    "id_solicitud": id_solicitud, "id_usuario_bodega": id_bodega})
    check("aprobar_pedido - ya aprobado", r, "NK", 400)

    # Crear otro pedido para rechazar
    r = req(pedid, {"operacion": "crear_pedido", "id_usuario": id_clinico,
                    "items": [{"id_insumo": id_insumo_1, "cantidad": 1}]})
    id_para_rechazar = int(r["msg"].split("N°")[1].split("creado")[0].strip())

    # Rechazar pedido
    r = req(pedid, {"operacion": "rechazar_pedido",
                    "id_solicitud": id_para_rechazar, "id_usuario_bodega": id_bodega})
    check("rechazar_pedido OK", r, "OK", 200)

    # Crear pedido con stock insuficiente para aprobar
    r = req(pedid, {"operacion": "crear_pedido", "id_usuario": id_clinico,
                    "items": [{"id_insumo": id_insumo_1, "cantidad": 999999}]})
    id_sin_stock = int(r["msg"].split("N°")[1].split("creado")[0].strip())
    r = req(pedid, {"operacion": "aprobar_pedido",
                    "id_solicitud": id_sin_stock, "id_usuario_bodega": id_bodega})
    check("aprobar_pedido - stock insuficiente", r, "NK", 400)

    # Verificar que el pedido sigue Pendiente después del rollback
    r = req(pedid, {"operacion": "listar_pendientes", "id_usuario": id_bodega})
    sigue_pendiente = any(s["id_solicitud"] == id_sin_stock for s in r["solicitudes"])
    if sigue_pendiente:
        check("rollback - pedido sigue Pendiente tras fallo", {"status":"OK","code":200,"msg":"Pedido sigue Pendiente"}, "OK")
    else:
        check("rollback - pedido sigue Pendiente tras fallo", {"status":"NK","code":500,"msg":"FAIL"}, "OK")


# ─── Ejecución ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("═══════════════════════════════════════════════════")
    print("  SGID — Test de integración de servicios")
    print("═══════════════════════════════════════════════════")

    try:
        id_clinico, id_admin = test_authe()
        id_insumo_1, id_insumo_nuevo, id_bodega = test_catal(id_clinico, id_admin)
        test_inven(id_clinico, id_bodega, id_insumo_1, id_insumo_nuevo)
        test_pedid(id_clinico, id_bodega, id_insumo_1, id_insumo_nuevo)
    except Exception as e:
        print(f"\n[ERROR INESPERADO] {e}")
        import traceback; traceback.print_exc()

    print(f"\n═══════════════════════════════════════════════════")
    print(f"  Resultado: {PASS} OK  |  {FAIL} FAIL")
    print(f"═══════════════════════════════════════════════════")
    sys.exit(0 if FAIL == 0 else 1)
