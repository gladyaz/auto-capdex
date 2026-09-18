@echo off
if not exist .venv\Scripts\python.exe (
    echo Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)

if not exist input (
    mkdir input
)

echo Put your .mp4 files (or series subfolders) inside the "input" folder.
echo Press any key once they are ready to start processing...
pause

.venv\Scripts\python pipeline.py --input .\input --output .\output --config .\config.yaml

echo.
echo Done. Check the "output" folder for .srt and subtitled .mp4 files.
echo If some videos failed, run resume.bat to retry only those.
pause
