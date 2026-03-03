@echo off
setlocal

echo.
echo ============================================================
echo   Wuji Hand Customer USD Build Pipeline
echo ============================================================
echo.

set BLENDER="C:\Program Files\Blender Foundation\Blender 3.3\blender.exe"
set PYTHON=C:\Python312\python.exe
set PROJECT=%~dp0..

echo Project: %PROJECT%
echo Blender: %BLENDER%
echo Python:  %PYTHON%
echo.

:: Step 1: Generate logo texture
echo [Step 1/5] Generating logo texture placeholder...
%PYTHON% "%PROJECT%\scripts\generate_logo_texture.py"
if errorlevel 1 (
    echo FAILED: Logo texture generation
    exit /b 1
)
echo.

:: Step 2: Build right hand in Blender
echo [Step 2/5] Building right hand in Blender...
%BLENDER% --background --python "%PROJECT%\scripts\blender_build_hand.py" -- --side right --save-blend
if errorlevel 1 (
    echo FAILED: Right hand Blender build
    exit /b 1
)
echo.

:: Step 3: Build left hand in Blender
echo [Step 3/5] Building left hand in Blender...
%BLENDER% --background --python "%PROJECT%\scripts\blender_build_hand.py" -- --side left --save-blend
if errorlevel 1 (
    echo FAILED: Left hand Blender build
    exit /b 1
)
echo.

:: Step 4: Post-process right hand
echo [Step 4/5] Post-processing right hand USD...
%PYTHON% "%PROJECT%\scripts\post_process_usd.py" --side right
if errorlevel 1 (
    echo FAILED: Right hand post-processing
    exit /b 1
)
echo.

:: Step 5: Post-process left hand
echo [Step 5/5] Post-processing left hand USD...
%PYTHON% "%PROJECT%\scripts\post_process_usd.py" --side left
if errorlevel 1 (
    echo FAILED: Left hand post-processing
    exit /b 1
)
echo.

echo ============================================================
echo   BUILD COMPLETE
echo ============================================================
echo.
echo Deliverables:
echo   %PROJECT%\exports\wuji_hand_right\
echo   %PROJECT%\exports\wuji_hand_left\
echo.
echo To verify: open the .usdc files in usdview or Omniverse
echo To debug:  open the .blend files in Blender GUI
echo.

endlocal
