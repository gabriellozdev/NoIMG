@echo off
rem Prepara o NoIMG depois de clonar o repositorio: ambiente Python, modelos e site.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente Python...
  python -m venv .venv || goto erro
)
echo Instalando dependencias Python...
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto erro

echo Baixando modelos de IA...
".venv\Scripts\python.exe" baixar_modelos.py || goto erro

echo Gerando o site...
pushd frontend
call npm install || goto erro_front
call npm run build || goto erro_front
popd

echo.
echo Pronto! Abra o iniciar.bat para usar o NoIMG.
pause
exit /b 0

:erro_front
popd
:erro
echo.
echo Algo deu errado. Leia a mensagem acima.
pause
exit /b 1
