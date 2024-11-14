import math
import requests
import xml.etree.ElementTree as ET
import os
import urllib.parse
import os
import sys
import time
import logging
import threading
import socket
from flask import Flask, Response, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from datetime import datetime
from werkzeug.serving import WSGIRequestHandler
import netifaces
from docker.errors import NotFound as DockerNotFound
from network_control import network_control
from monitor import monitor
from adaptive_throttling import adaptive_throttling
from dash_parser import dash_parser
from ai_server_selector import AIServerSelector

def clear_log_file(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'w') as f:
            f.write('')  # Escreve uma string vazia, efetivamente limpando o arquivo

# Caminhos para os arquivos de log
APP_LOG_PATH = 'app.log'
MONITOR_LOG_PATH = 'monitor.log'

# Limpa os arquivos de log
clear_log_file(APP_LOG_PATH)
clear_log_file(MONITOR_LOG_PATH)

def get_host_ip():
    try:
        # Tenta obter o IP da interface docker0
        docker_ip = netifaces.ifaddresses('docker0')[netifaces.AF_INET][0]['addr']
        return docker_ip
    except (ValueError, KeyError):
        try:
            # Se falhar, tenta obter o IP de qualquer interface não-loopback
            for interface in netifaces.interfaces():
                if interface != 'lo':
                    addresses = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addresses:
                        return addresses[netifaces.AF_INET][0]['addr']
        except:
            pass
    
    # Se tudo falhar, retorna localhost
    return "localhost"

def calculate_segment_metrics(content_length, download_time):
    """
    Calcula métricas de um segmento de vídeo baseado no tamanho e tempo de download.
    """
    if download_time > 0:
        throughput = (content_length * 8) / (1000 * download_time)  # kbits/s
        
        
        logger.info(f"Cálculo de métricas do segmento:")
        logger.info(f"- Tamanho do conteúdo: {content_length} bytes")
        logger.info(f"- Tempo de download: {download_time:.3f} segundos")
        logger.info(f"- Throughput calculado: {throughput:.2f} kbit/s")
        
        qoe = main_app.calculate_current_qoe(throughput)
        network_conditions = network_control.get_current_conditions()
        logger.info(f"LOG 4: [CALCULTE_SEGMENT_METRICS]")
        logger.info(f"Estatísticas: Throughput={throughput:.2f}kbit/s, "
                  f"Latência={network_conditions['latency']}ms, "
                  f"Perda de Pacotes={network_conditions['packet_loss']}%, "
                  f"Largura de Banda={network_conditions['bandwidth']}kbit/s, "
                  f"QoE={qoe:.2f}")
        
        return throughput, qoe
    else:
        logger.warning("Tempo de download é 0 ou negativo, não é possível calcular o throughput")
    return 0, 0

def calculate_qoe_by_preset(preset):
        """
        Define pesos base de QoE para cada preset
        """
        preset_qoe_base = {
            'poor': 1.0,      # 2G - base mínima
            'average': 2.0,   # 3G - base média-baixa
            'good': 3.0,      # 4G - base média
            '5g': 4.0,        # 5G - base média-alta
            '6g': 4.5,        # 6G - base alta
            'excellent': 5.0  # Fibra - base máxima
        }
        return preset_qoe_base.get(preset, 3.0)  # default para 'good' se preset não encontrado

def process_manifest(root, base_url):
        """
        Processa o manifesto DASH, modificando as URLs para usar o proxy_segment.
        
        Args:
            root: ElementTree root element do manifesto
            base_url: URL base para os segmentos
        
        Returns:
            str: Manifesto modificado em formato string
        """
        # Modifica as URLs no manifesto
        for element in root.iter():
            if 'initialization' in element.attrib:
                original = element.attrib['initialization']
                element.attrib['initialization'] = f"/proxy_segment?url={base_url}{original}"
                logger.info(f"URL de inicialização modificada: {original} -> {element.attrib['initialization']}")
            
            if 'media' in element.attrib:
                original = element.attrib['media']
                element.attrib['media'] = f"/proxy_segment?url={base_url}{original}"
                logger.info(f"URL de mídia modificada: {original} -> {element.attrib['media']}")

        # Converte o XML modificado para string
        return ET.tostring(root, encoding='unicode')

