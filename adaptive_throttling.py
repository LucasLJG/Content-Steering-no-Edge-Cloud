import time
import logging
from network_control import network_control

class AdaptiveThrottling:
    def __init__(self, update_interval=30, performance_window=10):
        self.update_interval = update_interval
        self.performance_window = performance_window
        self.last_update_time = 0
        self.performance_history = []
        self.min_bandwidth = 100  # 100 Kbit/s
        self.max_bandwidth = 1000000000  # 1 Gbit/s
        self.last_manual_update = 0
        self.cool_down_period = 30  # Segundos

    def update(self, current_performance):
        self.performance_history.append(current_performance)
        self.performance_history = self.performance_history[-self.performance_window:]

        current_time = time.time()
        if current_time - self.last_update_time >= self.update_interval:
            self._adjust_network_conditions()
            self.last_update_time = current_time

    def _adjust_network_conditions(self):
        if len(self.performance_history) < self.performance_window:
            return

        if time.time() - self.last_manual_update < self.cool_down_period:
            logging.info("Em período de cool down após atualização manual. Pulando ajuste adaptativo.")
            return

        weights = [i / sum(range(1, len(self.performance_history) + 1)) for i in range(1, len(self.performance_history) + 1)]
        avg_latency = sum(p['latency'] * w for p, w in zip(self.performance_history, weights))
        avg_packet_loss = sum(p['packet_loss'] * w for p, w in zip(self.performance_history, weights))
        avg_bandwidth = sum(p['bandwidth'] * w for p, w in zip(self.performance_history, weights))

        current_conditions = network_control.get_current_conditions()

        new_latency = self._adjust_metric(current_conditions['latency'], avg_latency, 'latency')
        new_packet_loss = self._adjust_metric(current_conditions['packet_loss'], avg_packet_loss, 'packet_loss')
        new_bandwidth = self._adjust_metric(current_conditions['bandwidth'], avg_bandwidth, 'bandwidth')

        network_control.update_conditions(latency=new_latency, packet_loss=new_packet_loss, bandwidth=new_bandwidth)
        logging.info(f"Throttling adaptativo ajustou as condições de rede: Latência={new_latency}ms, Perda de Pacotes={new_packet_loss}%, Largura de Banda={new_bandwidth}kbit/s")

    def _adjust_metric(self, current_value, avg_value, metric_name):
        adjustment_factor = 0.1  # Ajuste de 10%

        if metric_name == 'latency' or metric_name == 'packet_loss':
            delta = (avg_value - current_value) * adjustment_factor
            new_value = current_value + delta
            new_value = max(new_value, 1 if metric_name == 'latency' else 0)
        elif metric_name == 'bandwidth':
            delta = (avg_value - current_value) * adjustment_factor
            new_value = current_value + delta
            new_value = max(min(new_value, self.max_bandwidth), self.min_bandwidth)
        else:
            new_value = current_value

        return new_value

    def manual_update(self):
        self.last_manual_update = time.time()
        logging.info("Atualização manual detectada. Entrando em período de cool down.")

# Criar uma única instância para ser usada em toda a aplicação
adaptive_throttling = AdaptiveThrottling()

