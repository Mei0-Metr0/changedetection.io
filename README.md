# Sobre
Este projeto automatiza a coleta de URLs de um site específico e as importa para uma instância do changedetection.io, tudo orquestrado com Docker e Docker Compose.

O processo é dividido em fases:
   - Fase 0 (Opcional): Limpeza de URLs duplicadas já existentes no changedetection.io.
   - Fase 1: Coleta Incremental: Navega pelo site da UTFPR, encontra URLs relevantes e as salva em um arquivo de texto (`urls_coletadas.txt`).
   - Fase 2: Importação: Lê o arquivo de texto gerado, compara com as URLs já monitoradas na API, e envia apenas as novas URLs.

## Pré-requisitos:
   - Docker e Docker Compose.

## Como Rodar:
   - Passo 1: Descompacte o arquivo.
   
   - Passo 2: Configurar o Arquivo de Credenciais `(.env)` baseado no `.env.example`:

      Atenção: O `CDIO_BASE_URL` deve ser `http://changedetection:5000`, pois os contêineres se comunicam usando os nomes dos serviços definidos no docker-compose.yml.

   - Passo 3: Restaurar os Dados do Volume (Opcional):
      1. Crie o volume vazio: 
      
         Execute o `docker-compose` para que ele crie a estrutura do volume.
         ```bash
         docker-compose up -d changedetection
         ```

         Aguarde alguns segundos e então pare o serviço para liberar o volume:
         ```bash
         docker-compose down
         ```

      2. Restaure o backup:

         Execute o comando correspondente ao seu sistema operacional para descompactar os dados do backup para dentro do volume. (Lembre-se de substituir nome-do-projeto pelo nome da pasta do seu projeto).

         - No Linux:
            ```bash
            sudo tar -xzvf changedetection-data-backup.tar.gz -C "$(docker volume inspect -f '{{.Mountpoint}}' nome-do-projeto_changedetection-data)"
            ```

         - No Windows (com WSL 2, usando PowerShell):
            ```bash
            docker run --rm -v nome-do-projeto_changedetection-data:/volume_data -v "${pwd}:/backup" alpine tar -xzvf /backup/changedetection-data-backup.tar.gz -C /volume_data
            ```

   - Passo 4: Construir e Iniciar os Serviços:
      1. Construa a imagem do script importador:
         ```bash
         docker-compose build url-importer
         ```

      2. Inicie o serviço do changedetection.io:
         ```bash
         docker-compose up -d changedetection
         ```

         Após a execução, você pode acessar a interface web em `http://localhost:5000`.

   - Passo 5: Executar o Script de Coleta e Importação:
      O script de coleta não roda continuamente. Ele foi projetado para ser executado como uma tarefa.

      Para executar o processo completo de coleta e importação agora, use o seguinte comando:
      ```bash
      docker-compose run --rm url-importer
      ```

      - Este comando irá:
         1. Iniciar um contêiner temporário usando a imagem `url-importer`.
         2. Executar o `app.py` dentro dele.
         3. Exibir todo o progresso e os logs no seu terminal.
         4. Remover o contêiner `(--rm)` ao final da execução, mantendo seu sistema limpo.


      <hr>
      Funcionalidades Opcionais no `app.py`:
      <hr>
      Você pode personalizar o comportamento do script alterando as variáveis de configuração no topo do arquivo `app.py`:
      
      - RUN_PHASES = 0,1,2
         - Escolha das fases a ser executada, pode ser todas, ou pode configurar para executar cada uma de forma isolada, mais detalhes veja o arquivo de exemplo `.env.examples`.

      - FILTRAR_POR_ANO = False
         - Se definido como False, o script irá coletar e importar todas as URLs encontradas que contenham /estudenautfpr/, ignorando o filtro que restringe aos três anos mais recentes.