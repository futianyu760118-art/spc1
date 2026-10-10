#requires -Version 5.1
# SPC-v2 远程部署共享配置与 SSH 辅助函数
# 被 deploy-remote.ps1 / manage-version.ps1 dot-source，请勿单独运行。

# ===== 多服务器部署配置（按需修改，两脚本共用）=====
# 每台服务器一个条目：
#   Name        唯一名称（-Servers 筛选、manage-version.ps1 -Server 选择用）
#   Host/IP、User、Pass、IdentityFile、Path  连接信息（Pass 留空则用密钥或手动输入）
#   Role        full = postgres/redis/backend/frontend 全套；
#               app  = 仅 backend/frontend，DATABASE_URL/REDIS_URL 指向 full 服务器
#   EnvFile     该台使用的 .env 文件（相对仓库根或绝对路径；部署时覆盖远程 .env，
#               加 -KeepRemoteEnv 参数可保留远程已有 .env）
$DEPLOY_SERVERS = @(
    @{
        Name         = "main"
        Host         = "150.158.13.110"
        User         = "ubuntu"
        Pass         = ""
        IdentityFile = "D:\wanghuazheng\whz_server.pem"
        Path         = "/home/ubuntu/apps/hj-spc"
        Role         = "full"
        EnvFile      = ".env"
    }
    #@{
    #    Name         = "app1"
    #    Host         = "1.2.3.4"
    #    User         = "ubuntu"
    #    Pass         = ""
    #    IdentityFile = ""
    #    Path         = "/home/ubuntu/apps/hj-spc"
    #    Role         = "app"
    #    EnvFile      = ".env.app1"
    #}
)

# ===== 旧单机配置（$DEPLOY_SERVERS 为空时使用，向后兼容）=====
$DEPLOY_REMOTE_HOST   = "150.158.13.110"                  # 远程服务器 IP / 域名
$DEPLOY_REMOTE_USER   = "ubuntu"                          # SSH 用户名
$DEPLOY_REMOTE_PASS   = ""                                # SSH 密码（留空则用密钥或手动输入）
$DEPLOY_REMOTE_PATH   = "/home/ubuntu/apps/hj-spc"        # 远程部署目录
$DEPLOY_IDENTITY_FILE = "D:\wanghuazheng\whz_server.pem"  # SSH 密钥文件（留空用 ~/.ssh/id_rsa）
# ===== 配置结束 =====

# 控制台输出统一 UTF-8（中文在 UTF-8 终端不乱码；ssh 返回的 UTF-8 字节也能正确解码）
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# 返回生效的服务器列表（多服务器数组优先；数组为空回退旧单机变量）。
# 注意：多服务器数组与旧单机变量同时存在时只认数组，旧变量仅作回退。
function Get-DeployServers {
    $servers = @()
    if ($DEPLOY_SERVERS -and @($DEPLOY_SERVERS).Count -gt 0) {
        foreach ($s in @($DEPLOY_SERVERS)) {
            $servers += [pscustomobject]@{
                Name         = [string]$s.Name
                Host         = [string]$s.Host
                User         = [string]$s.User
                Pass         = [string]$s.Pass
                IdentityFile = [string]$s.IdentityFile
                Path         = [string]$s.Path
                Role         = if ([string]$s.Role -eq "app") { "app" } else { "full" }
                EnvFile      = [string]$s.EnvFile
            }
        }
    } elseif ($DEPLOY_REMOTE_HOST) {
        $servers += [pscustomobject]@{
            Name         = "main"
            Host         = $DEPLOY_REMOTE_HOST
            User         = $DEPLOY_REMOTE_USER
            Pass         = $DEPLOY_REMOTE_PASS
            IdentityFile = $DEPLOY_IDENTITY_FILE
            Path         = $DEPLOY_REMOTE_PATH
            Role         = "full"
            EnvFile      = ""
        }
    }
    if ($servers.Count -eq 0) { throw "未配置部署服务器：请在 deploy-config.ps1 配置 DEPLOY_SERVERS 数组或 DEPLOY_REMOTE_HOST" }

    $names = @{}
    foreach ($s in $servers) {
        if (-not $s.Name) { throw "服务器配置错误: Name 不能为空" }
        if (-not $s.Host) { throw "服务器 '$($s.Name)' 配置错误: Host 不能为空" }
        if (-not $s.User) { throw "服务器 '$($s.Name)' 配置错误: User 不能为空" }
        if (-not $s.Path) { throw "服务器 '$($s.Name)' 配置错误: Path 不能为空" }
        if ($names.ContainsKey($s.Name)) { throw "服务器 Name 重复: $($s.Name)" }
        $names[$s.Name] = $true
    }
    return ,$servers
}

