# CC Switch Usage Sidecar Docker 部署

这个部署方式使用 compose overlay 把 `cc-switch-usage-sidecar` 加到现有 sub2api Docker 栈里，不直接修改 `docker-compose.yml` 主文件，方便后续同步 sub2api 上游更新。

## 文件

| 文件 | 说明 |
|---|---|
| `docker-compose.cc-switch-sidecar.yml` | sidecar compose overlay |
| `.env.cc-switch-sidecar.example` | 需要追加到 `.env` 的变量示例 |
| `../../sidecar/Dockerfile` | sidecar 镜像构建文件 |

## 启动

在 `sub2api/deploy` 目录：

```bash
cp .env.example .env
cat .env.cc-switch-sidecar.example >> .env
```

编辑 `.env`，至少设置：

```env
POSTGRES_PASSWORD=change_this_secure_password
CC_USAGE_SIDECAR_REPORT_TOKEN=change-me-to-a-long-random-token
```

启动：

```bash
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml up -d --build
```

查看状态：

```bash
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml ps
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml logs -f sub2api
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml logs -f cc-switch-usage-sidecar
```

## 网络访问

## 管理端页面

本项目已在 sub2api 管理端增加 `CC-Switch 用量` 页面，访问路径：

```text
http://127.0.0.1:8080/admin/external-usage
```

注意：如果 compose 仍使用 `image: weishaw/sub2api:latest`，页面不会出现，因为官方镜像不包含本地补丁。需要把 sub2api 构建为本地镜像后再启动，例如在 `sub2api` 根目录执行：

```bash
docker build -t sub2api:cc-switch-local .
```

然后在 `sub2api/deploy/docker-compose.yml` 中把 sub2api 服务镜像改为：

```yaml
image: sub2api:cc-switch-local
```

重启 sub2api：

```bash
cd /mnt/f/work/code/other/20260626/CC_Switch_plugin/sub2api/deploy
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml up -d --force-recreate sub2api
```

默认配置没有把 sidecar 端口暴露到公网，只在 `sub2api-network` 内部监听 `0.0.0.0:8788`。

如果 `cc_usage_reporter` 在 Docker 宿主机或 Windows 上运行，需要在 `docker-compose.cc-switch-sidecar.yml` 里取消 `ports` 注释：

```yaml
ports:
  - "127.0.0.1:${CC_USAGE_SIDECAR_PORT:-8788}:8788"
```

然后重启：

```bash
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml up -d --force-recreate cc-switch-usage-sidecar
```

客户端配置示例：

```json
{
  "base_url": "http://127.0.0.1:8788",
  "token": "与 CC_USAGE_SIDECAR_REPORT_TOKEN 一致",
  "username": "alice"
}
```

## 数据库

sidecar 通过 compose 内部网络连接 PostgreSQL：

```text
postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}?sslmode=disable
```

首次启动时，如果 `CC_USAGE_SIDECAR_AUTO_MIGRATE=true`，会自动创建：

- `external_usage_daily`
- `admin_external_usage_v`

## 常见故障

### sub2api 报 `lookup postgres ... network is unreachable`

典型日志：

```text
Auto setup failed: database connection failed: ping failed: dial tcp: lookup postgres ... network is unreachable
```

这通常不是 PostgreSQL 密码问题，而是 `sub2api` 容器没有正确进入 compose 创建的内部网络，或者 Docker/WSL 网络状态异常。正常情况下，容器内解析 `postgres` 应该走 Docker 内置 DNS，并解析到同一 compose 网络中的 `postgres` 服务。

优先按下面步骤重建这一组容器：

```bash
cd /mnt/f/work/code/other/20260626/CC_Switch_plugin/sub2api/deploy

docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml down

docker rm -f sub2api sub2api-postgres sub2api-redis cc-switch-usage-sidecar 2>/dev/null || true

docker network prune -f

docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml up -d --build
```

如果仍然失败，检查容器是否在同一个网络：

```bash
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml ps

docker inspect sub2api --format '{{json .NetworkSettings.Networks}}'
docker inspect sub2api-postgres --format '{{json .NetworkSettings.Networks}}'
```

再进入 `sub2api` 容器检查 DNS：

```bash
docker exec -it sub2api sh -lc 'cat /etc/resolv.conf; getent hosts postgres || nslookup postgres || true'
```

如果 `/etc/resolv.conf` 里不是 Docker 内置 DNS，或 `postgres` 无法解析，可以重启 Docker Desktop / WSL 后重新启动 compose：

```powershell
wsl --shutdown
```

然后重新打开 WSL，回到 deploy 目录执行：

```bash
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml up -d --build
```

## 停止

```bash
docker compose -f docker-compose.yml -f docker-compose.cc-switch-sidecar.yml down
```

这不会删除 volume。删除数据请谨慎使用 `-v`。
