#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
deploy_api.py —— 不依赖 git 网络栈的发布方式

背景
----
某些网络环境（校园网 / 公司代理）下，git 的 HTTPS 传输（git-remote-https + libcurl）
无法通过代理建立 CONNECT 隧道，表现为：

    fatal: unable to access 'https://github.com/...': CONNECT tunnel failed, response 502
    fatal: unable to access 'https://github.com/...': Failed to connect ... Could not connect to server

而同一台机器上的 Python（urllib）走同样的代理访问 api.github.com 却完全正常。
本脚本因此改用 GitHub 官方的 Git Data REST API（blobs → tree → commit → ref）
直接把文件写进仓库，全程只用 HTTPS API 通道，不调用 git 的网络功能。

能力
----
1. 收集项目文件（自动排除 .git / .workbuddy / 缓存等）
2. 通过 API 一次性提交为一个 commit（即使仓库为空也能建立首个提交）
3. 开启 GitHub Pages（Deploy from a branch → main / root）
4. 可选轮询构建状态，直到站点可访问

用法
----
    $env:GITHUB_TOKEN = "ghp_xxx"          # Windows PowerShell
    python scripts/deploy_api.py --dry-run # 只列出将要上传的文件
    python scripts/deploy_api.py --wait    # 上传 + 开 Pages + 等上线

仅用 Python 标准库，无第三方依赖。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GITHUB_API = "https://api.github.com"
DEFAULT_OWNER = "eyiming"
DEFAULT_REPO = "eyiming.github.io"
DEFAULT_BRANCH = "main"
HTTP_TIMEOUT = 30

# 不上传的目录 / 文件（这些是本地私有内容或构建产物）
EXCLUDE_DIRS = {".git", ".workbuddy", "__pycache__", ".idea", ".vscode",
                "node_modules", ".pytest_cache", "data"}
EXCLUDE_FILES = {".DS_Store", "Thumbs.db", ".env"}
EXCLUDE_SUFFIX = {".pyc", ".pyo", ".log", ".zip", ".exe"}


class DeployError(Exception):
    """可预期的业务错误，直接以中文提示给用户，不抛堆栈。"""


def ok(msg: str) -> None:
    print(f"[成功] {msg}")


def info(msg: str) -> None:
    print(f"[信息] {msg}")


def warn(msg: str) -> None:
    print(f"[警告] {msg}")


def fail(msg: str) -> None:
    print(f"[错误] {msg}", file=sys.stderr)


# ------------------------------------------------------------------ HTTP

def http_json(method: str, path: str, token: str,
              payload: dict | None = None) -> tuple[int, object]:
    """调用 GitHub REST API，返回 (状态码, 解析后的 JSON 或原文)。"""
    url = GITHUB_API + path
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "resume-deploy-api")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("Authorization", f"Bearer {token}")
    if payload is not None:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT,
                                    context=ssl.create_default_context()) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"message": raw[:400]}
    except Exception as e:                                   # 网络层异常
        return 0, {"message": f"{type(e).__name__}: {e}"}


def explain(status: int, data: object, action: str) -> None:
    """把常见 HTTP 状态码翻译成中文提示。"""
    msg = data.get("message", "") if isinstance(data, dict) else str(data)
    table = {
        401: "令牌无效或已过期（401）。请重新生成 Personal Access Token。",
        403: f"权限不足或被限流（403）：{msg}。请确认令牌勾选了 repo 权限。",
        404: f"资源不存在（404）：{msg}。请确认用户名与仓库名是否正确。",
        422: f"参数被拒绝（422）：{msg}。",
    }
    if status == 0:
        raise DeployError(f"{action}失败：网络不可达 —— {msg}")
    if status in table:
        raise DeployError(f"{action}失败。{table[status]}")
    if status >= 400:
        raise DeployError(f"{action}失败：HTTP {status} —— {msg}")


def api_ok(status: int, data: object, action: str, expect: set[int]) -> dict:
    if status not in expect:
        explain(status, data, action)
    assert isinstance(data, dict)
    return data


# ------------------------------------------------------------------ 文件收集

