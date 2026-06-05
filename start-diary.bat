@echo off
cd /d "%~dp0"
python -c "import lunar_python" >nul 2>&1 || python -m pip install -r requirements.txt
start "" pythonw app.py
