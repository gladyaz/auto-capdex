@echo off
if not exist .venv\Scripts\python.exe (
    echo Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)

echo Retrying only the videos that previously failed...
.venv\Scripts\python pipeline.py --input .\input --output .\output --config .\config.yaml --resume

echo.
echo Done. Check the "output" folder for results.
pause
