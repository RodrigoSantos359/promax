# 🏗️ Arquitetura do PromaX Automation Suite

## Visão Geral

```
┌─────────────────────────────────────────────────────────────────┐
│                    PromaX Automation Suite                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              UI Layer (Interface Usuário)                 │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │ Flask Web Application / Tkinter Desktop App         │ │   │
│  │  │ - Dashboard de automações                           │ │   │
│  │  │ - Configuração por empresa                          │ │   │
│  │  │ - Agendamento de tarefas                            │ │   │
│  │  │ - Visualização de logs                              │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ↕                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            Orchestration Layer (Orquestração)             │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │ Executor: Gerencia execução de rotinas              │ │   │
│  │  │ Scheduler: Agenda tarefas por data/hora             │ │   │
│  │  │ Database: Persistência de configurações             │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ↕                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         Automation Layer (Lógica de Automação)            │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │ BaseRoutine (Classe Base Abstrata)               │   │   │
│  │  │ - Métodos comuns de navegação                    │   │   │
│  │  │ - Esperas explícitas (Selenium WebDriverWait)    │   │   │
│  │  │ - Tratamento de erros                            │   │   │
│  │  │ - Logging detalhado                              │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  │                     ↓ (herança)                          │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │ Rotinas Concretas                                │   │   │
│  │  │  ├─ Routine14_05_05 (Lançamentos)               │   │   │
│  │  │  ├─ RoutineXX_XX_XX (Novas rotinas)            │   │   │
│  │  │  └─ ...                                          │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ↕                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           Browser Layer (Controle de Navegador)           │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │ DriverManager (Gerenciador WebDriver)              │ │   │
│  │  │ - Criar Chrome WebDriver                           │ │   │
│  │  │ - Gerenciar ciclo de vida                          │ │   │
│  │  │ - Context managers                                 │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ↕                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Selenium WebDriver (Chrome)                 │   │
│  │  - Automação de navegador                               │   │
│  │  - Interação com elementos                              │   │
│  │  - Capturas de screenshot                               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ↕                                    │
└──────────────────────────────────────────────────────────────────┘
                              ↕
                 ┌────────────────────────────┐
                 │    PromaX Cloud Server      │
                 │ dibrasa.promaxcloud.com.br  │
                 └────────────────────────────┘
```

## Fluxo de Execução

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Usuário acessa interface web                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Dashboard mostra automações configuradas                 │
│    - Por empresa                                            │
│    - Com status (ativo/inativo)                             │
│    - Próxima execução                                       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Usuário clica em "Executar agora" ou scheduler aciona    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Executor inicia rotina                                   │
│    - Cria WebDriver (Chrome)                               │
│    - Instancia RoutineClass com driver                     │
│    - Chama routine.execute()                               │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Rotina começa:                                           │
│    a) Navigate → PromaX URL                                │
│    b) Handle alerts → Fechar janelas alert()               │
│    c) Wait for element → Aguardar tabela carregar         │
│    d) Process data → Extrair/processar dados              │
│    e) Return result → Retornar resultado                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Resultado persiste em banco de dados                     │
│    - execution_logs table                                  │
│    - Status (success/failed)                               │
│    - Duração, erros, etc                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Dashboard atualiza em tempo real                         │
│    - Status da última execução                             │
│    - Logs visíveis na interface                            │
└─────────────────────────────────────────────────────────────┘
```

## Estrutura de Diretórios Detalhada

```
promax/
│
├── 📄 main.py                          # Ponto de entrada
├── 📄 README.md                        # Documentação principal
├── 📄 GUIA_RAPIDO.md                  # Guia de uso em PT-BR
├── 📄 CLAUDE.md                        # Instruções para Claude
├── 📄 ARQUITETURA.md                  # Este arquivo
├── 📄 requirements.txt                 # Dependências Python
├── 📄 .env.example                     # Variáveis de ambiente
├── 📄 .gitignore                       # Git ignore rules
│
├── 📁 config/                          # Configuração
│   ├── __init__.py
│   ├── settings.py                    # Variáveis globais, timeouts, selectors
│   └── database.py                    # [TODO] SQLAlchemy models
│
├── 📁 src/                             # Código-fonte principal
│   ├── __init__.py
│   │
│   ├── 📁 browser/                     # Controle de navegador
│   │   ├── __init__.py
│   │   ├── driver.py                  # DriverManager - criação do WebDriver
│   │   └── waits.py                   # [TODO] Helpers de espera
│   │
│   ├── 📁 automation/                  # Engine de automação
│   │   ├── __init__.py                # Registry de rotinas
│   │   ├── base.py                    # BaseRoutine - classe abstrata
│   │   ├── login.py                   # [TODO] Login handler
│   │   ├── executor.py                # [TODO] Executor de tarefas
│   │   ├── scheduler.py               # [TODO] Agendador APScheduler
│   │   │
│   │   └── 📁 routines/               # Rotinas específicas
│   │       ├── __init__.py
│   │       ├── routine_template.py    # Template para novas rotinas
│   │       └── routine_14_05_05.py    # Exemplo: rotina 14.05.05
│   │
│   └── 📁 ui/                          # [TODO] Interface web/desktop
│       ├── __init__.py
│       ├── app.py                     # Flask app
│       ├── 📁 templates/
│       │   ├── dashboard.html
│       │   ├── company_form.html
│       │   └── automation_config.html
│       └── 📁 static/
│           ├── 📁 css/
│           │   └── style.css
│           └── 📁 js/
│               └── app.js
│
├── 📁 logs/                            # Logs de execução
│   └── automation.log                 # [Gerado em runtime]
│
├── 📁 data/                            # Persistência
│   └── promax.db                       # SQLite [Gerado em runtime]
│
├── 📁 tests/                           # Testes unitários
│   ├── __init__.py
│   ├── test_example.py                # Testes de exemplo
│   ├── test_login.py                  # [TODO] Testes de login
│   └── test_routines.py               # [TODO] Testes de rotinas
│
└── 📁 telas/                           # [Legacy] Telas capturadas (ref.)
    ├── Lançamentos rotina14.05.05.html
    └── ...
