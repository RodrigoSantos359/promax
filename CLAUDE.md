# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🎯 Project: PromaX Automation Suite

**Python automation framework** for PromaX Cloud tasks using Selenium WebDriver. Elegant, scalable, multi-company automation with web UI for configuration.

### Key Stack
- **Python 3.9+** with `selenium`, `flask` (or `tkinter` for desktop), `sqlalchemy`
- **Selenium WebDriver** for browser automation
- **SQLite** for configuration storage (encrypted credentials)
- **Elegant patterns**: Base classes, dependency injection, logging

## 📁 Repository Structure

```
promax/
├── telas/                          # [Legacy] Captured HTML screens for reference
├── config/                         # Configuration & settings
├── src/
│   ├── browser/                    # WebDriver management
│   ├── automation/
│   │   ├── base.py                 # BaseRoutine class
│   │   ├── login.py                # Login handler
│   │   └── routines/               # Individual automation routines
│   ├── executor.py                 # Task orchestrator
│   └── scheduler.py                # Task scheduling
├── ui/                             # Web interface (Flask) or desktop (Tkinter)
├── tests/                          # pytest test suite
├── requirements.txt
└── main.py                         # Entry point
```

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- ChromeDriver or automatic driver management (webdriver-manager)
- Windows PowerShell or Bash

### Setup
```bash
python -m venv venv
venv\Scripts\activate           # Windows
source venv/bin/activate        # Linux/Mac

pip install -r requirements.txt
python main.py
```

### Integração WKRADAR (dev local no Windows/Docker Desktop)

A API WKRADAR (`src/integrations/wkradar_client.py`) fica numa rede interna
(`172.20.5.0/24`) inalcançável por containers Docker neste ambiente — testado
exaustivamente com bridge, `--network host`, `macvlan` e `ipvlan`; todos
bloqueados pelo isolamento de rede do Docker Desktop/WSL2. A única rota real
é a distro WSL2 em si (fora do Docker).

Rode uma vez por máquina de desenvolvimento Windows:
```powershell
.\scripts\wkradar-proxy\setup.ps1
```
Isso instala um proxy TCP (`wkradar-proxy.service`, porta 18443 ->
172.20.5.8:443) como serviço systemd dentro da distro WSL2, mais um
keep-alive (pasta Startup do Windows) — sem ele, o Windows finaliza a
instância da distro por ociosidade e mata o proxy. O container acessa via
`host.docker.internal:18443` (já configurado em `docker-compose.yml`, var
`WKRADAR_TOKEN_URL`). Em produção (fora deste setup local), remova essa
variável de ambiente para usar o endpoint real direto.

**Nunca ative o modo de rede "mirrored" do WSL2** (`networkingMode=mirrored`
no `.wslconfig`) — quebra o port-forwarding do Docker Desktop para
`localhost` (o próprio app principal fica inacessível). Não é necessário:
a distro WSL2 já tem rota até a WKRADAR em modo de rede padrão.

### VPN corporativa (container `vpn/`)

Container `vpn` (strongSwan, IPsec IKEv1 Aggressive Mode) reproduzindo a
conexão FortiClient "Dibrasa" (45.162.237.6) para acessar recursos internos
da empresa sem instalar o FortiClient no container. `promax` compartilha a
rede desse container (`network_mode: service:vpn`) — por isso a porta 5000
e o DNS (`/etc/resolv.conf`) são configurados no serviço `vpn` no
`docker-compose.yml`, não em `promax`.

**Antes de subir**: preencha `secrets/vpn_psk.txt`, `secrets/vpn_xauth_user.txt`,
`secrets/vpn_xauth_password.txt` (nunca commitados — ver `secrets/README.md`).
Testado com PSK fake: o FortiGate aceita nossa proposta de Phase 1
(AES128/256+SHA256+DH14) e rejeita só na verificação do hash (esperado) —
a negociação de protocolo está correta; falta validar com credenciais reais.

`VPN_REMOTE_SUBNETS` (.env) controla full-tunnel (`0.0.0.0/0`, padrão, igual
ao FortiClient) vs. split-tunnel — descubra o subnet real do ProMAX interno
antes de restringir (ver análise completa na conversa que introduziu isso).

