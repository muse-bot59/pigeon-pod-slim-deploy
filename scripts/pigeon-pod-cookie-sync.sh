#!/bin/bash
# pigeon-cookie-sync.sh — keep pigeon-pod's YouTube cookie fresh.
# 1. Pull fresh cookies from PN40 Chrome (via the restricted cuecookie SSH).
# 2. Install as the shared MeTube cookie file.
# 3. Sync the same content into pigeon-pod's DB via its API.
# Runs every 15 min via pigeon-cookie-sync.timer. Logs to
# /root/pigeon-pod/cookie-sync.log. Never prints cookie content.
set -u
LOG=/root/pigeon-pod/cookie-sync.log
echo "$(date '+%F %T') sync start" >> "$LOG"
if ! ssh -T -n pn40 > /tmp/yt-cookies-new.txt 2>>"$LOG"; then
  echo "$(date '+%F %T') ERROR ssh pn40 failed" >> "$LOG"
  exit 1
fi
LINES=$(wc -l < /tmp/yt-cookies-new.txt)
if [ "$LINES" -lt 10 ]; then
  echo "$(date '+%F %T') ERROR cookie file too short: $LINES lines" >> "$LOG"
  exit 1
fi
cp /tmp/yt-cookies-new.txt /opt/metube/cookies/cookies.txt
chown 1000:1000 /opt/metube/cookies/cookies.txt
chmod 600 /opt/metube/cookies/cookies.txt
if python3 /root/pigeon-pod/pigeon-api.py sync-cookie >> "$LOG" 2>&1; then
  echo "$(date '+%F %T') sync ok ($LINES lines)" >> "$LOG"
else
  echo "$(date '+%F %T') ERROR pigeon-pod sync failed" >> "$LOG"
  exit 1
fi
