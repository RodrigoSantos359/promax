# PromaX Automation Suite

Automação elegante e escalável para processos no PromaX Cloud usando Python e Selenium.

## 📋 Visão Geral

Este projeto fornece um framework robusto para automação de tarefas repetitivas no PromaX Cloud (https://dibrasa.promaxcloud.com.br/), com:

- **Interface web** para configuração de automatizações por empresa
- **Agendamento** de tarefas com data, hora e retry automático
- **Multi-empresa** com suporte a múltiplas unidades
- **Extensível** para adicionar novas rotinas facilmente

## 🏗️ Arquitetura

```
promax-automation/
├── config/
│   ├── __init__.py
│   ├── settings.py                 # Variáveis globais
│   └── database.py                 # Conexão com BD (SQLite)
├── src/
│   ├── __init__.py
│   ├── browser/
│   │   ├── __init__.py
│   │   ├── driver.py               # Gerenciamento WebDriver (Selenium)
│   │   └── waits.py                # Helpers para esperas explícitas
│   ├── automation/
│   │   ├── __init__.py
│   │   ├── base.py                 # Classe base para automações
│   │   ├── login.py                # Rotina de login
│   │   └── routines/
│   │       ├── __init__.py
│   │       ├── routine_14_05_05.py # Exemplo: rotina 14.05.05
│   │       └── routine_template.py # Template para novas rotinas
│   ├── executor.py                 # Orquestrador de tarefas
│   └── scheduler.py                # Agendamento de tarefas
├── ui/
│   ├── __init__.py
│   ├── app.py                      # Aplicação Flask/Tkinter
│   ├── templates/
│   │   ├── dashboard.html          # Dashboard principal
│   │   ├── company_form.html       # Formulário de empresa
│   │   └── automation_config.html  # Configuração de automação
│   └── static/
│       ├── css/
│       │   └── style.css
│       └── js/
│           └── app.js
├── logs/
│   └── automation.log              # Logs de execução
├── data/
│   └── promax.db                   # Banco de dados (SQLite)
├── tests/
│   ├── __init__.py
│   ├── test_login.py
│   └── test_routines.py
├── requirements.txt
├── .env.example
├── main.py                         # Ponto de entrada
└── README.md
```

## 🚀 Quickstart

### Instalação

```bash
# Clone ou navegue até o diretório
cd promax-automation

# Crie um ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Instale dependências
pip install -r requirements.txt
```

### Configuração Inicial

1. Copie `.env.example` para `.env`:
```bash
cp .env.example .env
```

2. Configure suas credenciais do PromaX:
```env
PROMAX_URL=https://dibrasa.promaxcloud.com.br/
PROMAX_DEFAULT_USER=SEU_USUARIO_AQUI
PROMAX_DEFAULT_PASSWORD=SUA_SENHA_AQUI
```

3. (Opcional) Envio dos relatórios ao BPO ACENE. Com `BPO_ACENE_URL` vazio, nada é enviado:
```env
BPO_ACENE_URL=https://endereco-do-bpo
BPO_ACENE_VERIFY_SSL=True
# Padrão: 14.05.05,12.06.04,12.04.07.03,16.03.08,01.20.04,01.20.12
BPO_ACENE_ROTINAS=14.05.05,12.06.04,12.04.07.03,16.03.08,01.20.04,01.20.12
```
O token do BPO é cadastrado por empresa, na tela de empresas (campo "Token API BPO ACENE"), e fica criptografado.

4. Inicie a aplicação:
```bash
python main.py
```

A interface web abrirá em `http://localhost:5000`

## 📱 Interface Web

### Dashboard Principal
- Visualização de todas as automatizações ativas
- Status de execução em tempo real
- Logs das últimas execuções

### Configuração por Empresa
Formulário com campos:
- **Nome da Empresa**
- **Link do PromaX** (URL base da empresa)
- **Login/Senha** (criptografado em BD)
- **Unidade PromaX** (ex: 161.0001 - Dibrasa)
- **Ativação** (Ativo/Inativo)

### Configuração de Automação
Para cada empresa, configure:
- **Rotina** (dropdown com rotinas disponíveis)
- **Ativado** (checkbox)
- **Data de Início** (quando a automação começa)
- **Hora de Execução** (HH:MM)
- **Intervalo** (diária, semanal, mensal)
- **Máximo de Tentativas** (em caso de falha)
- **Intervalo entre Tentativas** (segundos)

## 🔌 Adicionando Novas Rotinas

### 1. Crie um novo arquivo em `src/automation/routines/`

```python
# src/automation/routines/routine_XX_XX_XX.py

from src.automation.base import BaseRoutine
from src.browser.waits import wait_for_element

class Routine14_05_05(BaseRoutine):
    """
    Rotina 14.05.05 - Lançamentos
    
    Responsável por: [descrever o que faz]
    """
    
    ROUTINE_ID = "14.05.05"
    ROUTINE_NAME = "Lançamentos"
    ROUTINE_URL = "/pw/cgi-bin/PP00100.exe?SessionID={session}&ppopcao=7&call=140505000000&SubSessionID={subsession}"
    
    def execute(self):
        """Executa a rotina principal"""
        try:
            self.logger.info(f"Iniciando {self.ROUTINE_NAME}")
            
            # Navegue até a rotina
            self.navigate_to_routine()
            
            # Implemente sua lógica aqui
            self._process_lancamentos()
            
            self.logger.info(f"{self.ROUTINE_NAME} concluída com sucesso")
            return {"status": "success", "processed": 0}
            
        except Exception as e:
            self.logger.error(f"Erro na {self.ROUTINE_NAME}: {str(e)}")
            raise
    
    def _process_lancamentos(self):
        """Lógica específica da rotina"""
        # Exemplo: aguardar elemento de carregamento
        table = wait_for_element(
            self.driver, 
            ("css_selector", ".TableTop"),
            timeout=10
        )
        # ... sua automação aqui
```

### 2. Registre a rotina em `src/automation/__init__.py`

```python
from src.automation.routines.routine_14_05_05 import Routine14_05_05

AVAILABLE_ROUTINES = {
    "14.05.05": Routine14_05_05,
    # Adicione novas rotinas aqui
}
```

### 3. A rotina está pronta!

Ela aparecerá automaticamente no dropdown de configuração.

## 🔐 Credenciais e Segurança

### Armazenamento
- Senhas são **criptografadas** com `cryptography.Fernet`
- Banco de dados usa **SQLite** (local)
- Variáveis sensíveis em `.env` (não versionado)

### Boas Práticas
```python
# ✅ Correto
from config.settings import get_encrypted_password
password = get_encrypted_password(company_id)

# ❌ Não faça
password = "senha_hardcoded"
```

## 📊 Banco de Dados

### Tabelas Principais

```sql
-- Empresas
CREATE TABLE companies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    promax_url TEXT NOT NULL,
    username TEXT NOT NULL,
    password_encrypted TEXT NOT NULL,
    unit TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Automações (agenda + último resultado)
CREATE TABLE automations (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    routine_id TEXT NOT NULL,        -- código do relatório, ex: '14.05.05'
    is_active BOOLEAN DEFAULT 1,
    start_date DATE NOT NULL,
    execution_time TEXT NOT NULL,    -- HH:MM
    interval TEXT NOT NULL,          -- 'daily', 'weekly', 'monthly'
    max_retries INTEGER DEFAULT 3,
    retry_delay INTEGER DEFAULT 60,
    last_execution TIMESTAMP,
    last_status TEXT,                -- 'success', 'failed'
    last_error TEXT,
    last_summary TEXT,
    rotina_map_id INTEGER,           -- rotina configurada na tela
    created_at TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- Logs de execução
CREATE TABLE execution_logs (
    id INTEGER PRIMARY KEY,
    automation_id INTEGER NOT NULL,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT,           -- 'success', 'failed'
    error_message TEXT,
    duration_seconds FLOAT,
    FOREIGN KEY (automation_id) REFERENCES automations(id)
);

-- Arquivos baixados, aguardando importação no Postgres
CREATE TABLE arquivos_baixados (
    id INTEGER PRIMARY KEY,
    id_rotina INTEGER,
    id_empresa INTEGER,
    nome_arquivo TEXT,
    data DATE NOT NULL,              -- data de referência (dia anterior à execução)
    status TEXT NOT NULL,            -- 'baixado', 'sem_dados', 'failed', 'erro_*'
    created_at TIMESTAMP
);

-- Fila de envio ao BPO ACENE
CREATE TABLE envios_bpo (
    id INTEGER PRIMARY KEY,
    id_empresa INTEGER NOT NULL,
    id_rotina INTEGER,
    competencia TEXT NOT NULL,       -- AAAA-MM
    caminho_arquivo TEXT NOT NULL,   -- cópia em data/envios_bpo
    nome_arquivo TEXT NOT NULL,
    status TEXT NOT NULL,            -- 'pendente', 'enviado', 'duplicado', 'rejeitado', 'erro'
    tentativas INTEGER DEFAULT 0,
    proxima_tentativa TIMESTAMP,
    http_status INTEGER,
    lote_id INTEGER,
    lote_status TEXT,
    mensagem TEXT,
    enviado_em TIMESTAMP
);
```

Os dados extraídos ficam no Postgres (banco `promax`), uma tabela `rel_<id>_<código>_v1` por relatório. A coluna `data` é a data da execução do robô; o movimento fica em `contabil` (pagamentos) ou `data_2` (extrato).

## 🧪 Testes

```bash
# Executar todos os testes
pytest

# Com cobertura
pytest --cov=src

# Apenas um arquivo
pytest tests/test_bpo_acene.py -v
```

Os testes usam um SQLite temporário (`tests/conftest.py`), sem tocar no banco real. Hoje há 1 falha antiga e não relacionada (`test_get_routine_class_not_found`).

## 📝 Logging

Logs são salvos em `logs/automation.log`:

```
2024-01-15 14:30:45 - INFO - Iniciando Lançamentos (14.05.05)
2024-01-15 14:30:52 - INFO - Login realizado com sucesso
2024-01-15 14:31:10 - INFO - Lançamentos concluída com sucesso
```

## 🐛 Troubleshooting

| Problema | Solução |
|----------|---------|
| `TimeoutException` ao logar | Aumente o timeout em `config/settings.py` |
| Elemento não encontrado | Verifique seletores CSS em `inspection` da página |
| Senha incorreta | Regenere credenciais criptografadas em `settings.py` |

## 📚 Referências

- **PromaX URL**: https://dibrasa.promaxcloud.com.br/
- **Selenium Docs**: https://www.selenium.dev/documentation/
- **Python Best Practices**: https://pep8.org/

## 📄 Licença

Propriedade da Dibrasa

## 👤 Autor

Desenvolvido por: Rodrigo (rodrigo@lifecti.com.br)
