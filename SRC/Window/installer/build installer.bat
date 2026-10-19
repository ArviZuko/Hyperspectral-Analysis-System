@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ====================================================================
echo  Hyperspectral Analysis System - Master Windows Build Pipeline
echo ====================================================================

:: ----------------------------------------------------------------------
:: Step 1/8: Check required build tools and dependencies
:: ----------------------------------------------------------------------
echo [Step 1/8] Checking build environment and tools...

if exist ".venv\Scripts\python.exe" goto :have_venv

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH or .venv!
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

echo Creating virtual environment .venv ...
python -m venv .venv
if errorlevel 1 (
    echo [ERROR] Failed to create .venv
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
set "PYTHON_EXE=.venv\Scripts\python.exe"
echo Installing dependencies from requirements.txt...
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)
goto :check_pyinstaller

:have_venv
set "PYTHON_EXE=.venv\Scripts\python.exe"
call ".venv\Scripts\activate.bat"

:check_pyinstaller
:: Verify PyInstaller
"%PYTHON_EXE%" -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    "%PYTHON_EXE%" -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] PyInstaller installation failed
        pause
        exit /b 1
    )
)

:: Locate Inno Setup Compiler (ISCC.exe)
set "ISCC_CMD="
where iscc >nul 2>nul && set "ISCC_CMD=iscc"
if "!ISCC_CMD!"=="" if exist "C:\Program Files\Inno Setup 7\ISCC.exe" set "ISCC_CMD=C:\Program Files\Inno Setup 7\ISCC.exe"
if "!ISCC_CMD!"=="" if exist "C:\Program Files (x86)\Inno Setup 7\ISCC.exe" set "ISCC_CMD=C:\Program Files (x86)\Inno Setup 7\ISCC.exe"
if "!ISCC_CMD!"=="" if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_CMD=C:\Program Files\Inno Setup 6\ISCC.exe"
if "!ISCC_CMD!"=="" if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_CMD=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if "!ISCC_CMD!"=="" if exist "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe" set "ISCC_CMD=%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
if "!ISCC_CMD!"=="" if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_CMD=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if "!ISCC_CMD!"=="" (
    echo [ERROR] Inno Setup compiler ISCC.exe was not found.
    echo Please install Inno Setup 6 or 7 from https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)
echo Found Inno Setup Compiler at: "!ISCC_CMD!"

:: ----------------------------------------------------------------------
:: Step 2/8: Build desktop application using PyInstaller
:: ----------------------------------------------------------------------
echo.
echo [Step 2/8] Building desktop application executable with PyInstaller...
"%PYTHON_EXE%" -m PyInstaller --noconfirm HyperspectralAnalysis.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller packaging failed!
    pause
    exit /b 1
)

:: ----------------------------------------------------------------------
:: Step 3/8: Check that expected application executable exists
:: ----------------------------------------------------------------------
echo.
echo [Step 3/8] Verifying application executable exists...
if not exist "dist\HyperspectralAnalysis.exe" (
    echo [ERROR] Expected binary dist\HyperspectralAnalysis.exe was not created!
    pause
    exit /b 1
)
echo Verified application binary: dist\HyperspectralAnalysis.exe

:: ----------------------------------------------------------------------
:: Step 4/8: Verify all required runtime resources are included
:: ----------------------------------------------------------------------
echo.
echo [Step 4/8] Verifying runtime resources...
if not exist "assets\weights\a.npy" (
    echo [ERROR] Missing model weight assets\weights\a.npy!
    pause
    exit /b 1
)
if not exist "assets\weights\b.npy" (
    echo [ERROR] Missing model weight assets\weights\b.npy!
    pause
    exit /b 1
)
if not exist "assets\weights\c.npy" (
    echo [ERROR] Missing model weight assets\weights\c.npy!
    pause
    exit /b 1
)
if not exist "assets\weights\d.npy" (
    echo [ERROR] Missing model weight assets\weights\d.npy!
    pause
    exit /b 1
)
if not exist "assets\weights\e.npy" (
    echo [ERROR] Missing model weight assets\weights\e.npy!
    pause
    exit /b 1
)
if not exist "assets\logo.ico" (
    echo [ERROR] Missing assets\logo.ico!
    pause
    exit /b 1
)
if not exist "assets\logo.png" (
    echo [ERROR] Missing assets\logo.png!
    pause
    exit /b 1
)
echo All required runtime resources are verified.

:: ----------------------------------------------------------------------
:: Step 5/8: Compile installer\HyperspectralAnalysis.iss using Inno Setup
:: ----------------------------------------------------------------------
echo.
echo [Step 5/8] Compiling Inno Setup script (installer\HyperspectralAnalysis.iss)...
if not exist "Output" mkdir "Output"
"!ISCC_CMD!" "installer\HyperspectralAnalysis.iss"
set "COMPILE_STATUS=%errorlevel%"

:: ----------------------------------------------------------------------
:: Step 6/8: Check compiler exit code
:: ----------------------------------------------------------------------
echo.
echo [Step 6/8] Checking compiler exit code...
if not "!COMPILE_STATUS!"=="0" (
    echo [ERROR] Inno Setup compilation failed with exit code: !COMPILE_STATUS!
    pause
    exit /b !COMPILE_STATUS!
)
echo Inno Setup compiler exited successfully (Code: 0).

:: ----------------------------------------------------------------------
:: Step 7/8: Confirm final installer exists at Output\HyperspectralAnalysis_Setup.exe
:: ----------------------------------------------------------------------
echo.
echo [Step 7/8] Confirming final installer binary...
if not exist "Output\HyperspectralAnalysis_Setup.exe" (
    echo [ERROR] Final installer Output\HyperspectralAnalysis_Setup.exe not found!
    pause
    exit /b 1
)

:: ----------------------------------------------------------------------
:: Step 8/8: Print clear success message and output location
:: ----------------------------------------------------------------------
echo.
echo [Step 8/8] Build pipeline completed successfully!
echo ====================================================================
echo  BUILD SUCCESSFUL!
echo.
echo  Windows Graphical Installer:
echo    Output\HyperspectralAnalysis_Setup.exe
echo.
echo  Standalone Application Binary:
echo    dist\HyperspectralAnalysis.exe
echo ====================================================================
if not "%1"=="--no-pause" pause
exit /b 0
