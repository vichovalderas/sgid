# SGID — Servidor SOA


---

## 1. Requisitos e instalacion

### Dependencias Python
El servidor usa unicamente una libreria externa:

```bash
pip install bcrypt
```

### Docker (Bus ESB)
El bus lo provee el profe como imagen Docker:

```bash
docker run -d -p 5000:5000 jrgiadach/soabus:v1
```

Esto levanta el bus en segundo plano en `localhost:5000`. Para ver sus logs:
```bash
docker logs -f <container_id>
```

---

## 2. Estructura de archivos

```
sgid_server/
├── soa_lib.py           # Libreria del profesor 
├── db.py                # Helpers de base de datos compartidos
├── init_db.py           # Crea la BD con tablas y datos de prueba
│
├── servicio_authe.py    # Servicio de autenticacion       → bus: "authe"
├── servicio_catal.py    # Servicio de catalogo            → bus: "catal"
├── servicio_inven.py    # Servicio de inventario          → bus: "inven"
├── servicio_pedid.py    # Servicio de pedidos             → bus: "pedid"
│
├── start_services.sh    # Script de arranque (todos los servicios)
└── test_servicios.py    # Tests de integracion (35 casos)
```

La base de datos `sgid.db` se crea automaticamente al ejecutar `init_db.py`.

---

## 3. Primeros pasos (orden obligatorio)

### Paso 1 — Levantar el bus ESB
```bash
docker run -d -p 5000:5000 jrgiadach/soabus:v1
```

### Paso 2 — Inicializar la base de datos
Solo la primera vez (o cuando quieras reiniciar los datos):
```bash
python3 init_db.py
```

Esto crea `sgid.db` con las 5 tablas y carga usuarios y datos de prueba.

### Paso 3 — Levantar los servicios

**Opcion A — Script automatico (recomendado):**
```bash
//linux

bash start_services.sh
```
```bash
//windows

start_services.bat
```
Levanta los 4 servicios en background y guarda los logs en archivos `.log`.

**Opcion B — Terminal por servicio (util para ver logs en vivo):**
```bash
# Abrir 4 terminales distintas, una por cada servicio
python3 servicio_authe.py
python3 servicio_catal.py
python3 servicio_inven.py
python3 servicio_pedid.py
```

### Paso 4 — Verificar que todo funciona
```bash
python3 test_servicios.py
```
Resultado esperado: `35 OK | 0 FAIL`

---

## 4. Usuarios de prueba

| Email              | Contraseña   | Rol      |
|--------------------|--------------|----------|
| `juan.perez`       | `clave123`   | Clinico  |
| `maria.gonzalez`   | `clave123`   | Clinico  |
| `pedro.bodega`     | `bodega2024` | Bodega   |
| `admin`            | `admin2024`  | Admin    |

---

## 5. Como comunicarse con los servicios

Todo mensaje pasa por el bus usando `soa_lib.py`. La estructura basica del cliente es siempre la misma:

```python
import json
from soa_lib import connect_to_bus, send_message, receive_message

sock = connect_to_bus()      # conectar al bus en localhost:5000
try:
    payload = json.dumps({ "operacion": "...", ... })
    send_message(sock, "SSSSS", payload)   # SSSSS = nombre del servicio (5 letras)

    raw = receive_message(sock)
    datos = json.loads(raw[5:].decode())   # saltar los 5 bytes del nombre del servicio

    if datos["status"] == "OK":
        print(datos["msg"])
    else:
        print(f"Error {datos['code']}: {datos['msg']}")
finally:
    sock.close()
```

### Formato de todas las respuestas

Todos los servicios responden con el mismo formato base:

```json
{
  "status": "OK",
  "code":   200,
  "msg":    "Texto legible para el usuario"
}
```

| `status` | `code` | Significado                                          |
|----------|--------|------------------------------------------------------|
| `OK`     | `200`  | Operacion exitosa                                    |
| `NK`     | `400`  | Error de negocio (campo faltante, stock insuficiente, etc.) |
| `NK`     | `401`  | Credenciales incorrectas (solo login)                |
| `NK`     | `403`  | Operacion no permitida para ese rol                  |
| `NK`     | `500`  | Error interno del servidor                           |

Algunos servicios agregan campos extra en la respuesta (ver cada seccion abajo).

---

## 6. Servicios disponibles

---

### 6.1 `authe` — Autenticacion y Usuarios

**Roles que pueden usarlo:** todos para `login`; solo `Admin` para el resto.

---

#### `login`
Valida credenciales. Devuelve `id_usuario` y `rol` para usar en todas las operaciones siguientes.

**Request:**
```json
{
  "operacion": "login",
  "user": "juan.perez",
  "pass": "clave123"
}
```

