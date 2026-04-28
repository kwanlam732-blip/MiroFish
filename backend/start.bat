@echo off
cd /d %~dp0
set PYTHONPATH=%CD%
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload