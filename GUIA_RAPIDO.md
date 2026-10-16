# 🚀 Guia Rápido - PromaX Automation

## ⚡ Setup Inicial

### 1. Instalar Dependências
```bash
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Configurar Credenciais
```bash
copy .env.example .env
# Editar .env com suas credenciais
```

### 3. Executar Teste
```bash
python main.py
```

## 📝 Criar uma Nova Rotina

### 1. Copiar Template
```bash
copy src\automation\routines\routine_template.py src\automation\routines\routine_XX_XX_XX.py
```

### 2. Editar Arquivo
```python
class RoutineXX_XX_XX(BaseRoutine):
    ROUTINE_ID = "XX.XX.XX"
    ROUTINE_NAME = "Minha Rotina"
    ROUTINE_URL = "/pw/cgi-bin/PPXXXXX.exe?..."
    
    def execute(self):
        self.log_execution_start()
        try:
            self.navigate_to_routine()
            # Sua lógica aqui
            return {"status": "success", "processed": 0}
        except Exception as e:
            return {"status": "failed", "error": str(e)}
```

### 3. Registrar em `src/automation/__init__.py`
```python
from src.automation.routines.routine_XX_XX_XX import RoutineXX_XX_XX

AVAILABLE_ROUTINES = {
    "XX.XX.XX": RoutineXX_XX_XX,
}
```

### 4. Pronto!
Sua rotina aparece no dropdown da interface web.

## 🔍 Métodos Comuns (BaseRoutine)

```python
# Aguardar e preencher campo
self.send_keys((By.NAME, "campo"), "valor")

# Aguardar e clicar
self.click_element((By.CSS_SELECTOR, ".botao"))

# Aguardar elemento aparecer
element = self.wait_for_element((By.XPATH, "//table"))

# Extrair texto
texto = self.get_text((By.ID, "resultado"))

# Fechar alerts
self.handle_alerts(max_retries=5)

# Capturar screenshot
self.take_screenshot("erro.png")

# Log
self.logger.info("Mensagem")
self.logger.error("Erro")
```

## 🎯 Padrão de Seletores

```python
from selenium.webdriver.common.by import By

# CSS Selector (recomendado)
(By.CSS_SELECTOR, ".classe")
(By.CSS_SELECTOR, "#id")
(By.CSS_SELECTOR, "table tbody tr")

# XPath
(By.XPATH, "//button[@id='salvar']")

# Name
(By.NAME, "usuario")

# ID
(By.ID, "campo_entrada")

# Class
(By.CLASS_NAME, "minha_classe")
```

## 📊 Estrutura de Resultado

Todas as rotinas devem retornar:
```python
{
    "status": "success" | "failed",
    "processed": 10,          # Número de registros processados
    "errors": 0,              # Número de erros
    "message": "Descrição",
    "error": "Mensagem de erro"  # Se falhou
}
```

## 🐛 Debugging

### Ver Logs
```bash
tail -f logs/automation.log  # Linux/Mac
type logs\automation.log     # Windows
```

### Screenshot em Caso de Erro
```python
self.take_screenshot("debug.png")
```

### Executar com Visualização
```python
driver = DriverManager.create_driver(headless=False)
# Ver navegador enquanto executa
```

### Inspeccionar Seletores
1. Abrir DevTools (F12) no navegador
2. Clicar em elemento
3. Copiar seletor: `Copy -> Copy selector` ou `Copy -> Copy XPath`

## 📚 Exemplo Completo: Logar e Extrair Dados

```python
from selenium.webdriver.common.by import By
from src.automation.base import BaseRoutine

class RotinaMeuExemplo(BaseRoutine):
    ROUTINE_ID = "01.02.03"
    ROUTINE_NAME = "Meu Exemplo"
    ROUTINE_URL = "/pagina"

    def execute(self):
        try:
            # 1. Navegar
            self.navigate_to_routine()
            
            # 2. Fechar alerts
            self.handle_alerts()
            
            # 3. Aguardar página
            self.wait_for_element((By.CSS_SELECTOR, "table"))
            
            # 4. Preencher formulário
            self.send_keys((By.NAME, "usuario"), "filipe")
            self.send_keys((By.NAME, "senha"), "senha123")
            
            # 5. Clicar em salvar
            self.click_element((By.CSS_SELECTOR, ".btn-submit"))
            
            # 6. Extrair dados
            linhas = self.driver.find_elements(By.CSS_SELECTOR, "table tr")
            processados = len(linhas)
            
            return {
                "status": "success",
                "processed": processados,
                "errors": 0,
                "message": f"Processadas {processados} linhas"
            }
            
        except Exception as e:
            self.logger.error(f"Erro: {str(e)}")
            self.take_screenshot("erro.png")
            return {"status": "failed", "error": str(e)}
```

## 📞 Resolução de Problemas

| Problema | Solução |
|----------|---------|
| `TimeoutException` | Aumentar timeout ou verificar seletor |
| Elemento não encontrado | Inspecionar com DevTools, copiar seletor exato |
| Senha incorreta | Verificar credenciais em `.env` |
| Chromedriver não encontrado | `pip install webdriver-manager` (já incluído) |
| Alerts não fecham | Aumentar `max_retries` em `handle_alerts()` |

## 🎓 Próximas Etapas

1. **Interface Web**: Implementar Flask UI para configuração
2. **Agendamento**: APScheduler para executar rotinas por horário
3. **Banco de Dados**: SQLAlchemy para persistir configurações
4. **Testes Unitários**: Pytest para testar cada rotina

---

**Perguntas?** Consulte [README.md](README.md) para mais detalhes.