# Constante base para URI
BASE_URI = f'http://{get_host_ip()}:30500'

# Inicialização da aplicação Flask e CORS
app = Flask(__name__)
CORS(app)

# Caminho para o dataset usando caminho relativo
DATASET_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'dataset', 'Eldorado', '4sec', 'avc'))

# Remove todos os handlers associados ao root logger
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# Define o nível do root logger como WARNING
logging.basicConfig(level=logging.WARNING)

# Configura o logger 'werkzeug'
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.INFO)

# Remove quaisquer handlers existentes do logger 'werkzeug'
for handler in werkzeug_logger.handlers[:]:
    werkzeug_logger.removeHandler(handler)

# Adiciona um FileHandler ao logger 'werkzeug'
werkzeug_file_handler = logging.FileHandler('app.log')
werkzeug_file_handler.setLevel(logging.INFO)
werkzeug_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
werkzeug_file_handler.setFormatter(werkzeug_formatter)
werkzeug_logger.addHandler(werkzeug_file_handler)

# Impede que o logger 'werkzeug' propague mensagens para o root logger
werkzeug_logger.propagate = False

# Configuração do logger
logger = logging.getLogger('app_logger')
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler('app.log')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Impede que o 'app_logger' propague mensagens para o root logger
logger.propagate = False

# Evento para encerrar a aplicação
shutdown_event = threading.Event()

# Flag para evitar execução duplicada das etapas de limpeza
is_shutting_down = False

def do_cleanup():
    """
    Realiza os passos de limpeza necessários ao encerrar a aplicação.
    - Para a captura de tráfego.
    - Não gera gráficos aqui para evitar duplicação; o script bash fará isso.
    """
    global is_shutting_down
    if not is_shutting_down:
        is_shutting_down = True
        print("Encerrando captura de tráfego e aplicação...")
        logger.info("Encerrando captura de tráfego e aplicação...")
        # Encerra a captura de tráfego
        monitor.stop_collecting()
        # Não gera gráficos aqui; será feito pelo script bash
        logger.info("Limpeza concluída.")
        print("Limpeza concluída.")

