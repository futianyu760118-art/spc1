#requires -Version 5.1
# 一键部署 SPC-v2 到远程 Docker（多服务器并行，带版本管理）
# 支持 1 台 full 服务器（postgres/redis/backend/frontend）+ N 台 app 服务器（仅 backend/frontend，
# 连 full 服务器的数据库/Redis）。每次完整部署所有目标服务器共用同一版本号 vN-时间戳
# （镜像双标签 + 配置快照，保留最近 5 个），出问题可用 scripts\manage-version.ps1 -Server <名称> rollback 秒级回退。
#
# 服务器列表与连接配置在 scripts\deploy-config.ps1 的 $DEPLOY_SERVERS 数组（旧单机变量仍兼容）。
# 可选参数：
#   -Servers <名称,名称>  只部署指定服务器（默认部署全部）
#   -KeepRemoteEnv        保留远程已有 .env 不覆盖（默认用该台 EnvFile 覆盖）
#   -SkipBuild / -SkipUpload / -SkipVerify / -NonInteractive  同旧版

param(
    [string]$RemoteHost = "",
    [string]$RemoteUser = "",
    [string]$RemotePath = "",
    [string]$IdentityFile = "",
    [string]$EnvFile = "",
    [string]$Note = "",
    [string]$Servers = "",
    [switch]$SkipBuild,
    [switch]$SkipUpload,
    [switch]$SkipVerify,
    [switch]$KeepRemoteEnv,
    [switch]$NonInteractive
)

. (Join-Path $PSScriptRoot "deploy-config.ps1")

# 命令行旧单机参数覆盖：传入任一即退化为单机模式（忽略服务器数组）
if ($RemoteHost -or $RemoteUser -or $RemotePath -or $IdentityFile) {
    $DEPLOY_SERVERS = @()
    if ($RemoteHost)   { $DEPLOY_REMOTE_HOST = $RemoteHost }
    if ($RemoteUser)   { $DEPLOY_REMOTE_USER = $RemoteUser }
    if ($RemotePath)   { $DEPLOY_REMOTE_PATH = $RemotePath }
    if ($IdentityFile) { $DEPLOY_IDENTITY_FILE = $IdentityFile }
}

$ErrorActionPreference = "Stop"

$scriptStart = Get-Date
$stepStart = $scriptStart
$script:jobs = @()

function Show-StepElapsed {
    param([Parameter(Mandatory = $true)][string]$Label)
    $sec = [math]::Round(((Get-Date) - $script:stepStart).TotalSeconds, 1)
    Write-Host "  [$Label] 耗时: ${sec}s"
    $script:stepStart = Get-Date
}

trap {
    $elapsed = [math]::Round(((Get-Date) - $script:scriptStart).TotalSeconds, 1)
    Write-Host ""
    Write-Host "===== 部署失败 (已运行 ${elapsed}s) =====" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($_.ScriptStackTrace) { Write-Host "位置: $($_.ScriptStackTrace)" }
    Write-Host "====================" -ForegroundColor Red
    if ($script:jobs) {
        $script:jobs | Stop-Job -ErrorAction SilentlyContinue
        $script:jobs | Remove-Job -Force -ErrorAction SilentlyContinue
    }
    if ($tmpDir -and (Test-Path $tmpDir)) { Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue }
    if (-not $NonInteractive) { Read-Host "按回车键退出..." }
    exit 1
}

$allServers = @(Get-DeployServers)

