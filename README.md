# Dock Panel

Cockpit 插件：按项目管理 Docker（兼容 Compose）、维护 TLS 证书、查看容器日志。

- 后端：Python 3 CLI，由 Cockpit `spawn` 调用
- 前端：Vue 3 + Vite，安装后出现在 Cockpit 侧栏

## 功能

1. **项目管理**
   - 新建托管 Compose 项目（写入 `/var/lib/dock-panel/projects/<name>/`）
   - 导入已有 `compose.yaml` / `docker-compose.yml`
   - 扫描 `/opt`、`/srv`、`/home` 等目录中的 Compose 文件
   - 发现本机已有的 `docker compose ls` 栈
   - 启动 / 停止 / 重启 / 拉取 / 卸载
   - 在线编辑 compose 与 `.env`
2. **证书维护**
   - 导入 PEM 证书/私钥/证书链
   - 用 openssl 生成自签证书（含 SAN）
   - 查看到期时间、指纹、主题
   - 关联到项目：在项目目录下创建 `certs/<name>/{cert,key}.pem` 符号链接，供 Compose volume 挂载
3. **日志**
   - 按项目、按服务查看
   - 跟踪（follow）实时输出

## 架构

```
浏览器 (Cockpit 页面)
    └─ Vue 3  SPA
         └─ cockpit.spawn(["python3", "-u", "/usr/libexec/dock-panel/cli.py", ...])
              └─ Python CLI  JSON stdin/stdout
                   ├─ docker compose
                   └─ openssl
```

Cockpit 插件不是独立 HTTP 服务。前端由 Cockpit 托管，系统操作全部通过 `cockpit.spawn` 在本机以当前用户（可提权）执行。

数据目录：

| 路径 | 用途 |
| --- | --- |
| `/usr/share/cockpit/dock-panel/` | 前端静态资源 |
| `/usr/libexec/dock-panel/` | Python 后端 |
| `/var/lib/dock-panel/projects.json` | 已登记项目 |
| `/var/lib/dock-panel/projects/` | 托管 Compose 项目 |
| `/var/lib/dock-panel/certs/` | 证书与私钥 |

在 Compose 中引用关联证书的示例：

```yaml
services:
  proxy:
    image: nginx:alpine
    ports:
      - "443:443"
    volumes:
      - ./certs/lab.local/cert.pem:/etc/nginx/tls/cert.pem:ro
      - ./certs/lab.local/key.pem:/etc/nginx/tls/key.pem:ro
```

## 依赖

服务器上需要：

- Cockpit
- Python 3.9+
- Docker Engine + Compose v2 插件（`docker compose`）
- openssl（证书功能）

当前用户要么在 `docker` 组，要么在 Cockpit 里使用管理员提权。

## 安装

服务器只要有 curl。前端由 GitHub Actions 编译，Release 里提供安装包。

```bash
curl -fsSL https://github.com/OptLTD/dock-panel/releases/latest/download/install.sh | sudo sh
sudo systemctl restart cockpit
```

指定版本：

```bash
curl -fsSL https://github.com/OptLTD/dock-panel/releases/latest/download/install.sh | sudo sh -s -- --version 0.1.0
```

然后打开 `https://<服务器>:9090`，侧栏会出现 **Dock Panel**。

私有仓库需要带 token：

```bash
curl -fsSL -H "Authorization: Bearer $GH_TOKEN" \
  https://github.com/OptLTD/dock-panel/releases/latest/download/install.sh \
  | sudo GH_TOKEN="$GH_TOKEN" sh
```

发布新版本（本机打 tag，Actions 自动编译并上传 Release）：

```bash
git tag v0.1.0
git push origin v0.1.0
```

也可在 GitHub Actions 里手动跑 **Release** 工作流。

### 本机打包后拷到服务器

不经过 GitHub 时，开发机需要 Node.js 18+：

```bash
make dist
scp dist/dock-panel-0.1.0.tar.gz user@server:
```

服务器：

```bash
tar xf dock-panel-0.1.0.tar.gz
cd dock-panel-0.1.0
sudo ./install.sh
sudo systemctl restart cockpit
```

若本机就是那台服务器：

```bash
sudo make install
```

开发机热更新（链接到用户目录，不写系统路径）：

```bash
make devel-install
```

仅预览 UI（无系统权限）：

```bash
cd frontend
npm install
npm run dev
```

## 后端调试

```bash
# 健康检查
echo '{}' | python3 backend/cli.py health

# 列出项目
echo '{}' | python3 backend/cli.py projects.list

# 创建托管项目
python3 backend/cli.py projects.create --payload '{"name":"demo","compose_yaml":"services:\\n  web:\\n    image: nginx:alpine\\n"}'
```

## 开发

```bash
make test          # Python 单测
make watch         # 监听构建前端
```

修改前端后，`make devel-install` 或 `make watch` 会更新 `frontend/dist`。用户目录下的插件不被 Cockpit 强缓存，刷新浏览器即可。
