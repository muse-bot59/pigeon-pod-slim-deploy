# pigeon-pod 研究记录（2026-11-13）

上游：https://github.com/aizhimou/pigeon-pod ，本地 clone：`~/workspace/pigeon-pod/`

> 本文档是研究上游源码后整理的流水线笔记（已去掉原部署环境的私有信息），供瘦身部署参考。

## 结论先行

- pigeon-pod **不是“JavaScript 编译的”**：后端是 **Java 17 + Spring Boot 3.5**（MyBatis-Plus、Flyway、Sa-Token、SQLite），前端是 React 19 + Vite。JS 只出现在两处：(1) React 前端；(2) yt-dlp 的 EJS 运行时（YouTube JS 挑战需要 JS 运行时，Docker 镜像因此装了 Deno）。
- 核心流水线很小：发现新视频 → yt-dlp 下载音频 → 存 S3 兼容存储 → 生成 Podcast RSS。
- **2026-11-13 在 Ubuntu 主机上实测全通**：WARP 代理下载、flat-playlist 发现、单视频详情、JS 运行时，全部验证通过，零 cookies。

## 核心流水线（从源码抽取）

### 1. 发现新视频（同步）—— `dev-docs/design/playlist-sync-hybrid-ytdlp-youtubeapi-design-zh.md`

```bash
yt-dlp --flat-playlist -J \
  --extractor-args "youtubetab:approximate_date" \
  "https://www.youtube.com/playlist?list=<id>"
# 或频道：https://www.youtube.com/channel/<id>/videos
```

- 快照（ID+顺序+标题）→ 本地做差集 → 只有新增 ID 才补详情。
- 补详情主路径是 YouTube Data API `videos.list`（批量 ≤50），兜底是 `yt-dlp -J --no-playlist <watchUrl>`。
- **可以完全不要 YouTube Data API**：详情也用 `yt-dlp -J` 单条补，零 API key、零配额。
- 过滤：关键词包含/排除、时长上下限、跳过 live/upcoming。

### 2. 下载（音频）—— `backend/.../handler/DownloadHandler.java`

```bash
yt-dlp -x --audio-format aac --audio-quality <0-10> \
  --add-metadata --write-thumbnail --embed-thumbnail --convert-thumbnails jpg \
  --remote-components ejs:npm \
  --cookies <临时cookies文件> \
  --proxy <代理地址> \
  --ignore-errors --no-embed-chapters \
  --write-info-json -o "infojson:%(id)s" \
  --print after_move:PIGEON_FINAL_FILEPATH:%(filepath)s \
  -o "<输出目录>/<basename>.%(ext)s" \
  "<视频URL>"
```

- 音频默认 AAC（`.m4a`），视频默认 `bestvideo+bestaudio` → mp4（`--merge-output-format mp4`，可选 H264/H265 强制转码 `--recode-video mp4`）。
- 章节：音频走两阶段（主下载 `--no-embed-chapters`，成功后第二遍 `--load-info-json … --embed-chapters`）；另生成 Podcasting 2.0 `.chapters.json`。
- 超时：进程级超时（可配，默认见 `application.yml` 的 `downloadProperties.processTimeoutMinutes`）。
- 失败：`EpisodeRetryPlanner` 退避重试；重试耗尽后邮件/webhook 汇总通知。
- 校验：文件存在且非空才算成功。

### 3. 登录态（cookies）—— `service/CookieService.java`

- Cookie 以 **Netscape 格式**文本存 DB；每次下载前写成临时文件，`--cookies <file>`，下载后删除。
- 用户在 UI 里粘贴 cookie 内容（浏览器扩展导出，如 Get cookies.txt LOCALLY）。
- **注意**：pigeon-pod 不认外部 Cookie 文件路径，只认 DB 里存的 Netscape 内容。外部 Cookie 要同步进去，得走 `PUT /api/cookies/YOUTUBE`（见本仓库 `scripts/pigeon-api.py` 的 `sync-cookie`）。
- 新视频常被 YouTube 要求登录态，Cookie 会轮换，旧的很快失效，下载前要新鲜的。

### 4. 代理 —— `service/YtDlpProxyService.java` + `config/OutboundProxyHolder.java`

- 就是 yt-dlp 的 `--proxy <url>`，URL 形如 `socks5://host:port` 或 `http://host:port`（可带用户名密码）。
- 参考部署用的是 `socks5://127.0.0.1:40000`（warp-cli WarpProxy）。

### 5. R2 存储 —— `service/storage/S3StorageService.java` + `util/MediaKeyUtil.java`

- AWS SDK v2 S3 客户端，endpoint 覆盖为 `https://<account-id>.r2.cloudflarestorage.com`，region 任意（R2 用 `auto`），`chunkedEncodingEnabled(false)`（R2 兼容关键），path-style 可开关，静态 AK/SK，预签名 GET URL 供播放。
- Key 布局：
  - 音频：`audio/<频道名>/<basename>.m4a`
  - 视频：`video/<频道名>/<basename>.mp4`
  - 附属：`<同前缀>.chapters.json`、`.thumbnail.jpg`、字幕 `.<lang>.vtt`
- S3 模式：先下载到本地临时目录，上传全部资产后删临时目录；失败回滚已传的 key。

### 6. 内部定时器（源码默认值）

- 频道/播放列表同步：每小时
- 下载队列：每 30 秒
- 失败下载汇总通知：每 8 小时（只汇总重试耗尽的，不是实时）
- 剧集清理：每 2 小时

### 7. 官方镜像的运行时（Dockerfile）

- wolfi-base + openjdk-17 + ffmpeg + python3 + yt-dlp + deno + sqlite；端口 8080；默认账号 root / Root@123。
- `app.jar` 在镜像的 `/app/app.jar`，附带脚本在 `/app/scripts/`。
- yt-dlp 的 EJS 运行时：镜像自带 deno；没有 deno 时可用 node，加 `--js-runtimes node` 即可（实测警告消失）。