class Main:
    def __init__(self):
        # Contagem de uso dos servidores
        self.server_usage_count = {
            'video-streaming-cache-1': True,
            'video-streaming-cache-2': True,
            'video-streaming-cache-3': True,
            'cloud': True
        }
        self.current_server = None
        self.last_throughput = 0
        self.session_start_time = None
        self.performance_update_interval = 5  # segundos
        self.last_performance_update = time.time()
        self.use_ai_steering = False
        self.current_preset = 'good'  # Preset inicial
        self.qoe_data = []

        # Definição dos presets de rede
        self.presets = {
            'poor': {
                'name': 'Poor (2G)',
                'latency': 250,
                'packet_loss': 2,
                'bandwidth': 500,
                'max_resolution': (640, 360),
                'qoe_base': 1.0
            },
            'average': {
                'name': 'Average (3G)',
                'latency': 100,
                'packet_loss': 1,
                'bandwidth': 1000,
                'max_resolution': (854, 480),
                'qoe_base': 2.0
            },
            'good': {
                'name': 'Good (4G)',
                'latency': 35,
                'packet_loss': 0.5,
                'bandwidth': 25000,
                'max_resolution': (1920, 1080),
                'qoe_base': 3.0
            },
            '5g': {
                'name': '5G',
                'latency': 10,
                'packet_loss': 0.1,
                'bandwidth': 100000,
                'max_resolution': (2560, 1440),
                'qoe_base': 4.0
            },
            '6g': {
                'name': '6G',
                'latency': 4,
                'packet_loss': 0.01,
                'bandwidth': 1000000,
                'max_resolution': (2560, 1440),
                'qoe_base': 4.5
            },
            'excellent': {
                'name': 'Excellent (Fiber)',
                'latency': 1,
                'packet_loss': 0.001,
                'bandwidth': 1000000,
                'max_resolution': (2560, 1440),
                'qoe_base': 5.0
            }
        }

        
        self.ai_server_selector = AIServerSelector()

    def select_server(self, network_conditions, active_nodes):
        if not active_nodes:
            logger.warning("Nenhum servidor ativo disponível. Usando fallback para 'cloud'.")
            return 'cloud'

        try:
            if self.use_ai_steering:
                selected_server = self.ai_server_selector.predict_best_server(network_conditions, active_nodes)
            else:
                selected_server = self.select_default_server(active_nodes)

            if selected_server:
                logger.info(f"Servidor selecionado: {selected_server}")
                return selected_server
            else:
                logger.warning("Nenhum servidor selecionado pelo método de steering. Usando primeiro servidor ativo.")
                return active_nodes[0][0]
        except Exception as e:
            logger.error(f"Erro ao selecionar servidor: {str(e)}")
            return active_nodes[0][0] if active_nodes else 'cloud'

    def select_default_server(self, active_nodes):
        if not hasattr(self, 'default_server_index'):
            self.default_server_index = 0
        if not active_nodes:
            return None  # Nenhum servidor disponível
        selected_server = active_nodes[self.default_server_index % len(active_nodes)][0]
        self.default_server_index += 1
        logger.info(f"Método padrão selecionou o servidor: {selected_server}")
        return selected_server

    def calculate_stats(self):
        """
        Calcula e retorna as estatísticas da aplicação.
        """
        uptime = datetime.now() - self.session_start_time if self.session_start_time else 'Not started'
        stats = {
            "uptime": str(uptime),
            "current_server": self.current_server,
            "network_conditions": network_control.get_current_conditions()
        }
        return stats

    def update_performance_metrics(self, throughput):
        """
        Atualiza as métricas de desempenho com base no throughput medido.
        """
        network_conditions = network_control.get_current_conditions()
        qoe = self.calculate_current_qoe()
        
        # Log de condições de rede atuais
        logger.info(f"LOG 1: [UPDATE_METRICS]")
        logger.info(f"Condições de Rede Atuais: Throughput={throughput:.2f}kbit/s, "
                    f"Latência={network_conditions['latency']}ms, "
                    f"Perda de Pacotes={network_conditions['packet_loss']}%, "
                    f"Largura de Banda={network_conditions['bandwidth']}kbit/s")

        # Log de estatísticas para o generate_graphs com throughput real
        logger.info(f"LOG 2: [UPDATE_METRICS]")
        logger.info(f"Estatísticas: Throughput={throughput:.2f}kbit/s, "
                    f"Latência={network_conditions['latency']}ms, "
                    f"Perda de Pacotes={network_conditions['packet_loss']}%, "
                    f"Largura de Banda={network_conditions['bandwidth']}kbit/s, "
                    f"QoE={qoe:.2f}")

        return qoe

    def log_request_stats(self, target, throughput, network_conditions, steering_info, qoe):
        """
        Registra as estatísticas da requisição DASH.
        """
        # Formato padronizado para o generate_graphs.py
        logger.info(f"Estatísticas: Throughput={throughput}kbit/s, Latência={network_conditions['latency']}ms, "
                    f"Perda de Pacotes={network_conditions['packet_loss']}%, "
                    f"Largura de Banda={network_conditions['bandwidth']}kbit/s, QoE={qoe:.2f}")
        
        # Logs adicionais para debug
        logger.debug(f"Requisição DASH: Caminho={target}")
        logger.debug(f"Steering Info: {steering_info}")
    
    
    def maintain_preset(self):
        """
        Mantém o preset atual e suas configurações.
        """
        if self.current_preset in self.presets:
            preset_data = self.presets[self.current_preset]
            return {
                'latency': preset_data['latency'],
                'packet_loss': preset_data['packet_loss'],
                'bandwidth': preset_data['bandwidth'],
                'preset': self.current_preset
            }
        return None
        
    def limit_resolution(width, height, max_width=2560, max_height=1440):
        aspect_ratio = width / height
        if width > max_width:
            width = max_width
            height = int(width / aspect_ratio)
        if height > max_height:
            height = max_height
            width = int(height * aspect_ratio)
        return width, height
    
    def log_network_preset(self, preset_name):
        """
        Registra o preset de rede de forma padronizada.
        """
        if preset_name in self.presets:
            preset_data = self.presets[preset_name]
            logger.info(f"NETWORK_PRESET: {preset_data['name']}")
        else:
            logger.info(f"NETWORK_PRESET: {preset_name}")

    def calculate_current_qoe(self, current_throughput=None):
        """
        Calcula a QoE de forma linear baseada nas condições de rede atuais.
        """
        network_conditions = network_control.get_current_conditions()
        throughput = current_throughput if current_throughput is not None else self.last_throughput
        
        latency = network_conditions['latency']
        packet_loss = network_conditions['packet_loss']
        bandwidth = network_conditions['bandwidth']

        
        
        latency_score = 5 - (4 * (latency - 1) / (250 - 1))
        
        
        packet_loss_score = 5 - (4 * (packet_loss - 0.01) / (2 - 0.01))
        
        
        bandwidth_score = 1 + (4 * (math.log10(bandwidth) - math.log10(500)) / 
                            (math.log10(1000000) - math.log10(500)))

        # Pesos para cada métrica
        weights = {
            'latency': 0.35,
            'packet_loss': 0.35,
            'bandwidth': 0.30
        }

        # Cálculo linear ponderado do QoE
        qoe = (weights['latency'] * latency_score +
            weights['packet_loss'] * packet_loss_score +
            weights['bandwidth'] * bandwidth_score)

        # Garantir limites
        qoe = max(min(qoe, 5.0), 1.0)

        # Suavização temporal para evitar mudanças muito bruscas
        if not hasattr(self, 'last_qoe'):
            self.last_qoe = qoe
        else:
            # Fator de suavização: 0.3 significa que 30% do novo valor é considerado
            alpha = 0.3
            qoe = alpha * qoe + (1 - alpha) * self.last_qoe
            self.last_qoe = qoe

        return qoe

    def after_request_processing(self, network_conditions, selected_server, qoe, available_servers):
        """
        Atualiza o modelo de IA com o feedback de desempenho após cada requisição.
        """
        self.ai_server_selector.update_model(network_conditions, selected_server, qoe, available_servers)

    def run(self):
        """
        Inicia a aplicação Flask.
        """
        try:
            print(" * Running on http://localhost:30500/ (Press CTRL+C to quit)")
            logger.info("Servidor iniciado.")
            app.run(host='localhost', port=30500, use_reloader=False, debug=True)
        except Exception as e:
            logger.error(f"Erro no servidor Flask: {str(e)}", exc_info=True)
            do_cleanup()
            sys.exit(1)