# 返回服务器角色对应的 compose 文件名
function Get-ComposeFileForRole {
    param([Parameter(Mandatory = $true)][string]$Role)
    if ($Role -eq "app") { return "docker-compose-app.yml" }
    return "docker-compose-prod.yml"
}

# 初始化指定服务器的 SSH 认证，生成 $script:DeploySshOpts / $script:DeployTarget / $script:DeployRemotePath。
# TempDir: 可写临时目录（密码认证时在其中生成 askpass 脚本）。
function Initialize-DeploySsh {
    param([Parameter(Mandatory = $true)][string]$TempDir,
          [Parameter(Mandatory = $true)]$Server)

    $script:DeployTarget = "$($Server.User)@$($Server.Host)"
    $script:DeployRemotePath = $Server.Path

    $keyFile = $Server.IdentityFile
    if (-not $keyFile) { $keyFile = Join-Path $env:USERPROFILE ".ssh\id_rsa" }

    $script:DeploySshOpts = @(
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=5"
    )

    if (Test-Path -LiteralPath $keyFile) {
        Write-Host "使用密钥认证: $keyFile"
        $script:DeploySshOpts = @("-i", $keyFile) + $script:DeploySshOpts
    } elseif ($Server.Pass) {
        $passFile = Join-Path $TempDir "pass.txt"
        [System.IO.File]::WriteAllText($passFile, $Server.Pass, [System.Text.Encoding]::ASCII)
        $askpassCmd = Join-Path $TempDir "askpass.cmd"
        Set-Content -Path $askpassCmd -Value "@echo off`r`ntype `"$passFile`"" -Encoding ASCII
        $env:SSH_ASKPASS = $askpassCmd
        $env:SSH_ASKPASS_REQUIRE = "force"
        Write-Host "使用密码认证（密钥文件不存在: $keyFile）"
    } else {
        Write-Host "未找到密钥文件且未配置密码，请在 ssh 提示时手动输入密码"
    }
}

# 执行远程命令，退出码非 0 时抛错（需先 Initialize-DeploySsh 指定服务器）
function Invoke-Remote {
    param([Parameter(Mandatory = $true)][string]$Command)
    & ssh @($script:DeploySshOpts + $script:DeployTarget + $Command)
    if ($LASTEXITCODE -ne 0) { throw "远程命令失败 (exit=$LASTEXITCODE): $Command" }
}

# 执行远程命令并捕获 stdout（忽略退出码；抑制 stderr 以免 PS5.1 EAP=Stop 抛错）
function Invoke-RemoteCapture {
    param([Parameter(Mandatory = $true)][string]$Command)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & ssh @($script:DeploySshOpts + $script:DeployTarget + $Command) 2>$null
    } finally {
        $ErrorActionPreference = $prev
    }
    return $out
}

# 上传本地文件到远程
function Copy-ToRemote {
    param([Parameter(Mandatory = $true)][string]$LocalFile,
          [Parameter(Mandatory = $true)][string]$RemoteDest)
    & scp @($script:DeploySshOpts + $LocalFile + "${script:DeployTarget}:${RemoteDest}")
    if ($LASTEXITCODE -ne 0) { throw "scp 失败: $LocalFile -> ${script:DeployTarget}:${RemoteDest}" }
}

# 把远程 bash 脚本写入本地临时文件（UTF-8 无 BOM）、scp 上传、远程 bash 执行。
# 说明：复杂脚本若直接作为 ssh 命令行参数传递，Windows ssh 重组参数时会丢失双引号
# （bash 中 echo "A|$B" 的 | 会变成管道），必须走文件通道保证内容逐字保真。
function Invoke-RemoteScript {
    param([Parameter(Mandatory = $true)][string]$Script,
          [Parameter(Mandatory = $true)][string]$TempDir,
          [switch]$Capture)
    $shLocal = Join-Path $TempDir "remote-run.sh"
    # 行尾归一化为 LF（若源 .ps1 被 git 重检出为 CRLF，here-string 会携带 \r 污染远程 bash，
    # 最坏情况 set -e\r 失效导致静默假成功，必须在此免疫）
    $Script = ($Script -replace "`r`n", "`n") -replace "`r", "`n"
    [System.IO.File]::WriteAllText($shLocal, $Script, (New-Object System.Text.UTF8Encoding $false))
    Copy-ToRemote $shLocal "$script:DeployRemotePath/.remote-run.sh"
    $runCmd = "bash $script:DeployRemotePath/.remote-run.sh"
    if ($Capture) {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $out = & ssh @($script:DeploySshOpts + $script:DeployTarget + $runCmd) 2>$null
        } finally {
            $ErrorActionPreference = $prev
        }
        return $out
    }
    & ssh @($script:DeploySshOpts + $script:DeployTarget + $runCmd)
    if ($LASTEXITCODE -ne 0) { throw "远程脚本执行失败 (exit=$LASTEXITCODE)" }
}
