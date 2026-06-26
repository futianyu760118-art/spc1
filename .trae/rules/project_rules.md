---
trigger: always
---

# 项目规则 — 任务完成后自动重启

## 任务完成后的自动操作

每次完成代码修改任务后，必须按以下步骤重启项目：

在根目录下执行：
```bash
docker compose build backend frontend
docker compose down backend frontend
docker compose up -d backend frontend
```

### 执行规则
- 如果只修改了后端代码（`backend`），只需构建和重启后端
- 如果只修改了前端代码（`frontend`），只需构建和重启前端
- 如果前后端都有修改，两个都需要重启
- 重启前先停止之前运行的容器，避免端口冲突
