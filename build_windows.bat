@echo off
setlocal

python -m venv .venv
call .venv\Scripts\activate

python -m pip install --upgrade pip
pip install -r requirements.txt

pyinstaller --noconfirm --clean --name LocalizadorDeFalta --windowed --onefile app.py

echo Build finalizado. Executavel em dist\LocalizadorDeFalta.exe
endlocal
