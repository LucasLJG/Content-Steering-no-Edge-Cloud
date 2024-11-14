import subprocess
import threading
import logging
import netifaces
import time
import docker

# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class NetworkControl:
    def __init__(self, interface=None):
        self.latency = 35  # ms
        self.packet_loss = 0.5  # %
        self.bandwidth = 10000  # kbit/s
        self.lock = threading.Lock()
        self.interface = interface or self.detect_interface()
        self.last_update_time = 0
        self.update_interval = 1  # Intervalo mínimo entre atualizações (em segundos)
        self.burst = '32kbit'
        self.tc_latency = '400ms'

    def detect_interface(self):
        interfaces = netifaces.interfaces()
        for iface in interfaces:
            if iface != 'lo':  # Ignore loopback
                addresses = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addresses:
                    return iface
        raise ValueError("Nenhuma interface de rede adequada encontrada")

    def update_conditions(self, latency=None, packet_loss=None, bandwidth=None):
        with self.lock:
            current_time = time.time()
            if current_time - self.last_update_time < self.update_interval:
                logging.info("Atualização ignorada devido ao rate limiting")
                return

            changed = False
            if latency is not None and self.latency != latency:
                self.latency = latency
                changed = True
            if packet_loss is not None and self.packet_loss != packet_loss:
                self.packet_loss = packet_loss
                changed = True
            if bandwidth is not None and self.bandwidth != bandwidth:
                self.bandwidth = bandwidth
                changed = True

            if changed:
                self._apply_tc_rules()
                self.last_update_time = current_time
            else:
                logging.info("Sem mudanças nas condições de rede, atualização ignorada")

    def _apply_tc_rules(self):
        try:
            # Remover regras existentes
            subprocess.run(["sudo", "tc", "qdisc", "del", "dev", self.interface, "root"], 
                           check=False, stderr=subprocess.PIPE)

            # Aplicar novas regras
            subprocess.run(["sudo", "tc", "qdisc", "add", "dev", self.interface, "root", "handle", "1:", "netem"], 
                           check=True)
            subprocess.run(["sudo", "tc", "qdisc", "add", "dev", self.interface, "parent", "1:", "handle", "2:", "tbf", 
                            "rate", f"{self.bandwidth}kbit", "burst", self.burst, "latency", self.tc_latency], 
                           check=True)
            subprocess.run(["sudo", "tc", "qdisc", "add", "dev", self.interface, "parent", "2:", "handle", "3:", "netem", 
                            "delay", f"{self.latency}ms", "loss", f"{self.packet_loss}%"], 
                           check=True)

            logging.info(f"Condições de rede aplicadas: Latência={self.latency}ms, Perda de Pacotes={self.packet_loss}%, "
                         f"Largura de Banda={self.bandwidth}kbit/s na interface {self.interface}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Erro ao aplicar regras tc: {e.stderr.decode().strip()}")

        # Mostrar as regras atuais
        self._show_current_rules()

    def _show_current_rules(self):
        try:
            current_rules = subprocess.check_output(["sudo", "tc", "qdisc", "show", "dev", self.interface], 
                                                    universal_newlines=True)
            logging.info(f"Regras TC atuais:\n{current_rules}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Erro ao obter regras tc atuais: {e.stderr.decode().strip()}")

    def get_current_conditions(self):
        with self.lock:
            return {
                "latency": self.latency,
                "packet_loss": self.packet_loss,
                "bandwidth": self.bandwidth,
                "interface": self.interface
            }

    def get_tc_rules(self):
        try:
            output = subprocess.check_output(["sudo", "tc", "qdisc", "show", "dev", self.interface], universal_newlines=True)
            return output
        except subprocess.CalledProcessError as e:
            logging.error(f"Erro ao obter regras tc: {e.stderr.decode().strip()}")
            return "Erro ao obter regras tc"

def resolve_server_ip(server_name):
    try:
        client = docker.from_env()
        container = client.containers.get(server_name)
        networks = container.attrs['NetworkSettings']['Networks']
        if 'streaming-service_default' in networks:
            return networks['streaming-service_default']['IPAddress']
        # Fallback para qualquer rede se 'streaming-service_default' não for encontrada
        for network in networks.values():
            if network['IPAddress']:
                return network['IPAddress']
        raise ValueError(f"No IP address found for {server_name}")
    except Exception as e:
        logging.error(f"Erro ao resolver IP para {server_name}: {str(e)}")
        return None

# Criar uma única instância para ser usada em toda a aplicação
network_control = NetworkControl()

if __name__ == "__main__":
    # Teste da classe NetworkControl
    logging.info("Testando NetworkControl...")
    network_control.update_conditions(latency=50, packet_loss=1, bandwidth=10000)
    time.sleep(2)
    network_control.update_conditions(latency=100, packet_loss=2, bandwidth=5000)
    time.sleep(2)
    current_conditions = network_control.get_current_conditions()
    logging.info(f"Condições atuais: {current_conditions}")
    tc_rules = network_control.get_tc_rules()
    logging.info(f"Regras TC atuais:\n{tc_rules}")

    # Teste da função de resolução de IP
    test_servers = ['video-streaming-cache-1', 'video-streaming-cache-2', 'video-streaming-cache-3']
    for server in test_servers:
        ip = resolve_server_ip(server)
        if ip:
            logging.info(f"IP resolvido para {server}: {ip}")
        else:
            logging.warning(f"Não foi possível resolver o IP para {server}")
