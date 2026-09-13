@echo off
REM ============================================================
REM  TASK-9 Falsifier Benchmark - WIRING CHECK (click-to-run)
REM  Double-click this file to run the ~90 s smoke check: every
REM  family, metric and code path, and it writes NOTHING - the
REM  committed falsifier_results.txt is never touched.
REM  The full ~12 min regeneration (which OVERWRITES the committed
REM  results file) is a deliberate typed command - see
REM  WALKTHROUGH.md section 3.1 before running it.
REM ============================================================
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Python was not found on this computer.
  echo   This interim version needs Python installed once.
  echo   See WALKTHROUGH.md, "One-time setup".
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
