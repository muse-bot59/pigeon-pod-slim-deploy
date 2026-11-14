#!/usr/bin/env python3
"""Pigeon-pod API helper (runs on the host).
Logs in as root, then performs one action:
  status  - show cookie summaries, notification config, system config (sync interval)
  sync-cookie - read /opt/metube/cookies/cookies.txt, PUT to /api/cookies/YOUTUBE
  set-webhook <url> - configure failed-download webhook to <url>
  test-webhook - send a test webhook using current config
Cookie content and webhook URL are never printed.
Usage: python3 pigeon-api.py <action> [arg]
"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8081"
COOKIE_FILE = "/opt/metube/cookies/cookies.txt"


def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("pigeonpod", token)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def read_password():
    # root-password.txt is a 4-line info file; the password is on the
    # "Password: <value>" line.
    for line in open("/root/pigeon-pod/root-password.txt"):
        if line.startswith("Password:"):
            return line.split(":", 1)[1].strip()
    raise SystemExit("no Password: line in root-password.txt")


def login():
    pw = read_password()
    data = json.dumps({"username": "root", "password": pw}).encode()
    r = urllib.request.Request(BASE + "/api/auth/login", data=data, method="POST")
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            out = json.loads(resp.read() or b"{}")
            if out.get("code") != 200:
                raise SystemExit(f"login failed: {out.get('code')} {out.get('msg')}")
            # Sa-Token token name is "pigeonpod" (see application.yml).
            token = resp.headers.get("pigeonpod")
            if not token:
                d = out.get("data", {})
                if isinstance(d, dict):
                    token = d.get("token")
            if not token:
                cookie = resp.headers.get("Set-Cookie") or ""
                for part in cookie.split(";"):
                    part = part.strip()
                    if part.startswith("pigeonpod="):
                        token = part.split("=", 1)[1]
                        break
            if not token:
                raise SystemExit("login ok but no token found")
            return token
    except urllib.error.HTTPError as e:
        raise SystemExit(f"login failed: {e.code} {e.read()[:200]}")


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    token = login()
    if action == "status":
        s, out = req("GET", "/api/cookies", token)
        print("cookies:", json.dumps(out.get("data"), ensure_ascii=False))
        s, out = req("GET", "/api/notification/config", token)
        cfg = out.get("data", {}) or {}
        print("webhookEnabled:", cfg.get("webhookEnabled"),
              "| webhookUrl set:", bool(cfg.get("webhookUrl")),
              "| emailEnabled:", cfg.get("emailEnabled"))
        s, out = req("GET", "/api/account/system-config", token)
        cfg = out.get("data", {}) or {}
        print("system-config keys:", sorted(cfg.keys())[:30])
        for k in ("syncInterval", "syncIntervalMinutes", "feedSyncInterval",
                  "autoSyncInterval", "checkInterval"):
            if k in cfg:
                print(f"  {k} = {cfg[k]}")
    elif action == "sync-cookie":
        with open(COOKIE_FILE) as f:
            content = f.read()
        s, out = req("PUT", "/api/cookies/YOUTUBE", token,
                     body={"cookiesContent": content})
        print("upsert cookie:", s, json.dumps(out, ensure_ascii=False)[:200])
    elif action == "set-webhook":
        url = sys.argv[2]
        # fetch current config first so we don't clobber other fields
        s, out = req("GET", "/api/notification/config", token)
        cfg = out.get("data", {}) or {}
        cfg["webhookEnabled"] = True
        cfg["webhookUrl"] = url
        cfg["webhookJsonBody"] = json.dumps(
            {"message": "PigeonPod 下载失败，需要处理：{title}\n{content}"},
            ensure_ascii=False)
        s, out = req("POST", "/api/notification/config", token, body=cfg)
        print("set webhook:", s, json.dumps(out, ensure_ascii=False)[:200])
    elif action == "test-webhook":
        s, out = req("GET", "/api/notification/config", token)
        cfg = out.get("data", {}) or {}
        s, out = req("POST", "/api/notification/test/webhook", token, body=cfg)
        print("test webhook:", s, json.dumps(out, ensure_ascii=False)[:300])
    elif action == "feeds":
        s, out = req("GET", "/api/feed/list", token)
        feeds = out.get("data", []) or []
        print("feeds:", len(feeds))
        for f in feeds:
            print(" -", f.get("name"), "| type:", f.get("type"),
                  "| id:", f.get("id"))
    elif action == "download":
        ep_id = sys.argv[2]
        s, out = req("POST", f"/api/episode/download/{ep_id}", token)
        print("download:", s, json.dumps(out, ensure_ascii=False)[:300])
    elif action == "retry":
        ep_id = sys.argv[2]
        s, out = req("POST", f"/api/episode/retry/{ep_id}", token)
        print("retry:", s, json.dumps(out, ensure_ascii=False)[:300])
    elif action == "episodes":
        feed_id = sys.argv[2]
        s, out = req("GET", f"/api/episode/list/{feed_id}", token)
        data = out.get("data", {}) or {}
        eps = data.get("records", data) if isinstance(data, dict) else data
        eps = eps or []
        print("episodes:", len(eps))
        for e in eps[:15]:
            print(" -", e.get("title"), "| status:", e.get("status"),
                  "| id:", e.get("id"))
    else:
        raise SystemExit(f"unknown action: {action}")


if __name__ == "__main__":
    main()
