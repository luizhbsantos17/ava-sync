@echo off
REM Usado pelo Agendador de Tarefas. Roda sync + guias (se houver IA) + painel.
cd /d "%~dp0\.."
python -m avasync tudo >> "%~dp0\..\agendador_saida.log" 2>&1