**Respuesta exitosa:**
```json
{
  "status": "OK",
  "code": 200,
  "msg": "Bienvenido juan.perez",
  "data": {
    "id_usuario": 1,
    "rol": "Clinico",
    "nombre": "Juan Perez"
  }
}
```

**Respuesta de error:**
```json
{ "status": "NK", "code": 401, "msg": "Credenciales incorrectas." }
```

---

#### `crear_usuario` *(solo Admin)*
Registra un nuevo usuario. La contraseña se hashea con bcrypt antes de guardarse.

**Request:**
```json
{
  "operacion": "crear_usuario",
  "id_usuario_admin": 4,
  "nombre": "Ana Lopez",
  "email": "ana.lopez",
  "pass": "nueva123",
  "rol": "Clinico"
}
```
> `rol` debe ser exactamente: `"Clinico"`, `"Bodega"` o `"Admin"`

**Respuesta exitosa:**
```json
{
  "status": "OK",
  "code": 200,
  "msg": "Usuario 'ana.lopez' creado correctamente.",
  "data": { "id_usuario": 5 }
}
```

---

#### `listar_usuarios` *(solo Admin)*

**Request:**
```json
{ "operacion": "listar_usuarios", "id_usuario_admin": 4 }
```

**Respuesta exitosa:**
```json
{
  "status": "OK",
  "code": 200,
  "msg": "4 usuario(s) encontrado(s).",
  "usuarios": [
    { "id_usuario": 1, "nombre": "Juan Perez", "email": "juan.perez", "rol": "Clinico" }
  ]
}
```

---

#### `actualizar_usuario` *(solo Admin)*
Modifica `nombre`, `rol` y/o `pass`. Debe enviar al menos uno de los tres.

**Request:**
```json
{
  "operacion": "actualizar_usuario",
  "id_usuario_admin": 4,
  "id_usuario": 1,
  "nombre": "Juan Perez Nuevo",
  "rol": "Bodega"
}
```

---

### 6.2 `catal` — Catalogo de Insumos

**Roles:** todos para `listar_todos`; `Bodega` y `Admin` para crear/actualizar.

---

#### `listar_todos`
Devuelve todos los insumos. El campo `bajo_critico` es `true` cuando el stock esta en o bajo el umbral minimo — el cliente debe resaltar estos insumos en la UI.

**Request:**
```json
{ "operacion": "listar_todos" }
```

**Respuesta exitosa:**
```json
{
  "status": "OK",
  "code": 200,
  "msg": "Catalogo cargado",
  "insumos": [
    {
      "id_insumo": 1,
      "nombre": "Jeringa 5ml",
      "stock": 100,
      "stock_critico": 20,
      "unidad_medida": "unidad",
      "codigo_interno": "INS-001",
      "bajo_critico": false
    },
    {
      "id_insumo": 7,
      "nombre": "Eyector de saliva",
      "stock": 0,
      "stock_critico": 5,
      "unidad_medida": "unidad",
      "codigo_interno": "INS-007",
      "bajo_critico": true
    }
  ]
}
```

---

#### `crear_insumo` *(Bodega, Admin)*
**Request:**
```json
{
  "operacion": "crear_insumo",
  "id_usuario": 3,
  "codigo_interno": "INS-011",
  "nombre": "Hilo de sutura 3-0",
  "stock_actual": 40,
  "stock_critico": 10,
  "unidad_medida": "rollo"
}
```

**Respuesta exitosa:**
```json
{
  "status": "OK",
  "code": 200,
  "msg": "Insumo 'Hilo de sutura 3-0' creado correctamente.",
  "data": { "id_insumo": 11, "codigo_interno": "INS-011" }
}
```

---

#### `actualizar_insumo` *(Bodega, Admin)*
Solo puede modificar `nombre`, `stock_critico` y `unidad_medida`. Intentar modificar `stock_actual` directamente devuelve error (eso es tarea exclusiva de `inven`).

**Request:**
```json
{
  "operacion": "actualizar_insumo",
  "id_usuario": 3,
  "id_insumo": 1,
  "stock_critico": 25,
  "nombre": "Jeringa 5ml desechable"
}
```

---

### 6.3 `inven` — Inventario (Nucleo Transaccional)

**Notas de implementacion:**
- `descontar` usa `BEGIN IMMEDIATE` → bloqueo exclusivo de escritura que serializa concurrencia.
- Los readers (`SELECT` sin transaccion) siguen operando gracias al modo WAL.
- Si el stock es insuficiente al momento de ejecutar la transaccion (aunque parecia suficiente al consultar el catalogo), el servidor responde `NK 400` — el cliente **no debe reintentar automaticamente**.

---

#### `descontar` *(solo Clinico)* — Flujo A
Uso directo en box dental. Descuenta stock de forma inmediata.

**Request:**
```json
{
  "operacion": "descontar",
  "id_insumo": 1,
  "cantidad": 2,
  "id_usuario": 1
}
```

