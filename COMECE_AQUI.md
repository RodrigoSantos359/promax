# 🎯 COMECE AQUI - Guia de Primeiros Passos

**Bem-vindo ao PromaX Automation Suite!**

Este arquivo vai orientá-lo através dos primeiros passos. Siga as etapas abaixo.

---

## ✅ Etapa 1: Instalação (5 minutos)

### Se é primeira vez:

```bash
# 1. Abra o terminal/PowerShell
# 2. Navegue até o diretório
cd c:\Users\Rodrigo\Documents\lifeCTI\promax

# 3. Crie ambiente virtual
python -m venv venv

# 4. Ative o ambiente
venv\Scripts\Activate.ps1     # Windows
source venv/bin/activate      # Linux/Mac

# 5. Instale dependências
pip install -r requirements.txt

# 6. Configure variáveis de ambiente
copy .env.example .env
```

**Resultado esperado:** Seu prompt começa com `(venv)`

---

## ✅ Etapa 2: Configuração (2 minutos)

### Edite o arquivo `.env`

```bash
# Abra .env em um editor
notepad .env          # Windows
code .env             # VS Code
vim .env              # Vim
```

**Verifique essas variáveis:**
```env
PROMAX_URL=https://dibrasa.promaxcloud.com.br/
PROMAX_DEFAULT_USER=filipe
PROMAX_DEFAULT_PASSWORD=SUA_SENHA_AQUI
FLASK_PORT=5000
```

---

## ✅ Etapa 3: Teste Rápido (3 minutos)

### Execute o teste básico:

```bash
python main.py
```

**O que vai acontecer:**
1. ✓ Seu navegador Chrome abrirá
2. ✓ Tentará fazer login no PromaX (com as credenciais)
3. ✓ Fechará automaticamente

**Se funcionou:** Parabéns! ✨

**Se não funcionou:** Verifique `logs/automation.log`

---

## ✅ Etapa 4: Interface Web (1 minuto)

### Inicie o dashboard:

```bash
# Primeiro, inicialize o banco de dados
python main.py --init-db

# Depois, inicie a interface web
python main.py --web
```

**Abra no navegador:** http://localhost:5000

**O que você verá:**
- Dashboard com empresas
- Estatísticas
- Botão para adicionar empresa

---

## 📚 Próximas Leituras (em ordem)

1. **[GUIA_RAPIDO.md](GUIA_RAPIDO.md)** ← LEIA ISTO AGORA
   - Como criar uma rotina
   - Padrões de código
   - Métodos disponíveis

2. **[README.md](README.md)**
   - Overview do projeto
   - Arquitetura
   - Exemplos

3. **[ARQUITETURA.md](ARQUITETURA.md)**
   - Diagramas
   - Fluxos
   - Padrões de design

4. **[STATUS.md](STATUS.md)**
   - O que foi implementado
   - O que falta fazer
   - Roadmap

---

## 🎯 Seu Primeiro Projeto (10 minutos)

### Criar uma rotina simples:

**1. Copiar template**
```bash
copy src\automation\routines\routine_template.py src\automation\routines\routine_99_99_99.py
```

**2. Editar o arquivo**

Abra `src/automation/routines/routine_99_99_99.py` e modifique:

```python
class Routine99_99_99(BaseRoutine):
    ROUTINE_ID = "99.99.99"          # Mude para seu ID
    ROUTINE_NAME = "Minha Automação" # Seu nome
    ROUTINE_URL = "/sua/pagina"      # URL da sua página

    def execute(self):
        self.log_execution_start()
        try:
            # Sua lógica aqui
            # Exemplo:
            self.navigate_to_routine()
            self.handle_alerts()
            
            # Aguardar e processar
            elemento = self.wait_for_element(
                (By.CSS_SELECTOR, ".meu-elemento")
            )
            
            return {"status": "success", "processed": 1}
            
        except Exception as e:
            self.logger.error(f"Erro: {str(e)}")
            return {"status": "failed", "error": str(e)}
```

**3. Registrar a rotina**

Abra `src/automation/__init__.py` e adicione:

```python
from src.automation.routines.routine_99_99_99 import Routine99_99_99

AVAILABLE_ROUTINES = {
    "14.05.05": Routine14_05_05,
    "99.99.99": Routine99_99_99,  # ← Adicione isto
}
```

**4. Teste**

```bash
python main.py
# Ou na interface web: http://localhost:5000
```

---

## 🔥 Atalhos Úteis

### Sempre use essa sequência ao trabalhar:

```bash
# 1. Abra terminal
# 2. Vá até o diretório
cd c:\Users\Rodrigo\Documents\lifeCTI\promax

# 3. Ative venv
venv\Scripts\Activate.ps1

# 4. Faça mudanças no código

# 5. Teste
python main.py --web

# 6. Ao terminar
deactivate
```

