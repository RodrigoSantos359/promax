# Secrets da VPN corporativa

Estes 3 arquivos são lidos pelo container `vpn` (via Docker secrets,
montados em `/run/secrets/...`) e **nunca** devem ser commitados — o
`.gitignore` já exclui `secrets/*.txt`.

Crie os arquivos (sem quebra de linha extra no final, conteúdo puro):

- `vpn_psk.txt` — a Pre-Shared Key da fase 1. **Não consigo extrair isso do
  `backup.conf` exportado do FortiClient** — o campo `<preshared_key>` vem
  ofuscado (`EncX ...`) com uma cifra proprietária do FortiClient, e não
  tentei quebrá-la. Peça a PSK para quem administra o FortiGate (ela é
  compartilhada entre todos os clientes dessa VPN, então alguém do time de
  rede/infra já tem o valor em texto puro).
- `vpn_xauth_user.txt` — o usuário que você digita hoje ao conectar pelo
  FortiClient.
- `vpn_xauth_password.txt` — a senha correspondente.

Exemplo (PowerShell, sem adicionar newline):
```powershell
Set-Content -Path secrets\vpn_psk.txt -Value "sua-psk-aqui" -NoNewline
Set-Content -Path secrets\vpn_xauth_user.txt -Value "seu-usuario" -NoNewline
Set-Content -Path secrets\vpn_xauth_password.txt -Value "sua-senha" -NoNewline
```

**Atenção**: este README NÃO está no `.gitignore` (só `secrets/*.txt` está) —
nunca cole valores reais aqui, só neste exemplo genérico. Se algum dia
colar algo real por engano, troque a PSK/senha reais com a empresa/infra
antes de considerar o incidente resolvido, mesmo que o arquivo nunca tenha
sido commitado.
