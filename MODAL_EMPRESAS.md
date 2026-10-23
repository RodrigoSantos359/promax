# 📋 Modal de Adicionar Empresas

## O Que foi Implementado

✅ **Modal interativa** para adicionar empresas  
✅ **Pré-preenchimento** com dados da Dibrasa  
✅ **Validação de formulário** no frontend  
✅ **Criptografia automática** de senha no backend  
✅ **Mensagens de feedback** ao usuário  

---

## Como Usar

### 1. Abrir a Interface Web

```bash
# Terminal
python main.py --web
```

### 2. Acessar o Dashboard

Abra: **http://localhost:5000**

### 3. Clicar em "+ Adicionar Empresa"

A modal abrirá com os campos já preenchidos com:
- **Nome:** Dibrasa
- **URL:** https://dibrasa.promaxcloud.com.br/
- **Usuário:** filipe
- **Senha:** SUA_SENHA_AQUI
- **Unidade:** 161.0001 - Dibrasa

### 4. Editar ou Manter os Dados

- **Manter como está:** Clique em "Adicionar Empresa"
- **Alterar:** Edite os campos conforme necessário

### 5. Confirmar

Ao clicar em "Adicionar Empresa":
- ✓ Dados são validados
- ✓ Senha é criptografada
- ✓ Empresa é salva no banco de dados
- ✓ Página recarrega com a nova empresa listada

---

## Campos do Formulário

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| Nome da Empresa | Texto | Sim | Nome identificador da empresa |
| URL do PromaX | URL | Sim | Link da plataforma PromaX |
| Usuário | Texto | Sim | Usuário de login |
| Senha | Senha | Sim | Senha do usuário (criptografada) |
| Unidade PromaX | Texto | Sim | Código da unidade (ex: 161.0001) |
| Configurar API WKRADAR | Seção | Não | Base/Empresa, usuário e senha da API WK Radar (senha criptografada) |
| Token API BPO ACENE | Senha | Não | Token de integração emitido no BPO (criptografado). Usado para enviar os relatórios ao BPO |

O token do BPO nunca é exibido de volta: a tela mostra só se já está configurado.
Ao editar, deixar o campo em branco mantém o token atual.

---

## Segurança

🔒 **Senhas são criptografadas** com Fernet antes de serem salvas  
🔒 **Nunca são armazenadas em texto plano**  
🔒 **Transmissão HTTPS-ready** (adicione SSL em produção)  

---

## Adicionar Mais Empresas

Para adicionar outra empresa:

1. Clique em "+ Adicionar Empresa" novamente
2. **Limpe os campos** (página anterior)
3. Preencha com as informações da nova empresa
4. Clique em "Adicionar Empresa"

**Nota:** Os dados de Dibrasa aparecem pré-preenchidos por padrão para facilitar.

---

## Ver Empresas Adicionadas

As empresas aparecem na seção **"Empresas Configuradas"** com:

- ✓ Nome da empresa
- ✓ Status (Ativa/Inativa)
- ✓ Usuário
- ✓ Link direto para PromaX
- ✓ Botões: "Ver Detalhes" e "Editar"

---

## Próximos Passos

Após adicionar uma empresa, você pode:

1. **Ver Detalhes** - Acessar configurações e automações
2. **Editar** - Alterar informações (URL, unidade, etc)
3. **Configurar Automações** - Adicionar rotinas para essa empresa
4. **Executar Manualmente** - Rodar automações sob demanda

---

## Troubleshooting

### Modal não abre?
```javascript
// Tente no console do navegador (F12)
openCompanyModal();
```

### Erro ao adicionar?
- Verifique se a URL do PromaX está correta
- Confirme que o usuário e senha estão corretos
- Veja os logs: `tail -f logs/automation.log`

### Senha não é salva?
- A senha é criptografada no backend
- Verifique que a variável `ENCRYPTION_KEY` está em `.env`

---

## API

### POST /api/companies

Adiciona uma nova empresa.

**Request:**
```json
{
    "name": "Dibrasa",
    "promax_url": "https://dibrasa.promaxcloud.com.br/",
    "username": "filipe",
    "password": "SUA_SENHA_AQUI",
    "unit": "161.0001 - Dibrasa",
    "bpo_acene_token": "OPCIONAL_TOKEN_BPO"
}
```

**Response (201):**
```json
{
    "id": 1,
    "name": "Dibrasa",
    "message": "Empresa criada com sucesso"
}
```

---

## Banco de Dados

### Tabela `companies`

```sql
CREATE TABLE companies (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    promax_url TEXT NOT NULL,
    username TEXT NOT NULL,
    password_encrypted TEXT NOT NULL,  -- Criptografado
    unit TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Exemplo de Uso Completo

```bash
# 1. Inicie a aplicação
python main.py --web

# 2. Abra http://localhost:5000

# 3. Clique em "+ Adicionar Empresa"

# 4. Modal abre com:
#    - Nome: Dibrasa
#    - URL: https://dibrasa.promaxcloud.com.br/
#    - Usuário: filipe
#    - Senha: SUA_SENHA_AQUI
#    - Unidade: 161.0001 - Dibrasa

# 5. Clique em "Adicionar Empresa"

# 6. Veja a empresa aparecer na lista!

# 7. Clique em "Ver Detalhes" para acessar configurações
```

---

Desenvolvido com ❤️ para facilitar a configuração de empresas no PromaX Automation Suite.
