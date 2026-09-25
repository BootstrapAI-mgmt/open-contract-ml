@echo off
REM ============================================================
REM  Falsifier Benchmark - WIRING CHECK (click-to-run)
REM  Double-click this file to run the ~90 s smoke check: every
REM  family, metric and code path, and it writes NOTHING - the
REM  committed falsifier_results.txt is never touched.
REM  The full ~12 min regeneration (which OVERWRITES the committed
REM  results file) is a deliberate typed command:
REM  python falsifier_benchmark.py
REM ============================================================
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Python was not found on this computer.
  echo   The benchmark needs Python with numpy, scipy and scikit-learn.
  echo.
  pause
  exit /b 1
)
if "%~1"=="" (
  python "%~dp0falsifier_benchmark.py" --smoke
) else (
  python "%~dp0falsifier_benchmark.py" %*
)
echo.
pause