## 📝 PromaX Access Details

**System**: PromaX Cloud (Dibrasa)
- **URL**: https://dibrasa.promaxcloud.com.br/
- **Default Login**: filipe / Acene003
- **Unit**: 161.0001 - Dibrasa
- **Language**: Portuguese

### Key Screens Referenced
- **Login**: `telas/PromaxWEB principal login.html`
  - Focus class: `TableTop` (login form container)
  - Multi-step: login → unit selection → confirmation
  - Warning: Multiple alert() dialogs appear after login
  
- **Main Dashboard**: Shortcut input field
  ```html
  <input type="text" name="atalho" id="atalho" onkeyup="MontaModulo();" 
         onkeypress="VerificaTeclaPress('13','AtalhoMenu()')" />
  ```

- **Routine 14.05.05** (Lançamentos): Entry/launches management
  ```
  https://dibrasa.promaxcloud.com.br/pw/cgi-bin/PP00100.exe?
    SessionID=...&ppopcao=7&call=140505000000&SubSessionID=...
  ```

## 🔐 Security & Credentials

- **Encryption**: Use `cryptography.Fernet` for password storage
- **Environment**: `.env` file for sensitive defaults (not versioned)
- **Database**: SQLite with encrypted password columns
- **Never hardcode** credentials in source files

## 🧩 Adding New Routines

1. Create `src/automation/routines/routine_XX_XX_XX.py`
2. Extend `BaseRoutine` class
3. Implement `execute()` method
4. Register in `src/automation/__init__.py` → `AVAILABLE_ROUTINES`
5. Appears auto in web UI dropdown

**Template**: See `src/automation/routines/routine_template.py`

## 🧪 Testing

```bash
pytest                              # All tests
pytest tests/test_login.py -v      # Single file
pytest --cov=src                   # With coverage
```

## 📊 Configuration UI Requirements

**Company Configuration:**
- Company name
- PromaX URL
- Login/Password (encrypted)
- Unit (e.g., 161.0001)
- Active/Inactive toggle

**Automation Configuration (per routine):**
- Routine selector (dropdown from AVAILABLE_ROUTINES)
- Active/Inactive toggle
- Start date
- Execution time (HH:MM)
- Interval (daily, weekly, monthly)
- Max retries (on failure)
- Retry delay (seconds)

**Dashboard:**
- List all automations with status
- Last execution time & result
- Real-time logs

## 🎨 Code Style

- **PEP 8** compliant
- **Type hints** for function parameters
- **Docstrings** for classes & public methods (Google style)
- **Logging** via `logging.getLogger(__name__)`
- **No magic numbers**: Use named constants
- **Elegant error handling**: Specific exceptions, context managers

### Example Pattern
```python
class BaseRoutine:
    def __init__(self, driver: WebDriver, logger: logging.Logger):
        self.driver = driver
        self.logger = logger
    
    def execute(self) -> dict:
        """Execute routine. Returns {'status': 'success'|'failed', ...}"""
        pass
```

## 🔍 Browser Automation Best Practices

- **Explicit waits** only (no `time.sleep()` in production code)
- **WebDriverWait** with expected_conditions
- **Try/except** around Selenium operations
- **Close/quit driver** in finally blocks or context managers
- **Session handling**: Parse SessionID/SubSessionID from PromaX responses

## 📋 Common Tasks

| Task | File |
|------|------|
| Login automation | `src/automation/login.py` |
| Add new routine | `src/automation/routines/routine_XX_XX_XX.py` |
| Configure company | UI form (auto-creates DB record) |
| View logs | `logs/automation.log` |
| Database schema | `config/database.py` |
| WebDriver setup | `src/browser/driver.py` |

## 🐛 Debugging

- **Logs**: Check `logs/automation.log` for detailed execution trace
- **Screenshots**: On failure, save screenshot: `driver.save_screenshot('error.png')`
- **Selectors**: Use browser DevTools to inspect `.TableTop`, form inputs, etc.
- **Waits**: If elements not found, increase timeout or review page load conditions
