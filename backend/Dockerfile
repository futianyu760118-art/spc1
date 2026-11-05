FROM python:3.12-slim-bookworm

WORKDIR /app

# 安装 Microsoft ODBC Driver 17 for SQL Server
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        postgresql-client-15 \
        gnupg2 \
        apt-transport-https \
        unixodbc \
        unixodbc-dev \
        libgssapi-krb5-2 && \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 && \
    apt-get purge -y --auto-remove curl gnupg2 apt-transport-https && \
    rm -rf /var/lib/apt/lists/*

# 降低 OpenSSL 安全等级，允许连接仅支持旧版 TLS 的 SQL Server
RUN sed -i '/\[openssl_init\]/a ssl_conf = ssl_sect' /etc/ssl/openssl.cnf && \
    printf '\n[ssl_sect]\nsystem_default = system_default_sect\n\n[system_default_sect]\nMinProtocol = TLSv1\nCipherString = DEFAULT:@SECLEVEL=0\n' >> /etc/ssl/openssl.cnf

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 订单写操作注册表唯一源在 agents/shared（构建时经 --build-context agents_shared 注入）
COPY --from=agents_shared order-write-operations.json /app/app/services/order/write_operations.json

# 文件存储目录（会被 docker-compose volume 挂载覆盖）
RUN mkdir -p /app/uploads /app/skills-imported

EXPOSE 8000

CMD python init_database.py && uvicorn app.main:app --host 0.0.0.0 --port 8000
