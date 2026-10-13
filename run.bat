@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
echo ==========================================
echo  Agente Financeiro/Fiscal - Fin Creser
echo ==========================================
echo.

REM Ativa o ambiente virtual
call venv\Scripts\activate.bat

REM Processa todos os PDFs da pasta data/input
set "PASTA_INPUT=data\input"

REM Verifica se existe algum PDF na pasta
if not exist "%PASTA_INPUT%\*.pdf" (
    echo AVISO: Nenhum PDF encontrado em %PASTA_INPUT%
    echo    Coloque as Notas Fiscais e Boletos nessa pasta e execute novamente.
    pause
    exit /b 1
)

REM Monta lista de arquivos PDF
set "ARQUIVOS="
for %%f in ("%PASTA_INPUT%\*.pdf") do (
    set "ARQUIVOS=!ARQUIVOS! "%%f""
)

REM Roda a aplicacao passando todos os PDFs encontrados
python -m src.main %ARQUIVOS%

echo.
echo ==========================================
echo  Processamento finalizado!
echo  Verifique os resultados em: output\servicos\
echo  Verifique revisoes em: output\A_Revisar\
echo  Logs em: output\logs\
echo ==========================================
pause