# Instanciando a classe Main
main_app = Main()

@app.route('/')
def index():
    """
    Rota para a página inicial.
    """
    logger.info("Servindo página inicial")
    return render_template('index.html', current_preset=main_app.current_preset)

@app.route('/update_network', methods=['POST'])
def update_network():
    data = request.json
    logger.info(f"Solicitação de atualização de rede recebida: {data}")
    try:
        preset_name = data.get('preset', '').lower()
        
        if preset_name and preset_name in main_app.presets:
            preset_data = main_app.presets[preset_name]
            latency = preset_data['latency']
            packet_loss = preset_data['packet_loss']
            bandwidth = preset_data['bandwidth']
            main_app.current_preset = preset_name
            
            main_app.log_network_preset(preset_name)
        else:
            # Manter o preset atual se for uma atualização manual
            latency = int(data.get('latency', 100))
            packet_loss = float(data.get('packetLoss', 2))
            bandwidth = int(data.get('bandwidth', 5000))
            

        
        network_control.update_conditions(
            latency=latency,
            packet_loss=packet_loss,
            bandwidth=bandwidth
        )
        
        adaptive_throttling.manual_update()
        updated_values = network_control.get_current_conditions()

        
        monitor.update_network_conditions(updated_values)
        dash_parser.update_bandwidth_threshold(bandwidth)
        
        return jsonify({
            "status": "sucesso",
            "updated_values": {
                "latency": latency,
                "packet_loss": packet_loss,
                "bandwidth": bandwidth
            },
            "preset": main_app.current_preset
        })
    except Exception as e:
        logger.error(f"Erro ao atualizar a rede: {str(e)}", exc_info=True)
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/manifest.json')
def get_manifest():
    """
    Rota para fornecer o manifesto DASH com base nas condições de rede e seleção de servidor.
    """
    try:
        if not main_app.session_start_time:
            main_app.session_start_time = datetime.now()
            logger.info(f"Nova sessão de streaming iniciada em {main_app.session_start_time}")

        target = request.args.get('_DASH_pathway', default='', type=str)
        throughput = request.args.get('_DASH_throughput', default=0.0, type=float)

        network_conditions = network_control.get_current_conditions()
        if throughput > 0:
            throughput = min(throughput / 1000, network_conditions['bandwidth'])
        else:
            throughput = main_app.last_throughput

        main_app.last_throughput = throughput

        logger.info(f"Requisição DASH: Caminho={target}, Throughput={throughput:.2f}kbit/s")

        nodes = monitor.getNodes('ip_address')
        active_nodes = [node for node in nodes if node[0] in main_app.server_usage_count and main_app.server_usage_count[node[0]]]
        logger.info(f"Nós ativos: {active_nodes}")
        
        network_conditions = network_control.get_current_conditions()
        logger.info(f"Condições de rede atuais: {network_conditions}")
        
        current_time = time.time()
        if current_time - main_app.last_performance_update >= main_app.performance_update_interval:
            qoe = main_app.update_performance_metrics(throughput)
            main_app.last_performance_update = current_time
        else:
            qoe = main_app.calculate_current_qoe()

        selected_server = main_app.select_server(network_conditions, active_nodes)
        logger.info(f"Servidor selecionado: {selected_server}")

        if not selected_server:
            logger.error("Nenhum servidor disponível para seleção.")
            return jsonify({"erro": "Nenhum servidor disponível para seleção."}), 500

        data, steering_info = dash_parser.build(
            target=target,
            nodes=active_nodes,
            uri=BASE_URI,
            request=request,
            network_conditions=network_conditions,
            selected_server=selected_server
        )

        main_app.current_server = steering_info['selected_server']
        logger.info(f"Servidor atual definido como: {main_app.current_server}")

        # Informar o monitor sobre o servidor selecionado
        monitor.set_selected_server(main_app.current_server)

        main_app.log_request_stats(target, throughput, network_conditions, steering_info, qoe)

        # Atualizar o modelo de IA com o feedback de desempenho
        if main_app.use_ai_steering:
            main_app.after_request_processing(network_conditions, selected_server, qoe, active_nodes)

        if selected_server in main_app.server_usage_count:
            main_app.server_usage_count[selected_server] += 1

        return jsonify(data)
    except Exception as e:
        logger.error(f"Erro ao gerar manifesto: {str(e)}", exc_info=True)
        return jsonify({"erro": str(e)}), 500

