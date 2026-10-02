@echo off
rem Double-click to start NEXUS OS. It checks the tools it needs, sets itself up on the first run,
rem and opens your browser at http://localhost:5173 when ready. Keep this window open while you use
rem NEXUS; press Ctrl+C or close the window to stop it.
cd /d "%~dp0"
where py >/dev/null 2>/dev/null && (py -3 scripts\dev.py %* & goto done)
where python >/dev/null 2>/dev/null && (python scripts\dev.py %* & goto done)
echo.
echo Python 3.11 or newer is needed. Get it from https://www.python.org/downloads/
echo (tick "Add python.exe to PATH" while installing), then double-click this file again.
:done
echo.
pause