# -Servers 筛选（按名称，默认全部）
# 注意：PowerShell 变量不区分大小写，$Servers 参数有 [string] 类型约束，
# 局部数组一律用 $targetServers，绝不能与参数同名（数组赋值会被强转成字符串）
$serverFilter = $Servers
if ($serverFilter) {
    $filterNames = @($serverFilter -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $available = (@($allServers | ForEach-Object { $_.Name }) -join ", ")
    $targetServers = @()
    foreach ($name in $filterNames) {
        $match = $allServers | Where-Object { $_.Name -eq $name }
        if (-not $match) { throw "找不到服务器: $name（可用: $available）" }
        $targetServers += $match
    }
} else {
    $targetServers = $allServers
}

$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path

# 每台服务器补全 EnvFile（空则用 -EnvFile 参数或仓库根 .env）
foreach ($s in $targetServers) {
    if (-not $s.EnvFile) {
        $s.EnvFile = if ($EnvFile) { $EnvFile } else { Join-Path $RepoRoot ".env" }
    } elseif (-not [System.IO.Path]::IsPathRooted($s.EnvFile)) {
        $s.EnvFile = Join-Path $RepoRoot $s.EnvFile
    }
    if (-not (Test-Path -LiteralPath $s.EnvFile)) { throw "服务器 '$($s.Name)' 的 EnvFile 不存在: $($s.EnvFile)" }
}

foreach ($tool in @("docker", "ssh", "scp", "tar", "gzip")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "缺少必需工具: $tool" }
}

