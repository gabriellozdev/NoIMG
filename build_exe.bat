@echo off
rem Gera o NoIMG.exe na pasta do projeto. Ele funciona sozinho (pode ir para um release do
rem GitHub): leva o app e o site gerado dentro dele. Precisa de Python 3.10+ e Node.js.
cd /d "%~dp0"

echo Gerando o site...
pushd frontend
call npm run build || goto erro_front
popd

if not exist ".venv-build\Scripts\python.exe" (
  echo Criando ambiente de build...
  python -m venv .venv-build || goto erro
)
".venv-build\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-build.txt || goto erro
".venv-build\Scripts\python.exe" launcher\make_payload.py || goto erro

".venv-build\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --console --name NoIMG ^
  --icon "%~dp0launcher\noimg.ico" --distpath "%~dp0." --workpath "%~dp0build" --specpath "%~dp0build" ^
  --add-data "%~dp0build\payload;payload" ^
  "%~dp0launcher\noimg_launcher.py" || goto erro

echo.
echo Pronto: NoIMG.exe
exit /b 0

:erro_front
popd
:erro
echo.
echo Algo deu errado. Leia a mensagem acima.
exit /b 1
