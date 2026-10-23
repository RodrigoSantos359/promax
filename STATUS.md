# 📊 Status do Projeto - PromaX Automation Suite

**Atualizado em:** 2026-10-23
**Versão:** 2.0.0
**Status:** ✅ Robô em produção (Dibrasa) · ⏳ Envio ao BPO ACENE implementado, aguardando endereço do servidor e token

---

## 🧭 Resumo do estado atual

| Área | Situação |
|---|---|
| Extração dos relatórios do PromaX | ✅ 12 rotinas cadastradas; última execução de todas com `success` (22/10) |
| Rotina do extrato 12.04.07.03 (caixa/banco) | ✅ Corrigida e validada em 22/10: 5 arquivos gerados, 27 portadores sem movimento, 0 erros |
| Importação no Postgres (`promax`) | ✅ Corrigida: a duplicidade agora considera o portador (antes um arquivo por data bloqueava os demais) |
| Envio dos relatórios originais ao BPO ACENE | ⏳ Código pronto e testado com API simulada; **envio desligado** (`BPO_ACENE_URL` vazio) |
| Teste com a API real do BPO | ⏳ Depende do endereço do servidor e do token da Dibrasa |
| Testes automatizados | ✅ 24 testes: 23 passam; 1 falha antiga e não relacionada (`test_get_routine_class_not_found`) |
| Versionamento | ⚠️ Alterações de 22/10 ainda **não commitadas** |

---

## 🎯 Rotinas do PromaX

Cadastradas para a empresa Dibrasa (161.0001). Todas usam `GenericRoutine` (campos configurados em `camps_map_conf`), exceto a 14.05.05, que tem classe própria.

| Rotina | Relatório | Uso | Observação |
|---|---|---|---|
| 14.05.05 | Contas a pagar · lançamentos | Pagamentos | Classe própria (`routine_14_05_05.py`) · enviado ao BPO |
| 12.06.04 | Financeiro · lançamentos | Recebimentos | Enviado ao BPO |
| 12.04.07.03 | Movimento caixa/banco · lançamentos | Extrato bancário | Gera **um arquivo por portador** (`gerar_lista_opcoes`) · enviado ao BPO |
| 16.03.08 | Análise de lançamento contábil | Despesas por título | Enviado ao BPO |
| 01.20.04 | Fornecedores | Cadastro | Enviado ao BPO |
| 01.20.12 | Exportação geoposicionamento | Clientes | Largura fixa, sem cabeçalho · enviado ao BPO |
| 14.05.10 | Contas a pagar · situação dos títulos | Situação | Não enviado ao BPO |
| 12.06.07 | Financeiro · situação dos títulos | Situação | Não enviado ao BPO |
| 16.03.05 | Plano de contas | Cadastro | Não enviado ao BPO |
| 03.02.37 | Notas fiscais (entradas e saídas) | Fiscal | Não enviado ao BPO · teve uma falha de login pontual em 22/10, recuperada |
| 01.20.01.12 | Cadastro de bancos | Cadastro | Não enviado ao BPO |

### Rotina do extrato (12.04.07.03): o que foi corrigido

O relatório abre em outra janela, e o robô não voltava para a tela de filtros. Além disso, o alerta "Nenhuma informação encontrada" (portador sem movimento) tirava a página do fluxo. Correções em `src/automation/base.py`:

- Fecha a janela do relatório depois de cada portador.
- Recarrega a URL da tela de filtros guardada no início (mesma sessão, sem novo login) e preenche o período de novo.
- Timeout de download de 120 s por portador (o Bradesco 237 é grande).
- "Nenhuma informação encontrada" conta como portador sem movimento, não como erro.

Duração: cerca de 2 minutos para os 32 portadores (antes, 19 minutos com falhas).

---

## 📤 Envio ao BPO ACENE

Após a importação de cada arquivo de uma das seis rotinas abaixo, uma cópia é guardada e enviada à API do BPO (`POST /api/bpo/promax/importacoes`):

- 14.05.05 pagamentos · 12.06.04 recebimentos · 12.04.07.03 extrato · 16.03.08 despesas por título · 01.20.04 fornecedores · 01.20.12 clientes

