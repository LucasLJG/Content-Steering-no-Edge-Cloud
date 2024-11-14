import docker
from docker.errors import NotFound as DockerNotFound
import threading
import logging
import time
import requests
from requests.exceptions import RequestException
from network_control import resolve_server_ip

# Configuração do logger
monitor_logger = logging.getLogger('monitor_logger')
monitor_logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler('monitor.log')
file_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

monitor_logger.addHandler(file_handler)
monitor_logger.propagate = False

class ContainerMonitor:
    def __init__(self):
        self.docker_client = docker.from_env()
        self.selected_server = None
        self.running = False
        self.thread = None
        self.user_active_servers = set(['video-streaming-cache-1', 'video-streaming-cache-2', 'video-streaming-cache-3'])
        self.active_servers = set(['video-streaming-cache-1', 'video-streaming-cache-2', 'video-streaming-cache-3'])
        self.health_check_retries = 3
        self.health_check_backoff = 1
        self.network_conditions = {}

        # Lock para garantir a atualização segura de user_active_servers
        self.user_active_servers_lock = threading.Lock()
        
        # Inicializa os contêineres se não estiverem rodando
        for server_name in self.user_active_servers:
            self.ensure_container_running(server_name)

    def ensure_container_running(self, server_name):
        try:
            container = self.docker_client.containers.get(server_name)
            if container.status != 'running':
                container.start()
                monitor_logger.info(f"Contêiner {server_name} iniciado durante a inicialização.")
                time.sleep(5)  # Aguarda um pouco para o contêiner inicializar completamente
        except DockerNotFound:
            monitor_logger.error(f"Contêiner {server_name} não encontrado durante a inicialização.")
        except Exception as e:
            monitor_logger.error(f"Erro ao inicializar o contêiner {server_name}: {str(e)}")

    def start_collecting(self):
        self.running = True
        self.thread = threading.Thread(target=self._collect_loop)
        self.thread.start()
        monitor_logger.info("Monitoramento de contêineres iniciado")

    def stop_collecting(self):
        self.running = False
        if self.thread:
            self.thread.join()
        monitor_logger.info("Monitoramento de contêineres encerrado")

    def _collect_loop(self):
        while self.running:
            try:
                self.check_containers()
            except Exception as e:
                monitor_logger.error(f"Erro no loop de monitoramento: {str(e)}", exc_info=True)
            time.sleep(10)  # Intervalo de verificação de 10 segundos

    def check_server_health(self, server_name):
        ip = resolve_server_ip(server_name)
        if not ip:
            monitor_logger.error(f"Não foi possível resolver o IP para {server_name}")
            return False

        url = f"http://{ip}:80/"
        for attempt in range(self.health_check_retries):
            try:
                response = requests.head(url, timeout=5)
                monitor_logger.info(f"Resposta do servidor {server_name}: status {response.status_code}")
                return response.status_code == 200
            except RequestException as e:
                monitor_logger.warning(f"Tentativa {attempt + 1} falhou para {server_name}: {str(e)}")
                time.sleep(self.health_check_backoff * (2 ** attempt))

        monitor_logger.error(f"Falha ao verificar saúde do servidor {server_name} após {self.health_check_retries} tentativas")
        return False

    def getNodes(self, metric='ip_address'):
        nodes = []
        with self.user_active_servers_lock:
            for server_name in self.user_active_servers:
                if server_name in self.active_servers:
                    try:
                        ip = resolve_server_ip(server_name)
                        if ip and self.check_server_health(server_name):
                            nodes.append((server_name, ip))
                            monitor_logger.info(f"Nó ativo encontrado: {server_name} ({ip})")
                    except Exception as e:
                        monitor_logger.error(f"Erro ao obter informações do nó {server_name}: {str(e)}")
        monitor_logger.info(f"Total de nós ativos: {len(nodes)}")
        return nodes

    def set_selected_server(self, server_name):
        self.selected_server = server_name
        monitor_logger.info(f"Servidor selecionado: {server_name}")

    def update_server_state(self, server_name, is_active):
        monitor_logger.info(f"Atualizando estado do servidor {server_name} para {'ativo' if is_active else 'inativo'}")
        try:
            with self.user_active_servers_lock:
                if is_active:
                    self.user_active_servers.add(server_name)
                    self.ensure_container_running(server_name)
                else:
                    self.user_active_servers.discard(server_name)
                    container = self.docker_client.containers.get(server_name)
                    if container.status == 'running':
                        container.stop()
                        monitor_logger.info(f"Contêiner {server_name} parado.")
                    self.active_servers.discard(server_name)

        except DockerNotFound:
            monitor_logger.error(f"Contêiner {server_name} não encontrado.")
        except Exception as e:
            monitor_logger.error(f"Erro ao atualizar estado do servidor {server_name}: {str(e)}")

    def update_network_conditions(self, network_conditions):
        """
        Atualiza as condições de rede armazenadas no monitor.
        """
        monitor_logger.info(f"Atualizando condições de rede: {network_conditions}")
        self.network_conditions = network_conditions

    def check_containers(self):
        with self.user_active_servers_lock:
            active_servers_copy = self.user_active_servers.copy()

        self.active_servers.clear()

        for container_name in active_servers_copy:
            try:
                container = self.docker_client.containers.get(container_name)
                is_running = container.status == 'running'
                is_user_active = container_name in self.user_active_servers

                if not is_running or not is_user_active:
                    monitor_logger.info(f"Contêiner {container_name} não está em execução ou não está ativo pelo usuário.")
                    continue

                is_healthy = self.check_server_health(container_name)

                if is_healthy and is_running:
                    monitor_logger.info(f"Servidor {container_name} está saudável e em execução.")
                    self.active_servers.add(container_name)
                else:
                    reasons = []
                    if not is_running:
                        reasons.append("não está em execução")
                    if not is_healthy:
                        reasons.append("não está respondendo")
                    reason = " e ".join(reasons)
                    monitor_logger.warning(f"Servidor {container_name} {reason}, mas está ativo para o usuário.")

            except DockerNotFound:
                monitor_logger.error(f"Contêiner {container_name} não encontrado.")
            except Exception as e:
                monitor_logger.error(f"Erro ao verificar contêiner {container_name}: {str(e)}", exc_info=True)

        monitor_logger.info(f"Servidores ativos: {self.active_servers}")
        monitor_logger.info(f"Servidores ativos para o usuário: {self.user_active_servers}")

# Criar uma única instância para ser usada em toda a aplicação
monitor = ContainerMonitor()

if __name__ == '__main__':
    monitor.start_collecting()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        monitor.stop_collecting()
        print("Monitoramento encerrado")