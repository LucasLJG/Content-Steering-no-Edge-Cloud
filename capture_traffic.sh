#!/bin/bash

# Defina a interface de rede (substitua 'eth0' pela interface correta)
INTERFACE="eth0"

# Defina o nome do arquivo de saída
OUTPUT_FILE="traffic_capture.pcap"

# Execute o tcpdump
sudo tcpdump -i $INTERFACE -w $OUTPUT_FILE
