#!/bin/bash
# pigeon-pod 下载前 WARP 守卫：每次下载前探一次 YouTube（用不设限的经典视频做探针）。
# 探针失败 = 当前 WARP 出口 IP 被 YouTube 封了 -> 重启 WARP 换 IP。
# 重启节流：两次重启之间至少间隔 60 秒，避免一串下载反复重启。
# 永远 exit 0，绝不因守卫本身拦住下载。
CANARY_URL="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
PROXY="socks5://127.0.0.1:40000"
STATE_FILE="/root/pigeon-pod/.warp-last-restart"
LOG_FILE="/root/pigeon-pod/warp-guard.log"
COOLDOWN=60
YTDLP="$(command -v yt-dlp || echo /usr/local/bin/yt-dlp)"
WARPCLI="$(command -v warp-cli || echo /usr/bin/warp-cli)"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [warp-guard] $*" >> "$LOG_FILE"; }

probe() {
  timeout 60 "$YTDLP" --simulate --no-playlist --no-warnings \
    --js-runtimes node --remote-components ejs:npm \
    --proxy "$PROXY" "$CANARY_URL" >/dev/null 2>&1
}

warp_restart() {
  log "probe failed, restarting WARP"
  "$WARPCLI" disconnect >/dev/null 2>&1
  sleep 3
  "$WARPCLI" connect >/dev/null 2>&1
  for i in $(seq 1 15); do
    if "$WARPCLI" status 2>/dev/null | grep -qi "Connected"; then
      log "WARP reconnected"
      return 0
    fi
    sleep 2
  done
  log "WARP reconnect slow, restarting warp-svc"
  systemctl restart warp-svc >/dev/null 2>&1
  sleep 5
}

if probe; then
  log "probe OK, IP fine"
  exit 0
fi

now=$(date +%s)
if [ -f "$STATE_FILE" ]; then
  last=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
  if [ -n "$last" ] && [ $((now - last)) -lt $COOLDOWN ]; then
    log "probe failed but last restart was $((now - last))s ago (< ${COOLDOWN}s), skipping restart"
    exit 0
  fi
fi

echo "$now" > "$STATE_FILE"
warp_restart

if probe; then
  log "re-probe OK after restart"
else
  log "re-probe still failing after restart, letting download try anyway"
fi
exit 0