**Respuesta exitosa:**
```json
{
  "status": "OK",
  "code": 200,
  "msg": "Stock descontado. Quedan 98.",
  "nuevo_stock": 98
}
```

**Respuesta de error — stock insuficiente:**
```json
{ "status": "NK", "code": 400, "msg": "No hay stock suficiente (Solicito 2, Quedan 1)" }
```

**Respuesta de error — rol incorrecto:**
```json
{ "status": "NK", "code": 403, "msg": "El rol 'Bodega' no tiene permiso para descontar stock directamente. Solo el rol 'Clinico' puede realizar consumos rapidos de box." }
```

---

#### `registrar_entrada` *(Bodega, Admin)*
Registra el ingreso de insumos a bodega (reposicion, compra). Incrementa `stock_actual`.

**Request:**
```json
{
  "operacion": "registrar_entrada",
  "id_insumo": 7,
  "cantidad": 50,
  "id_usuario": 3,
  "observacion": "Reposicion compra OC-2024-001"
}
```

**Respuesta exitosa:**
```json
{
  "status": "OK",
  "code": 200,
  "msg": "Entrada registrada. Stock de 'Eyector de saliva': 50.",
  "nuevo_stock": 50
}
```

---

#### `listar_movimientos` *(Bodega, Admin)*
Historial de movimientos de stock con filtros opcionales.

**Request:**
```json
{
  "operacion": "listar_movimientos",
  "id_usuario": 3,
  "tipo": "SALIDA",
  "id_insumo": 1,
  "limite": 20
}
```
> Todos los filtros son opcionales excepto `id_usuario`.

**Respuesta exitosa:**
```json
{
  "status": "OK",
  "code": 200,
  "msg": "3 movimiento(s) encontrado(s).",
  "movimientos": [
    {
      "id_movimiento": 1,
      "tipo_movimiento": "SALIDA",
      "cantidad": 2,
      "fecha_movimiento": "2026-06-07 15:30:00",
      "observacion": "Consumo directo en box",
      "nombre_insumo": "Jeringa 5ml",
      "id_insumo": 1,
      "nombre_usuario": "Juan Perez",
      "email_usuario": "juan.perez",
      "id_solicitud": null
    }
  ]
}
```

---

### 6.4 `pedid` — Gestion de Pedidos

**Flujo B completo:**
1. El clinico crea un pedido → queda en estado `"Pendiente"` (sin tocar el stock)
2. El personal de bodega revisa los pendientes y aprueba o rechaza
3. Al aprobar → el servidor descuenta el stock de cada item en la **misma transaccion**

> **El cliente de bodega NO debe llamar a `inven` despues de aprobar un pedido.** El descuento ocurre automaticamente dentro de `aprobar_pedido`.

---

#### `crear_pedido` *(solo Clinico)*

**Request:**
```json
{
  "operacion": "crear_pedido",
  "id_usuario": 1,
  "items": [
    { "id_insumo": 1, "cantidad": 10 },
    { "id_insumo": 2, "cantidad": 5 }
  ]
}
```

**Respuesta exitosa:**
```json
{ "status": "OK", "code": 200, "msg": "Pedido N° 1 creado (Pendiente)" }
```

**Errores posibles:**
```json
{ "status": "NK", "code": 400, "msg": "El pedido debe contener al menos un item en el campo 'items'." }
{ "status": "NK", "code": 400, "msg": "El id_insumo 99 (item #2) no existe en el catalogo." }
{ "status": "NK", "code": 403, "msg": "El rol 'Bodega' no tiene permiso para crear pedidos. Solo rol 'Clinico'." }
```

---

#### `listar_pendientes` *(Bodega, Admin)*
Devuelve todos los pedidos en estado `"Pendiente"` con sus items y el stock disponible actual de cada uno.

**Request:**
```json
{ "operacion": "listar_pendientes", "id_usuario": 3 }
```

**Respuesta exitosa:**
```json
{
  "status": "OK",
  "code": 200,
  "msg": "1 solicitud(es) pendiente(s).",
  "solicitudes": [
    {
      "id_solicitud": 1,
      "fecha_creacion": "2026-06-07 15:00:00",
      "estado": "Pendiente",
      "solicitante": "Juan Perez",
      "email_solicitante": "juan.perez",
      "items": [
        { "id_insumo": 1, "nombre_insumo": "Jeringa 5ml", "cantidad": 10, "stock_disponible": 98 },
        { "id_insumo": 2, "nombre_insumo": "Guantes nitrilo (caja)", "cantidad": 5, "stock_disponible": 50 }
      ]
    }
  ]
}
```

---

#### `listar_por_usuario` *(todos los roles)*
Devuelve los pedidos de un usuario especifico con su estado actual.

