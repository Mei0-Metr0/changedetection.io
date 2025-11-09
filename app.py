import requests
import sys
import time
import logging
from tqdm import tqdm
from bs4 import BeautifulSoup
import urllib3
import re
import datetime
import os
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

FILTRAR_POR_ANO = os.getenv('FILTRAR_POR_ANO', 'True').lower() in ('true', '1', 't')
RAW_PHASES = os.getenv('RUN_PHASES', '0,1,2')
RUN_PHASES = {int(p.strip()) for p in RAW_PHASES.split(',') if p.strip().isdigit()}
CDIO_BASE_URL = os.getenv("CDIO_BASE_URL", "http://localhost:5000")
CDIO_API_KEY = os.getenv("CDIO_API_KEY")
CDIO_TAG = os.getenv("CDIO_TAG", "estudenautfpr")
DATA_DIR = os.getenv('DATA_DIR', '/app/data')

os.makedirs(DATA_DIR, exist_ok=True)

# --- CONFIGURAÇÃO DO LOG ---
log_filename = os.path.join(DATA_DIR, 'import_log.txt')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
URLS_INICIAIS = ["https://www.utfpr.edu.br/cursos/estudenautfpr"]
ano_atual = datetime.date.today().year
ANOS_PERMITIDOS = {str(y) for y in range(ano_atual - 2, ano_atual + 1)}

def url_e_permitida_pelo_ano(url):
    """Verifica se uma URL é permitida com base no ano encontrado nela"""
    anos_encontrados_na_url = set(re.findall(r'20\d{2}', url))
    if not anos_encontrados_na_url:
        return True
    return bool(anos_encontrados_na_url.intersection(ANOS_PERMITIDOS))

# --- FASE 0: LIMPEZA DE DUPLICATAS ---
def apagar_urls_duplicadas(headers):
    logging.info("--- INICIANDO FASE 0: Limpeza de Duplicatas ---")
    api_url = f"{CDIO_BASE_URL}/api/v1/watch"
    try:
        response = requests.get(api_url, headers=headers, timeout=60)
        response.raise_for_status()
        watches = response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"LIMPEZA: Erro ao buscar monitores: {e}. Abortando fase 0.")
        return

    urls_vistas = defaultdict(list)
    for uuid, details in watches.items():
        if isinstance(details, dict) and 'url' in details:
            urls_vistas[details['url']].append(uuid)

    total_duplicatas_removidas = 0
    for url, uuids in urls_vistas.items():
        if len(uuids) > 1:
            uuids_para_apagar = uuids[1:]
            logging.warning(f"LIMPEZA: URL duplicada encontrada: {url}. Mantendo {uuids[0]}, apagando {len(uuids_para_apagar)} cópia(s).")
            for uuid_para_apagar in uuids_para_apagar:
                delete_url = f"{CDIO_BASE_URL}/api/v1/watch/{uuid_para_apagar}"
                try:
                    del_response = requests.delete(delete_url, headers=headers, timeout=20)
                    del_response.raise_for_status()
                    logging.info(f"  -> Sucesso ao apagar {uuid_para_apagar}")
                    total_duplicatas_removidas += 1
                except requests.exceptions.RequestException as e:
                    logging.error(f"  -> Falha ao apagar {uuid_para_apagar}: {e}")
    
    if total_duplicatas_removidas == 0:
        logging.info("LIMPEZA: Nenhuma URL duplicada encontrada.")
    else:
        logging.info(f"LIMPEZA: Fase finalizada. {total_duplicatas_removidas} monitores duplicados removidos.")

# --- FASE 1: COLETA DE DADOS ---
def coletar_e_salvar_urls_incrementalmente():
    logging.info("--- INICIANDO FASE 1: Coleta de URLs ---")
    if FILTRAR_POR_ANO:
        logging.info(f"COLETA: Filtro de ano ativado para os anos: {sorted(list(ANOS_PERMITIDOS), reverse=True)}")
    else:
        logging.info("COLETA: Filtro de ano desativado.")
    
    urls_para_visitar = set(URLS_INICIAIS)
    urls_processadas = set()
    
    nome_arquivo_saida = os.path.join(DATA_DIR, "urls_coletadas.txt")
    logging.info(f"COLETA: URLs serão salvas em '{nome_arquivo_saida}'.")
    
    with open(nome_arquivo_saida, "w", encoding="utf-8") as output_file:
        with tqdm(desc="Analisando Páginas", unit="página") as pbar:
            while urls_para_visitar:
                url = urls_para_visitar.pop()
                if url in urls_processadas:
                    continue
                
                urls_processadas.add(url)
                pbar.update(1)
                pbar.set_postfix_str(f"Analisando: {url[:70]}...")

                try:
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                    resp = requests.get(url, headers=headers, verify=False, timeout=15)
                    resp.raise_for_status()
                    output_file.write(url + "\n")
                    soup = BeautifulSoup(resp.text, "lxml")

                    for link in soup.find_all("a", href=True):
                        href = link["href"]
                        if "/estudenautfpr/" in href:
                            if href.startswith("/"):
                                href = "https://www.utfpr.edu.br" + href
                            if href.startswith("https://www.utfpr.edu.br"):
                                url_limpa = href.split("#")[0]
                                if url_limpa not in urls_processadas:
                                    urls_para_visitar.add(url_limpa)
                except requests.exceptions.RequestException as e:
                    logging.error(f"COLETA: Erro ao analisar {url}: {e}")

    logging.info(f"COLETA: Fase finalizada. {len(urls_processadas)} URLs únicas salvas.")
    return nome_arquivo_saida

