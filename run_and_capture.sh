#!/bin/bash

# Definição de variáveis
PYTHON_SCRIPT="app.py"
CAPTURE_FILE="capture.pcap"
LOG_FILE="app.log"
GRAPH_SCRIPT="generate_graphs.py"
PORT=30500
HOST="0.0.0.0"
URL="http://localhost:$PORT"

# Função para limpar e encerrar
cleanup() {
    echo "Encerrando captura de tráfego e aplicação..."
    if [ ! -z "$TCPDUMP_PID" ] && kill -0 $TCPDUMP_PID 2>/dev/null; then
        sudo kill $TCPDUMP_PID
        wait $TCPDUMP_PID 2>/dev/null
    fi
    if [ ! -z "$PYTHON_PID" ] && kill -0 $PYTHON_PID 2>/dev/null; then
        kill $PYTHON_PID
        wait $PYTHON_PID 2>/dev/null
    fi
    echo "Gerando gráficos..."
    python3 $GRAPH_SCRIPT
    echo "Limpeza concluída."
    exit 0
}

# Configura a trap para chamar cleanup() quando receber SIGINT (Ctrl+C) ou SIGTERM
trap cleanup SIGINT SIGTERM

# Limpa logs anteriores
echo "Limpando logs..."
> $LOG_FILE
echo "Logs limpos."

# Verifica e encerra processos na porta especificada
echo "Verificando processos na porta $PORT..."
EXISTING_PID=$(sudo lsof -ti :$PORT)
if [ ! -z "$EXISTING_PID" ]; then
    echo "Porta $PORT está em uso. Encerrando o processo..."
    sudo kill -9 $EXISTING_PID
    sleep 2
fi
echo "Nenhum processo encontrado na porta $PORT."

# Inicia a captura de tráfego
echo "Iniciando captura de tráfego..."
sudo tcpdump -i any -w $CAPTURE_FILE &
TCPDUMP_PID=$!

# Define variáveis de ambiente para a aplicação Flask
export FLASK_APP=$PYTHON_SCRIPT
export FLASK_ENV=development
export DOCKER_HOST=unix:///var/run/docker.sock

# Inicia a aplicação Python
echo "Iniciando aplicação Python..."
python3 $PYTHON_SCRIPT &
PYTHON_PID=$!

# Aguarda a aplicação iniciar
echo "Aguardando a aplicação iniciar..."
while ! nc -z $HOST $PORT; do   
  sleep 0.1
done

echo "Aplicação iniciada."
echo "A interface web está disponível em: $URL"
echo "Pressione Ctrl+C para encerrar e gerar gráficos."

# Monitora o processo Python
while kill -0 $PYTHON_PID 2>/dev/null; do
    sleep 1
done

# Se o processo Python encerrar por conta própria, realiza a limpeza
echo "Aplicação Python encerrada. Realizando limpeza..."
cleanup
