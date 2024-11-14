import matplotlib.pyplot as plt
import re
from collections import defaultdict
import matplotlib.dates as mdates
from datetime import datetime
import os
import shutil

def create_graphs_folder():
    graphs_folder = 'graphs'
    if os.path.exists(graphs_folder):
        shutil.rmtree(graphs_folder)
    os.makedirs(graphs_folder)
    return graphs_folder

def parse_log_file(file_path):
    network_conditions = []
    steering_changes = []
    qoe_data = []
    preset_changes = []
    first_stats = None
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\w+) - (.+)', line)
                if match:
                    timestamp_str, log_level, message = match.groups()
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')

                    # Capturar informações de rede iniciais
                    if 'Condições iniciais de rede configuradas:' in message:
                        match_initial = re.search(r'Latência=(\d+)ms, Perda de Pacotes=([\d.]+)%, Largura de Banda=(\d+)kbit/s', message)
                        if match_initial:
                            latency, packet_loss, bandwidth = map(float, match_initial.groups())
                            first_stats = {
                                'timestamp': timestamp,
                                'latency': latency,
                                'packet_loss': packet_loss,
                                'bandwidth': bandwidth
                            }

                    if 'Estatísticas:' in message:
                        match = re.search(r'Throughput=([\d.]+)kbit/s, Latência=([\d.]+)ms, Perda de Pacotes=([\d.]+)%, Largura de Banda=([\d.]+)kbit/s(?:, QoE=([\d.]+))?', message)
                        if match:
                            throughput, latency, packet_loss, bandwidth, qoe = match.groups()
                            throughput = float(throughput)
                            latency = float(latency)
                            packet_loss = float(packet_loss)
                            bandwidth = float(bandwidth)
                            
                            # Adicionar condições de rede
                            network_conditions.append((timestamp, latency, packet_loss, bandwidth))
                            
                            if qoe is not None:
                                qoe = float(qoe)
                                qoe_data.append((timestamp, qoe))
                                
                    elif 'Método de steering alterado para:' in message:
                        method = 'IA' if 'IA' in message else 'Padrão'
                        steering_changes.append((timestamp, f"Steering: {method}"))
                    elif 'NETWORK_PRESET:' in message:
                        preset = message.split(':', 1)[1].strip()
                        preset_changes.append((timestamp, f"Preset: {preset}"))

            except Exception as e:
                print(f"Erro ao analisar linha: {line.strip()}")
                print(f"Detalhes do erro: {str(e)}")
                continue

    # Adicionar as condições iniciais se disponíveis
    if first_stats:
        # Inserir as condições iniciais no início das listas
        network_conditions.insert(0, (first_stats['timestamp'], 
                                    first_stats['latency'], 
                                    first_stats['packet_loss'], 
                                    first_stats['bandwidth']))

        # Calcular QoE inicial baseado nas condições iniciais
        initial_qoe = 3.0  # QoE padrão para condições iniciais
        qoe_data.insert(0, (first_stats['timestamp'], initial_qoe))

    return network_conditions, steering_changes, qoe_data, preset_changes

def plot_qoe(times, values, steering_changes, preset_changes, filename, graphs_folder):
    fig, ax = plt.subplots(figsize=(12, 6))

    # Plotar linha de QoE
    ax.plot(times, values, linewidth=1)
    
    ax.set_xlabel('Tempo')
    ax.set_ylabel('QoE')
    ax.set_title('Qualidade de Experiência (QoE)')
    ax.grid(True, linestyle='--', alpha=0.7)

    ax.set_ylim(bottom=1, top=5)

    # Combinar mudanças de steering e preset
    all_changes = steering_changes + preset_changes
    all_changes.sort(key=lambda x: x[0])

    last_x = None
    y_offset = 0
    max_y = ax.get_ylim()[1]
    
    for time, label in all_changes:
        if last_x and (time - last_x).total_seconds() < 5:
            y_offset += 0.05
        else:
            y_offset = 0
            
        color = 'r' if 'Steering' in label else 'g'
        linestyle = '--' if 'Steering' in label else ':'
        alpha = 0.3
        
        ax.axvline(x=time, color=color, linestyle=linestyle, alpha=alpha)
        text_y = max_y * (1 - y_offset)
        ax.text(time, text_y, label, rotation=90,
                verticalalignment='top', horizontalalignment='right',
                color=color, alpha=0.8)
        
        last_x = time

    plt.gcf().autofmt_xdate()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))

    plt.tight_layout()
    plt.savefig(os.path.join(graphs_folder, filename), dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Gerado {filename}")

def plot_network_metric(times, values, ylabel, title, steering_changes, preset_changes, filename, graphs_folder):
    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(times, values, linewidth=1)
    ax.set_xlabel('Tempo')
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True)

    # Configurar escalas específicas
    if 'Latência' in title:
        ax.set_ylim(bottom=0, top=max(values) * 1.1)
    elif 'Perda de Pacotes' in title:
        ax.set_yscale('log')
        ax.set_ylim(bottom=max(0.001, min(values) / 2), top=max(10, max(values) * 2))
    elif 'Largura de Banda' in title:
        ax.set_yscale('log')
        ax.set_ylim(bottom=max(1e2, min(values) / 2), top=min(1e9, max(values) * 2))

    # Combinar mudanças
    all_changes = steering_changes + preset_changes
    all_changes.sort(key=lambda x: x[0])

    last_x = None
    y_offset = 0
    for time, label in all_changes:
        if last_x and (time - last_x).total_seconds() < 5:
            y_offset += 0.05
        else:
            y_offset = 0

        color = 'r' if 'Steering' in label else 'g'
        linestyle = '--' if 'Steering' in label else ':'
        alpha = 0.3
        
        ax.axvline(x=time, color=color, linestyle=linestyle, alpha=alpha)
        ax.text(time, ax.get_ylim()[1] * (1 - y_offset), label, rotation=90,
                verticalalignment='top', horizontalalignment='right', color=color)

        last_x = time

    plt.gcf().autofmt_xdate()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))

    plt.tight_layout()
    plt.savefig(os.path.join(graphs_folder, filename), dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Gerado {filename}")

if __name__ == '__main__':
    log_file = 'app.log'
    try:
        print(f"Iniciando análise do arquivo de log: {log_file}")
        network_conditions, steering_changes, qoe_data, preset_changes = parse_log_file(log_file)

        graphs_folder = create_graphs_folder()

        if network_conditions:
            times, latencies, packet_losses, bandwidths = zip(*network_conditions)

            plot_network_metric(times, latencies, 'Latência (ms)', 'Latência',
                                steering_changes, preset_changes, 'latencia.png', graphs_folder)
            plot_network_metric(times, packet_losses, 'Perda de Pacotes (%)', 'Perda de Pacotes',
                                steering_changes, preset_changes, 'perda_pacotes.png', graphs_folder)
            plot_network_metric(times, bandwidths, 'Largura de Banda (kbit/s)', 'Largura de Banda',
                                steering_changes, preset_changes, 'largura_banda.png', graphs_folder)
        else:
            print("Sem dados suficientes para gerar os gráficos de condições de rede.")

        if qoe_data:
            qoe_times, qoe_values = zip(*qoe_data)
            plot_qoe(qoe_times, qoe_values, steering_changes, preset_changes, 'qoe.png', graphs_folder)
        else:
            print("Sem dados suficientes para gerar o gráfico de QoE.")

        print("Geração de gráficos concluída.")
    except Exception as e:
        print(f"Ocorreu um erro durante a geração dos gráficos: {str(e)}")
        import traceback
        traceback.print_exc()