**Request:**
```json
{ "operacion": "listar_por_usuario", "id_usuario": 1 }
```

---

#### `aprobar_pedido` *(solo Bodega)*
Aprueba el pedido y descuenta el stock de todos sus items en una transaccion atomica.
Si falta stock para **cualquier item**, el pedido queda `"Pendiente"` sin modificacion alguna.

**Request:**
```json
{
  "operacion": "aprobar_pedido",
  "id_solicitud": 1,
  "id_usuario_bodega": 3
}
```

**Respuesta exitosa:**
```json
{ "status": "OK", "code": 200, "msg": "Pedido N° 1 aprobado. Stock descontado correctamente." }
```

**Error — stock insuficiente (rollback completo):**
```json
{ "status": "NK", "code": 400, "msg": "No se puede aprobar. Falta stock para el item 'Guantes nitrilo (caja)' (ID 2): se necesitan 5, hay 3." }
```

**Error — pedido no esta pendiente:**
```json
{ "status": "NK", "code": 400, "msg": "La solicitud N° 1 no esta en estado Pendiente (estado actual: Aprobada)." }
```

---

#### `rechazar_pedido` *(solo Bodega)*
Cambia el estado a `"Rechazada"` sin modificar el stock.

**Request:**
```json
{
  "operacion": "rechazar_pedido",
  "id_solicitud": 2,
  "id_usuario_bodega": 3
}
```

**Respuesta exitosa:**
```json
{ "status": "OK", "code": 200, "msg": "Pedido N° 2 rechazado correctamente." }
```

---

## 7. Resumen de operaciones por rol

| Operacion                        | Clinico | Bodega | Admin |
|----------------------------------|:-------:|:------:|:-----:|
| `authe / login`                  | ✓       | ✓      | ✓     |
| `authe / crear_usuario`          |         |        | ✓     |
| `authe / listar_usuarios`        |         |        | ✓     |
| `authe / actualizar_usuario`     |         |        | ✓     |
| `catal / listar_todos`           | ✓       | ✓      | ✓     |
| `catal / crear_insumo`           |         | ✓      | ✓     |
| `catal / actualizar_insumo`      |         | ✓      | ✓     |
| `inven / descontar`              | ✓       |        |       |
| `inven / registrar_entrada`      |         | ✓      | ✓     |
| `inven / listar_movimientos`     |         | ✓      | ✓     |
| `pedid / crear_pedido`           | ✓       |        |       |
| `pedid / listar_pendientes`      |         | ✓      | ✓     |
| `pedid / listar_por_usuario`     | ✓       | ✓      | ✓     |
| `pedid / aprobar_pedido`         |         | ✓      |       |
| `pedid / rechazar_pedido`        |         | ✓      |       |

---

## 8. Ejemplo de sesion completa (Flujo A + Flujo B)

```python
import json
from soa_lib import connect_to_bus, send_message, receive_message

def llamar(sock, servicio, payload):
    send_message(sock, servicio, json.dumps(payload))
    raw = receive_message(sock)
    return json.loads(raw[5:].decode())

sock = connect_to_bus()
try:
    # 1. Login como clinico
    r = llamar(sock, "authe", {"operacion": "login", "user": "juan.perez", "pass": "clave123"})
    id_clinico = r["data"]["id_usuario"]   # → 1

    # 2. Ver catalogo
    r = llamar(sock, "catal", {"operacion": "listar_todos"})
    for insumo in r["insumos"]:
        alerta = " ⚠ STOCK BAJO" if insumo["bajo_critico"] else ""
        print(f"  [{insumo['id_insumo']}] {insumo['nombre']}: {insumo['stock']}{alerta}")

    # 3. Flujo A — consumo directo en box
    r = llamar(sock, "inven", {
        "operacion": "descontar",
        "id_insumo": 1, "cantidad": 2, "id_usuario": id_clinico
    })
    print(r["msg"])   # "Stock descontado. Quedan 98."

    # 4. Flujo B — crear pedido a bodega
    r = llamar(sock, "pedid", {
        "operacion": "crear_pedido",
        "id_usuario": id_clinico,
        "items": [{"id_insumo": 7, "cantidad": 20}, {"id_insumo": 8, "cantidad": 5}]
    })
    print(r["msg"])   # "Pedido N° 1 creado (Pendiente)"

    # 5. Login como bodega y aprobar el pedido
    r = llamar(sock, "authe", {"operacion": "login", "user": "pedro.bodega", "pass": "bodega2024"})
    id_bodega = r["data"]["id_usuario"]   # → 3

    r = llamar(sock, "pedid", {
        "operacion": "aprobar_pedido",
        "id_solicitud": 1, "id_usuario_bodega": id_bodega
    })
    print(r["msg"])   # "Pedido N° 1 aprobado. Stock descontado correctamente."

finally:
    sock.close()
```