@app.route('/dataset/<path:filename>')
def serve_dataset(filename):
    """
    Rota para servir arquivos do dataset.
    """
    try:
        full_path = os.path.join(DATASET_PATH, filename)

        if os.path.exists(full_path):
            return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))
        else:
            logger.error(f"Arquivo não encontrado: {full_path}")
            return f"Arquivo não encontrado: {full_path}", 404
    except Exception as e:
        logger.error(f"Erro ao servir arquivo {filename}: {str(e)}", exc_info=True)
        return f"Erro ao servir arquivo: {str(e)}", 500

@app.route('/stats')
def get_stats():
    """
    Rota para obter estatísticas da aplicação.
    """
    stats = main_app.calculate_stats()
    stats["server_usage"] = main_app.server_usage_count
    logger.info(f"Estatísticas solicitadas: {stats}")
    return jsonify(stats)

@app.route('/current_server')
def get_current_server():
    logger.info(f"Servidor atual solicitado: {main_app.current_server}")
    return jsonify({"current_server": main_app.current_server})

@app.route('/force_server_selection', methods=['POST'])
def force_server_selection():
    try:
        network_conditions = network_control.get_current_conditions()
        nodes = monitor.getNodes('ip_address')
        active_nodes = [node for node in nodes if node[0] in main_app.server_usage_count and main_app.server_usage_count[node[0]]]
        
        selected_server = main_app.select_server(network_conditions, active_nodes)
        main_app.current_server = selected_server
        
        logger.info(f"Forçada nova seleção de servidor. Selecionado: {selected_server}")
        return jsonify({"success": True, "selected_server": selected_server})
    except Exception as e:
        logger.error(f"Erro ao forçar seleção de servidor: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/toggle_server', methods=['POST'])
def toggle_server():
    data = request.json
    server_name = data.get('server')
    logger.info(f"Solicitação de alternância de servidor recebida: {server_name}")
    
    if server_name in main_app.server_usage_count:
        current_state = main_app.server_usage_count[server_name]
        new_state = not current_state
        main_app.server_usage_count[server_name] = new_state
        
        threading.Thread(target=monitor.update_server_state, args=(server_name, new_state)).start()
        
        return jsonify({
            "status": "sucesso", 
            "server": server_name, 
            "active": new_state,
            "message": f"Operação de {'ativação' if new_state else 'desativação'} iniciada para {server_name}"
        })
    
    logger.warning(f"Nome de servidor inválido recebido: {server_name}")
    return jsonify({"status": "erro", "mensagem": "Nome de servidor inválido"}), 400

@app.route('/server_status')
def server_status():
    """
    Rota para obter o status atual de todos os servidores.
    """
    logger.info(f"Status dos servidores solicitado: {main_app.server_usage_count}")
    return jsonify(main_app.server_usage_count)

@app.route('/toggle_steering_method', methods=['POST'])
def toggle_steering_method():
    """
    Rota para alternar o método de steering entre IA e padrão.
    """
    main_app.use_ai_steering = not main_app.use_ai_steering
    method = "IA" if main_app.use_ai_steering else "Padrão"
    logger.info(f"Método de steering alterado para: {method}")
    return jsonify({"use_ai_steering": main_app.use_ai_steering})

@app.route('/get_steering_method', methods=['GET'])
def get_steering_method():
    """
    Rota para obter o método de steering atual.
    """
    method = "IA" if main_app.use_ai_steering else "Padrão"
    logger.info(f"Método de steering atual solicitado: {method}")
    return jsonify({"use_ai_steering": main_app.use_ai_steering})

@app.route('/load_external_manifest', methods=['POST'])
def load_external_manifest():
    data = request.json
    manifest_url = data.get('url')
    
    if not manifest_url:
        logger.error("URL do manifesto não fornecida")
        return jsonify({"success": False, "error": "URL do manifesto não fornecida"})

    try:
        response = requests.get(manifest_url)
        response.raise_for_status()
        manifest_content = response.text

        logger.info("Manifesto externo obtido com sucesso")
        root = ET.fromstring(manifest_content)
        base_url = urllib.parse.urljoin(manifest_url, '.')
        logger.info(f"URL base: {base_url}")

        modified_manifest = process_manifest(root, base_url)
        local_manifest_path = os.path.join(DATASET_PATH, 'external_manifest.mpd')
        
        with open(local_manifest_path, 'w') as f:
            f.write(modified_manifest)

        logger.info(f"Manifesto modificado salvo em: {local_manifest_path}")

        # Manter o preset atual ao invés de redefinir
        network_conditions = network_control.get_current_conditions()
        nodes = monitor.getNodes('ip_address')
        active_nodes = [node for node in nodes if node[0] in main_app.server_usage_count and main_app.server_usage_count[node[0]]]
        
        selected_server = main_app.select_server(network_conditions, active_nodes)
        main_app.current_server = selected_server

        preset_data = main_app.presets[main_app.current_preset]
        logger.info(f"NETWORK_PRESET: {preset_data['name']}")

        # Atualizar as condições de rede mantendo o preset atual
        network_control.update_conditions(
            latency=preset_data['latency'],
            packet_loss=preset_data['packet_loss'],
            bandwidth=preset_data['bandwidth']
        )

        return jsonify({
            "success": True, 
            "local_manifest_url": f"/dataset/external_manifest.mpd",
            "selected_server": selected_server,
            "current_preset": main_app.current_preset,  # Adicionar o preset atual na resposta
            "preset_data": preset_data  # Incluir os dados do preset
        })
    except Exception as e:
        logger.error(f"Erro ao carregar manifesto externo: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/proxy_segment')
def proxy_segment():
    url = request.args.get('url')
    segment_path = request.url.split('?')[0].split('/proxy_segment')[1]
    
    logger.info(f"Processando segmento:")
    logger.info(f"- URL: {url}")
    logger.info(f"- Segment Path: {segment_path}")
    
    if not url:
        logger.error("URL não fornecida")
        return "URL não fornecida", 400

    if not segment_path and '?' in request.url:
        segment_path = request.url.split('?')[1].split('&')[0].split('=')[1]
        logger.info(f"- Segment Path extraído da query string: {segment_path}")

    if not segment_path:
        logger.error("Caminho do segmento não fornecido")
        return "Caminho do segmento não fornecido", 400

    full_url = urllib.parse.urljoin(url, segment_path)
    logger.info(f"- URL completa: {full_url}")
    
    try:
        start_time = time.time()
        response = requests.get(full_url)
        response.raise_for_status()
        
        download_time = time.time() - start_time
        content_length = float(response.headers.get('Content-Length', 0))
        
        logger.info(f"Download do segmento:")
        logger.info(f"- Tempo de download: {download_time:.3f} segundos")
        logger.info(f"- Tamanho do conteúdo: {content_length} bytes")
        
        throughput, _ = calculate_segment_metrics(content_length, download_time)
        
        logger.info(f"- Throughput calculado: {throughput:.2f} kbit/s")
        
        content_type = response.headers.get('Content-Type', 'application/octet-stream')
        return Response(response.content, content_type=content_type)
    except Exception as e:
        logger.error(f"Erro ao buscar segmento: {str(e)}")
        return str(e), 500

@app.route('/shutdown', methods=['POST'])
def shutdown():
    def delayed_shutdown():
        logger.info("Iniciando processo de encerramento...")
        do_cleanup()
        shutdown_event.set()
        os._exit(0)

    threading.Thread(target=delayed_shutdown).start()
    return jsonify({"status": "sucesso", "mensagem": "Aplicação será encerrada."})

# Adicionar uma nova rota para verificação de status
@app.route('/status')
def status():
    return jsonify({"status": "running"})

@app.route('/favicon.ico')
def favicon():
    return '', 204

if __name__ == '__main__':
    # Log das informações iniciais
    logger.info(f"Versão do Python: {sys.version}")
    logger.info(f"Diretório de trabalho atual: {os.getcwd()}")
    logger.info(f"DATASET_PATH: {DATASET_PATH}")

    # Inicia a captura de tráfego
    monitor.start_collecting()

    # Configurar condições iniciais de rede com base no preset inicial
    initial_preset = main_app.current_preset
    preset_data = main_app.presets.get(initial_preset)

    if preset_data:
        latency = preset_data['latency']
        packet_loss = preset_data['packet_loss']
        bandwidth = preset_data['bandwidth']
    else:
        latency = 100
        packet_loss = 2
        bandwidth = 5000

    network_control.update_conditions(latency=latency, packet_loss=packet_loss, bandwidth=bandwidth)
    dash_parser.update_bandwidth_threshold(bandwidth)
    preset_name = main_app.presets.get(initial_preset, {}).get('name', 'Custom')

    logger.info(f"NETWORK_PRESET: {preset_name}")
    logger.info(f"Condições iniciais de rede configuradas: Latência={latency}ms, Perda de Pacotes={packet_loss}%, Largura de Banda={bandwidth}kbit/s")

    # Iniciar o servidor Flask
    app.run(host='0.0.0.0', port=30500, use_reloader=False, debug=True)

