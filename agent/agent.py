"""
CyberPrint Pay - Print Agent (Windows Python Native)
Direct native Windows GDI printing for both PDFs and images (No SumatraPDF required).
Supports: PDF, JPG, PNG, BMP with page range, copies, color/bw, and orientation.
Background mode with Windows Action Center Toast and interactive floating notification cards.
"""

import os
import sys
import time
import json
import re
import socket
import atexit
import datetime
import shutil
import subprocess
import threading
import http.server
import urllib.request
import urllib.error
import urllib.parse
import random
import base64
import tkinter as tk
import ctypes
from pathlib import Path

# Enable High-DPI awareness on Windows so screen coordinates and popup layout are 100% accurate
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# Safe streams for pythonw (where stdout/stderr may be None)
class _SafeStream:
    def write(self, s): pass
    def flush(self): pass

if sys.stdout is None:
    sys.stdout = _SafeStream()
if sys.stderr is None:
    sys.stderr = _SafeStream()

# Printing & Image processing
import win32print
import win32ui
import win32gui
import win32con
from PIL import Image, ImageWin
import pypdfium2 as pdfium

try:
    import winsound
except ImportError:
    winsound = None

LOG_FILE = Path(__file__).parent / "agent.log"
PID_FILE = Path(__file__).parent / "agent.pid"


def _cleanup_pid():
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception:
        pass


atexit.register(_cleanup_pid)


def now_str():
    return datetime.datetime.now().strftime("%H:%M:%S")


