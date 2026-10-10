---
name: deploy-project
description: 当用户说"部署项目"、"部署到远程"、"发布部署"、"deploy"、"Deploy"、"上服务器" 等时触发。运行 SPC-v2 一键部署脚本 scripts/deploy-remote.ps1，自动构建镜像并并行部署到多台远程服务器 Docker。仅用于部署本项目到远程，不要用于其它任务。
---

# 部署项目 (deploy-project)

用户要把 SPC-v2 项目部署到远程服务器的 Docker。直接运行一键部署脚本即可，无需其它步骤。

## 操作

在仓库根目录（`D:\wanghuazheng\project\SPC-v2`）用 bash 运行：

```bash
powershell -ExecutionPolicy Bypass -File scripts\deploy-remote.ps1 -NonInteractive
```

**必须**：
- 加 `-NonInteractive`（脚本失败时不阻塞等待回车）。
- 给 bash 调用设长超时（建议 ≥ 1800000ms，即 30 分钟），因为镜像构建 + 打包 + 上传远程可能耗时 5~30 分钟。

## 服务器拓扑与配置

- 多台服务器配置在 `scripts/deploy-config.ps1` 的 `$DEPLOY_SERVERS` 数组（Name/Host/User/Pass/IdentityFile/Path/Role/EnvFile）。
- `Role = full`：部署 postgres/redis/backend/frontend 全套（docker-compose-prod.yml，redis 发布 16379 供 app 服务器连接）。
- `Role = app`：只部署 backend/frontend（docker-compose-app.yml），`DATABASE_URL`/`REDIS_URL` 指向 full 服务器；每个 app 服务器必须有独立的 `EnvFile`（里面配置指向主库的连接串与不同的 `SERVER_ID`）。
- 兼容旧单机配置：`$DEPLOY_SERVERS` 为空时回退 `$DEPLOY_REMOTE_HOST` 等旧变量，行为与旧版一致。
- 默认部署数组中全部服务器；`-Servers main,app1` 只部署指定名称的服务器。

## 新增一台纯应用服务器

1. 在 `$DEPLOY_SERVERS` 加一个条目：`Role = "app"`、`EnvFile` 指向新建的 env 文件（复制仓库根 `.env.app1.example` 模板，填好后保存为 `.env.app1`，**不进仓库**）
2. `.env.app1` 关键项：
   - `DATABASE_URL` / `DATABASE_URL_SYNC`：指向 full 服务器（postgres 端口 15432）
   - `REDIS_URL`：指向 full 服务器（redis 端口 16379，密码同 `REDIS_PASSWORD`）
   - `SERVER_ID`：每台唯一（如 `spc-app1`，记录在同步日志里）
   - `SECRET_KEY`：**与 full 服务器一致**（共库签发 JWT，不一致会导致跨实例 token 失效）
   - `ERP_SYNC_ENABLED=false`：ERP 同步只应在 full 服务器跑
   - `WRITEBACK_ENABLED` 留空：回写 Worker 只应在一台服务器开启
3. 新服务器装 Docker、配置 SSH 密钥、开放 18084/18085，然后正常执行一键部署（bundle 已含 nginx.conf，首次部署自动写入）

## 脚本行为（全自动，无需人工干预）

1. 探测各台目标服务器版本号，取全局最大序号 +1 作为本次统一版本号
2. 构建 `spc-v2-backend:latest` / `spc-v2-frontend:latest` 镜像（一次）
3. 打包：公共镜像包 `images.tar.gz` 压缩一次；每台服务器另打小 config bundle（两个 compose + 权威版 nginx.conf（`scripts/remote/nginx.conf`）+ 该台 EnvFile 作 .env）
4. 每台一个并行任务：scp 上传 → 远程 `docker load` + 版本化（镜像双标签、快照 .env/compose/meta 到 versions/<版本>/）+ 按角色 `docker compose up -d` + 健康检查 + 自动清理只保留最近 5 个版本
5. 汇总结果表（每台 成功/失败/耗时/地址）；单台失败不中断其余，最终 exit code 非零、失败日志保留在临时目录
6. 验证：远程侧权威健康检查（后端 ping + 前端 18084 返回 200）；本机探测前端仅作参考，失败为黄色警告不中断（操作者本机可能经代理）

## 可选参数（用户没提就别加）

- `-Servers <名称,名称>`：只部署指定服务器（默认全部）
- `-KeepRemoteEnv`：保留远程已有 .env 不覆盖（默认用该台 EnvFile 覆盖远程 .env）
- `-SkipBuild`：跳过构建（本机镜像未变化时提速）
- `-SkipUpload`：镜像已在远程，只重启容器
- `-SkipVerify`：跳过验证

## 版本回退

部署自动生成版本（vN-时间戳，可在部署输出中看到）。出问题时回退到历史版本：

```bash
powershell -ExecutionPolicy Bypass -File scripts\manage-version.ps1 list                                   # 查看版本（默认第一台服务器）
powershell -ExecutionPolicy Bypass -File scripts\manage-version.ps1 -Server app1 list                      # 指定服务器
powershell -ExecutionPolicy Bypass -File scripts\manage-version.ps1 -Server app1 rollback v11-20260827-0930
powershell -ExecutionPolicy Bypass -File scripts\manage-version.ps1 -Server app1 cleanup                   # 手动清理（保留最近 5 个）
```

## 输出解读

- 成功：末尾打印 `===== 部署结果汇总 =====` 表格（每台 成功/地址），向用户报告部署成功及各台访问地址 `http://<ip>:18084`。
- 失败：脚本打印红色 `===== 部署失败 =====` 或 `===== 部分服务器部署失败 =====` 及错误原因。把报错内容原样告诉用户。
  - 若是 SSH 认证失败（`Permission denied`），提示用户检查 `scripts/deploy-config.ps1` 中对应服务器的 `Pass` / `IdentityFile` 配置是否正确。
  - 若是远程命令失败，把远程命令和 exit 码一并给出。
  - 部分失败时，失败服务器的完整日志保留在输出提示的临时目录 `logs\<名称>.log` 中。

## 安全红线

- `.env`（含数据库/Redis/ERP 密码）与 SSH 密钥**永不进仓库**、永不出现在汇报文本里。
- `deploy-config.ps1` 只填连接信息与文件路径；SSH 密码建议留空走密钥认证或手动输入。
- nginx.conf 权威源在 `scripts/remote/nginx.conf`（部署 bundle 只会在远程缺失时写入，不覆盖远程已手工配置的版本）。
