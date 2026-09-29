# 分支说明 / Fork Notice

本仓库是 <https://github.com/23Star/xianyu-super-butler>（**GNU Affero GPL v3**，全文见
[`LICENSE`](LICENSE)）的**修改版**。上游作者与本项目无关，问题请先自查下面这些改动。

按 AGPLv3 §5(a) 要求，此处以显著方式声明改动内容与日期。

## 与上游的差异

基线：`upstream/main` = `eeb9b6d`（v3.2.0，2026-09-29），已在 `6947b1f` 并入。

| 提交 | 日期 | 改动 | 原因 |
| --- | --- | --- | --- |
| ~~`67a7962`~~ | 2026-09-25 | 曾新增 `app/delivery_template.py`、`app/services/notification_test.py`，并给 `app/reply_server.py` 的物流路由加缺文件降级 | 当时上游任何分支和 tag 都没发布这 4 个文件，顶层无条件导入 → 后台 import 阶段即崩。**上游 `2c11ac2`（2026-09-29）已正式补交，本仓库这几处已改回上游实现** |
| `6d91946` | 2026-09-25 | 新增 `docker-compose.cloud.yml`、`nginx/nginx.cloud.conf`、`.env.cloud.example` 与云服务器部署文档 | 面向 2~4 G 内存的云服务器：拉预构建镜像、应用端口只绑回环、Nginx 对外 |
| `3efac43` | 2026-09-25 | 云配置显式设 `API_HOST`/`API_PORT`；`.gitattributes` 增加 `.env* text eol=lf` | `AUTO_REPLY.api.host/port` 就是 uvicorn 的监听地址（`Start.py:694`），本机调试值一旦随仓库挂载进容器，健康检查恒失败；CRLF 会让 `.env` 的值尾部带 `\r` |
| `cc4beb0` | 2026-09-25 | 更正部署前提与传码方式 | 本仓库无上游写权限 |
| `deafda2` | 2026-09-25 | 镜像地址可用 `APP_IMAGE` 覆盖，补国内 ghcr 备选路线 | 国内云主机直拉 ghcr 常拉不动 |

其余提交是 `docs/` 下的部署实测记录（机型、内存、swap、断线补发等）。

## 跟上游同步

```bash
git fetch upstream
git branch backup/pre-merge-<日期> main   # 先留退路
git merge upstream/main
```

本次同步（`6947b1f`）的冲突处理：`app/delivery_template.py`、`app/services/notification_test.py`
取上游实现；`.gitignore` 取上游把测试忽略规则限定到 `tests/` 的写法，另保留 `!FORK.md` 与
`!.env.cloud.example` 两处例外；`app/reply_server.py`、`README.md`、`docs/deployment.md` 自动合并。

## 部署时的 AGPL 义务（不是法律意见，但值得先知道）

§13 规定：修改版通过网络让**用户**与之交互时，必须向这些用户显著提供你的对应源码。
本系统带多用户与开放注册能力，如果只是自己店铺运营用、后台不对外开注册，一般用不上这条；
一旦把面板开放给他人使用（例如给别的卖家开账号），就需要同时提供修改版源码的获取途径，
把仓库公开通常就是最省事的做法。
