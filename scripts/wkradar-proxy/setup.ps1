<#
.SYNOPSIS
    Configura o proxy TCP que permite ao container `promax-automation`
    (Docker Desktop/Windows) alcançar a API WKRADAR (rede interna
    172.20.5.0/24), e deixa tudo pronto para sobreviver a reinicializações.

.DESCRIPTION
    Containers Docker, neste ambiente (Docker Desktop + WSL2 no Windows),
    NÃO conseguem rotear até a rede da WKRADAR — testado exaustivamente com
    bridge, --network host, macvlan e ipvlan, todos bloqueados pelo
    isolamento de rede do Docker Desktop. A distro WSL2 em si (fora do
    Docker) consegue, porque usa a rota real do Windows/roteador local.

    Este script:
      1. Garante `vmIdleTimeout=-1` no `.wslconfig` do usuário (sem isso, o
         Windows desliga a distro WSL2 depois de ficar ociosa, matando o
         proxy junto).
      2. Copia `proxy.py` para dentro da distro WSL2 e instala como serviço
         systemd (`wkradar-proxy.service`), com restart automático.
      3. Registra um "keep-alive" (processo `wsl.exe ... sleep infinity`) na
         pasta Startup do Windows — necessário porque o Windows finaliza
         instâncias de distro WSL2 individuais quando não há nenhum
         processo/sessão ativa ligado a elas, independente do
         `vmIdleTimeout` (que só controla a VM utilitária inteira).
      4. Testa a conectividade final.

    Idempotente — pode rodar de novo sem duplicar nada.

.PARAMETER DistroName
    Nome da distro WSL2 onde o proxy vai rodar. Default: a distro padrão
    configurada no WSL (primeira linha de `wsl -l -q`).

.EXAMPLE
    .\scripts\wkradar-proxy\setup.ps1
#>

param(
    [string]$DistroName = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $DistroName) {
    $DistroName = (wsl -l -q 2>$null | Select-Object -First 1) -replace "`0", ""
    $DistroName = $DistroName.Trim()
}
if (-not $DistroName) {
    throw "Não foi possível detectar a distro WSL2 padrão. Informe explicitamente: .\setup.ps1 -DistroName Ubuntu-26.04"
}
Write-Output "Distro WSL2 usada: $DistroName"

# --- 1. .wslconfig: garante vmIdleTimeout=-1 (preserva o resto do arquivo) ---
$wslConfigPath = Join-Path $env:USERPROFILE ".wslconfig"
$lines = @()
if (Test-Path $wslConfigPath) {
    $lines = Get-Content $wslConfigPath
}

if ($lines -notcontains "[wsl2]") {
    $lines += "[wsl2]"
}

$hasIdleTimeout = $lines | Where-Object { $_ -match "^\s*vmIdleTimeout\s*=" }
if (-not $hasIdleTimeout) {
    $wsl2Index = [array]::IndexOf($lines, "[wsl2]")
    $lines = $lines[0..$wsl2Index] + "vmIdleTimeout=-1" + $lines[($wsl2Index + 1)..($lines.Length - 1)]
    Set-Content -Path $wslConfigPath -Value $lines -Encoding utf8
    Write-Output "[wslconfig] vmIdleTimeout=-1 adicionado em $wslConfigPath (reinicie o WSL2 com 'wsl --shutdown' para aplicar, se ainda nao aplicado)"
} else {
    Write-Output "[wslconfig] vmIdleTimeout ja configurado, nada a fazer"
}

# --- 2. Proxy + serviço systemd dentro da distro ---
function Invoke-Wsl {
    param([string]$Command)
    $env:MSYS_NO_PATHCONV = "1"
    wsl.exe -d $DistroName -u root -- sh -c $Command
}

Write-Output "[wsl] Criando /opt/wkradar-proxy e copiando proxy.py..."
Invoke-Wsl "mkdir -p /opt/wkradar-proxy"
Get-Content (Join-Path $scriptDir "proxy.py") -Raw |
    wsl.exe -d $DistroName -u root -- sh -c "cat > /opt/wkradar-proxy/proxy.py"

Write-Output "[wsl] Instalando o servico systemd..."
(Get-Content (Join-Path $scriptDir "wkradar-proxy.service") -Raw) -replace "`r`n", "`n" |
    wsl.exe -d $DistroName -u root -- sh -c "cat > /etc/systemd/system/wkradar-proxy.service"
Invoke-Wsl "systemctl daemon-reload && systemctl enable --now wkradar-proxy.service"

Start-Sleep -Seconds 2
$status = wsl.exe -d $DistroName -u root -- systemctl is-active wkradar-proxy.service
Write-Output "[wsl] Status do servico: $status"

# --- 3. Keep-alive (Startup do Windows + já inicia agora) ---
# O keep-alive precisa ser auto-regenerativo: um unico "wsl.exe ... sleep
# infinity" solto pode morrer por qualquer motivo transitorio (suspensao do
# PC, etc.) e, sem supervisao, nada o reinicia antes do proximo login. Em vez
# disso, o VBS roda um loop (wscript.exe residente) que relanca o processo
# sempre que ele cair.
$startupFolder = [Environment]::GetFolderPath("Startup")
$vbsPath = Join-Path $startupFolder "wkradar-proxy-keepalive.vbs"
$vbsContent = @"
Do While True
    CreateObject("WScript.Shell").Run "wsl.exe -d $DistroName -u root -e sleep infinity", 0, True
    WScript.Sleep 3000
Loop
"@
Set-Content -Path $vbsPath -Value $vbsContent -Encoding ASCII
Write-Output "[startup] Keep-alive (auto-regenerativo) registrado em: $vbsPath"

$supervisorRunning = Get-CimInstance Win32_Process -Filter "Name='wscript.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*wkradar-proxy-keepalive.vbs*" }
if (-not $supervisorRunning) {
    Start-Process -FilePath "wscript.exe" -ArgumentList "`"$vbsPath`"" -WindowStyle Hidden
    Write-Output "[startup] Supervisor do keep-alive iniciado agora (nao precisa esperar o proximo login)"
} else {
    Write-Output "[startup] Supervisor do keep-alive ja estava em execucao (PID $($supervisorRunning.ProcessId))"
}

# --- 4. Teste final ---
Write-Output "[teste] Verificando conectividade 172.20.5.8:443 a partir da distro..."
Invoke-Wsl "nc -zv -w 5 172.20.5.8 443"

Write-Output ""
Write-Output "Setup concluido. O container deve acessar a API WKRADAR via:"
Write-Output "  https://host.docker.internal:18443/wk.api/api/v1/token"
Write-Output "(ja configurado em docker-compose.yml via WKRADAR_TOKEN_URL)"
