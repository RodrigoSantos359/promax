# 🚀 Guia de Instalação - PromaX Automation Suite

Instruções passo a passo para instalar e configurar o projeto.

---

## 📋 Pré-requisitos

- **Python 3.9+** instalado ([Download](https://www.python.org/downloads/))
- **Git** instalado ([Download](https://git-scm.com/))
- **Windows PowerShell** ou **Bash** (Git Bash)
- **Conexão de internet** (para download de dependências)

### Verificar instalação

```bash
python --version      # Deve ser 3.9 ou superior
pip --version         # Deve estar disponível
git --version         # Deve estar disponível
```

---

## 🔧 Instalação Passo a Passo

### Passo 1: Clonar ou Navegar até o Repositório

```bash
# Se é um novo projeto
cd c:\Users\Rodrigo\Documents\lifeCTI\promax

# Ou se for clonar
git clone <url_do_repositorio>
cd promax
```

### Passo 2: Criar Ambiente Virtual

```bash
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Windows (Git Bash)
python -m venv venv
source venv/Scripts/activate

# Linux/Mac
python -m venv venv
source venv/bin/activate
```

**Resultado esperado:** Seu prompt deve começar com `(venv)`

```
(venv) C:\Users\Rodrigo\Documents\lifeCTI\promax>
```

### Passo 3: Atualizar pip

```bash
python -m pip install --upgrade pip
```

### Passo 4: Instalar Dependências

```bash
pip install -r requirements.txt
```

**Tempo esperado:** 2-5 minutos

**Resultado esperado:**
```
Successfully installed selenium-4.15.2 webdriver-manager-4.0.1 Flask-3.0.0 ...
```

### Passo 5: Configurar Variáveis de Ambiente

```bash
# Copiar arquivo de exemplo
copy .env.example .env          # Windows
# ou
cp .env.example .env            # Linux/Mac

# Editar .env com suas credenciais
# Você pode usar qualquer editor de texto
notepad .env                    # Windows (Notepad)
code .env                       # VS Code
vim .env                        # Vim
```

**Conteúdo de `.env` deve ser:**
```env
PROMAX_URL=https://dibrasa.promaxcloud.com.br/
PROMAX_DEFAULT_USER=filipe
PROMAX_DEFAULT_PASSWORD=SUA_SENHA_AQUI
DATABASE_URL=sqlite:///data/promax.db
LOG_LEVEL=INFO
FLASK_PORT=5000
FLASK_DEBUG=True

# Envio dos relatórios ao BPO ACENE (vazio = desligado)
BPO_ACENE_URL=
BPO_ACENE_VERIFY_SSL=True
```

### Passo 6: Verificar Instalação

```bash
python -c "import selenium; print('✓ Selenium OK')"
python -c "import flask; print('✓ Flask OK')"
python -c "import sqlalchemy; print('✓ SQLAlchemy OK')"
python -c "import cryptography; print('✓ Cryptography OK')"
```

**Resultado esperado:**
```
✓ Selenium OK
✓ Flask OK
✓ SQLAlchemy OK
✓ Cryptography OK
```

---

## ✅ Teste a Instalação

### Opção 1: Teste Simples (Recomendado)

```bash
python main.py
```

**Resultado esperado:**
```
... [INFO] Iniciando PromaX Automation Suite
... [INFO] ✓ Rotinas disponíveis: 1
...   - 14.05.05
... [INFO] ▶️  Executando rotina: 14.05.05
... [INFO] Criando WebDriver (headless=False, size=1920x1080)
... [INFO] WebDriver criado com sucesso
```

Seu navegador Chrome abrirá e tentará acessar o PromaX.

### Opção 2: Inicializar Banco de Dados

```bash
python main.py --init-db
```

**Resultado esperado:**
```
✓ Banco de dados inicializado com sucesso
```

### Opção 3: Iniciar Interface Web

```bash
python main.py --init-db
python main.py --web
```

**Resultado esperado:**
```
... [INFO] Inicializando banco de dados...
... [INFO] ✓ Banco de dados ready
... [INFO] ✓ Iniciando Flask em http://localhost:5000
... [INFO] Pressione CTRL+C para parar
 * Running on http://127.0.0.1:5000
```

**Acesse:** http://localhost:5000 no seu navegador

---

## 🚨 Solução de Problemas

### Erro: "ModuleNotFoundError: No module named 'selenium'"

**Solução:**
```bash
# Verifique se o ambiente virtual está ativado
# (venv) deve aparecer no seu prompt
pip install -r requirements.txt
```

### Erro: "Python não é reconhecido como um comando interno"

**Solução (Windows):**
1. Adicione Python ao PATH
2. Ou use o caminho completo: `C:\Python39\python.exe main.py`

### Erro: "Chromedriver não encontrado"

**Solução:**
```bash
# webdriver-manager fará o download automaticamente
# Se ainda não funcionar:
pip install --upgrade webdriver-manager
```

### Erro: "Database is locked"

**Solução:**
```bash
# Feche outras instâncias da aplicação
# Ou delete o banco de dados e recrie
rm data/promax.db
python main.py --init-db
```

### Erro: "Port 5000 already in use"

**Solução (Windows PowerShell):**
```bash
# Encontre o processo usando a porta
netstat -ano | findstr :5000

# Mate o processo (substitua PID)
taskkill /PID <PID> /F

# Ou mude a porta em .env
FLASK_PORT=5001
```

### Erro: "Could not find a version"

**Solução:**
```bash
# Atualize pip e tente novamente
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 📁 Estrutura Pós-Instalação

Após completar a instalação, você terá:

```
promax/
├── venv/                  # Ambiente virtual
├── data/
│   └── promax.db          # [Criado] Banco de dados
├── logs/
│   └── automation.log     # [Criado] Arquivo de logs
├── src/                   # Código-fonte
├── config/                # Configuração
├── .env                   # [Criado] Variáveis de ambiente
└── ... (outros arquivos)
```

---

## 🔄 Atualizações Futuras

Para manter o projeto atualizado:

```bash
# Ativar ambiente virtual
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/Mac

# Atualizar dependências
pip install -r requirements.txt --upgrade

# Commit de mudanças
git add .
git commit -m "Atualizar dependências"
git push
```

---

## 🐍 Gerenciamento do Ambiente Virtual

### Ativar (toda vez que abrir o terminal)

```bash
# Windows
venv\Scripts\Activate.ps1

# Linux/Mac
source venv/bin/activate
```

### Desativar

```bash
deactivate
```

### Deletar e Recriar

```bash
# Deletar
rmdir /s /q venv              # Windows
rm -rf venv                   # Linux/Mac

# Recriar
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/Mac
pip install -r requirements.txt
```

---

## 🎯 Próximos Passos Após Instalação

1. **Revisar a documentação:**
   - Leia `README.md` para overview
   - Leia `GUIA_RAPIDO.md` para uso rápido
   - Leia `ARQUITETURA.md` para entender a estrutura

2. **Explorar o código:**
   ```bash
   code .                     # Abrir no VS Code
   # ou
   explorer .                 # Windows Explorer
   ```

3. **Criar sua primeira rotina:**
   - Copie `src/automation/routines/routine_template.py`
   - Edite com sua lógica
   - Registre em `src/automation/__init__.py`

4. **Testar a interface web:**
   ```bash
   python main.py --web
   ```

5. **Explorar a API:**
   - Use Postman ou cURL
   - Exemplos em `GUIA_RAPIDO.md`

---

## 📞 Suporte

Se encontrar problemas:

1. Consulte `GUIA_RAPIDO.md` - Seção "Resolução de Problemas"
2. Verifique os logs: `logs/automation.log`
3. Leia a documentação do Selenium: https://selenium.dev/
4. Contate: rodrigo@lifecti.com.br

---

## ✅ Checklist de Instalação

- [ ] Python 3.9+ instalado
- [ ] Ambiente virtual criado (`venv`)
- [ ] Ambiente virtual ativado (prompt começa com `(venv)`)
- [ ] Dependências instaladas (`pip install -r requirements.txt`)
- [ ] `.env` configurado
- [ ] Teste simples passou (`python main.py`)
- [ ] Banco de dados inicializado (`python main.py --init-db`)
- [ ] Interface web funciona (`python main.py --web`)

---

**Parabéns! Você está pronto para usar PromaX Automation Suite! 🎉**

Para começar, leia [GUIA_RAPIDO.md](GUIA_RAPIDO.md)
