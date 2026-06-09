# 任务完成后自动构建并重启 Docker Compose

每次完成代码修改任务后，必须在项目根目录自动执行：

```powershell
.\scripts\restart-docker-compose.ps1
```

默认效果：

- 使用 `docker-compose.yml`
- 执行 `docker compose up -d --build`
- 完成后输出 `docker compose ps`

如果明确需要开发环境 compose 文件，则执行：

```powershell
.\scripts\restart-docker-compose.ps1 -ComposeFile docker-compose-dev.yml
```
