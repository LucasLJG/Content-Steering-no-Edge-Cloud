# Content-Steering-no-Edge-Cloud

Este projeto apresenta um sistema adaptativo de content steering desenvolvido para otimizar o streaming de vídeo em ambientes edge-cloud. A solução combina gerenciamento dinâmico de servidores de cache com controle adaptativo de condições de rede, utilizando tecnologias como Docker para simular uma infraestrutura distribuída e um dashboard web para monitoramento e controle em tempo real. Com suporte a diferentes presets de rede (2G a Fiber) e métodos de seleção de servidores baseados em métricas tradicionais e Inteligência Artificial, o sistema oferece uma abordagem robusta para manter a Qualidade de Experiência (QoE) mesmo em cenários adversos. Além disso, a arquitetura modular, a geração de gráficos e o sistema de logging facilitam análises detalhadas e futuras expansões, tornando esta solução uma contribuição prática e eficiente para o campo do streaming adaptativo.

## Tutorial de Configuração do Projeto.
O arquivo de extensão .ova está disponível no Drive no link: https://drive.google.com/file/d/15MfoyMp_JRJUxL6LIcwKE7o_nVePt80T/view?usp=sharing.  
O projeto foi desenvolvido inteiramente utilizando o sistema operacional linux e rodando uma VM sobre o linux. O software de virtualização (VirtualBox) utilizado encontra-se disponível no link: https://www.virtualbox.org/.  
Observação 1: Foi testado o sistema operacional Windows e também funcionou corretamente, porém lembre-se de modificar a quantidade de núcleos e memória ram conforme disponível em sua máquina para o bom funcionamento da máquina virtual.
Após instalado corretamente o VirtualBox, vá no menu Arquivo -> Importar Appliance -> Selecione o arquivo .ova no diretório onde foi baixado e espere a importação finalizar.  
Observação 2: Sempre que solicitar senha (especialmente com comandos sudo no terminal) digite tutorial  
1) Inicie a VM
2) Vá para o diretório: /home/tutorial/Documents/content-steering-tutorial/streaming-service e execute o script de nome update_servers.sh no terminal através do comando: sudo ./update_servers.sh. Esse script inicializará os servidores de cache responsáveis pela distribuição de conteúdo.
3) Em seguida, inicie a aplicação no diretório /home/tutorial/Documents/content-steering-tutorial/steering-service/src executando o script de nome run and capture.sh no terminal utilizando o comando sudo ./run_and_capture.sh. Este script realiza diversas tarefas cruciais para o funcionamento do sistema: limpa logs anteriores, verifica e libera a porta 30500 se necessário, inicia a captura de tráfego para análise posterior e inicializa a aplicação Python principal.
4) A interface web será iniciada no seguinte endereço: http://localhost:30500.
5) O link: https://ftp.itec.aau.at/datasets/mmsys22/Eldorado/4sec/ contém os arquivos manifestos com os diferentes codecs. Por exemplo, o codec av1 possui link: https://ftp.itec.aau.at/datasets/mmsys22/Eldorado/4sec/av1/manifest.mpd, enquanto que o codec avc possui link: https://ftp.itec.aau.at/datasets/mmsys22/Eldorado/4sec/avc/manifest.mpd. Teste eles na aplicação inserindo esses links na url do campo na interface web.
6) Para encerrar a aplicação, clique no botão chamado Encerrar Aplicação no canto superior direito.
7) Os gráficos gerados após a execução da aplicação estão na pasta graphs.  
Observação: Há codecs que o navegador ou o player dash ainda não tem suporte (hevc ou vvc), então o player vai reproduzir somente o áudio, porém sem a imagem.






