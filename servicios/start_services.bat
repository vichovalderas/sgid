@echo off
chcp 65001 >nul
echo ===================================================
echo   SGID ^— Sistema de Gestion de Insumos Dentales
echo   RedSalud ^· Arranque de Servicios SOA
echo ===================================================
echo.

:: ── Verificar que Python esta disponible ────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instalalo desde https://python.org
    pause
    exit /b 1
)

:: ── Verificar que el bus ESB esta corriendo ──────────────────────────────────
echo [check] Verificando conexion al bus ESB en localhost:5000...
python -c "import socket,sys; s=socket.create_connection(('localhost',5000),timeout=2); s.close(); print('[check] Bus ESB disponible.')" 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] No se puede conectar al bus en localhost:5000
    echo         Ejecuta primero en otra terminal:
    echo         docker run -d -p 5000:5000 jrgiadach/soabus:v1
    echo.
    pause
    exit /b 1
)

:: ── Inicializar BD si no existe ───────────────────────────────────────────────
if not exist sgid.db (
    echo.
    echo [init] Base de datos no encontrada. Inicializando...
    python init_db.py
    if errorlevel 1 (
        echo [ERROR] Fallo al inicializar la base de datos.
        pause
        exit /b 1
    )
)

:: ── Levantar los 4 servicios en ventanas separadas ───────────────────────────
echo.
echo [start] Levantando servicios en ventanas separadas...
echo.

start "SGID - authe" cmd /k "python servicio_authe.py"
timeout /t 1 /nobreak >nul

start "SGID - catal" cmd /k "python servicio_catal.py"
timeout /t 1 /nobreak >nul

start "SGID - inven" cmd /k "python servicio_inven.py"
timeout /t 1 /nobreak >nul

start "SGID - pedid" cmd /k "python servicio_pedid.py"
timeout /t 1 /nobreak >nul

echo   [authe] abierto en nueva ventana
echo   [catal] abierto en nueva ventana
echo   [inven] abierto en nueva ventana
echo   [pedid] abierto en nueva ventana
echo.
echo ===================================================
echo   Todos los servicios levantados.
echo   Para detenerlos: cierra cada ventana o presiona
echo   Ctrl+C dentro de cada una.
echo ===================================================
echo.
pause
