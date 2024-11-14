import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import numpy as np
from collections import deque
import threading
import logging
from monitor import monitor

class AIServerSelector:
    def __init__(self, max_samples=1000, update_threshold=100):
        self.model = None
        self.scaler = StandardScaler()
        self.max_samples = max_samples
        self.update_threshold = update_threshold
        self.data_buffer = deque(maxlen=max_samples)
        self.target_buffer = deque(maxlen=max_samples)
        self.sample_count = 0
        self.lock = threading.Lock()
        self.server_mapping = {}  # Mapeamento de servidores para índices
        self.load_or_train_model()

    def load_or_train_model(self):
        try:
            self.model = joblib.load('server_selection_model.joblib')
            self.scaler = joblib.load('server_selection_scaler.joblib')
            self.server_mapping = joblib.load('server_mapping.joblib')
            logging.info("Modelo de seleção de servidor carregado com sucesso.")
        except FileNotFoundError:
            self.model = RandomForestRegressor(n_estimators=100, random_state=42)
            # Inicializar com dados sintéticos representativos
            dummy_data = []
            dummy_targets = []
            
            for latency in [50, 100, 200]:
                for packet_loss in [0.1, 0.5, 1]:
                    for bandwidth in [5000, 10000, 20000]:
                        for cpu_usage in [20, 50, 80]:
                            for memory_usage in [30, 60, 90]:
                                features = [latency, packet_loss, bandwidth, cpu_usage, memory_usage]
                                # Suposição: QoE diminui com alta latência, perda de pacotes, alto uso de CPU/memória
                                qoe = self.calculate_qoe(latency, packet_loss, bandwidth, cpu_usage, memory_usage)
                                dummy_data.append(features)
                                dummy_targets.append(qoe)
            dummy_data = np.array(dummy_data)
            dummy_targets = np.array(dummy_targets)
            self.scaler.fit(dummy_data)
            scaled_data = self.scaler.transform(dummy_data)
            self.model.fit(scaled_data, dummy_targets)
            self.server_mapping = {}
            joblib.dump(self.model, 'server_selection_model.joblib')
            joblib.dump(self.scaler, 'server_selection_scaler.joblib')
            joblib.dump(self.server_mapping, 'server_mapping.joblib')
            logging.info("Modelo de seleção de servidor treinado com dados sintéticos.")

    def calculate_qoe(self, latency, packet_loss, bandwidth, cpu_usage, memory_usage):
        # Fórmula simplificada para QoE
        qoe = 5 - (latency / 100) - (packet_loss / 2) - (cpu_usage / 100) - (memory_usage / 100)
        qoe += bandwidth / 100000  # Benefício de maior largura de banda
        qoe = max(min(qoe, 5), 1)
        return qoe

    def predict_best_server(self, network_conditions, available_servers):
        if not available_servers:
            logging.warning("Nenhum servidor disponível para seleção.")
            return None

        server_metrics = self.get_server_metrics(available_servers)
        qoe_predictions = []

        for metrics in server_metrics:
            features = [
                network_conditions['latency'],
                network_conditions['packet_loss'],
                network_conditions['bandwidth'],
                metrics['cpu_usage'],
                metrics['memory_usage']
            ]
            input_data = np.array([features])
            try:
                input_data_scaled = self.scaler.transform(input_data)
            except Exception as e:
                logging.error(f"Erro ao escalar dados de entrada: {e}")
                continue

            with self.lock:
                try:
                    qoe_pred = self.model.predict(input_data_scaled)[0]
                except Exception as e:
                    logging.error(f"Erro na predição do modelo: {e}")
                    qoe_pred = 0  # Valor padrão de QoE baixo

            qoe_predictions.append((qoe_pred, metrics['server_name']))

        if not qoe_predictions:
            logging.warning("Nenhuma previsão de QoE disponível.")
            return None

        # Selecionar o servidor com a maior previsão de QoE
        best_server = max(qoe_predictions, key=lambda x: x[0])[1]
        logging.info(f"Servidores disponíveis e previsões de QoE: {qoe_predictions}")
        logging.info(f"Servidor selecionado pelo método IA: {best_server}")

        return best_server

    def get_server_metrics(self, available_servers):
        metrics = []
        for server in available_servers:
            server_name = server[0]
            try:
                cpu_usage = monitor.get_cpu_usage(server_name)
                memory_usage = monitor.get_memory_usage(server_name)
            except AttributeError:
                logging.warning(f"Não foi possível obter métricas para {server_name}. Usando valores padrão.")
                cpu_usage = 0
                memory_usage = 0
            
            metrics.append({
                'server_name': server_name,
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage
            })
        return metrics

    def update_model(self, network_conditions, selected_server, performance, available_servers):
        if not selected_server:
            logging.warning("Nenhum servidor selecionado para atualização do modelo.")
            return

        
        server_metrics = self.get_server_metrics(available_servers)
        selected_metrics = next((metrics for metrics in server_metrics if metrics['server_name'] == selected_server), None)
        if selected_metrics is None:
            logging.warning(f"Métricas do servidor {selected_server} não encontradas.")
            return

        features = [
            network_conditions['latency'],
            network_conditions['packet_loss'],
            network_conditions['bandwidth'],
            selected_metrics['cpu_usage'],
            selected_metrics['memory_usage']
        ]

        with self.lock:
            self.data_buffer.append(features)
            self.target_buffer.append(performance)  # QoE real obtida
            self.sample_count += 1

            if self.sample_count >= self.update_threshold:
                self._perform_model_update()

    def _perform_model_update(self):
        X = np.array(self.data_buffer)
        y = np.array(self.target_buffer)

        if len(X) == 0:
            logging.warning("Nenhum dado disponível para atualização do modelo.")
            return

        self.scaler.fit(X)
        X_scaled = self.scaler.transform(X)

        try:
            self.model.fit(X_scaled, y)
        except Exception as e:
            logging.error(f"Erro ao treinar o modelo: {e}")
            return

        joblib.dump(self.model, 'server_selection_model.joblib')
        joblib.dump(self.scaler, 'server_selection_scaler.joblib')

        self.sample_count = 0
        logging.info(f"Modelo atualizado com {len(X)} amostras.")

    def get_model_performance(self):
        with self.lock:
            return {
                "samples_collected": len(self.data_buffer),
                "updates_performed": self.sample_count // self.update_threshold
            }