### VS Code (Recomendado)

```bash
code .
```

Então em VS Code:
- Ctrl+` → Abre terminal integrado
- Ctrl+Shift+P → Command Palette
- Ctrl+/ → Comentar linha

---

## 🐛 Problemas Comuns

### "ModuleNotFoundError"
```bash
# Verifique se (venv) aparece no prompt
# Se não:
venv\Scripts\Activate.ps1
```

### "Port 5000 already in use"
```bash
# Mude a porta em .env
FLASK_PORT=5001
```

### "Chromedriver not found"
```bash
# Será baixado automaticamente, mas se não:
pip install --upgrade webdriver-manager
```

### "Database is locked"
```bash
# Feche outras instâncias e tente novamente
# Ou delete e recrie:
del data\promax.db
python main.py --init-db
```

---

## 📖 Documentação Rápida

| Arquivo | Descrição | Leia quando |
|---------|-----------|-------------|
| `GUIA_RAPIDO.md` | Guia em português | Agora |
| `README.md` | Overview | Depois |
| `ARQUITETURA.md` | Design detalhado | Para entender |
| `INSTALACAO.md` | Passo a passo instalação | Se tiver erro |
| `STATUS.md` | O que foi feito | Para explorar |
| `ESTRUTURA.txt` | Árvore de arquivos | Para navegar |

---

## 🎓 Conceitos Importantes

### BaseRoutine (Classe Base)
```python
# Cada rotina herda de BaseRoutine
class MinhaRotina(BaseRoutine):
    ROUTINE_ID = "01.02.03"
    
    def execute(self):
        # Sua lógica aqui
        pass
```

### Métodos Disponíveis
```python
# Navegação
self.navigate_to_routine()
self.wait_for_element((By.CSS_SELECTOR, ".selector"))

# Interação
self.click_element((By.CSS_SELECTOR, ".botao"))
self.send_keys((By.NAME, "campo"), "valor")
self.get_text((By.ID, "id"))

# Tratamento
self.handle_alerts()
self.take_screenshot("arquivo.png")

# Logging
self.logger.info("mensagem")
self.logger.error("erro")
```

---

## 💡 Dicas

### 1. Sempre use Explicit Waits
```python
# ✓ Correto
elemento = self.wait_for_element((By.CSS_SELECTOR, ".tabela"), timeout=10)

# ✗ Evite
time.sleep(5)  # Muito lento e frágil
```

### 2. Use Logging
```python
# ✓ Correto
self.logger.info("Iniciando processamento")

# ✗ Evite
print("Iniciando processamento")  # Não aparece nos logs
```

### 3. Sempre trate exceções
```python
# ✓ Correto
try:
    # sua lógica
except Exception as e:
    self.logger.error(f"Erro: {str(e)}")
    return {"status": "failed", "error": str(e)}

# ✗ Evite
# (código sem try-except)
```

### 4. Inspecione os seletores
```bash
# Use DevTools do Chrome (F12)
# Click direito → Inspect
# Copie o seletor
# Use em seu código
```

---

## 🚀 Próximos Passos

Depois de dominar o básico:

1. **Crie suas rotinas** - Implemente suas automações
2. **Configure empresas** - Use a interface web
3. **Agende tarefas** - Implemente APScheduler
4. **Faça deploy** - Use Docker
5. **Monitore** - Veja os logs

---

## ❓ Precisa de Ajuda?

### 1. Verifique os logs
```bash
tail -f logs/automation.log      # Linux/Mac
type logs\automation.log         # Windows (mostrar todo)
```

### 2. Leia a documentação relevante
- Erro de login? → Veja `src/automation/login.py`
- Erro de WebDriver? → Veja `src/browser/driver.py`
- Erro de rotina? → Veja `src/automation/base.py`

### 3. Consulte exemplos
- Template: `src/automation/routines/routine_template.py`
- Exemplo real: `src/automation/routines/routine_14_05_05.py`

### 4. Contato
Email: rodrigo@lifecti.com.br

---

## ✨ Checklist - Você Está Pronto Quando:

- [ ] Instalou e ativou o venv
- [ ] Rodou `python main.py` com sucesso
- [ ] Iniciou `python main.py --web`
- [ ] Acessou http://localhost:5000
- [ ] Leu `GUIA_RAPIDO.md`
- [ ] Criou uma rotina teste
- [ ] Entendeu a estrutura (leia `ARQUITETURA.md`)

---

## 🎉 Parabéns!

Você está pronto para usar **PromaX Automation Suite**!

**Próximo passo:** Leia [GUIA_RAPIDO.md](GUIA_RAPIDO.md)

---

*Desenvolvido com ❤️ por Rodrigo*  
*PromaX Automation Suite v1.0.0*
