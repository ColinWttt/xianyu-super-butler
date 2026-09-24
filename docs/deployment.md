# 部署与排查

README 只保留最短路径，这里放完整细节。

## 目录

- [滑块与人机验证](#滑块与人机验证)
- [云服务器部署](#云服务器部署)
- [部署失败排查](#部署失败排查)
- [使用流程](#使用流程)
- [更新](#更新)
- [数据与安全](#数据与安全)

## 滑块与人机验证

闲鱼在账号登录、Token 续期时可能要求人机验证（滑块、人脸）。部署前请先了解现状。

**自动过滑块不保证成功。** 阿里风控会区分浏览器自动化注入的鼠标事件与真实硬件鼠标事件：
真人鼠标在一帧内上报多个高频子事件，而自动化派发的事件每帧只有一个，落点再精确也可能被判定失败。
这是自动化方案的共同限制，不是配置问题。

系统为此做了几层处理：

- 滑块以**有头模式**运行，容器内由 Xvfb 提供虚拟显示（镜像已内置，无需额外配置）。
  无头 Chrome 的 WebGL、字体列表、屏幕参数与有头差异明显，更容易被识别。
- 浏览器内核优先使用 Patchright（Playwright 的反检测分支），消除 `navigator.webdriver` 等自动化标志。
- 拖动轨迹按设计时间轴回放，机器性能不足时自动降采样，避免轨迹被拉长而失真。
- 全局同时只允许一个浏览器实例，避免多账号同时验证互相拖慢。
- 自动验证失败后立即熔断并进入冷却，不会反复重试——继续重试只会延长风控时间。

**自动失败时转人工**：账号页对处于风控状态的账号提供「人工验证」，
会把服务器上的浏览器画面投屏到当前页面，用鼠标拖动即可，无需登录服务器桌面。

**机器配置的影响**：低配设备（J4125、N5105 等）上浏览器帧率不足会进一步降低通过率。
日志出现下面这行说明机器已吃力，可减少同时运行的账号数：

```text
机器性能不足以维持滑动采样率: 丢弃 N/M 个采样点, 最大滞后 XXXms
```

确认虚拟显示与反检测内核已生效：

```bash
docker compose logs xianyu-app | grep -E "Xvfb|Patchright"
```

应看到：

```text
[entrypoint] Xvfb 已就绪 DISPLAY=:99 (1920x1080x24)
【账号】Patchright 启动成功（反检测内核）
```

若出现 `Missing X server or $DISPLAY`，说明虚拟显示未启动（系统会自动回退无头模式，
服务本身不受影响，但滑块通过率下降），请提供容器内 `/tmp/xvfb.log`。

使用 VPN、代理或海外服务器时风控明显收紧，建议使用国内网络环境。

## 云服务器部署

`docker-compose.cloud.yml` 是云服务器专用配置：拉预构建镜像（压缩 0.67 GB，约 2 GB 磁盘）、
应用端口只绑 `127.0.0.1`、由 Nginx 对外提供 80/443。

### 机型

| 项目 | 结论 |
| --- | --- |
| 内存 | **2 GiB 是及格线不是舒适线**。主机系统与 dockerd 占 400~500 M，Python 常驻 250~400 M，滑块验证拉起有头 Chromium + Xvfb 峰值 300~500 M，合计 1.2~1.7 G。建议 2 核 4 G |
| CPU | 2 核够用，高于文档里点名的 J4125 / N5105 |
| 磁盘 | 40 G 充裕：系统与 Docker 约 6 G、镜像解压实测 **2.84 G**（`docker system df`，压缩传输 0.67 G）留两份用于升级、SQLite 与日志约 2 G。日志回收写在代码里（`XianyuAutoAsync.py:163` 保留 7 天，`app/file_log_collector.py:66` 10 M × 3 天）；本配置另加 `logging.max-size` 上限，避免容器 stdout 无限增长 |

应用容器内存上限由 `.env` 的 `MEMORY_LIMIT` 控制：2 G 主机保持默认 `1536M`，4 G 主机改 `3072M`。

### 镜像与补齐文件

`ghcr.io/23star/xianyu-super-butler` 由仓库作者那条 `main` 的 `.github/workflows/docker-publish.yml`
构建。2026-09-25 实测 `latest`：镜像内缺 `app/delivery_template.py`、
`app/services/notification_test.py`、`app/routers/logistics_quote.py`、`app/routers/logistics_agent.py`，
而 `app/reply_server.py` 顶层无条件导入 → `uvicorn服务器启动失败: No module named 'app.delivery_template'`，
健康检查恒失败、Nginx 因 `depends_on: service_healthy` 不启动。**这与服务器配置无关，任何机器光 pull 都起不来。**
本地补齐不会让上游镜像变完整，所以云上必须靠下面的覆盖挂载把补齐的文件带进去。

`docker-compose.cloud.yml` 默认把补齐的三个文件覆盖挂载进镜像，所以**服务器上必须有这份 checkout**：

```bash
# 核对镜像与本地 checkout 同版：只差 13 行，即物流路由 try/except 那处补丁
docker exec xianyu-super-butler wc -l /app/app/reply_server.py
wc -l app/reply_server.py
```

补齐的提交只在你本地，服务器上 `git clone` 上游拿不到，所以把已提交的文件送过去。
Windows 的 Git Bash 没有 `rsync`，用 `git archive` 走 ssh 管道最省事——它只送跟踪文件，
`data/`、`logs/`、`browser_data/`、以及本机 `global_config.yml` 那处端口调试天然不会过去
（缺挂载源文件时 Docker 会在容器内建同名空目录，报错从 `ModuleNotFound` 变成更难读的
`IsADirectoryError`）：

```bash
# 本机 Git Bash 里执行
ssh root@<服务器IP> 'mkdir -p ~/xianyu-super-butler'
git archive --format=tar HEAD | ssh root@<服务器IP> 'tar -x -C ~/xianyu-super-butler'
```

服务器上随后：

```bash
cd ~/xianyu-super-butler
cp .env.cloud.example .env && mkdir -p data logs backups nginx/ssl
vi .env        # 改 ADMIN_PASSWORD、SERVER_HOST；4 G 机器改 MEMORY_LIMIT=3072M
```

日后上游作者补齐了那 4 个文件，镜像就是自足的，可以删掉三段挂载。判断依据：

```bash
docker compose -f docker-compose.cloud.yml pull
docker compose -f docker-compose.cloud.yml run --rm --entrypoint sh xianyu-app \
  -c 'ls /app/app/delivery_template.py /app/app/services/notification_test.py'
```

想彻底摆脱挂载和手工传文件，就把这个仓库 fork 到**你自己的** GitHub 账号下再推上去：
`.github/workflows/docker-publish.yml` 会在你的账号里构建出含补齐文件的
`ghcr.io/<你的用户名>/xianyu-super-butler:latest`，服务器改成 `git clone` 你自己的 fork 即可。

### 步骤

```bash
# 1) 2 GiB 主机必做：加 swap 接住 Chromium 冷启动峰值，否则 OOM killer
#    优先杀掉浏览器，配合 restart 策略表现为反复重启、CPU 持续打满
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swap.conf && sudo sysctl --system

# 2) 代码用上面「镜像与补齐文件」里的 git archive 管道送过来（clone 上游拿不到补齐的模块），
#    然后准备环境变量（务必先改 ADMIN_PASSWORD，后台用的是无盐 SHA-256 哈希）
cd ~/xianyu-super-butler
cp .env.cloud.example .env && mkdir -p data logs backups nginx/ssl
vi .env    # ADMIN_PASSWORD、SERVER_HOST=公网IP或域名；4 G 机器再改 MEMORY_LIMIT

# 3) 启动
docker compose -f docker-compose.cloud.yml up -d
docker compose -f docker-compose.cloud.yml ps      # 等到 xianyu-app 为 healthy
docker compose -f docker-compose.cloud.yml logs --tail=50 xianyu-app   # 看 Xvfb 已就绪
curl -fsS http://localhost/health                  # 经 Nginx 的健康检查
```

访问 `http://公网IP/`（无域名时只有 HTTP；上 HTTPS 见 `nginx/nginx.cloud.conf` 末尾注释）。
在云服务器安全组里放通 80/443，**不要**放通 8080，应用端口只监听回环。

更新（本机改完代码提交后重跑那条 `git archive` 管道即可；单文件 bind mount 锁的是 inode，
覆盖后必须重建容器才看得到新代码，`docker compose restart` 无效）：

```bash
# 本机
git archive --format=tar HEAD | ssh root@<服务器IP> 'tar -x -C ~/xianyu-super-butler'
# 服务器
cd ~/xianyu-super-butler
docker compose -f docker-compose.cloud.yml pull          # 想要升级镜像时
docker compose -f docker-compose.cloud.yml up -d --force-recreate
sudo docker image prune -f
```

### 国内云主机的镜像可达性

应用镜像在 `ghcr.io`，而 GitHub 容器仓库对大陆线路的可达性不稳定：国内云主机上
`docker pull` 可能超时或极慢，这时起不来跟机器配置无关，纯粹是拉不到镜像。先在服务器上单试这一条：

```bash
docker pull ghcr.io/23star/xianyu-super-butler:latest
```

拉不动就按代价二选一：

```bash
# A. 本机已有镜像，管道直传（解压 2.84 G，gzip 后约 0.9 G）
docker save ghcr.io/23star/xianyu-super-butler:latest | gzip \
  | ssh root@<服务器IP> 'gunzip | docker load'

# B. 转推到阿里云容器镜像服务个人版（免费），服务器改从 registry.cn-<区域>.aliyuncs.com 拉
docker tag ghcr.io/23star/xianyu-super-butler:latest \
  registry.cn-hangzhou.aliyuncs.com/<命名空间>/xianyu-butler:latest
docker login registry.cn-hangzhou.aliyuncs.com
docker push registry.cn-hangzhou.aliyuncs.com/<命名空间>/xianyu-butler:latest
# 然后把 docker-compose.cloud.yml 里的 image: 换成该地址，或改用 APP_IMAGE 环境变量
```

无论走哪条，镜像里仍缺那 4 个模块（见「镜像与补齐文件」），三段覆盖挂载照旧保留。

### 环境变量里哪些是真生效的

只有这些在 Python 侧有 `os.getenv` 读取：`DB_PATH`（`app/db_manager.py:30`）、
`ADMIN_PASSWORD`（`app/db_manager.py:1271`，仅首次建库）、`SQL_LOG_ENABLED`、`SQL_LOG_LEVEL`、
`SERVER_HOST` / `PUBLIC_IP`（`utils/item_search.py:88`）、`API_HOST` / `API_PORT`
（`Start.py:690`）、`AI_MAX_TOKENS`。

`docker-compose.yml` 里的 `AUTO_REPLY_ENABLED`、`AI_REPLY_ENABLED`、`SESSION_TIMEOUT`、
`MULTIUSER_ENABLED`、`HEARTBEAT_*`、`WEBSOCKET_URL` 等**代码从不读取**，改它们没有效果——
这些开关的真实来源是 `global_config.yml` 和后台界面写入的 SQLite。

注意 `AUTO_REPLY.api.host` 与 `.port` **就是后端进程的监听地址**（`Start.py:694` 传给
`uvicorn.Config`），与 `api.enabled` 那个「走外部接口回复」的开关无关。仓库里这份
`global_config.yml` 会随容器挂载进去，所以本机调试时把它改成 `127.0.0.1:8088` 一旦提交，
服务器上容器内健康检查打 `localhost:8080` 会一直失败，Nginx 因 `depends_on: service_healthy`
永不启动。`docker-compose.cloud.yml` 用 `API_HOST` / `API_PORT` 把它钉在 `0.0.0.0:8080`。

`global_config.yml` 以只读方式挂进容器是安全的：`app/config.py` 的 `Config.save()` 全仓零调用。

### Nginx 必配的超时

人工滑块验证走 `/api/captcha/ws/{id}`（`app/api_captcha_remote.py:35`），服务器持续推截图、
浏览器回传鼠标事件。上游 `nginx/nginx.conf` 的 `proxy_read_timeout 30s` 会在拖动中途掐断连接，
`nginx/nginx.cloud.conf` 对该路径放宽到 3600s 并关闭 `proxy_buffering`。
`client_max_body_size` 也放宽到 30M，否则批量商品配图上传返回 413。

### 本机实测记录（2026-09-25，Docker Desktop）

用独立的空 `data/` 起过一遍，不接真实账号：

- `nginx -t` 通过；`/health` 经 Nginx 返回 200，首页返回 1487 字节 SPA
- `/api/captcha/ws/...` 经 Nginx 握手返回 `101 Switching Protocols`，30s 超时问题不复现
- 挂载的 `global_config.yml` 写着 `127.0.0.1:8088` 时，`API_HOST`/`API_PORT` 仍把后端钉在
  `http://0.0.0.0:8080`（日志 `Uvicorn running on http://0.0.0.0:8080`）
- `[entrypoint] Xvfb 已就绪 DISPLAY=:99`，物流路由按预期只降级不崩：
  `⚠️ 物流报价与物流 Agent 路由未注册，接口将返回 404`
- 空库自动建表并生成首份备份，`data/xianyu_data.db` 446 KB

## 部署失败排查

重复部署失败通常不是前端问题，优先按以下顺序检查：

1. **NAS / 低配设备不要本地构建**：CPU 被打满、内存耗尽、构建中途被杀，绝大多数是本机编译导致的。
   改用 `docker compose -f docker-compose.nas.yml up -d` 拉取预构建镜像。
2. **确认版本**：使用 Docker Engine 24+、Docker Compose v2；本地构建至少 4 GB 可用内存，仅拉取镜像 2 GB 即可。
3. **确认 `.env`**：不填也能启动，会使用默认账号 admin / admin123。
4. **确认端口**：`8080` 被占用时，在 `.env` 设置 `WEB_PORT=8081`，然后访问对应端口。
5. **确认目录权限**：容器必须能够写入 `data`、`logs` 和 `backups`。
6. **国内网络用 CN 配置**：`Dockerfile-cn` 已把 apt、pip、npm 和 Chromium 全部指向国内镜像；
   用默认 `Dockerfile` 在国内构建，通常会卡在下载 Chromium 直到超时。
7. **检查健康状态**：运行 `docker compose ps`，健康接口应返回 `healthy`。
8. **查看真实错误**：运行 `docker compose logs --tail=200 xianyu-app`，不要只看浏览器"无法访问"。
9. **清理失败构建缓存**：确认数据已备份后运行 `docker compose build --no-cache xianyu-app`，再重新启动。

常用诊断命令：

```bash
docker compose config
docker compose ps
docker compose logs --tail=200 xianyu-app
curl http://localhost:8080/health
```

## 使用流程

1. 登录后台，在「设置 → 账号与同步 → 修改登录密码」改掉默认管理员密码。
2. 在「账号」页面登录闲鱼账号，等待状态显示「在线」和「监听中」。
3. 在「商品」页面选择账号并同步商品。
4. 在「卡密」页面创建卡券分组并导入库存。
5. 在「自动回复」或「人工智能回复」配置客服策略。
6. 在「自动发货」中为指定商品绑定卡券，或设置账号级、全局关键词规则。
7. 在「订单」和「消息管理」页面核对实际触发结果。
8. 在「通知与日志」中排查过滤、暂停、无规则、发送失败和监听退出。

### 账号状态说明

- `在线 / 离线`：Cookie 和闲鱼连接状态
- `监听中`：后台消息与订单任务正在运行
- `监听异常`：任务意外退出，可重新登录或重新启用账号触发重启
- `已停用`：该账号被手动停用，不会处理消息和订单

仅显示「在线」但没有「监听中」时，请先查看「通知与日志」中的启动错误。

### 发货规则优先级

1. `指定账号 + 指定商品`：按商品 ID 精确发货，优先级最高，关键词可留空。
2. `指定账号 + 关键词`：只匹配该账号下的商品标题、详情或买家消息。
3. `全部账号 + 关键词`：通用兜底规则。

配置路径：`自动发货 → 添加发货规则 → 选择账号 → 选择商品 → 关联卡券`。

### 开放注册

「设置 → 访问与安全」里的「允许用户注册」控制登录页是否出现注册入口；
「注册邮箱验证」控制注册是否必须填邮箱验证码。验证码依赖「邮件服务」里的 SMTP 配置，
未配置 SMTP 时请关闭「注册邮箱验证」，否则用户收不到验证码、无法完成注册。

## 更新

预构建镜像（NAS、低配设备）：

```bash
docker compose -f docker-compose.nas.yml pull
docker compose -f docker-compose.nas.yml up -d
```

本地构建：

```bash
git pull
docker compose up -d --build
```

源码运行：`git pull` 后重启 `Start.py`。依赖未变动时无需重装。

### 验证

后端测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m compileall -q Start.py XianyuAutoAsync.py app utils tests
```

前端检查：

```powershell
cd frontend
.\node_modules\.bin\tsc.cmd --noEmit
npm run build
```

## 数据与安全

- 不要提交数据库、日志、Cookie、Token、卡密、浏览器状态和本地配置。
- 日志不得输出完整 Cookie、Authorization、签名或模型 API Key。
- 自动发货、发送卡密、删除商品等操作应先用测试账号验证。
- 闲鱼页面和接口可能随平台更新变化，升级后应重新验证登录、消息、商品和订单链路。
- 仍兼容旧版无盐 SHA-256 密码哈希，不建议未经额外防护直接暴露到公网。
- 验证码邮件只经由你自己配置的 SMTP 发送，发不出去直接报错，不会转交第三方接口代发。
- `ADMIN_PASSWORD` 只在首次创建数据库时生效。数据库已存在时改环境变量不会改密码，请在后台改。
