@echo off
cd /d "%~dp0"
if not exist .env (
  echo Falta configurar .env. Consulta README.md.
  pause
  exit /b 1
)
if not exist venv\Scripts\python.exe (
  echo Falta instalar el entorno virtual. Consulta README.md.
  pause
  exit /b 1
)
echo Servidor local: http://127.0.0.1:8000/
venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
pause
