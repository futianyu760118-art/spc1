---
trigger: always
---

# Task Completion Docker Compose Restart

After every completed coding task in this project, automatically rebuild and restart the Docker Compose services.

Run from the project root:

```powershell
.\scripts\restart-docker-compose.ps1
```

Default behavior:

- Uses `docker-compose.yml`.
- Runs `docker compose up -d --build`.
- Prints `docker compose ps` after restart.

For the development compose file, run:

```powershell
.\scripts\restart-docker-compose.ps1 -ComposeFile docker-compose-dev.yml
```
