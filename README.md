# Explorando Estratégias de Content Steering para Transmissões de Vídeo Adaptativas

Este projeto apresenta um sistema adaptativo de content steering desenvolvido para otimizar o streaming de vídeo em ambientes edge-cloud. A solução combina gerenciamento dinâmico de servidores de cache com controle adaptativo de condições de rede, utilizando tecnologias como Docker para simular uma infraestrutura distribuída e um dashboard web para monitoramento e controle em tempo real. Com suporte a diferentes presets de rede (2G a Fiber) e métodos de seleção de servidores baseados em métricas tradicionais e Inteligência Artificial, o sistema oferece uma abordagem para manter a Qualidade de Experiência (QoE) mesmo em cenários adversos. Além disso, a arquitetura modular, a geração de gráficos e o sistema de logging facilitam análises detalhadas e futuras expansões, tornando esta solução uma contribuição prática para o campo do streaming adaptativo.

## Tutorial de Configuração do Projeto

### Passo a Passo

Este tutorial descreve como configurar e executar o projeto adaptativo de **content steering** em uma máquina virtual (VM) utilizando o VirtualBox.

### 1. Baixar os Arquivos Necessários
- O arquivo `.ova` (imagem da VM) está disponível no link:  
  [Download da Máquina Virtual](https://drive.google.com/file/d/15MfoyMp_JRJUxL6LIcwKE7o_nVePt80T/view?usp=sharing).  
- O software de virtualização **VirtualBox** pode ser baixado aqui:  
  [Download do VirtualBox](https://www.virtualbox.org/).
 
**Dica**: Para um melhor desempenho, ajuste os recursos da máquina virtual (número de núcleos de CPU e memória RAM) de acordo com as especificações do seu hardware.

---

### 2. Configurar a Máquina Virtual
1. **Instale o VirtualBox**.
2. No VirtualBox, acesse o menu:  
   **Arquivo → Importar Appliance**.  
3. Selecione o arquivo `.ova` que você baixou e conclua o processo de importação.

**Observação 1**: Sempre que for solicitado uma senha no terminal (ao usar comandos `sudo`), utilize a senha padrão: `tutorial`.

---

### 3. Iniciar a Aplicação
1. **Inicie a VM**.
2. Acesse o diretório onde o script de inicialização dos servidores está localizado:  
   ```
   /home/tutorial/Documents/content-steering-tutorial/streaming-service
   ```
3. Execute o script `update_servers.sh` no terminal com o comando:  
   ```bash
   sudo ./update_servers.sh
   ```
   Este script inicializa os servidores de cache responsáveis pela distribuição de conteúdo.

4. Vá para o diretório da aplicação principal:  
   ```
   /home/tutorial/Documents/content-steering-tutorial/steering-service/src
   ```
5. Execute o script `run_and_capture.sh` com o comando:  
   ```bash
   sudo ./run_and_capture.sh
   ```
   **O que este script faz:**  
   - Limpa logs anteriores.  
   - Libera a porta 30500, se necessário.  
   - Inicia a captura de tráfego para análise.  
   - Inicializa a aplicação Python principal.

---

### 4. Testar a Interface Web
1. Acesse a interface web no navegador através do endereço:  
   [http://localhost:30500](http://localhost:30500).

2. Para testar, utilize os links de arquivos manifestos (com diferentes codecs) disponíveis no seguinte diretório:  
   [Arquivos Manifestos](https://ftp.itec.aau.at/datasets/mmsys22/Eldorado/4sec/).  

   - **Codec AV1:**  
     [Manifesto AV1](https://ftp.itec.aau.at/datasets/mmsys22/Eldorado/4sec/av1/manifest.mpd)  
   - **Codec AVC:**  
     [Manifesto AVC](https://ftp.itec.aau.at/datasets/mmsys22/Eldorado/4sec/avc/manifest.mpd)  

   **Dica**: Insira esses links na interface web no campo de URL para iniciar o teste.

---

### 5. Encerrar a Aplicação
- Para finalizar a aplicação, clique no botão **Encerrar Aplicação** no canto superior direito da interface web.  

---

### 6. Analisar os Resultados
- Os gráficos gerados após a execução do sistema estão disponíveis na pasta:  
  ```
  /graphs
  ```

**Observação**: Alguns codecs, como **HEVC** ou **VVC**, podem não ser suportados pelo navegador ou player **DASH** utilizado. Nesse caso, apenas o áudio será reproduzido, sem a imagem.

---







