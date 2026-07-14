@echo off
echo ================================================
echo   Quartermaster - Iniciando aplicacion
echo ================================================
echo.

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: No se encontro Python en el PATH. Instala Python 3.10+ y volve a intentar.
    pause
    exit /b 1
)

echo Instalando dependencias...
python -m pip install --upgrade pip --quiet
rem Antes esto listaba paquetes sueltos a mano (fastapi, uvicorn, etc.) --
rem se fue desactualizando cada vez que agregamos una dependencia nueva
rem (cryptography, pyjwt para el login) sin acordarnos de tocar este
rem archivo. Instalar el extra "api" del pyproject.toml en cambio
rem significa que este .bat nunca vuelve a quedar desactualizado.
python -m pip install -e ".[api]" --quiet

echo.
echo Configurando .env (genera automaticamente lo que se puede generar solo)...
rem Antes esto era 100% manual -- copiar .env.example a .env, correr dos
rem comandos de Python, copiar cada resultado a mano. Fuente real de
rem bugs: un copy-paste que corta el "=" final del base64 de
rem QUARTERMASTER_ENCRYPTION_KEY rompe el login con un error dificil de
rem diagnosticar a simple vista. Este script genera y escribe las 4
rem claves auto-generables DIRECTO en el archivo -- cero copy-paste.
rem Seguro de correr siempre: nunca pisa un valor ya seteado.
python scripts\setup_env.py

set API_PORT=8000
set STREAMLIT_PORT=8501
set NICEGUI_PORT=8502

echo.
echo Iniciando API en el puerto %API_PORT%...
rem La API corre en su propia ventana para que puedas ver sus logs
rem (y el progreso del Smart Auto-Seed) por separado de Streamlit.
start "Quartermaster API" python -m uvicorn presentation.api.main:app --app-dir src --port %API_PORT%

echo Esperando a que la API arranque...
timeout /t 5 /nobreak >nul

echo.
echo Iniciando Streamlit en el puerto %STREAMLIT_PORT%...
echo Si el navegador no se abre solo en unos segundos, entra manualmente a:
echo   http://localhost:%STREAMLIT_PORT%
echo.

rem --server.headless false ya hace que Streamlit abra el navegador solo --
rem antes había ACA TAMBIEN un "start http://localhost:..." explícito
rem "por las dudas", pensado como red de seguridad -- pero terminaba
rem abriendo DOS pestañas siempre, no solo cuando --server.headless
rem fallaba. Sacado: si en algún Windows --server.headless no dispara el
rem navegador, el mensaje de arriba con la URL manual ya cubre ese caso.
start "" /b python -m streamlit run src\presentation\streamlit_app\app.py --server.headless false --server.port %STREAMLIT_PORT%

echo.
echo Iniciando NiceGUI en el puerto %NICEGUI_PORT%...
rem El .bat original solo levantaba Streamlit -- NiceGUI (la segunda UI,
rem ver src/presentation/ui/) nunca se agregó acá. `ui.run()` en
rem main.py ya abre el navegador solo por default (mismo mecanismo que
rem --server.headless de Streamlit), así que no hace falta un "start
rem http://..." manual acá tampoco.
rem Corre en su propia ventana (como la API) para poder ver sus logs
rem por separado -- a diferencia de Streamlit, que se lanza en segundo
rem plano con /b, porque Streamlit ya tenía ese patrón funcionando bien.
set QUARTERMASTER_UI_PORT=%NICEGUI_PORT%
start "Quartermaster NiceGUI" python src\presentation\ui\main.py

echo.
echo La aplicacion esta corriendo (API + Streamlit + NiceGUI, tres ventanas).
echo   Streamlit: http://localhost:%STREAMLIT_PORT%
echo   NiceGUI:   http://localhost:%NICEGUI_PORT%
echo Cerra las TRES ventanas para detenerla del todo.
pause
