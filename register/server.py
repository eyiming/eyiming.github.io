#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""极简注册服务 —— 纯 Python 标准库实现，零第三方依赖（Python 3.9+）。

用途：演示「表单提交后结果原地渲染，页面不跳转、不刷新」。

核心约定（前端依赖这套契约渲染结果）：
    POST /api/register
    Content-Type: application/json
    请求体: {"username": "...", "email": "...", "password": "...", "confirm": "..."}

    成功 → HTTP 201，{"ok": true,  "code": "REGISTERED", "message": "...", "data": {...}}
    失败 → HTTP 4xx/5xx，{"ok": false, "code": "...", "message": "...", "errors": {"字段": "原因"}}

关键：绝不能返回 302 重定向或整页 HTML —— 那会让浏览器离开当前页，
      前端就拿不到可渲染的结果了。本文件所有 /api/* 分支一律返回 JSON。

启动:
    python server.py                # 默认 127.0.0.1:8000
    python server.py --port 8080
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import secrets
import sys
import threading
import traceback
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

# Windows 控制台默认 cp936，直接 print 中文可能崩溃；统一切成 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover - 非 Windows 或不支持重配置时忽略
    pass

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"
DATA_FILE = BASE_DIR / "data" / "users.json"

MAX_BODY_BYTES = 8 * 1024          # 请求体上限，防止超大 payload
PBKDF2_ROUNDS = 120_000            # 口令派生迭代次数
REQUEST_TIMEOUT = 10               # socket 读超时（秒）

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
RESERVED_USERNAMES = {"admin", "root", "administrator", "support", "github"}

# ---------------------------------------------------------------- 异常与响应


class ApiError(Exception):
    """业务异常：携带 HTTP 状态码、机器可读 code 与可选字段级错误。"""

    def __init__(self, status: int, code: str, message: str,
                 errors: Optional[Dict[str, str]] = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.errors = errors or {}


def ok_payload(message: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """统一成功响应结构。"""
    return {"ok": True, "code": "REGISTERED", "message": message, "data": data}


def err_payload(code: str, message: str,
                errors: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """统一失败响应结构；errors 用于前端做字段级高亮。"""
    return {"ok": False, "code": code, "message": message, "errors": errors or {}}


# ---------------------------------------------------------------- 口令处理


def hash_password(password: str) -> str:
    """PBKDF2-HMAC-SHA256 派生，格式：算法$轮数$盐(hex)$摘要(hex)。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """校验口令（注册流程本身用不到，保留以便登录复用）。"""
    try:
        algo, rounds, salt_hex, digest_hex = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


# ---------------------------------------------------------------- 存储层


class UserStore:
    """JSON 文件持久化的用户表；读写加锁，避免多线程并发写坏文件。

    生产环境请替换为真实数据库；接口（taken / add）保持不变即可。
    """

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _read(self) -> list:
        try:
            return json.loads(self.path.read_text(encoding="utf-8") or "[]")
        except (json.JSONDecodeError, OSError):
            # 文件损坏时不要让服务崩溃，退化为空表（并备份原文件）
            backup = self.path.with_suffix(".corrupt.json")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            return []

    def _write(self, rows: list) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def taken(self, field: str, value: str) -> bool:
        """用户名/邮箱查重，大小写不敏感。"""
        target = value.strip().lower()
        with self._lock:
            for row in self._read():
                if str(row.get(field, "")).strip().lower() == target:
                    return True
        return False

    def add(self, username: str, email: str, password: str) -> Dict[str, Any]:
        """写入新用户；返回不含任何口令信息的用户摘要。"""
        with self._lock:
            rows = self._read()
            user = {
                "id": len(rows) + 1,
                "username": username,
                "email": email,
                "password_hash": hash_password(password),   # 只存派生值
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            rows.append(user)
            self._write(rows)
        # 返回给前端的字段白名单：绝不包含 password / password_hash
        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "created_at": user["created_at"],
        }


STORE = UserStore(DATA_FILE)


# ---------------------------------------------------------------- 校验


def _as_text(value: Any) -> str:
    """只接受字符串/数字，其他类型（dict、list、None）一律视为空串。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def validate(payload: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """服务端校验（前端校验只是体验优化，可被绕过，所以这里必须再校验一次）。

    :return: (清洗后的数据, 字段级错误字典)
    """
    errors: Dict[str, str] = {}

    username = _as_text(payload.get("username"))
    email = _as_text(payload.get("email"))
    password = payload.get("password")
    confirm = payload.get("confirm")
    password_text = password if isinstance(password, str) else ""
    confirm_text = confirm if isinstance(confirm, str) else ""

    if not username:
        errors["username"] = "用户名不能为空"
    elif not USERNAME_RE.match(username):
        errors["username"] = "用户名为 3–20 位字母、数字或下划线"
    elif username.lower() in RESERVED_USERNAMES:
        errors["username"] = "该用户名为系统保留，请更换"

    if not email:
        errors["email"] = "邮箱不能为空"
    elif len(email) > 254 or not EMAIL_RE.match(email):
        errors["email"] = "邮箱格式不正确"

    if not password_text:
        errors["password"] = "密码不能为空"
    elif len(password_text) < 8:
        errors["password"] = "密码至少 8 位"
    elif len(password_text) > 128:
        errors["password"] = "密码最长 128 位"
    elif not (any(c.isalpha() for c in password_text) and any(c.isdigit() for c in password_text)):
        errors["password"] = "密码需同时包含字母和数字"

    if confirm is not None and confirm_text != password_text:
        errors["confirm"] = "两次输入的密码不一致"

    clean = {"username": username, "email": email, "password": password_text}
    return clean, errors


# ---------------------------------------------------------------- HTTP 处理


class RegisterHandler(BaseHTTPRequestHandler):
    server_version = "TinyRegister/1.0"
    protocol_version = "HTTP/1.1"
    timeout = REQUEST_TIMEOUT

    # ---------- 底层工具 ----------

    def _send(self, status: int, body: bytes, content_type: str,
              extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")   # 结果不进缓存，避免看到旧响应
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _send_html(self, status: int, text: str) -> None:
        self._send(status, text.encode("utf-8"), "text/html; charset=utf-8")

    def _read_json_body(self) -> Dict[str, Any]:
        """读取并解析 JSON 请求体；任何异常都转成明确的 ApiError。"""
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_MEDIA_TYPE",
                           "请以 application/json 提交数据")

        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            raise ApiError(HTTPStatus.LENGTH_REQUIRED, "LENGTH_REQUIRED",
                           "缺少 Content-Length，或不支持分块传输")
        try:
            length = int(raw_len)
        except ValueError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "BAD_REQUEST", "Content-Length 非法")

        if length <= 0:
            raise ApiError(HTTPStatus.BAD_REQUEST, "EMPTY_BODY", "请求体为空")
        if length > MAX_BODY_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "PAYLOAD_TOO_LARGE",
                           f"请求体超过 {MAX_BODY_BYTES} 字节上限")

        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "INVALID_ENCODING", "请求体不是 UTF-8 文本")
        except json.JSONDecodeError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "INVALID_JSON", "请求体不是合法 JSON")

        if not isinstance(data, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "INVALID_JSON", "JSON 根节点必须是对象")
        return data

    def _handle_api_error(self, exc: ApiError) -> None:
        self._send_json(exc.status, err_payload(exc.code, exc.message, exc.errors))

    # ---------- 路由 ----------

    def do_GET(self) -> None:          # noqa: N802 - 父类约定的方法名
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            if not INDEX_FILE.exists():
                self._send_html(HTTPStatus.NOT_FOUND, "<h1>404</h1><p>index.html 不存在</p>")
                return
            self._send_html(HTTPStatus.OK, INDEX_FILE.read_text(encoding="utf-8"))
        elif path == "/api/register":
            self._send_json(HTTPStatus.METHOD_NOT_ALLOWED,
                            err_payload("METHOD_NOT_ALLOWED", "该接口仅支持 POST"))
        else:
            self._send_html(HTTPStatus.NOT_FOUND, "<h1>404</h1><p>页面不存在</p>")

    def do_POST(self) -> None:         # noqa: N802
        path = urlparse(self.path).path
        if path != "/api/register":
            self._send_json(HTTPStatus.NOT_FOUND, err_payload("NOT_FOUND", "接口不存在"))
            return
        try:
            payload = self._read_json_body()
            clean, errors = validate(payload)
            if errors:
                raise ApiError(HTTPStatus.BAD_REQUEST, "VALIDATION_FAILED",
                               "请检查表单填写", errors)

            if STORE.taken("username", clean["username"]):
                raise ApiError(HTTPStatus.CONFLICT, "USERNAME_TAKEN", "该用户名已被占用",
                               {"username": "换一个试试，例如加上数字后缀"})
            if STORE.taken("email", clean["email"]):
                raise ApiError(HTTPStatus.CONFLICT, "EMAIL_TAKEN", "该邮箱已注册",
                               {"email": "该邮箱已注册，请直接登录或找回密码"})

            user = STORE.add(clean["username"], clean["email"], clean["password"])
            self._send_json(HTTPStatus.CREATED,
                            ok_payload("注册成功，已为你创建账号", user))

        except ApiError as exc:
            self._handle_api_error(exc)
        except Exception:  # noqa: BLE001 - 兜底，避免把堆栈抛给客户端
            traceback.print_exc()
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR,
                            err_payload("INTERNAL_ERROR", "服务器开小差了，请稍后重试"))

    def log_message(self, fmt: str, *args: Any) -> None:
        """精简访问日志：只打方法与路径，不记录请求体（含口令）。"""
        sys.stderr.write("%s - %s %s\n" % (self.address_string(), self.command, self.path))


# ---------------------------------------------------------------- 入口


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="极简注册服务（纯标准库）")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000, help="监听端口，默认 8000")
    args = parser.parse_args(argv)

    try:
        server = ThreadingHTTPServer((args.host, args.port), RegisterHandler)
    except OSError as exc:
        print(f"启动失败：{exc}（端口 {args.port} 可能已被占用，换 --port 试试）")
        return 1

    server.daemon_threads = True
    print(f"注册服务已启动： http://{args.host}:{args.port}")
    print(f"用户数据文件： {DATA_FILE}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止…")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