$tmpDir = Join-Path $env:TEMP ("spc-deploy-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmpDir | Out-Null
New-Item -ItemType Directory -Path (Join-Path $tmpDir "logs") | Out-Null

# ===== [1/6] 确定版本号（所有目标服务器取全局最大序号 +1；SkipUpload 不产生新版本）=====
$Version = ""
$versionNum = 0
if (-not $SkipUpload) {
    $serverNames = (@($targetServers | ForEach-Object { $_.Name }) -join ", ")
    Write-Host "[1/6] 确定版本号（目标服务器: $serverNames）..."
    $lastNum = 0
    foreach ($s in $targetServers) {
        Initialize-DeploySsh -TempDir $tmpDir -Server $s
        Invoke-Remote "echo SSH-OK" | Out-Null
        $raw = Invoke-RemoteCapture "cat $($s.Path)/last_version.txt 2>/dev/null || echo EMPTY"
        $lastNumStr = ("$raw").Trim()
        if ($lastNumStr -match '^\d+$') {
            if ([int]$lastNumStr -gt $lastNum) { $lastNum = [int]$lastNumStr }
        } else {
            $dirsRaw = Invoke-RemoteCapture "ls -1 $($s.Path)/versions 2>/dev/null || true"
            foreach ($line in @($dirsRaw)) {
                $t = "$line".Trim()
                if ($t -match '^v(\d+)-') {
                    $n = [int]$Matches[1]
                    if ($n -gt $lastNum) { $lastNum = $n }
                }
            }
        }
        Write-Host "  服务器 '$($s.Name)' 上一版本序号: $lastNumStr"
    }
    $versionNum = $lastNum + 1
    $Version = "v${versionNum}-" + (Get-Date -Format "yyyyMMdd-HHmm")
    Write-Host "  本次部署版本: $Version（全局最大序号: $lastNum）"
} else {
    Write-Host "[1/6] 跳过版本号（SkipUpload 不产生新版本）"
}
Show-StepElapsed "1/6"

# git 短哈希（记录进 meta，失败容忍）
$gitHash = ""
try {
    $gitOut = & git -C $RepoRoot rev-parse --short HEAD 2>$null
    if ($LASTEXITCODE -eq 0) { $gitHash = "$gitOut".Trim() }
} catch { $gitHash = "" }

if (-not $SkipUpload) {
    Write-Host "[2/6] 构建镜像 (SkipBuild=$SkipBuild) ..."
    if (-not $SkipBuild) {
        & docker build -t spc-v2-backend:latest -t "spc-v2-backend:$Version" (Join-Path $RepoRoot "backend")
        if ($LASTEXITCODE -ne 0) { throw "backend 镜像构建失败" }
        & docker build -t spc-v2-frontend:latest -t "spc-v2-frontend:$Version" (Join-Path $RepoRoot "frontend")
        if ($LASTEXITCODE -ne 0) { throw "frontend 镜像构建失败" }
        & docker build -f (Join-Path $RepoRoot "agents\gateway-agent\Dockerfile") -t aeos-gateway:latest -t "aeos-gateway:$Version" (Join-Path $RepoRoot "agents")
        if ($LASTEXITCODE -ne 0) { throw "gateway 镜像构建失败" }
    } else {
        & docker tag spc-v2-backend:latest "spc-v2-backend:$Version"
        if ($LASTEXITCODE -ne 0) { throw "本机不存在 spc-v2-backend:latest，无法 -SkipBuild（请先完整构建）" }
        & docker tag spc-v2-frontend:latest "spc-v2-frontend:$Version"
        if ($LASTEXITCODE -ne 0) { throw "本机不存在 spc-v2-frontend:latest，无法 -SkipBuild（请先完整构建）" }
        & docker image inspect aeos-gateway:latest | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "本机不存在 aeos-gateway:latest，无法 -SkipBuild（请先完整构建）" }
        & docker tag aeos-gateway:latest "aeos-gateway:$Version"
        if ($LASTEXITCODE -ne 0) { throw "gateway 镜像打版本标签失败" }
    }
    Show-StepElapsed "2/6"

    Write-Host "[3/6] 打包镜像与配置 ..."
    # 公共镜像包只压缩一次；每台服务器另有小 config bundle（compose + nginx.conf + 该台 .env）
    $imagesTar = Join-Path $tmpDir "images.tar"
    & docker save -o $imagesTar "spc-v2-backend:$Version" "spc-v2-frontend:$Version" "aeos-gateway:latest" "aeos-gateway:$Version"
    if ($LASTEXITCODE -ne 0) { throw "docker save 失败" }
    & gzip -f $imagesTar
    if ($LASTEXITCODE -ne 0) { throw "images.tar 压缩失败" }
    $imagesTarGz = "$imagesTar.gz"

    $noteSafe = ($Note -replace "[`r`n]+", " ").Replace("'", "")
    $created = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    # 远程权威 nginx 配置在 scripts/remote/nginx.conf（listen 18084 + resolver），
    # 仓库根 nginx.conf 是本地开发版（listen 80），只作回退。
    $nginxConf = Join-Path $RepoRoot "scripts\remote\nginx.conf"
    if (-not (Test-Path -LiteralPath $nginxConf)) { $nginxConf = Join-Path $RepoRoot "nginx.conf" }
    $nginxStage = Join-Path $tmpDir "nginx.conf"
    Copy-Item -LiteralPath $nginxConf -Destination $nginxStage -Force

    # 远程部署脚本模板：单引号 here-string（内部 bash $ 无需转义），占位符 .Replace 注入
    $remoteScriptTemplate = @'
set -e
export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH
cd __P__
mkdir -p data/uploads data/wecom_verify data/minio
gunzip -f images.tar.gz
docker load -i images.tar
docker tag "spc-v2-backend:__V__" spc-v2-backend:latest
docker tag "spc-v2-frontend:__V__" spc-v2-frontend:latest
mkdir -p .bundle-new
tar -xzf bundle.tar.gz -C .bundle-new
cp -f .bundle-new/docker-compose-prod.yml ./docker-compose-prod.yml
cp -f .bundle-new/docker-compose-app.yml ./docker-compose-app.yml
mkdir -p backend/certs
cp -f .bundle-new/backend/certs/caddy-root.crt ./backend/certs/caddy-root.crt
if [ "__KEEP_ENV__" = "1" ] && [ -f .env ]; then echo ENV-KEPT; else cp -f .bundle-new/.env ./.env; fi
if [ ! -f nginx.conf ]; then cp -f .bundle-new/nginx.conf ./nginx.conf; else echo NGINX-KEPT; fi
rm -rf .bundle-new
COMPOSE_FILE='__COMPOSE__'
mkdir -p "versions/__V__"
cp .env docker-compose-prod.yml docker-compose-app.yml "versions/__V__/"
printf 'version=%s\ncreated=%s\ngit=%s\nnote=%s\ncompose=%s\n' '__V__' '__CREATED__' '__GIT__' '__NOTE__' '__COMPOSE__' > "versions/__V__/meta.txt"
echo __N__ > last_version.txt
echo '__V__' > current.txt
docker compose -f "$COMPOSE_FILE" up -d
docker compose -f "$COMPOSE_FILE" ps
(for i in {1..20}; do
  if curl -s -o /dev/null http://localhost:18085/api/v1/common/ping; then echo BACKEND-OK; exit 0; fi
  sleep 3
done
echo BACKEND-NOT-READY
echo '--- compose ps ---'
docker compose -f "$COMPOSE_FILE" ps
echo '--- backend logs (tail 50) ---'
docker logs --tail 50 $(docker compose -f "$COMPOSE_FILE" ps -q backend 2>/dev/null | head -n1) 2>/dev/null
exit 1)
# 远程侧前端权威检查（不依赖操作者本机网络/代理）
fcode=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:18084/ || echo 000)
if [ "$fcode" != "200" ]; then fcode=$(curl -sk -o /dev/null -w '%{http_code}' https://localhost:18084/ || echo 000); fi
if [ "$fcode" = "200" ]; then echo FRONTEND-OK; else echo "FRONTEND-BAD:$fcode"; docker compose -f "$COMPOSE_FILE" logs --tail 20 frontend; exit 1; fi
# 清理旧版本：按目录名序号降序保留最近 5 个，当前运行版本不清理
cur=$(cat current.txt 2>/dev/null || echo '')
ls -1 versions 2>/dev/null | grep -E '^v[0-9]+-' | sed 's/^v\([0-9][0-9]*\)-.*/\1 &/' | sort -rn | awk '{print $2}' | tail -n +6 | while read old; do
  if [ "$old" = "$cur" ]; then continue; fi
  docker rmi "spc-v2-backend:$old" "spc-v2-frontend:$old" >/dev/null 2>&1 || true
  rm -rf "versions/$old"
  echo "已清理旧版本: $old"
done
# 清理本次部署的解包残留（镜像已 load 进 docker，tar 包不再需要）
rm -f bundle.tar.gz images.tar.gz images.tar
echo DEPLOY-VERSIONED __V__
'@

    $bundleFiles = @{}
    $remoteScripts = @{}
    foreach ($s in $targetServers) {
        $compose = Get-ComposeFileForRole -Role $s.Role
        $keepEnv = if ($KeepRemoteEnv) { "1" } else { "0" }

        $envStage = Join-Path $tmpDir "env\$($s.Name)"
        New-Item -ItemType Directory -Path $envStage -Force | Out-Null
        Copy-Item -LiteralPath $s.EnvFile -Destination (Join-Path $envStage ".env") -Force
        $bundleTar = Join-Path $tmpDir "bundle-$($s.Name).tar"
        & tar -cf $bundleTar -C $RepoRoot docker-compose-prod.yml docker-compose-app.yml backend/certs/caddy-root.crt -C $tmpDir nginx.conf -C $envStage .env
        if ($LASTEXITCODE -ne 0) { throw "服务器 '$($s.Name)' bundle 打包失败" }
        & gzip -f $bundleTar
        if ($LASTEXITCODE -ne 0) { throw "服务器 '$($s.Name)' bundle 压缩失败" }
        $bundleFiles[$s.Name] = "$bundleTar.gz"

        $remoteScripts[$s.Name] = $remoteScriptTemplate.
            Replace('__P__', $s.Path).Replace('__V__', $Version).
            Replace('__N__', "$versionNum").Replace('__CREATED__', $created).
            Replace('__GIT__', $gitHash).Replace('__NOTE__', $noteSafe).
            Replace('__KEEP_ENV__', $keepEnv).Replace('__COMPOSE__', $compose)
    }
    Show-StepElapsed "3/6"

    Write-Host "[4/6] 并行上传并部署到 $($targetServers.Count) 台服务器 ..."
    $script:jobs = @()
    foreach ($s in $targetServers) {
        $jobTmp = Join-Path $tmpDir "jobs\$($s.Name)"
        New-Item -ItemType Directory -Path $jobTmp -Force | Out-Null
        $logFile = Join-Path $tmpDir "logs\$($s.Name).log"
        $script:jobs += Start-Job -Name $s.Name -ScriptBlock {
            param($Server, $ConfigPath, $ImagesTarGz, $ConfigBundle, $RemoteScriptText, $JobTmpDir, $LogFile)
            . $ConfigPath
            $ErrorActionPreference = "Stop"
            $jobStart = Get-Date
            function Job-Out {
                param([Parameter(ValueFromPipeline = $true)][AllowEmptyString()]$Line)
                process {
                    $s = "$Line"
                    Write-Host $s
                    try {
                        [System.IO.File]::AppendAllText($LogFile, $s + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding $false))
                    } catch { }
                }
            }
            try {
                Initialize-DeploySsh -TempDir $JobTmpDir -Server $Server
                Invoke-Remote "mkdir -p $($Server.Path)" | Job-Out
                Copy-ToRemote $ImagesTarGz "$($Server.Path)/images.tar.gz"
                Copy-ToRemote $ConfigBundle "$($Server.Path)/bundle.tar.gz"
                Invoke-RemoteScript -Script $RemoteScriptText -TempDir $JobTmpDir | Job-Out
                [pscustomobject]@{
                    Name = $Server.Name; Role = $Server.Role; Success = $true
                    Message = "部署成功"; ElapsedSec = [math]::Round(((Get-Date) - $jobStart).TotalSeconds, 1)
                }
            } catch {
                $_.Exception.Message | Job-Out
                [pscustomobject]@{
                    Name = $Server.Name; Role = $Server.Role; Success = $false
                    Message = $_.Exception.Message; ElapsedSec = [math]::Round(((Get-Date) - $jobStart).TotalSeconds, 1)
                }
            }
        } -ArgumentList $s, (Join-Path $PSScriptRoot "deploy-config.ps1"), $imagesTarGz, $bundleFiles[$s.Name], $remoteScripts[$s.Name], $jobTmp, $logFile
    }
    Write-Host "  已启动 $($script:jobs.Count) 个并行任务"

    # 轮询输出各任务日志（带服务器名前缀），直到全部结束
    $offsets = @{}
    foreach ($j in $script:jobs) { $offsets[$j.Name] = 0 }
    while (@($script:jobs | Where-Object { $_.State -notin @("Completed", "Failed", "Stopped") }).Count -gt 0) {
        foreach ($j in $script:jobs) {
            $logFile = Join-Path $tmpDir "logs\$($j.Name).log"
            if (Test-Path -LiteralPath $logFile) {
                $lines = @(Get-Content -LiteralPath $logFile -ErrorAction SilentlyContinue)
                for ($i = $offsets[$j.Name]; $i -lt $lines.Count; $i++) {
                    Write-Host "[$($j.Name)] $($lines[$i])"
                }
                $offsets[$j.Name] = $lines.Count
            }
        }
        Start-Sleep -Seconds 2
    }
    foreach ($j in $script:jobs) {
        $logFile = Join-Path $tmpDir "logs\$($j.Name).log"
        if (Test-Path -LiteralPath $logFile) {
            $lines = @(Get-Content -LiteralPath $logFile -ErrorAction SilentlyContinue)
            for ($i = $offsets[$j.Name]; $i -lt $lines.Count; $i++) {
                Write-Host "[$($j.Name)] $($lines[$i])"
            }
        }
    }
    Show-StepElapsed "4/6"

    Write-Host "[5/6] 汇总结果 ..."
    $results = @()
    foreach ($j in $script:jobs) {
        $result = $null
        try {
            $out = @(Receive-Job -Job $j -ErrorAction SilentlyContinue)
            $result = $out | Where-Object { $_ -is [pscustomobject] -and $_.Name } | Select-Object -First 1
        } catch {
            $result = $null
        }
        if (-not $result) {
            $result = [pscustomobject]@{
                Name = $j.Name; Role = ""; Success = $false
                Message = "任务异常结束（详见日志 $tmpDir\logs\$($j.Name).log）"; ElapsedSec = 0
            }
        }
        $results += $result
    }
    $script:jobs | Remove-Job -Force -ErrorAction SilentlyContinue
    $script:jobs = @()
    Show-StepElapsed "5/6"
} else {
    Write-Host "[2/6] 跳过构建（SkipUpload 不上传，无需构建）"
    Write-Host "[3/6] 跳过打包（SkipUpload 不上传，无需打包）"
    Write-Host "[4/6] 跳过上传 (SkipUpload=$SkipUpload) ..."
    Write-Host "[5/6] 仅远程启动 ..."
    foreach ($s in $targetServers) {
        $compose = Get-ComposeFileForRole -Role $s.Role
        Initialize-DeploySsh -TempDir $tmpDir -Server $s
        Invoke-Remote "export PATH=/opt/homebrew/bin:/usr/local/bin:`$PATH; cd $($s.Path) && docker compose -f $compose down && docker compose -f $compose up -d && docker compose -f $compose ps"
    }
    $results = foreach ($s in $targetServers) {
        [pscustomobject]@{ Name = $s.Name; Role = $s.Role; Success = $true; Message = "已重启"; ElapsedSec = 0 }
    }
    Show-StepElapsed "5/6"
}

