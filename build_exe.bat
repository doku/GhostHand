@echo off
echo Building GhostHand...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo Installing/Updating PyInstaller...
call .\venv\Scripts\pip install pyinstaller

echo Running PyInstaller...
.\venv\Scripts\pyinstaller --noconsole --onefile --icon=ghost_hand.png ^
    --name=GhostHand ^
    --add-data "ghost_hand.png;." ^
    --add-data "scroll_icon.png;." ^
    --hidden-import "mediapipe" ^
    --collect-all "mediapipe" ^
    main.py

echo.
echo Build Complete! Check the 'dist' folder.
pause
