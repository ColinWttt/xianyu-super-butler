# 分支说明 / Fork Notice

本仓库是 <https://github.com/23Star/xianyu-super-butler>（**GNU Affero GPL v3**，全文见
[`LICENSE`](LICENSE)）的**修改版**。上游作者与本项目无关，问题请先自查下面这些改动。

按 AGPLv3 §5(a) 要求，此处以显著方式声明改动内容与日期。

## 与上游的差异

基线：`upstream/main` = `66081a3`（2026-09-25 取回）。上游之后的提交只动
`docs/fork-network-stars.{json,svg}`（fork 星数统计），**没有代码差异**。

| 提交 | 日期 | 改动 | 原因 |
| --- | --- | --- | --- |
| `67a7962` | 2026-09-25 | 新增 `app/delivery_template.py`、`app/services/notification_test.py`；`app/reply_server.py` 里物流两个路由改为缺文件时降级 | 上游任何分支和 tag 都没发布这 4 个文件，`reply_server.py` 顶层无条件导入 → 后台进程 import 阶段即崩，监听与自动发货全不跑 |
| `6d91946` | 2026-09-25 | 新增 `docker-compose.cloud.yml`、`nginx/nginx.cloud.conf`、`.env.cloud.example` 与云服务器部署文档 | 面向 2~4 G 内存的云服务器：拉预构建镜像、应用端口只绑回环、Nginx 对外 |
| `3efac43` | 2026-09-25 | 云配置显式设 `API_HOST`/`API_PORT`；`.gitattributes` 增加 `.env* text eol=lf` | `AUTO_REPLY.api.host/port` 就是 uvicorn 的监听地址（`Start.py:694`），本机调试值一旦随仓库挂载进容器，健康检查恒失败；CRLF 会让 `.env` 的值尾部带 `\r` |
| `af179f9` | 2026-09-25 | 记录上游镜像缺模块的实测结论 | `ghcr.io/23star/...:latest` 由上游那条 main 构建，同样缺上述 4 个文件，光 pull 起不来 |
| `2565a1b` | 2026-09-25 | 补齐文件的覆盖挂载改为云配置默认启用 | 上游镜像不会因本地补齐而变完整 |
| `cc4beb0` | 2026-09-25 | 更正部署前提与传码方式 | 本仓库无上游写权限 |

## 跟上游同步

```bash
git fetch upstream
git rebase upstream/main
```

上游目前待并入的提交只动星数统计文件，所以现在 rebase 是干净的；等他们再改
`app/reply_server.py` 的导入区时才会冲突。

## 部署时的 AGPL 义务（不是法律意见，但值得先知道）

§13 规定：修改版通过网络让**用户**与之交互时，必须向这些用户显著提供你的对应源码。
本系统带多用户与开放注册能力，如果只是自己店铺运营用、后台不对外开注册，一般用不上这条；
一旦把面板开放给他人使用（例如给别的卖家开账号），就需要同时提供修改版源码的获取途径，
把仓库公开通常就是最省事的做法。
