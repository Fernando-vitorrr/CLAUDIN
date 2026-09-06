@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================================
echo  Instalacao da Base de Conhecimento do YouTube
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo ERRO: Python nao foi encontrado.
  echo Instale o Python 3.11 ou superior em https://www.python.org/downloads/
  echo Durante a instalacao, marque "Add Python to PATH".
  pause
  exit /b 1
)

where ollama >nul 2>nul
if errorlevel 1 (
  echo ERRO: Ollama nao foi encontrado.
  echo Instale-o em https://ollama.com/download/windows e abra o programa.
  pause
  exit /b 1
)

echo [1/4] Atualizando o instalador de pacotes...
python -m pip install --upgrade pip
if errorlevel 1 goto :falha

echo [2/4] Instalando os componentes do aplicativo...
python -m pip install -r requirements.txt
if errorlevel 1 goto :falha

echo [3/4] Baixando o modelo local qwen3.5:9b...
echo O download ocupa aproximadamente 6,6 GB e acontece somente uma vez.
ollama pull qwen3.5:9b
if errorlevel 1 goto :falha

echo [4/4] Baixando o modelo de transcricao de audio...
echo Usado apenas em videos sem legenda. Ocupa cerca de 500 MB.
python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"
if errorlevel 1 (
  echo Aviso: o modelo de audio nao foi baixado agora.
  echo Ele sera baixado automaticamente no primeiro video sem legenda.
)

echo.
echo Instalacao concluida.
echo Agora use o arquivo ABRIR_APP.bat.
echo.
echo Se quiser usar o motor "Claude" (API da Anthropic) em vez do modelo
echo local, cole sua chave no campo "Chave API Claude" da interface, ou
echo defina a variavel de ambiente ANTHROPIC_API_KEY no Windows.
pause
exit /b 0

:falha
echo.
echo A instalacao nao foi concluida. Verifique a mensagem acima.
pause
exit /b 1
