"""
Configurações globais e constantes do projeto PromaX Automation.
"""

import os
import logging
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Diretórios
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
SRC_DIR = BASE_DIR / "src"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
DOWNLOAD_DIR = DATA_DIR / "arquivos"

# Cria diretórios se não existirem
LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

# PromaX
PROMAX_URL = os.getenv("PROMAX_URL", "https://dibrasa.promaxcloud.com.br/")
PROMAX_DEFAULT_USER = os.getenv("PROMAX_DEFAULT_USER", "filipe")
PROMAX_DEFAULT_PASSWORD = os.getenv("PROMAX_DEFAULT_PASSWORD", "Acene003")

# Gerenciador de Arquivos — app separado (mesmas credenciais do PromaX) usado
# para localizar/baixar arquivos que algumas rotinas (ex: 01.31.60) geram
# diretamente no servidor, em pastas compartilhadas como ..\integ\dvs\, sem
# oferecer download direto no navegador da tela da rotina.
FILE_MANAGER_URL = os.getenv("FILE_MANAGER_URL", f"http://{urlparse(PROMAX_URL).hostname}:8080")

# API WKRADAR — endpoint real fica numa rede interna (172.20.5.0/24). Em dev
# local no Windows (Docker Desktop), o container não consegue rotear até lá
# mesmo com o WSL2 em modo de rede "mirrored" (limitação de isolamento de
# rede dos containers no Docker Desktop) — por isso, nesse ambiente,
# WKRADAR_TOKEN_URL é sobrescrita via variável de ambiente para apontar a um
# proxy TCP rodando fora do Docker, direto no WSL2 (veja
# src/integrations/wkradar_client.py e o serviço systemd 'wkradar-proxy' na
# distro WSL2). Em produção (fora deste setup), usa o endpoint real direto.
WKRADAR_TOKEN_URL = os.getenv("WKRADAR_TOKEN_URL", "https://172.20.5.8/wk.api/api/v1/token")

# API BPO ACENE — recebe os relatórios do PromaX (arquivo original, como foi
# baixado) para o sistema de integração contábil. Endereço base do servidor
# (ex: https://bpo.acene.com.br); o caminho /api/bpo/promax é acrescentado
# pelo client. Vazio = envio desligado. O token é por empresa (cadastro da
# empresa, criptografado) — veja src/integrations/bpo_acene_client.py.
BPO_ACENE_URL = os.getenv("BPO_ACENE_URL", "").rstrip("/")
BPO_ACENE_VERIFY_SSL = os.getenv("BPO_ACENE_VERIFY_SSL", "True").lower() == "true"
# Rotinas cujos arquivos são enviados, pelo código PromaX (separadas por vírgula).
BPO_ACENE_ROTINAS = [
    r.strip()
    for r in os.getenv("BPO_ACENE_ROTINAS", "14.05.05,12.06.04,12.04.07.03,16.03.08,01.20.04,01.20.12").split(",")
    if r.strip()
]
# Cópias dos arquivos aguardando envio (o original é apagado após a importação no Postgres).
BPO_ACENE_OUTBOX_DIR = DATA_DIR / "envios_bpo"
BPO_ACENE_OUTBOX_DIR.mkdir(exist_ok=True)

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'promax.db'}")

# Postgres — usado apenas para as tabelas dinâmicas de dados de relatório
# (map_col_rel_rotina), a configuração principal (empresas, rotinas,
# execuções) continua no SQLite acima.
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "promax")
POSTGRES_USER = os.getenv("POSTGRES_USER", "promax_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "promax_password")
POSTGRES_URL = (
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-in-production")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "dev-encryption-key")

# WebDriver
# BROWSER: "chrome" (padrão) ou "edge_ie" (Edge em modo de Compatibilidade com
# Internet Explorer — necessário para telas do PromaX que usam VBScript,
# só suportado em IE / IE mode do Edge).
BROWSER = os.getenv("BROWSER", "chrome").lower()
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", None)
IEDRIVER_PATH = os.getenv("IEDRIVER_PATH", None)
EDGE_EXECUTABLE_PATH = os.getenv(
    "EDGE_EXECUTABLE_PATH",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)
HEADLESS = os.getenv("HEADLESS", "False").lower() == "true"
WINDOW_SIZE = os.getenv("WINDOW_SIZE", "1920,1080")

# User-Agent customizado (ex: spoof de IE7) — apenas altera o cabeçalho
# User-Agent enviado ao servidor. NÃO faz o Chromium executar VBScript/ActiveX
# nem renderizar com o motor Trident; é só para o caso da tela fazer sniffing
# de UA no servidor/JS sem realmente depender de APIs exclusivas do IE.
USER_AGENT = os.getenv("USER_AGENT", None)
IE7_USER_AGENT = "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.1)"

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = LOGS_DIR / "automation.log"

# Setup Logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

# Flask
FLASK_ENV = os.getenv("FLASK_ENV", "development")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "True").lower() == "true"

# Scheduler
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")

# Timeouts
SELENIUM_WAIT_TIMEOUT = 10
SELENIUM_IMPLICIT_WAIT = 5

# VPN (FortiClient) — o PromaX da Dibrasa só é acessível com a VPN conectada.
# Verificação por conectividade direta ao host (ver src/browser/vpn_check.py),
# não pelo status do adaptador de rede (se mostrou pouco confiável).
VPN_CHECK_ENABLED = os.getenv("VPN_CHECK_ENABLED", "True").lower() == "true"

# Selectors (CSS/XPath)
# Extraídos de telas/PromaxWEB principal login_files/PP00100.html (tela real de login)
SELECTORS = {
    "login_form": ".TableTop",
    "username_input": "input[name='Usuario']",
    "password_input": "input[name='Senha']",
    "login_button": "input[name='cmdConfirma']",
    # Tela de seleção de Unidade não foi capturada nos arquivos de referência;
    # os seletores abaixo são melhores-esforços e tolerantes a falha.
    "unit_selector": "select",
    "unit_link_xpath": "//a[contains(., '{unit}')] | //*[@onclick][contains(., '{unit}')]",
    "confirm_button": "input[type='submit'], input.Btn",
    "shortcut_input": "input[name='atalho']",
}

# PromaX Routines Configuration
AVAILABLE_ROUTINES = {
    "14.05.05": {
        "name": "Lançamentos",
        "description": "Rotina de lançamentos/entries",
        "url_path": "/pw/cgi-bin/PP00100.exe",
        "url_params": {
            "ppopcao": "7",
            "call": "140505000000",
        }
    },
    # Adicione mais rotinas aqui
}

# Alerts e popups
MAX_ALERT_RETRIES = 5
ALERT_WAIT_TIME = 1

if __name__ == "__main__":
    logger.info(f"Base Directory: {BASE_DIR}")
    logger.info(f"Log File: {LOG_FILE}")
    logger.info(f"Database: {DATABASE_URL}")
    logger.info(f"PromaX URL: {PROMAX_URL}")
