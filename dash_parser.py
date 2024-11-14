import math
import logging
from network_control import resolve_server_ip

class DashParser:
    def __init__(self):
        self.weights = {
            'latency': 0.3,
            'packet_loss': 0.3,
            'bandwidth': 0.4
        }
        self.bandwidth_threshold = 1000000  # 1 Gbps

    def build(self, target, nodes, uri, request, network_conditions, selected_server=None):
        message = {}
        message['VERSION'] = 1
        message['TTL'] = 10
        message['RELOAD-URI'] = f'{uri}{request.path}'

        sorted_nodes = self.sort_nodes_by_conditions(nodes, self.dict_to_tuple(network_conditions))

        message["PATHWAY-PRIORITY"] = [node[0] for node, _ in sorted_nodes] + ['cloud']

        if selected_server:
            if selected_server in message["PATHWAY-PRIORITY"]:
                message["PATHWAY-PRIORITY"].remove(selected_server)
            message["PATHWAY-PRIORITY"].insert(0, selected_server)

        if nodes:
            message['PATHWAY-CLONES'] = self.pathway_clones(sorted_nodes)

        steering_info = {
            "selected_server": message["PATHWAY-PRIORITY"][0] if message["PATHWAY-PRIORITY"] else 'cloud',
            "all_servers": message["PATHWAY-PRIORITY"],
            "network_conditions": network_conditions,
            "sorted_nodes": [(node[0], score) for node, score in sorted_nodes]
        }

        logging.info(f"Manifesto construído: Prioridade={message['PATHWAY-PRIORITY']}")

        return message, steering_info

    def pathway_clones(self, nodes):
        return [
            {
                'BASE-ID': 'cloud',
                'ID': node[0],
                'URI-REPLACEMENT': {
                    'HOST': f'http://{node[1]}'
                }
            } for node, _ in nodes if node[0].startswith('video-streaming-cache-')
        ]

    def sort_nodes_by_conditions(self, nodes, network_conditions):
        scored_nodes = [(node, self.calculate_node_score(node, network_conditions)) for node in nodes]
        sorted_nodes = sorted(scored_nodes, key=lambda x: x[1], reverse=True)
        return sorted_nodes

    def calculate_node_score(self, node, network_conditions):
        latency, packet_loss, bandwidth = network_conditions

        node_latency = latency
        node_packet_loss = packet_loss
        node_bandwidth = bandwidth

        latency_score = self.sigmoid(node_latency, midpoint=100, steepness=0.05)
        packet_loss_score = self.sigmoid(node_packet_loss, midpoint=2, steepness=2)
        bandwidth_score = self.sigmoid(node_bandwidth, midpoint=self.bandwidth_threshold, steepness=0.00001)

        total_score = (
            self.weights['latency'] * (1 - latency_score) +
            self.weights['packet_loss'] * (1 - packet_loss_score) +
            self.weights['bandwidth'] * bandwidth_score
        )

        return total_score

    @staticmethod
    def sigmoid(x, midpoint, steepness):
        try:
            return 1 / (1 + math.exp(-steepness * (x - midpoint)))
        except OverflowError:
            return 0 if x < midpoint else 1

    @staticmethod
    def dict_to_tuple(d):
        return (d.get('latency', 0), d.get('packet_loss', 0), d.get('bandwidth', 0))

    def update_weights(self, new_weights):
        self.weights.update(new_weights)
        logging.info(f"Pesos atualizados: {self.weights}")

    def update_bandwidth_threshold(self, new_threshold):
        self.bandwidth_threshold = new_threshold
        logging.info(f"Limite de largura de banda atualizado: {self.bandwidth_threshold}")

# Criar uma única instância para ser usada em toda a aplicação
dash_parser = DashParser()

if __name__ == "__main__":
    # Teste da classe DashParser
    logging.basicConfig(level=logging.INFO)
    
    # Simular nós e condições de rede
    test_nodes = [
        ('video-streaming-cache-1', '172.18.0.3'),
        ('video-streaming-cache-2', '172.18.0.4'),
        ('video-streaming-cache-3', '172.18.0.5')
    ]
    test_conditions = {'latency': 50, 'packet_loss': 0.5, 'bandwidth': 10000}
    
    # Construir manifesto de teste
    test_message, test_info = dash_parser.build(
        target='test',
        nodes=test_nodes,
        uri='http://localhost:30500',
        request=type('obj', (object,), {'path': '/test'})(),
        network_conditions=test_conditions,
        selected_server='video-streaming-cache-2'
    )
    
    # Exibir resultados
    logging.info("Manifesto de teste construído:")
    logging.info(f"PATHWAY-PRIORITY: {test_message['PATHWAY-PRIORITY']}")
    logging.info(f"PATHWAY-CLONES: {test_message['PATHWAY-CLONES']}")
    logging.info(f"Informações de steering: {test_info}")
