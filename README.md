# pigeon-pod 瘦身部署

把 pigeon-pod 从约 1.04 GB 的 Docker 镜像精简成一个约 63 MB 的 `app.jar`，用 systemd 直接跑在主机上，不用 Docker。

## 这是干什么的

- 订阅 YouTube 频道 / 播放列表，新视频自动下载成音频（M4A）
- 音频存到 R2（S3 兼容），按 `audio/<频道>/<文件名>.m4a` 归档
- 每个订阅自动生成 Podcast RSS，手机播客 App、CarPlay 都能听
- 每小时自动同步频道，下载队列 30 秒跑一次
- 下载失败自动重试，耗尽后邮件 / webhook 汇总通知（每 8 小时）

## 上游致谢

- 上游项目：https://github.com/aizhimou/pigeon-pod（作者 aizhimou）
- 后端 Java 17 + Spring Boot 3.5，前端 React 19，SQLite
- 上游许可证 GPL-3.0，本仓库的 LICENSE 与上游一致
- **`app.jar` 是上游作者的作品，本仓库不包含**，按下面步骤自己从官方镜像抽
- 上游默认：端口 8080，账号 root，密码 `Root@123`（部署后立刻改掉）

## 瘦身效果（实测）

| | 官方 Docker | 瘦身后 |
|---|---|---|
| 体积 | 镜像约 1.04 GB | `app.jar` 约 63 MB |
| 运行 | Docker 容器 | systemd 服务 |
| 内存占用 | — | 约 150 MB |

## 前置条件

- Java 17+（实测 Java 21）
- ffmpeg、yt-dlp、deno（yt-dlp 的 EJS 运行时要用到；已有 node 的话可用 `--js-runtimes node` 代替 deno）
- 一个 S3 兼容存储（实测 Cloudflare R2，bucket 自备）
- 可选：代理（参考部署用 Cloudflare WARP，SOCKS5 `127.0.0.1:40000`）
- 可选：YouTube Data API key（没有也能跑，详情改走 yt-dlp）
- 可选：一个能导出新鲜 YouTube Cookie 的可信来源（见第 4 步）

## 部署步骤

### 1. 从官方镜像抽出 app.jar

```bash
docker pull ghcr.io/aizhimou/pigeon-pod:latest
docker create --name pigeon-tmp ghcr.io/aizhimou/pigeon-pod:latest
mkdir -p /root/pigeon-pod
docker cp pigeon-tmp:/app/app.jar /root/pigeon-pod/app.jar
docker cp pigeon-tmp:/app/scripts /root/pigeon-pod/scripts   # 可选，上游自带脚本
docker rm pigeon-tmp
docker rmi ghcr.io/aizhimou/pigeon-pod:latest   # 镜像不再需要，可删
```

### 2. 装 systemd 服务

```bash
cp systemd/pigeon-pod.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pigeon-pod.service
```

默认端口 8081（上游默认是 8080，这里改了，见 `systemd/pigeon-pod.service` 里的 `SERVER_PORT`）。
打开 `http://你的主机:8081`，账号 root，密码 `Root@123`，登录后立刻改密码。

### 3. 配 R2 / 代理 / API key

在网页设置里填：R2 endpoint、bucket、Access Key、Secret Key（region 填 `auto`，path-style 关）；代理填 SOCKS5 地址；YouTube API key 可填可不填。
也可以用 `scripts/pigeon-api.py` 走 API 配，见 `scripts/pigeon-api.py` 开头的用法说明。

### 4.（可选）Cookie 同步

新视频常被 YouTube 要求登录态，旧 Cookie 很快失效。`scripts/pigeon-pod-cookie-sync.sh` 每 15 分钟拉一次新鲜 Cookie 写进数据库：

```bash
cp scripts/pigeon-pod-cookie-sync.sh /usr/local/bin/
cp scripts/pigeon-api.py /root/pigeon-pod/pigeon-api.py
cp systemd/pigeon-cookie-sync.* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pigeon-cookie-sync.timer
```

注意：脚本里的 Cookie 来源是参考部署的做法——从一台可信主机的登录态 Chrome 经受限 SSH 拉取，并同时写一份共享 Cookie 文件（供 MeTube 共用）。
换成你自己的来源：改脚本里 `ssh pn40` 那一行，让它输出 Netscape 格式的 Cookie 内容就行。
`pigeon-api.py` 从 `/root/pigeon-pod/root-password.txt` 的 `Password:` 行读密码（文件权限 600，只存密码，不进仓库）。

### 5.（可选）WARP 守卫

每次下载前探一次 YouTube，出口 IP 被封就重启 WARP 换 IP：

```bash
cp scripts/warp-guard.sh /root/pigeon-pod/warp-guard.sh
```

然后在 pigeon-pod 的 yt-dlp 全局参数里加：

```
--exec-before-download /root/pigeon-pod/warp-guard.sh
```

注意：守卫在抽取阶段之后才跑，抽取阶段就被挡的视频它拦不住——那种情况只能靠新鲜 Cookie。

### 6. 订阅，验证

网页里加频道或播放列表，等一小时同步，或手动点同步。
下载的音频按 `audio/<频道>/` 进 R2，订阅的 RSS 链接在每个订阅里找，贴进播客 App 就能听。

## 目录说明

```
.
├── README.md
├── LICENSE                        # GPL-3.0，与上游一致
├── scripts/
│   ├── pigeon-api.py              # API 助手：看状态、同步 Cookie、配 webhook、看订阅/剧集
│   ├── pigeon-pod-cookie-sync.sh  # 每 15 分钟拉新鲜 Cookie 并同步进数据库
│   └── warp-guard.sh              # 下载前探 YouTube，被封就重启 WARP 换 IP
├── systemd/
│   ├── pigeon-pod.service         # 主服务，端口 8081
│   ├── pigeon-cookie-sync.service # Cookie 同步（一次性任务）
│   └── pigeon-cookie-sync.timer   # 每 15 分钟
└── docs/
    └── RESEARCH.md                # 源码流水线笔记：发现、下载、Cookie、代理、R2
```

## 已知限制

- 新视频可能被 YouTube 以“请登录确认你不是机器人”拦截：WARP 换 IP 解决不了，必须用登录态 Cookie，而且 Cookie 会轮换，下载前要新鲜的。
- 失败通知是汇总制，每 8 小时发一次，不是实时的；内容里没有 YouTube 链接（上游通知模板只有标题、内容、总数几个字段）。
- pigeon-pod 不认外部 Cookie 文件路径，Cookie 只能通过 API 同步进数据库（就是上面第 4 步干的事）。
- 升级：重新从新版官方镜像抽 `app.jar` 替换，重启服务。

## 许可证

本仓库的脚本与文档以 GPL-3.0 发布（与上游一致）。`app.jar` 及 pigeon-pod 本身版权归上游作者 aizhimou 所有。
