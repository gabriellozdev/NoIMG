@echo off
rem Gera o NoIMG.exe (o iniciador) na pasta do projeto. Precisa de um Python 3.10+ instalado.
cd /d "%~dp0"

if not exist ".venv-build\Scripts\python.exe" (
  echo Criando ambiente de build...
  python -m venv .venv-build || goto erro
)
".venv-build\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-build.txt || goto erro

".venv-build\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --console --name NoIMG ^
  --icon "%~dp0launcher\noimg.ico" --distpath "%~dp0." --workpath "%~dp0build" --specpath "%~dp0build" ^
  "%~dp0launcher\noimg_launcher.py" || goto erro

echo.
echo Pronto: NoIMG.exe
exit /b 0

:erro
echo.
echo Algo deu errado. Leia a mensagem acima.
exit /b 1
