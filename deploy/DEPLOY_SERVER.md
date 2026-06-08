# Thread Reader 部署说明

## 目录约定

建议把项目放在：

```text
/opt/thread-reader
```

服务启动后通过 `nginx -> python 服务` 的方式对外提供访问。

## 1. 准备服务器

以 Debian/Ubuntu 为例：

```bash
sudo apt update
sudo apt install -y python3 nginx certbot python3-certbot-nginx
```

创建运行用户：

```bash
sudo useradd --system --home /opt/thread-reader --shell /usr/sbin/nologin threadreader
```

创建目录并上传文件：

```bash
sudo mkdir -p /opt/thread-reader
sudo chown -R $USER:$USER /opt/thread-reader
```

把这些文件传到 `/opt/thread-reader`：

```text
index.html
server_home.html
server_portal.css
server_auth.js
server_login.js
server_home.js
post_reader_server.html
post_reader_server.css
post_reader_server.js
thread_reader_server.py
build_index.py
manage_users.py
auth_users.json
data/
deploy/
```

上传完成后建议设置属主：

```bash
sudo chown -R threadreader:threadreader /opt/thread-reader
```

## 2. 生成目录索引和账号

先生成目录索引：

```bash
cd /opt/thread-reader
python3 build_index.py
```

如需修改账号，编辑 `manage_users.py` 顶部变量后执行：

```bash
python3 manage_users.py
```

## 3. 配置 systemd

复制环境变量文件：

```bash
cd /opt/thread-reader
cp deploy/thread-reader.env.example deploy/thread-reader.env
```

推荐生产配置：

```ini
THREAD_READER_HOST=127.0.0.1
THREAD_READER_PORT=8080
THREAD_READER_SESSION_TTL=43200
THREAD_READER_COOKIE_SECURE=true
```

安装服务文件：

```bash
sudo cp /opt/thread-reader/deploy/thread-reader.service /etc/systemd/system/thread-reader.service
sudo systemctl daemon-reload
sudo systemctl enable --now thread-reader.service
```

查看状态：

```bash
sudo systemctl status thread-reader.service
```

查看日志：

```bash
sudo journalctl -u thread-reader.service -f
```

## 4. 配置 nginx 反代

复制并编辑站点配置：

```bash
sudo cp /opt/thread-reader/deploy/nginx-thread-reader.conf /etc/nginx/sites-available/thread-reader
```

把里面的：

```text
your.domain.example
```

替换成你的真实域名。

启用站点：

```bash
sudo ln -s /etc/nginx/sites-available/thread-reader /etc/nginx/sites-enabled/thread-reader
sudo nginx -t
sudo systemctl reload nginx
```

## 5. 申请 HTTPS 证书

确保域名已经解析到服务器公网 IP，然后执行：

```bash
sudo certbot --nginx -d your.domain.example
```

证书完成后再检查一次：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 6. 防火墙

只开放：

```text
22/tcp
80/tcp
443/tcp
```

如果用 `ufw`：

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

不要对公网开放 8080，因为 `thread_reader_server.py` 应该只监听 `127.0.0.1`。

## 7. 最小安全建议

### 必做

- 账号密码不要继续用默认值，先运行一次 `manage_users.py` 重新生成。
- `deploy/thread-reader.env` 里把 `THREAD_READER_COOKIE_SECURE=true` 保持开启。
- Python 服务监听 `127.0.0.1`，不要直接监听 `0.0.0.0`。
- 只通过 `nginx` 暴露 `443`，不要让外网直接打 Python 端口。
- 服务器系统和 `nginx` 定期更新安全补丁。
- `auth_users.json` 权限尽量收紧，比如 `chmod 600 auth_users.json`。

### 建议做

- 用一个不常见的强密码，至少 16 位。
- 如果只有你自己用，可以在 `nginx` 上再加 IP 白名单。
- 定期备份 `data/`、`auth_users.json` 和站点配置。
- 用 `fail2ban` 或者至少关注 `nginx` / `systemd` 日志，防止暴力尝试。

### 当前这套的边界

- 现在是单文件 Python 服务，适合轻量个人站点，不适合高并发公开站。
- 会话保存在进程内存里，重启服务后所有登录态会失效，这是正常现象。
- 目前没有登录失败限速。如果后面你要长期外网开放，最好再补登录限流。

## 8. 常用维护命令

重建索引：

```bash
cd /opt/thread-reader
python3 build_index.py
sudo systemctl restart thread-reader.service
```

更新账号：

```bash
cd /opt/thread-reader
python3 manage_users.py
sudo systemctl restart thread-reader.service
```

重启服务：

```bash
sudo systemctl restart thread-reader.service
```

查看日志：

```bash
sudo journalctl -u thread-reader.service -n 100 --no-pager
```