Componentes:

- `src/integrations/bpo_acene_client.py`: chamada HTTP e classificação da resposta (enviado, duplicado, rejeitado, tentar de novo).
- `src/integrations/bpo_acene_outbox.py`: fila (`envios_bpo`), envio em segundo plano, até 30 chamadas por minuto, até 10 tentativas com espera crescente para falhas temporárias. Rejeições (401, 403, 422) ficam registradas com a mensagem da API.
- Token por empresa, criptografado (Fernet) e nunca exibido pela API. Campo na tela de empresas.

Para ativar: definir `BPO_ACENE_URL` no `.env`, cadastrar o token da empresa e reiniciar o container.

**Limitações conhecidas:**

- Arquivos importados **antes** de ativar o envio não entram na fila automaticamente.
- Um arquivo de portador que já tem dados para a data é pulado pelo importador. Nesse caso ele também não entra na fila.
- O 01.20.12 é de largura fixa (sem cabeçalho). Se o BPO reconhece o layout pelo cabeçalho, pode recusá-lo com erro de layout.

---

## 🗄️ Banco de dados

**Configuração (SQLite, `data/promax.db`):**

- `companies`: empresas, credenciais criptografadas, parâmetros WK Radar e `bpo_acene_token`.
- `automations`, `execution_logs`: agenda e histórico de execuções.
- `rotinas_map`, `camps_map_conf`: rotinas e campos configurados na tela.
- `map_col_rel_rotina`, `map_col_rel_rotina_versoes`: layout dos relatórios.
- `arquivos_baixados`: arquivos baixados, aguardando importação.
- `envios_bpo`: fila de envio ao BPO.

**Dados extraídos (Postgres `promax`):** uma tabela `rel_<id>_<código>_v1` por relatório, com colunas de texto. Colunas `data` = data da execução do robô; o movimento fica em `contabil` (pagamentos) ou `data_2` (extrato).

---

## ✅ Implementado

- Login no PromaX (formulário, alertas, seleção de unidade) e navegação por atalho.
- Execução de rotinas com campos configurados na tela, inclusive rotinas que geram um relatório por opção.
- Download, renomeação e importação dos relatórios no Postgres, com versionamento de layout.
- Agendador (cron) e fila de execução.
- Interface web (Flask) com CRUD de empresas e automações, token WK Radar e token BPO ACENE.
- Integração WK Radar (token, por empresa).
- Envio ao BPO ACENE (código pronto; ativação pendente).

## ⏳ Pendente

- Endereço do servidor BPO ACENE e token da Dibrasa; teste com a API real (enviar um arquivo, consultar o lote).
- Reenvio ao BPO dos arquivos de setembro e outubro (backfill).
- Commit das alterações de 22/10.
- Rever a segurança do projeto: a senha padrão do PromaX ainda aparece em código-fonte (`config/settings.py`, `main.py`), e a senha da API WK foi exposta em conversa. Ambas devem ser trocadas e movidas para o `.env` ou o cadastro criptografado.
- Confirmar com a equipe a separação de VPN por cliente (ainda não implementada).

---

## 🧪 Testes

```bash
pytest                      # todos
pytest tests/test_bpo_acene.py -v
```

- `tests/conftest.py` usa um SQLite temporário e uma chave de criptografia de teste, sem tocar no banco real.
- `tests/test_bpo_acene.py`: cliente e fila do BPO, com a API simulada.
- `tests/test_example.py`: testes básicos do registro de rotinas (1 falha antiga).

Não há teste automatizado para o importador (`file_processor.py`) nem para a navegação da rotina do extrato. Ambos foram validados em execução real.

---

## 📈 Histórico recente

| Data | Mudança |
|---|---|
| 2026-10-22 | Rotina 12.04.07.03 corrigida (janelas, URL de retorno, timeouts, alerta sem movimento) e validada com status success |
| 2026-10-22 | Importador: duplicidade por data e portador (antes descartava arquivos de outros portadores do mesmo dia) |
| 2026-10-22 | Envio ao BPO ACENE: fila, cliente, token por empresa, campo na tela, 6 rotinas |