def collect_files(root: Path) -> list[tuple[str, bytes]]:
    """收集待上传文件，返回 [(仓库内相对路径, 字节内容), ...]。"""
    if not root.is_dir():
        raise DeployError(f"项目目录不存在：{root}")

    result: list[tuple[str, bytes]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        parts = rel.parts
        if any(p in EXCLUDE_DIRS for p in parts):
            continue
        if rel.name in EXCLUDE_FILES:
            continue
        if path.suffix.lower() in EXCLUDE_SUFFIX:
            continue
        try:
            content = path.read_bytes()
        except OSError as e:
            warn(f"跳过无法读取的文件 {rel}：{e}")
            continue
        result.append((rel.as_posix(), content))

    if not result:
        raise DeployError(f"目录中没有可上传的文件：{root}")
    return result


# ------------------------------------------------------------------ Git Data API

def _bootstrap_empty_repo(owner: str, repo: str, token: str, branch: str,
                          rel: str, content: bytes, message: str) -> str:
    """
    空仓库无法直接创建 blob（GitHub 会返回 409 "Git Repository is empty"），
    必须先用 Contents API 落地第一个文件，仓库才会真正初始化出默认分支。
    返回该初始化提交的 sha。
    """
    payload = {
        "message": message,
        "content": base64.b64encode(content).decode("ascii"),
        "branch": branch,
    }
    path = "/".join(urllib.parse.quote(p, safe="") for p in rel.split("/"))
    st, data = http_json("PUT", f"/repos/{owner}/{repo}/contents/{path}", token, payload)
    api_ok(st, data, f"初始化文件 {rel}", {201})
    sha = ""
    if isinstance(data, dict):
        commit = data.get("commit") or {}
        sha = commit.get("sha", "")
    ok(f"空仓库已初始化（首个文件 {rel}，commit {sha[:7]}）")
    return sha


def upload_commit(owner: str, repo: str, token: str, branch: str,
                  files: list[tuple[str, bytes]], message: str,
                  dry_run: bool) -> str:
    """用 blobs → tree → commit → ref 四步把文件提交为一个 commit。"""
    total = sum(len(c) for _, c in files)
    info(f"待上传 {len(files)} 个文件，共 {total / 1024:.1f} KB")
    if dry_run:
        for rel, content in files:
            print(f"    (dry-run) {rel}  {len(content)} bytes")
        return "(dry-run)"

    pending = list(files)

    # 判断分支是否已存在；不存在说明仓库为空，需要先初始化
    parents: list[str] = []
    st, ref_data = http_json("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}", token)
    if st == 200 and isinstance(ref_data, dict):
        parents = [ref_data["object"]["sha"]]
    else:
        first_rel, first_content = pending.pop(0)
        _bootstrap_empty_repo(owner, repo, token, branch,
                              first_rel, first_content, message)
        st2, ref2 = http_json("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}", token)
        if st2 == 200 and isinstance(ref2, dict):
            parents = [ref2["object"]["sha"]]
        else:
            explain(st2, ref2, "读取初始化后的分支")

    if not pending:
        ok("全部文件已提交")
        return parents[0] if parents else ""

    # 1) 为每个文件创建 blob
    tree_items = []
    for rel, content in pending:
        b64 = base64.b64encode(content).decode("ascii")
        st, data = http_json("POST", f"/repos/{owner}/{repo}/git/blobs", token,
                             {"content": b64, "encoding": "base64"})
        blob = api_ok(st, data, f"创建 blob {rel}", {201})
        tree_items.append({"path": rel, "mode": "100644",
                           "type": "blob", "sha": blob["sha"]})
    ok(f"已创建 {len(tree_items)} 个 blob")

    # 2) 创建 tree（路径中的目录会自动创建）
    st, data = http_json("POST", f"/repos/{owner}/{repo}/git/trees", token,
                         {"tree": tree_items})
    tree = api_ok(st, data, "创建 tree", {201})
    ok("已创建 tree")

    # 3) 创建 commit，挂到当前分支尖端
    st, data = http_json("POST", f"/repos/{owner}/{repo}/git/commits", token,
                         {"message": message, "tree": tree["sha"], "parents": parents})
    commit = api_ok(st, data, "创建 commit", {201})
    ok(f"已创建 commit {commit['sha'][:7]}：{message}")

    # 4) 让分支指向新提交（此时分支必然已存在）
    st, data = http_json("PATCH", f"/repos/{owner}/{repo}/git/refs/heads/{branch}",
                         token, {"sha": commit["sha"]})
    api_ok(st, data, f"更新 {branch} 分支", {200})
    ok(f"已将 {branch} 指向最新提交")
    return commit["sha"]


def enable_pages(owner: str, repo: str, token: str, branch: str) -> str:
    """开启 Pages（Deploy from a branch）。已开启则跳过。"""
    base_url = f"https://{owner}.github.io" if repo.lower() == f"{owner.lower()}.github.io" \
        else f"https://{owner}.github.io/{repo}/"

    st, data = http_json("GET", f"/repos/{owner}/{repo}/pages", token)
    if st == 200:
        info("Pages 已开启，跳过创建")
        return base_url

    st, data = http_json("POST", f"/repos/{owner}/{repo}/pages", token,
                         {"source": {"branch": branch, "path": "/"}})
    api_ok(st, data, "开启 GitHub Pages", {201, 204, 409})
    ok(f"已开启 Pages：source = {branch} / (root)")
    return base_url


def wait_for_pages(owner: str, repo: str, token: str, site_url: str,
                   timeout: int = 240) -> None:
    """轮询 Pages 构建状态，直到 status 为 built。"""
    info("等待 Pages 构建（首次通常需要 30 秒 ~ 3 分钟）…")
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        st, data = http_json("GET", f"/repos/{owner}/{repo}/pages", token)
        if st == 200 and isinstance(data, dict):
            status = data.get("status", "")
            if status != last:
                info(f"    构建状态：{status or '（排队中）'}")
                last = status
            if status == "built":
                ok(f"Pages 已构建完成：{site_url}")
                return
        time.sleep(10)
    warn(f"超过 {timeout} 秒仍未收到 built 状态，请手动访问确认：{site_url}")


def verify_site(url: str) -> bool:
    """从公网请求站点首页，确认真的能打开。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30,
                                    context=ssl.create_default_context()) as resp:
            body = resp.read().decode("utf-8", "replace")
            ok(f"站点可访问：HTTP {resp.status}，{len(body)} 字节")
            return "鄂一铭" in body or "eyiming" in body.lower()
    except urllib.error.HTTPError as e:
        warn(f"站点返回 HTTP {e.code}（首次部署未生效时常见 404）")
        return False
    except Exception as e:
        warn(f"站点暂时无法访问：{type(e).__name__}: {e}")
        return False


# ------------------------------------------------------------------ 入口

def resolve_token(cli_token: str | None) -> str:
    token = cli_token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise DeployError(
            "未找到 GitHub Token。请设置环境变量后重试：\n"
            '    $env:GITHUB_TOKEN = "ghp_xxx"      (PowerShell)\n'
            "    export GITHUB_TOKEN=ghp_xxx        (bash)"
        )
    return token.strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="deploy_api.py",
        description="通过 GitHub API 提交文件并开启 Pages（不依赖 git 网络栈）",
    )
    parser.add_argument("--dir", type=Path,
                        default=Path(__file__).resolve().parent.parent,
                        help="项目根目录，默认为本脚本的上级目录")
    parser.add_argument("--owner", default=DEFAULT_OWNER, help="GitHub 用户名")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="仓库名")
    parser.add_argument("--branch", default=DEFAULT_BRANCH, help="分支名")
    parser.add_argument("--message", default="feat: 初始化在线简历站点（API 提交）",
                        help="提交信息")
    parser.add_argument("--token", default=None, help="GitHub Token，建议用环境变量")
    parser.add_argument("--no-pages", action="store_true", help="只提交，不开 Pages")
    parser.add_argument("--wait", action="store_true", help="等待 Pages 构建完成")
    parser.add_argument("--dry-run", action="store_true", help="只列出文件，不实际上传")
    args = parser.parse_args()

    try:
        root: Path = args.dir
        token = "<dry-run>" if args.dry_run else resolve_token(args.token)

        files = collect_files(root)
        if not args.dry_run:
            # 确认目标仓库可达
            st, data = http_json("GET", f"/repos/{args.owner}/{args.repo}", token)
            if st == 200:
                info(f"目标仓库：{args.owner}/{args.repo}（已存在）")
            elif st == 404:
                st2, d2 = http_json("POST", "/user/repos", token, {
                    "name": args.repo,
                    "description": "鄂一铭 的在线简历 · 大数据管理与应用方向",
                    "private": False,
                    "auto_init": False,
                })
                api_ok(st2, d2, "创建远端仓库", {201})
                ok(f"已创建仓库：{d2.get('html_url')}")
            else:
                explain(st, data, "访问目标仓库")

        upload_commit(args.owner, args.repo, token, args.branch,
                      files, args.message, args.dry_run)

        if args.dry_run:
            ok("dry-run 结束，未做任何修改")
            return 0

        repo_url = f"https://github.com/{args.owner}/{args.repo}"
        ok(f"仓库地址：{repo_url}")

        if not args.no_pages:
            site_url = enable_pages(args.owner, args.repo, token, args.branch)
            if args.wait:
                wait_for_pages(args.owner, args.repo, token, site_url)
                verify_site(site_url)
            info(f"访问地址：{site_url}")

        return 0

    except DeployError as e:
        fail(str(e))
        return 1
    except KeyboardInterrupt:
        fail("已取消")
        return 130


if __name__ == "__main__":
    sys.exit(main())