def log(msg):
    line = f"{now_str()}  {msg}"
    try:
        print(line, flush=True)
    except Exception:
        try:
            print(line.encode("ascii", errors="replace").decode("ascii"), flush=True)
        except Exception:
            pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_lan_ip():
    """Detects current primary IPv4 on LAN (Wi-Fi or Ethernet)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def parse_multipart(data_bytes, content_type_header):
    """Memory-efficient boundary extractor for multipart/form-data uploads."""
    m = re.search(r'boundary=([^;]+)', content_type_header)
    if not m:
        return []
    boundary = m.group(1).strip().strip('"').encode('utf-8')
    delimiter = b'--' + boundary
    files = []
    pos = 0
    total_len = len(data_bytes)
    while pos < total_len:
        idx = data_bytes.find(delimiter, pos)
        if idx == -1:
            break
        next_idx = data_bytes.find(delimiter, idx + len(delimiter))
        part = data_bytes[idx + len(delimiter):next_idx] if next_idx != -1 else data_bytes[idx + len(delimiter):]
        pos = next_idx if next_idx != -1 else total_len
        if not part or part.startswith(b'--'):
            continue
        if b'\r\n\r\n' in part:
            hdr_raw, body = part.split(b'\r\n\r\n', 1)
            if body.endswith(b'\r\n'):
                body = body[:-2]
            hdr_str = hdr_raw.decode('utf-8', errors='ignore')
            fn_match = re.search(r'filename=["\']?([^"\'\r\n;]+)["\']?', hdr_str)
            if fn_match:
                filename = fn_match.group(1).strip()
                files.append({'filename': filename, 'data': body})
    return files


GLOBAL_PC_SHARES = {}
PC_SHARES_DIR = Path(__file__).parent / "pc_shares"
PC_SHARES_META_FILE = PC_SHARES_DIR / "shares_meta.json"


def get_pc_shares_meta():
    PC_SHARES_DIR.mkdir(parents=True, exist_ok=True)
    meta = {}
    if PC_SHARES_META_FILE.exists():
        try:
            meta = json.loads(PC_SHARES_META_FILE.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    changed = False
    # Remove files that no longer exist on disk
    for code, item in list(meta.items()):
        dp = item.get("disk_path")
        if not dp or not Path(dp).exists():
            meta.pop(code, None)
            changed = True
    # Auto-index any existing files on disk
    if PC_SHARES_DIR.exists():
        for p in PC_SHARES_DIR.iterdir():
            if p.is_file() and p.name != "shares_meta.json" and "_" in p.name:
                parts = p.name.split("_", 1)
                code = parts[0].upper()
                raw_name = parts[1]
                if code not in meta:
                    try:
                        mtime_str = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        mtime_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    meta[code] = {
                        "code": code,
                        "name": raw_name,
                        "size": p.stat().st_size,
                        "created_at": mtime_str,
                        "downloads": 0,
                        "disk_path": str(p.resolve()),
                        "cloud_url": "",
                        "local_url": "",
                        "storage_path": f"pc_shares/{code}/{raw_name}"
                    }
                    changed = True
    if changed:
        save_pc_shares_meta(meta)
    return meta


def save_pc_shares_meta(meta):
    try:
        PC_SHARES_DIR.mkdir(parents=True, exist_ok=True)
        PC_SHARES_META_FILE.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log(f"Warning: Failed to save shares_meta.json: {e}")


def record_share_download(code):
    code = (code or "").strip().upper()
    if not code:
        return 0
    meta = get_pc_shares_meta()
    if code in meta:
        meta[code]["downloads"] = meta[code].get("downloads", 0) + 1
        save_pc_shares_meta(meta)
        log(f"📥 Download recorded for PC Share #{code} (Total downloads: {meta[code]['downloads']})")
        return meta[code]["downloads"]
    return 0


def delete_pc_share(code, agent_ref=None):
    code = (code or "").strip().upper()
    if not code or not re.match(r'^[A-Z0-9]{4,12}$', code):
        return False
    meta = get_pc_shares_meta()
    share = meta.get(code)

    # 1. Delete from local disk
    if share and share.get("disk_path") and Path(share["disk_path"]).exists():
        try:
            Path(share["disk_path"]).unlink(missing_ok=True)
        except Exception as e:
            log(f"Warning: could not delete file {share['disk_path']}: {e}")
    for p in PC_SHARES_DIR.glob(f"{code}_*"):
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass

    # 2. Delete from Supabase Storage & Job record if agent_ref is online
    if agent_ref and getattr(agent_ref, "sb_url", None):
        try:
            agent_ref.ensure_token()
            storage_path = share.get("storage_path") if share else ""
            if not storage_path and share:
                safe_fn = re.sub(r'[^\w.\-]+', '_', share.get('name', 'file'))
                storage_path = f"pc_shares/{code}/{safe_fn}"
            if storage_path:
                del_url = f"{agent_ref.sb_url}/storage/v1/object/jobs/{storage_path}"
                del_req = urllib.request.Request(
                    del_url,
                    headers={
                        "apikey": agent_ref.anon_key,
                        "Authorization": f"Bearer {agent_ref.access_token}"
                    },
                    method="DELETE"
                )
                try:
                    with urllib.request.urlopen(del_req, timeout=10) as _:
                        pass
                except Exception:
                    pass
            # Mark Supabase job as cancelled & file_deleted
            agent_ref.api_request(
                "PATCH",
                f"/rest/v1/jobs?note=like.PC_SHARE#{code}%",
                body={"file_deleted": True, "status": "cancelled"}
            )
        except Exception as e:
            log(f"Warning: Cloud cleanup for #{code} failed: {e}")

    # 3. Clean from memory & meta
    meta.pop(code, None)
    save_pc_shares_meta(meta)
    GLOBAL_PC_SHARES.pop(code, None)
    log(f"🗑️ PC Share #{code} deleted")
    return True


def delete_all_pc_shares(agent_ref=None):
    meta = get_pc_shares_meta()
    codes = list(meta.keys())
    for code in codes:
        delete_pc_share(code, agent_ref=agent_ref)
    GLOBAL_PC_SHARES.clear()
    save_pc_shares_meta({})
    log("🗑️ All PC Shares deleted")
    return True


class DropHttpHandler(http.server.BaseHTTPRequestHandler):
    agent_ref = None

    def log_message(self, format, *args):
        pass  # Quiet HTTP handler logs

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def find_share(self, code):
        code = (code or "").strip().upper()
        if not code:
            return None
        meta = get_pc_shares_meta()
        if code in meta:
            rec = dict(meta[code])
            lan_ip = self.agent_ref.lan_ip if (self.agent_ref and self.agent_ref.lan_ip) else get_lan_ip()
            port = self.agent_ref.http_port if (self.agent_ref and self.agent_ref.http_port) else 8085
            rec["local_url"] = f"http://{lan_ip}:{port}/api/pc-share-download/{code}"
            if not rec.get("url"):
                rec["url"] = rec.get("cloud_url") or rec["local_url"]
            GLOBAL_PC_SHARES[code] = rec
            return rec
        return None

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ("", "/drop", "/index", "/drop.html", "/index.html"):
            target_file = Path(__file__).parent.parent / "index.html"
            if not target_file.exists():
                target_file = Path(__file__).parent / "index.html"
            if not target_file.exists():
                target_file = Path(__file__).parent.parent / "drop.html"
            if not target_file.exists():
                target_file = Path(__file__).parent / "drop.html"
            if target_file.exists():
                html = target_file.read_bytes()
                self.send_response(200)
                self.send_cors_headers()
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            else:
                self.send_error(404, "index.html not found")
            return

        if path in ("/api/ip", "/api/info"):
            info = {
                "ip": self.agent_ref.lan_ip if self.agent_ref else get_lan_ip(),
                "port": self.agent_ref.http_port if self.agent_ref else 8085,
                "printer": self.agent_ref.printer_name if self.agent_ref else "",
                "status": "online"
            }
            body = json.dumps(info).encode("utf-8")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/open-downloads":
            try:
                os.startfile(str(self.agent_ref.downloads_dir))
                resp = json.dumps({"ok": True}).encode("utf-8")
            except Exception as e:
                resp = json.dumps({"ok": False, "error": str(e)}).encode("utf-8")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        if path in ("/api/pc-shares", "/api/pc-share-list"):
            meta = get_pc_shares_meta()
            lan_ip = self.agent_ref.lan_ip if (self.agent_ref and self.agent_ref.lan_ip) else get_lan_ip()
            port = self.agent_ref.http_port if (self.agent_ref and self.agent_ref.http_port) else 8085
            shares_list = []
            total_downloads = 0
            for code, item in meta.items():
                total_downloads += item.get("downloads", 0)
                item_copy = dict(item)
                item_copy["local_url"] = f"http://{lan_ip}:{port}/api/pc-share-download/{code}"
                if not item_copy.get("url"):
                    item_copy["url"] = item_copy.get("cloud_url") or item_copy["local_url"]
                shares_list.append(item_copy)
            shares_list.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            resp = json.dumps({
                "ok": True,
                "total_sent": len(shares_list),
                "total_downloads": total_downloads,
                "shares": shares_list
            }).encode("utf-8")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        if path in ("/api/pc-share-download-ping", "/api/pc-share-download-count"):
            code = ""
            if "?" in self.path:
                qs = urllib.parse.parse_qs(self.path.split("?")[1])
                code = qs.get("code", [""])[0].strip().upper()
            new_count = record_share_download(code)
            resp = json.dumps({"ok": True, "code": code, "downloads": new_count}).encode("utf-8")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        if path in ("/api/get-share", "/api/pc-share-info"):
            code = ""
            if "?" in self.path:
                qs = urllib.parse.parse_qs(self.path.split("?")[1])
                code = qs.get("code", [""])[0].strip().upper()
            share = self.find_share(code)
            if share:
                resp = json.dumps({"ok": True, "file": share}).encode("utf-8")
                self.send_response(200)
            else:
                resp = json.dumps({"ok": False, "error": "Share not found"}).encode("utf-8")
                self.send_response(404)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        if path.startswith("/api/pc-share-download/"):
            code = path.replace("/api/pc-share-download/", "").strip().upper()
            share = self.find_share(code)
            if share and Path(share.get("disk_path", "")).exists():
                file_path = Path(share["disk_path"])
                record_share_download(code)
                file_size = file_path.stat().st_size
                fn = share["name"]
                self.send_response(200)
                self.send_cors_headers()
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{fn}"')
                self.send_header("Content-Length", str(file_size))
                self.end_headers()
                with open(file_path, "rb") as f:
                    shutil.copyfileobj(f, self.wfile, length=64 * 1024)
                return
            else:
                self.send_error(404, "Shared file not found")
                return

        # Serve static project files (e.g. index.html, admin.html, config.js, qrcode.min.js)
        clean_rel = path.lstrip("/")
        if clean_rel:
            root_dir = Path(__file__).parent.parent
            target = (root_dir / clean_rel).resolve()
            if target.is_relative_to(root_dir) and target.exists() and target.is_file():
                lower_name = target.name.lower()
                lower_ext = target.suffix.lower()
                # Strictly block hidden files, .env, scripts, databases, logs, and sensitive configs
                if (
                    lower_name.startswith(".")
                    or lower_name in ("config.json", "agent.log", "agent.pid", "shares_meta.json")
                    or lower_ext in (".env", ".py", ".pyc", ".bat", ".cmd", ".ps1", ".sql", ".log", ".pid")
                ):
                    self.send_error(403, "Access denied")
                    return

                ext_map = {
                    ".html": "text/html; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                    ".json": "application/json; charset=utf-8",
                    ".css": "text/css; charset=utf-8",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".svg": "image/svg+xml",
                    ".ico": "image/x-icon"
                }
                if lower_ext not in ext_map:
                    self.send_error(403, "Access denied")
                    return

                # For JSON files, only allow public manifest and animation files
                if lower_ext == ".json" and lower_name not in ("manifest.json", "manifest-admin.json", "printer-printing.json"):
                    self.send_error(403, "Access denied")
                    return

                ctype = ext_map.get(lower_ext, "application/octet-stream")
                data = target.read_bytes()
                self.send_response(200)
                self.send_cors_headers()
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        path = self.path.split("?")[0]
        log(f"do_POST received path: {path}")
        content_type = self.headers.get("Content-Type", "")
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except Exception:
            content_length = 0

        if path in ("/api/pc-share-delete", "/api/pc-shares/delete", "/api/pc-shares-delete-all", "/api/pc-shares/delete-all"):
            body = self.rfile.read(content_length) if content_length > 0 else b""
            if path in ("/api/pc-shares-delete-all", "/api/pc-shares/delete-all"):
                delete_all_pc_shares(self.agent_ref)
                resp = json.dumps({
                    "ok": True,
                    "message": "All PC shared files deleted",
                    "total_sent": 0,
                    "total_downloads": 0,
                    "shares": []
                }).encode("utf-8")
            else:
                code = ""
                if "?" in self.path:
                    qs = urllib.parse.parse_qs(self.path.split("?")[1])
                    code = qs.get("code", [""])[0].strip().upper()
                if not code and body:
                    try:
                        data = json.loads(body.decode("utf-8"))
                        code = data.get("code", "").strip().upper()
                    except Exception:
                        pass
                success = delete_pc_share(code, self.agent_ref)
                meta = get_pc_shares_meta()
                total_downloads = sum(s.get("downloads", 0) for s in meta.values())
                resp = json.dumps({
                    "ok": success,
                    "deleted": code,
                    "total_sent": len(meta),
                    "total_downloads": total_downloads
                }).encode("utf-8")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        if content_length <= 0 or content_length > 200 * 1024 * 1024:
            self.send_response(400)
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(b'{"error": "Invalid content length (max 200MB)"}')
            return

        body = self.rfile.read(content_length)

        if path == "/upload":
            files = parse_multipart(body, content_type)
            if not files:
                self.send_response(400)
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "No file detected in upload"}')
                return

            saved_files = []
            for f in files:
                fn = f["filename"]
                safe_fn = re.sub(r'[^\w.\-]+', '_', fn)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                save_name = f"{timestamp}_{safe_fn}"
                out_path = self.agent_ref.downloads_dir / save_name
                out_path.write_bytes(f["data"])
                saved_files.append(save_name)
                log(f"📥 File Drop: saved '{save_name}' ({len(f['data'])} bytes) to downloads/")

            count = len(saved_files)
            summary = saved_files[0] if count == 1 else f"{count} files"
            send_windows_toast("Mobile File Drop 📥", f"{summary} received from mobile and saved to Downloads.")
            if winsound:
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    pass

            resp = json.dumps({"ok": True, "files": saved_files}).encode("utf-8")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        if path == "/local-print-upload":
            files = parse_multipart(body, content_type)
            if not files:
                self.send_response(400)
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "No file in local print upload"}')
                return

            f = files[0]
            job_id = None
            if "?" in self.path:
                qs = urllib.parse.parse_qs(self.path.split("?")[1])
                job_id = qs.get("id", [None])[0]

            raw_name = f["filename"]
            safe_name = re.sub(r'[^\w.\-]+', '_', raw_name)
            target_name = f"{job_id}_{safe_name}" if job_id else safe_name
            target_path = self.agent_ref.tmp_dir / target_name
            target_path.write_bytes(f["data"])
            log(f"💻 Local Print Upload: saved '{target_name}' ({len(f['data'])} bytes) to tmp/")

            resp = json.dumps({"ok": True, "file_path": f"local://{target_name}"}).encode("utf-8")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        if path == "/api/pc-share-upload":
            files = parse_multipart(body, content_type)
            if not files:
                self.send_response(400)
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "No file in share upload"}')
                return

            code = ""
            if "?" in self.path:
                qs = urllib.parse.parse_qs(self.path.split("?")[1])
                code = qs.get("code", [""])[0].strip().upper()
            if not code:
                code = str(random.randint(100000, 999999))

            f = files[0]
            raw_name = f["filename"]
            safe_name = re.sub(r'[^\w.\-]+', '_', raw_name)
            shares_dir = Path(__file__).parent / "pc_shares"
            shares_dir.mkdir(parents=True, exist_ok=True)
            target_path = shares_dir / f"{code}_{safe_name}"
            target_path.write_bytes(f["data"])

            lan_ip = self.agent_ref.lan_ip if (self.agent_ref and self.agent_ref.lan_ip) else get_lan_ip()
            port = self.agent_ref.http_port if (self.agent_ref and self.agent_ref.http_port) else 8085
            local_download_url = f"http://{lan_ip}:{port}/api/pc-share-download/{code}"

            cloud_download_url = ""
            if self.agent_ref and self.agent_ref.sb_url:
                try:
                    self.agent_ref.ensure_token()
                    storage_path = f"pc_shares/{code}/{safe_name}"
                    up_url = f"{self.agent_ref.sb_url}/storage/v1/object/jobs/{storage_path}"
                    up_req = urllib.request.Request(
                        up_url,
                        data=f["data"],
                        headers={
                            "apikey": self.agent_ref.anon_key,
                            "Authorization": f"Bearer {self.agent_ref.access_token}",
                            "Content-Type": "application/octet-stream",
                            "x-upsert": "false"
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(up_req, timeout=30) as up_res:
                        pass

                    sign_url = f"{self.agent_ref.sb_url}/storage/v1/object/sign/jobs/{storage_path}"
                    sign_payload = json.dumps({"expiresIn": 86400 * 7}).encode("utf-8")
                    sign_req = urllib.request.Request(
                        sign_url,
                        data=sign_payload,
                        headers={
                            "apikey": self.agent_ref.anon_key,
                            "Authorization": f"Bearer {self.agent_ref.access_token}",
                            "Content-Type": "application/json"
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(sign_req, timeout=15) as sign_res:
                        s_data = json.loads(sign_res.read().decode("utf-8"))
                        if "signedURL" in s_data:
                            cloud_download_url = f"{self.agent_ref.sb_url}/storage/v1{s_data['signedURL']}"
                            log(f"☁️ Cloud Signed URL created for PC Share #{code}")
                except Exception as e:
                    log(f"Warning: Cloud upload for share #{code} failed: {e}")

            GLOBAL_PC_SHARES[code] = {
                "name": raw_name,
                "size": len(f["data"]),
                "url": cloud_download_url or local_download_url,
                "local_url": local_download_url,
                "cloud_url": cloud_download_url,
                "disk_path": str(target_path)
            }
            # Also record in persistent shares_meta.json
            meta = get_pc_shares_meta()
            meta[code] = {
                "code": code,
                "name": raw_name,
                "size": len(f["data"]),
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "downloads": 0,
                "cloud_url": cloud_download_url,
                "local_url": local_download_url,
                "url": cloud_download_url or local_download_url,
                "disk_path": str(target_path),
                "storage_path": storage_path if cloud_download_url else ""
            }
            save_pc_shares_meta(meta)
            log(f"📤 PC to Mobile Share created: #{code} '{raw_name}' ({len(f['data'])} bytes)")

            resp = json.dumps({
                "ok": True,
                "code": code,
                "url": cloud_download_url or local_download_url,
                "cloud_url": cloud_download_url,
                "local_url": local_download_url,
                "name": raw_name,
                "size": len(f["data"])
            }).encode("utf-8")
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        self.send_error(404, "Endpoint not found")

    def do_DELETE(self):
        return self.do_POST()


def send_windows_toast(title, message):
    """Sends a native Windows 10/11 Toast notification asynchronously and securely."""
    try:
        t_clean = re.sub(r'[\r\n\t]+', ' ', str(title))[:64].strip()
        m_clean = re.sub(r'[\r\n\t]+', ' ', str(message))[:128].strip()
        t_b64 = base64.b64encode(t_clean.encode('utf-8', errors='ignore')).decode('ascii')
        m_b64 = base64.b64encode(m_clean.encode('utf-8', errors='ignore')).decode('ascii')
        ps_cmd = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
            "$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            "$nodes = $template.GetElementsByTagName('text'); "
            f"$t = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{t_b64}')); "
            f"$m = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{m_b64}')); "
            "$nodes.Item(0).AppendChild($template.CreateTextNode($t)) | Out-Null; "
            "$nodes.Item(1).AppendChild($template.CreateTextNode($m)) | Out-Null; "
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('CyberPrint Pay').Show($toast);"
        )
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            creationflags=flags
        )
    except Exception:
        pass


class PrintAgent:
    def __init__(self, config_path):
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"config.json not found at {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        self.sb_url = cfg["supabase_url"].strip().rstrip("/")
        self.anon_key = cfg["anon_key"].strip().strip('"').strip("'")
        self.email = cfg["email"].strip()
        self.password = str(cfg["password"])
        self.poll_seconds = int(cfg.get("poll_seconds", 3))
        self.printer_name = cfg.get("printer", "").strip()
        self.agent_id = cfg.get("agent_id", "counter-pc").strip()
        self.bucket = cfg.get("bucket", "jobs").strip()

        # If printer is empty, use the system default printer
        if not self.printer_name:
            try:
                self.printer_name = win32print.GetDefaultPrinter()
            except Exception:
                self.printer_name = ""

        self.tmp_dir = self.config_path.parent / "tmp"
        self.tmp_dir.mkdir(exist_ok=True)
        self.downloads_dir = self.config_path.parent / "downloads"
        self.downloads_dir.mkdir(exist_ok=True)

        self.http_port = int(cfg.get("http_port", 8085))
        self.lan_ip = get_lan_ip()
        self.httpd = None

        self.access_token = None
        self.refresh_token = None
        self.expires_at = datetime.datetime.min
        self.active_prompt = None

    def start_http_server(self):
        try:
            handler_class = DropHttpHandler
            handler_class.agent_ref = self
            self.httpd = http.server.ThreadingHTTPServer(("0.0.0.0", self.http_port), handler_class)
            srv_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            srv_thread.start()
            log(f"Local Drop Server active: http://{self.lan_ip}:{self.http_port}/ (Mobile-to-PC File Drop)")
        except Exception as e:
            log(f"Local Drop Server failed to start on port {self.http_port}: {e}")

    def sign_in(self):
        url = f"{self.sb_url}/auth/v1/token?grant_type=password"
        payload = json.dumps({"email": self.email, "password": self.password}).encode("utf-8")
        headers = {
            "apikey": self.anon_key,
            "Content-Type": "application/json"
        }
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.access_token = data["access_token"]
                self.refresh_token = data.get("refresh_token")
                expires_in = int(data.get("expires_in", 3600))
                self.expires_at = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)
                log("signed in (password) - will refresh silently from now on")
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            raise RuntimeError(f"Sign-in failed ({e.code}): {err_msg}")

    def refresh(self):
        if not self.refresh_token:
            self.sign_in()
            return

        url = f"{self.sb_url}/auth/v1/token?grant_type=refresh_token"
        payload = json.dumps({"refresh_token": self.refresh_token}).encode("utf-8")
        headers = {
            "apikey": self.anon_key,
            "Content-Type": "application/json"
        }
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.access_token = data["access_token"]
                if "refresh_token" in data:
                    self.refresh_token = data["refresh_token"]
                expires_in = int(data.get("expires_in", 3600))
                self.expires_at = datetime.datetime.now() + datetime.timedelta(seconds=expires_in)
                log("token refreshed")
        except Exception as e:
            log(f"token refresh failed ({e}) -> re-signing in with password")
            self.sign_in()

    def ensure_token(self):
        if not self.access_token or datetime.datetime.now() >= (self.expires_at - datetime.timedelta(seconds=60)):
            try:
                self.refresh()
            except Exception:
                self.sign_in()

    def api_request(self, method, endpoint, body=None, extra_headers=None):
        self.ensure_token()
        url = f"{self.sb_url}{endpoint}"
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8") if isinstance(body, (dict, list)) else body

        headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.access_token}"
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)

        for attempt in range(2):
            req = urllib.request.Request(url, data=payload, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp_body = resp.read().decode("utf-8")
                    return json.loads(resp_body) if resp_body else None
            except urllib.error.HTTPError as e:
                err_text = e.read().decode("utf-8")
                if (e.code == 401 or "Invalid API key" in err_text) and attempt == 0:
                    log("session expired or invalid, re-authenticating...")
                    self.sign_in()
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    continue
                raise RuntimeError(f"HTTP {e.code}: {err_text}")
            except urllib.error.URLError as e:
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise

    def check_tables(self):
        for tbl in ["jobs", "agent_status"]:
            try:
                self.api_request("GET", f"/rest/v1/{tbl}?select=*&limit=1")
                log(f"table ok: {tbl}")
            except Exception as e:
                log(f"TABLE MISSING: {tbl} -> {e}")
                log("Run supabase-setup.sql in your Supabase SQL editor.")
                return False
        return True

    def heartbeat(self, note):
        payload = {
            "id": self.agent_id,
            "last_seen": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "printer": self.printer_name,
            "note": f"{note} | http://{self.lan_ip}:{self.http_port}"
        }
        try:
            self.api_request(
                "POST",
                "/rest/v1/agent_status?on_conflict=id",
                body=payload,
                extra_headers={"Prefer": "resolution=merge-duplicates"}
            )
        except Exception:
            pass  # Suppress transient network blips on background heartbeats

    def get_pending_jobs(self):
        jobs = self.api_request(
            "GET",
            "/rest/v1/jobs?status=in.(pending,approved)&or=(customer_name.is.null,customer_name.neq.PC_TO_MOBILE)&select=*&order=created_at.asc"
        )
        return jobs or []

    def claim_job(self, job_id):
        try:
            res = self.api_request(
                "PATCH",
                f"/rest/v1/jobs?id=eq.{job_id}&status=in.(pending,approved)",
                body={"status": "printing"},
                extra_headers={"Prefer": "return=representation"}
            )
            return bool(res and len(res) > 0)
        except Exception as e:
            log(f"claim failed for #{job_id}: {e}")
            return False

    def finish_job(self, job_id, status, error=None):
        patch = {"status": status}
        if error:
            patch["print_error"] = str(error)
        else:
            patch["printed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            patch["print_error"] = None

        self.api_request("PATCH", f"/rest/v1/jobs?id=eq.{job_id}", body=patch)

    def reject_job(self, job_id):
        self.api_request("PATCH", f"/rest/v1/jobs?id=eq.{job_id}", body={"status": "rejected"})

    def signed_url(self, file_path):
        res = self.api_request(
            "POST",
            f"/storage/v1/object/sign/{self.bucket}/{file_path}",
            body={"expiresIn": 300}
        )
        signed_path = res["signedURL"]
        return f"{self.sb_url}/storage/v1{signed_path}"

    def beep(self):
        if winsound:
            try:
                winsound.Beep(587, 120)
                winsound.Beep(880, 220)
            except Exception:
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    pass

    def show_job_popup(self, jobs_input, code=None, color_lbl=None, range_text=None):
        """Displays a sleek floating notification card at bottom-right corner of screen."""
        decision = [None]
        try:
            root = tk.Tk()
        except Exception as e:
            log(f"GUI not available ({e}) - will check console")
            return None

        jobs_list = jobs_input if isinstance(jobs_input, list) else [jobs_input]
        is_batch = len(jobs_list) > 1
        first_job = jobs_list[0]
        batch_id = first_job.get("batch_id")
        if not code:
            code = (batch_id.replace("-", "")[:6].upper()) if batch_id else first_job["id"].replace("-", "")[:6].upper()

        total_price = sum(float(j.get("total_price", 0) or 0) for j in jobs_list)
        total_price_str = f"{int(total_price) if total_price.is_integer() else total_price}"

        if is_batch:
            root.title(f"CyberPrint Pay - Batch #{code} ({len(jobs_list)} Files)")
        else:
            root.title(f"CyberPrint Pay - Job #{code}")
        root.attributes("-topmost", True)
        root.resizable(False, False)

        # Position in bottom-right corner above taskbar
        w = 460 if is_batch else 440
        h = min(420, 260 + (len(jobs_list) - 1) * 36) if is_batch else 250
        try:
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            x = max(10, sw - w - 24)
            y = max(10, sh - h - 70)
            root.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            root.geometry(f"{w}x{h}")

        root.configure(bg="#ffffff")

        # Win32 force to foreground (guarantees window appears in front even when launched via pythonw)
        def force_foreground():
            try:
                root.update_idletasks()
                root.deiconify()
                root.lift()
                root.focus_force()
                user32 = ctypes.windll.user32
                child = root.winfo_id()
                parent = user32.GetParent(child)
                hwnd = parent if parent else child

                user32.ShowWindow(hwnd, 5) # SW_SHOW
                user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)

                cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
                fg_hwnd = user32.GetForegroundWindow()
                fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
                if cur_tid != fg_tid:
                    user32.AttachThreadInput(cur_tid, fg_tid, True)
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                    user32.AttachThreadInput(cur_tid, fg_tid, False)
                else:
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)

                user32.FlashWindow(hwnd, True)
            except Exception:
                pass

        root.after(40, force_foreground)
        root.after(300, force_foreground)
        root.after(700, force_foreground)

        # Header bar
        hdr = tk.Frame(root, bg="#0f172a", height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        header_title = f"🖨️ CyberPrint Pay — BATCH #{code} ({len(jobs_list)} Files)" if is_batch else f"🖨️ CyberPrint Pay — NAYA PRINT JOB #{code}"
        title_lbl = tk.Label(
            hdr, text=header_title,
            fg="#ffffff", bg="#0f172a", font=("Segoe UI", 11, "bold")
        )
        title_lbl.pack(side="left", padx=14, pady=9)

        # Body frame
        body = tk.Frame(root, bg="#ffffff", padx=16, pady=12)
        body.pack(fill="both", expand=True)

        if is_batch:
            list_box = tk.Frame(body, bg="#f8fafc", padx=8, pady=6, highlightbackground="#e2e8f0", highlightthickness=1)
            list_box.pack(fill="both", expand=True, pady=(0, 8))
            for idx, j in enumerate(jobs_list[:6], 1):
                raw_name = j.get("file_name", "document")
                f_name = (raw_name[:26] + "...") if len(raw_name) > 28 else raw_name
                c_mode = "Color" if j.get("color_mode") == "color" else "B&W"
                row_text = f"{idx}. {f_name}  ({j.get('page_count')}p · {j.get('copies')}c · {c_mode} · ₹{j.get('total_price', 0)})"
                row_lbl = tk.Label(
                    list_box, text=row_text,
                    fg="#1e293b", bg="#f8fafc", font=("Segoe UI", 9, "bold"), anchor="w"
                )
                row_lbl.pack(fill="x", pady=1)
            if len(jobs_list) > 6:
                more_lbl = tk.Label(
                    list_box, text=f"...aur {len(jobs_list) - 6} documents",
                    fg="#64748b", bg="#f8fafc", font=("Segoe UI", 8, "italic"), anchor="w"
                )
                more_lbl.pack(fill="x")
        else:
            raw_name = first_job.get("file_name", "document")
            file_name = (raw_name[:34] + "...") if len(raw_name) > 36 else raw_name

            fn_lbl = tk.Label(
                body, text=file_name,
                fg="#0f172a", bg="#ffffff", font=("Segoe UI", 12, "bold"), anchor="w"
            )
            fn_lbl.pack(fill="x")

            c_lbl = color_lbl or ("Rangeen (Color)" if first_job.get("color_mode") == "color" else "Kala-Safed (B&W)")
            r_txt = range_text or (f" (pages {first_job.get('page_range')})" if first_job.get("page_range") else "")
            specs_text = f"📄 {first_job.get('page_count')} Page{r_txt} · {first_job.get('copies')} Copy · {c_lbl} · {first_job.get('paper_size')}"
            specs_lbl = tk.Label(
                body, text=specs_text,
                fg="#64748b", bg="#ffffff", font=("Segoe UI", 10), anchor="w"
            )
            specs_lbl.pack(fill="x", pady=(2, 8))

        amt_frame = tk.Frame(body, bg="#f0fdf4", padx=10, pady=6, highlightbackground="#86efac", highlightthickness=1)
        amt_frame.pack(fill="x", pady=(0, 10))

        amt_desc = f"Kul {len(jobs_list)} files ka total" if is_batch else "UPI ya Cash check karein"
        amt_lbl = tk.Label(
            amt_frame, text=f"COLLECT KAREIN : ₹{total_price_str} ({amt_desc})",
            fg="#15803d", bg="#f0fdf4", font=("Segoe UI", 10, "bold")
        )
        amt_lbl.pack(side="left")

        # Action buttons
        btn_frame = tk.Frame(body, bg="#ffffff")
        btn_frame.pack(fill="x")

        is_closing = [False]

        def safe_close():
            if not is_closing[0]:
                is_closing[0] = True
                try:
                    root.destroy()
                except Exception:
                    pass

        def on_print():
            decision[0] = "Y"
            safe_close()

        def on_reject():
            decision[0] = "N"
            safe_close()

        root.protocol("WM_DELETE_WINDOW", safe_close)

        btn_print_text = "✅ Sabhi Print Nikalo (Y)" if is_batch else "✅ Print Nikalo (Y)"
        print_btn = tk.Button(
            btn_frame, text=btn_print_text,
            bg="#16a34a", fg="#ffffff", activebackground="#15803d", activeforeground="#ffffff",
            font=("Segoe UI", 10, "bold"), relief="flat", padx=12, pady=7, cursor="hand2",
            command=on_print
        )
        print_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        btn_reject_text = "❌ Sabhi Reject Karo (N)" if is_batch else "❌ Reject Karo (N)"
        reject_btn = tk.Button(
            btn_frame, text=btn_reject_text,
            bg="#fee2e2", fg="#dc2626", activebackground="#fecaca", activeforeground="#b91c1c",
            font=("Segoe UI", 10, "bold"), relief="flat", padx=12, pady=7, cursor="hand2",
            command=on_reject
        )
        reject_btn.pack(side="right", expand=True, fill="x", padx=(6, 0))

        # Hotkeys
        root.bind("<Return>", lambda e: on_print())
        root.bind("<Key-y>", lambda e: on_print())
        root.bind("<Key-Y>", lambda e: on_print())
        root.bind("<Escape>", lambda e: on_reject())
        root.bind("<Key-n>", lambda e: on_reject())
        root.bind("<Key-N>", lambda e: on_reject())

        def poll_external_worker():
            """Runs external status checks asynchronously so slow network never freezes GUI."""
            job_ids = [j["id"] for j in jobs_list]
            while not is_closing[0]:
                try:
                    self.heartbeat("awaiting confirmation")
                    if is_batch:
                        chk = self.api_request(
                            "GET",
                            f"/rest/v1/jobs?id=in.({','.join(job_ids)})&select=id,status"
                        )
                        if chk and not is_closing[0]:
                            all_appr = len(chk) == len(job_ids) and all(item.get("status") == "approved" for item in chk)
                            any_rej = any(item.get("status") in ("cancelled", "rejected", "failed") for item in chk)
                            if all_appr:
                                log("batch was approved via mobile admin panel while popup was open - printing!")
                                decision[0] = "Y"
                                root.after(0, safe_close)
                                return
                            elif any_rej:
                                log("one or more jobs in batch was rejected/cancelled externally - dialog closing")
                                root.after(0, safe_close)
                                return
                    else:
                        chk = self.api_request(
                            "GET",
                            f"/rest/v1/jobs?id=eq.{first_job['id']}&select=status"
                        )
                        if chk and not is_closing[0]:
                            st = chk[0].get("status")
                            if st == "approved":
                                log("job was approved via mobile admin panel while popup was open - printing!")
                                decision[0] = "Y"
                                root.after(0, safe_close)
                                return
                            elif st != "pending":
                                log(f"job was marked '{st}' externally - dialog closing")
                                root.after(0, safe_close)
                                return
                except Exception:
                    pass
                time.sleep(2)

        poll_thread = threading.Thread(target=poll_external_worker, daemon=True)
        poll_thread.start()

        root.mainloop()
        return decision[0]

    def notify_job(self, jobs_input):
        self.beep()
        jobs_list = jobs_input if isinstance(jobs_input, list) else [jobs_input]
        is_batch = len(jobs_list) > 1
        first_job = jobs_list[0]
        batch_id = first_job.get("batch_id")
        code = (batch_id.replace("-", "")[:6].upper()) if batch_id else first_job["id"].replace("-", "")[:6].upper()
        total_price = sum(float(j.get("total_price", 0) or 0) for j in jobs_list)
        total_price_str = f"{int(total_price) if total_price.is_integer() else total_price}"

        # 1. Console Log
        print("", flush=True)
        print("=" * 64)
        if is_batch:
            print(f"  NAYA PRINT BATCH #{code} ({len(jobs_list)} Files) -- kripya payment check karein")
            for idx, j in enumerate(jobs_list, 1):
                p_range = j.get("page_range")
                r_txt = f" (pages {p_range})" if p_range else ""
                c_lbl = "Color" if j.get("color_mode") == "color" else "B&W"
                f_name = re.sub(r'[\r\n\t]+', ' ', str(j.get("file_name", "document"))).strip()
                print(f"  [{idx}/{len(jobs_list)}] {f_name}")
                print(f"       {j.get('page_count')} page{r_txt} | {j.get('copies')} copy | {c_lbl} | {j.get('paper_size')} | ₹{j.get('total_price', 0)}")
            print(f"  KUL COLLECT : Rs {total_price_str} (UPI ya Cash)")
            print("  Customer ka payment check karein, phir key dabayein:")
            print("      Y  = Sabhi Print nikalo (Approve Batch)")
            print("      N  = Sabhi Reject karo (Cancel Batch)")
        else:
            page_range = first_job.get("page_range")
            range_text = f" (pages {page_range})" if page_range else ""
            color_lbl = "Rangeen (Color)" if first_job.get("color_mode") == "color" else "Kala-Safed (B&W)"
            raw_name = first_job.get("file_name", "document")
            file_name = re.sub(r'[\r\n\t]+', ' ', str(raw_name)).strip()
            print(f"  NAYA PRINT JOB #{code}   -- kripya payment check karein")
            print(f"  File    : {file_name}")
            print(f"  Specs   : {first_job.get('page_count')} page{range_text} | {first_job.get('copies')} copy | {color_lbl} | {first_job.get('paper_size')}")
            print(f"  COLLECT : Rs {total_price_str} (UPI ya Cash)")
            print("  Customer ka payment check karein, phir key dabayein:")
            print("      Y  = Print nikalo (Approve)")
            print("      N  = Reject karo (Cancel)")
        print("=" * 64, flush=True)

        # 2. Windows 10/11 Action Center Toast Notification (sanitized)
        if is_batch:
            send_windows_toast(
                f"🖨️ CyberPrint Pay — Naya Batch #{code} ({len(jobs_list)} Files)",
                f"{len(jobs_list)} files · KUL COLLECT : Rs {total_price_str}"
            )
        else:
            send_windows_toast(
                f"🖨️ CyberPrint Pay — Naya Job #{code}",
                f"{first_job.get('file_name', 'document')} · COLLECT : Rs {total_price_str}"
            )

        # 3. Interactive Floating Popup Card
        decision = self.show_job_popup(jobs_list, code)
        return decision

    def print_gdi_image(self, hdc, img, color_mode="color", orientation="portrait"):
        """Draws a PIL Image onto a Windows printer DC, scaled to fit printable margins."""
        HORZRES = 8
        VERTRES = 10
        printable_width = hdc.GetDeviceCaps(HORZRES)
        printable_height = hdc.GetDeviceCaps(VERTRES)

        # Convert to 8-bit grayscale for B&W to cut USB transfer payload by 66%
        if color_mode == "bw":
            if img.mode != "L":
                img = img.convert("L")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Auto-rotate if image orientation doesn't match page orientation
        img_w, img_h = img.size
        img_is_landscape = img_w > img_h
        page_is_landscape = (orientation == "landscape") or (printable_width > printable_height)

        if img_is_landscape != page_is_landscape:
            img = img.rotate(90, expand=True)
            img_w, img_h = img.size

        # Fit to printable margins
        ratio = min(printable_width / img_w, printable_height / img_h)
        new_w = int(img_w * ratio)
        new_h = int(img_h * ratio)
        pos_x = int((printable_width - new_w) / 2)
        pos_y = int((printable_height - new_h) / 2)

        dib = ImageWin.Dib(img)
        dib.draw(hdc.GetHandleOutput(), (pos_x, pos_y, pos_x + new_w, pos_y + new_h))

    @staticmethod
    def _parse_page_range(range_str, total_pages):
        """Safely parses page ranges (e.g. '1-3', '1, 3, 5', '2-') or defaults to all pages."""
        if not range_str:
            return list(range(total_pages))
        try:
            pages = set()
            for part in str(range_str).split(","):
                part = part.strip()
                if not part:
                    continue
                if "-" in part:
                    subparts = part.split("-", 1)
                    s_str, e_str = subparts[0].strip(), subparts[1].strip()
                    s = int(s_str) if s_str else 1
                    e = int(e_str) if e_str else total_pages
                    s = max(1, min(s, total_pages))
                    e = max(1, min(e, total_pages))
                    low, high = (s, e) if s <= e else (e, s)
                    pages.update(range(low - 1, high))
                else:
                    val = int(part)
                    if 1 <= val <= total_pages:
                        pages.add(val - 1)
            if pages:
                return sorted(list(pages))
        except Exception as e:
            log(f"Warning: page_range '{range_str}' invalid ({e}), defaulting to all {total_pages} pages")
        return list(range(total_pages))

    def print_file_native(self, file_path, job):
        """Prints a PDF or image directly through Windows GDI with hardware DEVMODE optimization."""
        file_path = Path(file_path)
        ext = file_path.suffix.lower()
        copies = max(1, int(job.get("copies", 1)))
        color_mode = job.get("color_mode", "bw")
        orientation = job.get("orientation", "portrait")
        page_range = job.get("page_range")

        log(f"  opening printer: '{self.printer_name}'")
        hprinter = win32print.OpenPrinter(self.printer_name)
        hdc = None
        try:
            pinfo = win32print.GetPrinter(hprinter, 2)
            devmode = pinfo.get("pDevMode")
            if devmode:
                if color_mode == "color":
                    devmode.Color = win32con.DMCOLOR_COLOR
                else:
                    devmode.Color = win32con.DMCOLOR_MONOCHROME

                if orientation == "landscape":
                    devmode.Orientation = win32con.DMORIENT_LANDSCAPE
                else:
                    devmode.Orientation = win32con.DMORIENT_PORTRAIT

                hdc_raw = win32gui.CreateDC("WINSPOOL", self.printer_name, devmode)
                hdc = win32ui.CreateDCFromHandle(hdc_raw)
            else:
                hdc = win32ui.CreateDC()
                hdc.CreatePrinterDC(self.printer_name)

            if ext == ".pdf":
                pdf = pdfium.PdfDocument(str(file_path))
                total_pages = len(pdf)
                pages_to_print = self._parse_page_range(page_range, total_pages)

                log(f"  streaming {len(pages_to_print)} page(s) to printer (mode: {color_mode}, copies: {copies})...")
                for c in range(copies):
                    hdc.StartDoc(f"CyberPrint - {file_path.name}")
                    for p_idx in pages_to_print:
                        page = pdf[p_idx]
                        pil_img = page.render(scale=2.0).to_pil()
                        try:
                            hdc.StartPage()
                            self.print_gdi_image(hdc, pil_img, color_mode, orientation)
                            hdc.EndPage()
                        finally:
                            try:
                                pil_img.close()
                            except Exception:
                                pass
                    hdc.EndDoc()

            elif ext in [".png", ".jpg", ".jpeg", ".bmp"]:
                log(f"  loading image: {file_path.name}")
                with Image.open(file_path) as pil_img:
                    pil_img.load()
                    HORZRES = 8
                    VERTRES = 10
                    max_w = hdc.GetDeviceCaps(HORZRES)
                    max_h = hdc.GetDeviceCaps(VERTRES)
                    if pil_img.width > max_w or pil_img.height > max_h:
                        pil_img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

                    for c in range(copies):
                        hdc.StartDoc(f"CyberPrint - {file_path.name}")
                        hdc.StartPage()
                        self.print_gdi_image(hdc, pil_img, color_mode, orientation)
                        hdc.EndPage()
                        hdc.EndDoc()
            else:
                raise ValueError(f"Unsupported file format: {ext}")

            log("  spooler received document successfully")
            return 0
        finally:
            if hdc is not None:
                try:
                    hdc.DeleteDC()
                except Exception:
                    pass
            win32print.ClosePrinter(hprinter)

    def process_print(self, job):
        job_id = job["id"]
        code = job_id.replace("-", "")[:6].upper()
        if not self.claim_job(job_id):
            log(f"job #{code} is no longer pending - skipped")
            return

        file_name = job.get("file_name", "document")
        log(f"printing #{code}  {file_name}")
        local_path = None
        try:
            file_path = job.get("file_path")
            if not file_path:
                raise RuntimeError("File already removed from storage")

            if file_path.startswith("local://"):
                local_rel = file_path[len("local://"):]
                local_path = self.tmp_dir / local_rel
                if not local_path.exists():
                    if (self.downloads_dir / local_rel).exists():
                        local_path = self.downloads_dir / local_rel
                    else:
                        raise RuntimeError(f"Local file not found on PC disk: {local_rel}")
                log(f"  reading file directly from local PC disk: {local_path.name} (zero cloud download)")
            else:
                url = self.signed_url(file_path)
                raw_ext = Path(file_name).suffix.lower() if Path(file_name).suffix else Path(file_path).suffix.lower()
                ext = raw_ext or ".pdf"
                local_path = self.tmp_dir / f"{job_id}{ext}"

                # Download file
                urllib.request.urlretrieve(url, str(local_path))

            # Native Print
            self.print_file_native(local_path, job)

            # Mark printed
            self.finish_job(job_id, "printed")
            log(f"printed  #{code}")

        except Exception as e:
            log(f"FAILED   #{code}: {e}")
            try:
                self.finish_job(job_id, "failed", error=str(e))
            except Exception:
                pass
        finally:
            if local_path and local_path.exists() and local_path.parent == self.tmp_dir:
                try:
                    local_path.unlink()
                except Exception:
                    pass

    def process_cloud_file_drop(self, job):
        job_id = job["id"]
        code = job_id.replace("-", "")[:6].upper()
        if not self.claim_job(job_id):
            return

        file_name = job.get("file_name", "dropped_file")
        file_path = job.get("file_path")
        log(f"📥 Cloud File Drop received: #{code} - {file_name}")

        try:
            if not file_path:
                raise RuntimeError("File path missing in record")

            url = self.signed_url(file_path)
            safe_name = re.sub(r'[^\w.\-]+', '_', file_name)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            target_name = f"{timestamp}_{safe_name}"
            out_path = self.downloads_dir / target_name

            # Download file into agent/downloads
            urllib.request.urlretrieve(url, str(out_path))
            size_kb = round(out_path.stat().st_size / 1024, 1)
            log(f"  saved to downloads/{target_name} ({size_kb} KB)")

            # Windows toast notification & sound
            send_windows_toast("Mobile File Drop 📥", f"{file_name} received via Cloud ({size_kb} KB) and saved to Downloads.")
            if winsound:
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    pass

            # Mark job downloaded/completed in Supabase
            self.api_request(
                "PATCH",
                f"/rest/v1/jobs?id=eq.{job_id}",
                body={
                    "status": "printed",
                    "printed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "note": "FILE_DROP_SAVED"
                }
            )

            # Clean up file from Supabase storage so zero cloud quota is used
            try:
                self.api_request(
                    "DELETE",
                    f"/storage/v1/object/{self.bucket}",
                    body={"prefixes": [file_path]}
                )
            except Exception:
                pass

        except Exception as e:
            log(f"  File Drop download failed #{code}: {e}")
            try:
                self.finish_job(job_id, "failed", error=str(e))
            except Exception:
                pass

    def run(self):
        try:
            with open(PID_FILE, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
        except Exception:
            pass

        log(f"config file: {self.config_path}")
        log(f"supabase   : {self.sb_url}   (anon key length {len(self.anon_key)})")
        log(f"agent '{self.agent_id}' running (PID: {os.getpid()}) - printer: '{self.printer_name}'")
        log("Notification mode active: screen popup and Windows Toast notifications will alert on new jobs.")

        self.start_http_server()
        self.sign_in()
        self.check_tables()

        while True:
            try:
                self.heartbeat("idle")
                pending = self.get_pending_jobs()
                if pending:
                    first = pending[0]
                    note = first.get("note") or ""
                    if first.get("customer_name") == "COMMAND":
                        if "OPEN_DOWNLOADS" in note:
                            try:
                                os.startfile(str(self.downloads_dir))
                                log("📂 Opened downloads folder via remote command")
                            except Exception as ex:
                                log(f"Error opening downloads folder: {ex}")
                        try:
                            self.api_request("PATCH", f"/rest/v1/jobs?id=eq.{first['id']}", body={"status": "cancelled", "note": "COMMAND_DONE"})
                        except Exception:
                            pass
                        time.sleep(0.5)
                        continue
                    if "PC_SHARE" in note or first.get("customer_name") == "PC_TO_MOBILE":
                        try:
                            self.api_request("PATCH", f"/rest/v1/jobs?id=eq.{first['id']}", body={"status": "cancelled"})
                        except Exception:
                            pass
                        time.sleep(0.5)
                        continue
                    if "FILE_DROP" in note:
                        self.process_cloud_file_drop(first)
                        time.sleep(0.5)
                        continue

                    # Group batch jobs if batch_id exists
                    batch_id = first.get("batch_id")
                    if batch_id:
                        batch_jobs = [j for j in pending if j.get("batch_id") == batch_id]
                    else:
                        batch_jobs = [first]

                    all_approved = all(j.get("status") == "approved" for j in batch_jobs)
                    if all_approved:
                        code = (batch_id.replace("-", "")[:6].upper()) if batch_id else first["id"].replace("-", "")[:6].upper()
                        log(f"job(s) #{code} ({len(batch_jobs)} file(s)) approved via admin panel - printing sequentially...")
                        for j in batch_jobs:
                            self.process_print(j)
                    else:
                        decision = self.notify_job(batch_jobs)
                        if decision == "Y":
                            for j in batch_jobs:
                                self.process_print(j)
                        elif decision == "N":
                            for j in batch_jobs:
                                self.reject_job(j["id"])
                                log(f"rejected #{j['id']}")
            except Exception as e:
                log(f"loop error: {e}")

            time.sleep(self.poll_seconds)


if __name__ == "__main__":
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

    cfg_file = Path(__file__).parent / "config.json"
    agent = PrintAgent(cfg_file)
    agent.run()