# --- FASE 2: ENVIO PARA A API ---
def importar_urls_do_arquivo(nome_arquivo):
    logging.info("--- INICIANDO FASE 2: Importação para a API ---")
    
    api_headers = {"Content-Type": "application/json", "x-api-key": CDIO_API_KEY}
    
    # 1. Obter URLs já existentes na API
    logging.info("API: Buscando lista de URLs já existentes...")
    try:
        response = requests.get(f"{CDIO_BASE_URL}/api/v1/watch", headers=api_headers, timeout=60)
        response.raise_for_status()
        watches = response.json()
        urls_existentes = {details['url'] for uuid, details in watches.items() if isinstance(details, dict) and 'url' in details}
        logging.info(f"API: Encontradas {len(urls_existentes)} URLs já monitoradas.")
    except requests.exceptions.RequestException as e:
        logging.error(f"API: Erro fatal ao buscar URLs existentes: {e}. Abortando fase 2.")
        return

    # 2. Ler URLs do arquivo coletado
    try:
        with open(nome_arquivo, 'r', encoding='utf-8') as f:
            urls_coletadas = {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        logging.error(f"API: Erro - O arquivo '{nome_arquivo}' não foi encontrado para importação.")
        return
    
    # 3. Filtrar URLs (por ano e por existência na API)
    urls_filtradas_por_ano = {url for url in urls_coletadas if url_e_permitida_pelo_ano(url)} if FILTRAR_POR_ANO else urls_coletadas
    urls_para_enviar = urls_filtradas_por_ano - urls_existentes
    
    if not urls_para_enviar:
        logging.info("IMPORTAÇÃO: Nenhuma URL nova para adicionar.")
        return
        
    logging.info(f"IMPORTAÇÃO: {len(urls_para_enviar)} novas URLs para importar. Iniciando envio...")
    contadores = {"sucesso": 0, "falha": 0}

    for url in tqdm(sorted(list(urls_para_enviar)), desc="Enviando para API", unit="url", ncols=100):
        # 4. Enviar para a API
        api_url_post = f"{CDIO_BASE_URL}/api/v1/watch"
        payload = {"url": url, "tag": CDIO_TAG}
        try:
            post_response = requests.post(api_url_post, headers=api_headers, json=payload, timeout=20)
            if post_response.ok:
                contadores["sucesso"] += 1
            else:
                post_response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"API: Falha ao enviar URL: {url} -> {e}")
            contadores["falha"] += 1
        time.sleep(0.05)

    logging.info("--- Resumo da Importação para API ---")
    logging.info(f"URLs novas adicionadas com sucesso: {contadores['sucesso']}")
    logging.info(f"URLs que falharam no envio: {contadores['falha']}")

def main():
    """Função que orquestra a execução das fases selecionadas."""
    logging.info(f"Iniciando script. Fases a serem executadas: {sorted(list(RUN_PHASES))}")
    
    if not CDIO_API_KEY:
        logging.critical("CRÍTICO: Chave de API (CDIO_API_KEY) não configurada no .env. Abortando.")
        return

    api_headers = {"x-api-key": CDIO_API_KEY}

    # FASE 0 (Opcional)
    if 0 in RUN_PHASES:
        apagar_urls_duplicadas(api_headers)

    # FASE 1
    urls_coletadas_arquivo = os.path.join(DATA_DIR, "urls_coletadas.txt")
    if 1 in RUN_PHASES:
        coletar_e_salvar_urls_incrementalmente()
    
    # FASE 2
    if 2 in RUN_PHASES:
        importar_urls_do_arquivo(urls_coletadas_arquivo)
    
    logging.info("--- PROCESSAMENTO FINALIZADO ---")
    logging.info(f"Log completo salvo em: {log_filename}")

if __name__ == "__main__":
    main()