if (-not $SkipVerify) {
    Write-Host "[6/6] 验证 ..."
    foreach ($r in $results) {
        if (-not $r.Success) { continue }
        $srv = $targetServers | Where-Object { $_.Name -eq $r.Name } | Select-Object -First 1
        if (-not $srv) { continue }
        try {
            $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://$($srv.Host):18084/" -TimeoutSec 10
            if ($resp.StatusCode -ne 200) { throw "HTTP $($resp.StatusCode)" }
            Write-Host "  [$($srv.Name)] 前端 http://$($srv.Host):18084/ 返回 200"
        } catch {
            Write-Host "  [$($srv.Name)] 警告: 本机探测前端失败（可能经代理或网络受限: $($_.Exception.Message)）；远程侧健康检查已通过（BACKEND-OK + FRONTEND-OK）" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "[6/6] 跳过验证 (SkipVerify=$SkipVerify)"
}
Show-StepElapsed "6/6"

$totalMin = [math]::Round(((Get-Date) - $scriptStart).TotalSeconds / 60, 1)
Write-Host "总耗时: ${totalMin} 分钟（约 $([math]::Round(((Get-Date) - $scriptStart).TotalSeconds, 0))s）"
if ($Version) { Write-Host "已部署版本: $Version（所有目标服务器）" }

Write-Host ""
Write-Host "===== 部署结果汇总 ====="
$summaryTable = foreach ($r in $results) {
    $srv = $targetServers | Where-Object { $_.Name -eq $r.Name } | Select-Object -First 1
    [pscustomobject]@{
        服务器 = $r.Name
        角色   = if ($srv) { if ($srv.Role -eq "app") { "纯应用" } else { "全套" } } else { "-" }
        结果   = if ($r.Success) { "成功" } else { "失败" }
        耗时   = "$($r.ElapsedSec)s"
        地址   = if ($r.Success -and $srv) { "http://$($srv.Host):18084" } else { "-" }
        说明   = $r.Message
    }
}
$summaryTable | Format-Table -AutoSize

$anyFailed = @($results | Where-Object { -not $_.Success }).Count -gt 0
if (-not $anyFailed) {
    Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
    if ($Version) { Write-Host "如需回退: .\scripts\manage-version.ps1 -Server <名称> rollback <版本名>（先 .\scripts\manage-version.ps1 -Server <名称> list 查看）" }
    Write-Host "部署完成。"
} else {
    Write-Host "===== 部分服务器部署失败 =====" -ForegroundColor Red
    Write-Host "失败服务器的日志已保留在: $tmpDir\logs" -ForegroundColor Yellow
    exit 1
}