```

## Padrões de Design Utilizados

### 1. **Base Class Pattern**
```python
class BaseRoutine(ABC):
    """Classe base para todas as rotinas"""
    @abstractmethod
    def execute(self) -> dict:
        pass
```

### 2. **Factory Pattern**
```python
RoutineClass = get_routine_class("14.05.05")
routine = RoutineClass(driver=driver, logger=logger)
```

### 3. **Context Manager Pattern**
```python
with DriverManager.create_context_driver() as driver:
    routine = Routine14_05_05(driver)
    routine.execute()
```

### 4. **Registry Pattern**
```python
AVAILABLE_ROUTINES = {
    "14.05.05": Routine14_05_05,
    "XX.XX.XX": RoutineXX_XX_XX,
}
```

### 5. **Dependency Injection**
```python
routine = Routine14_05_05(
    driver=driver,
    logger=logger,
    timeout=10
)
```

## Fluxo de Dados

### Criar Nova Automação
```
User Interface
    ↓
POST /api/automations
    ↓
Executor.create_automation(company_id, routine_id, config)
    ↓
Database.insert(automations table)
    ↓
Scheduler.add_job(routine_id, schedule)
    ↓
Dashboard atualiza
```

### Executar Automação
```
Schedule Trigger / Manual Click
    ↓
Executor.execute(automation_id)
    ↓
Get Automation Config from DB
    ↓
DriverManager.create_driver()
    ↓
RoutineClass(driver).execute()
    ↓
Result: {status, processed, errors, ...}
    ↓
Database.insert(execution_logs)
    ↓
Dashboard atualiza status
    ↓
DriverManager.quit_driver()
```

## Importação e envio ao BPO ACENE

```
PromaX ──(rotina: navega, preenche período, gera e baixa o CSV/INF)──▶ data/arquivos
   │
   ▼  ArquivoBaixadoMonitor (a cada 15 s)
src/database/file_processor.py
   ├─ reconhece o layout (cabeçalho ou largura fixa)
   ├─ pula o que já existe no Postgres (data + portador)          ─┐
   ├─ insere em rel_<id>_<código>_v1 (banco promax)                │
   ├─ enfileira cópia do original (rotinas em BPO_ACENE_ROTINAS)  ─┤─▶ data/envios_bpo + tabela envios_bpo
   └─ apaga o arquivo baixado                                      │
                                                                   ▼  EnvioBpoMonitor (a cada 30 s)
                                     POST {BPO_ACENE_URL}/api/bpo/promax/importacoes
                                     (≤ 30/min · tentativas com espera · rejeições registradas)
```

Cada etapa é isolada: falha no envio não interrompe a importação, e falha na importação
não gera envio.

## Componentes [TODO]

- [ ] `src/automation/login.py` - Automação de login genérica
- [ ] `src/automation/executor.py` - Orquestrador de tarefas
- [ ] `src/automation/scheduler.py` - Agendador APScheduler
- [ ] `config/database.py` - Modelos SQLAlchemy
- [ ] `src/ui/app.py` - Interface Flask
- [ ] `src/browser/waits.py` - Helpers de espera
- [ ] `tests/test_login.py` - Testes de login
- [ ] `tests/test_routines.py` - Testes de rotinas

## Segurança

- ✅ Senhas criptografadas com `cryptography.Fernet`
- ✅ `.env` file não versionado
- ✅ Logs não contêm credenciais
- ⚠️ [TODO] CSRF protection em Flask
- ⚠️ [TODO] Autenticação de usuários na UI

## Performance

- ✅ WebDriverWait (explicit waits) ao invés de sleep()
- ✅ Logging assíncrono
- ⚠️ [TODO] Paralelização de múltiplas automações
- ⚠️ [TODO] Cache de seletores CSS

## Escalabilidade

- ✅ Multi-empresa (company_id nas configs)
- ✅ Fácil adicionar novas rotinas
- ⚠️ [TODO] Suporte a múltiplos browsers (Firefox, Edge)
- ⚠️ [TODO] Distribuição de tarefas (Celery + Redis)

---

**Próximas fases:**
1. Implementar UI (Flask)
2. Adicionar database models (SQLAlchemy)
3. Implementar scheduler (APScheduler)
4. Adicionar testes unitários (pytest)
5. Deploy em produção (Docker)
