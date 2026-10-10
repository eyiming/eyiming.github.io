#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish.py —— 简历站点一键发布工具

把「仓库初始化 → 提交 → 建远端仓库 → 推送 → 开启 GitHub Pages」整条链路
封装成本地可运行的脚本，仅依赖 Python 标准库（3.9+），无需 pip 安装任何包。

用法示例：
    python scripts/publish.py check                 # 只做环境体检，不改任何东西
    python scripts/publish.py publish --dry-run     # 预演，打印将执行的命令
    python scripts/publish.py all                   # 体检 + 初始化 + 提交 + 推送 + 开 Pages

凭据：
    SSH   —— 推荐。脚本检测到 ~/.ssh 下有公钥时默认走 SSH，token 非必需。
    HTTPS —— 设置环境变量 GITHUB_TOKEN（或 GH_TOKEN）。
             脚本通过 `git -c http.extraHeader=...` 传递，不会把 token 写进 .git/config。

退出码： 0 成功 / 1 运行出错 / 2 环境体检未通过
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------- 常量配置

GITHUB_API = "https://api.github.com"
DEFAULT_REPO = "eyiming.github.io"           # 仓库名与用户名一致 → Pages 发布到根域名
DEFAULT_BRANCH = "main"
DEFAULT_DESC = "鄂一铭 的在线简历 · 大数据管理与应用方向"
DEFAULT_COMMIT = "feat: 初始化在线简历站点（index.html + RESUME.md + README）"
REQUIRED_FILES = ("index.html", "RESUME.md", "README.md")   # 缺任一则拒绝提交
HTTP_TIMEOUT = 20
PAGES_POLL_INTERVAL = 10                     # Pages 构建状态轮询间隔（秒）
PAGES_POLL_TIMEOUT = 180                     # 最长等待时间（秒）

# git 不在 PATH 时的回退探测路径（便携版 / 用户级安装常见位置）
CANDIDATE_GIT_PATHS = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "cmd" / "git.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "bin" / "git.exe",
    Path(r"C:\Program Files\Git\cmd\git.exe"),
    Path(r"C:\Program Files\Git\bin\git.exe"),
    Path(r"C:\Program Files (x86)\Git\cmd\git.exe"),
)

_GIT_EXE: str | None = None                  # 解析结果缓存，避免重复探测


class PublishError(Exception):
    """可预期的业务错误：直接打印原因并以非 0 退出，不抛堆栈。"""


# ---------------------------------------------------------------- 基础工具

def setup_io() -> None:
    """Windows 控制台默认 cp936，输出中文/特殊符号会崩，统一改成 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def info(msg: str) -> None:
    print(f"[信息] {msg}")


def ok(msg: str) -> None:
    print(f"[成功] {msg}")


def warn(msg: str) -> None:
    print(f"[警告] {msg}")


def fail(msg: str) -> None:
    print(f"[错误] {msg}", file=sys.stderr)


def find_git() -> str:
    """
    定位 git 可执行文件。

    先在 PATH 中查找；找不到再依次探测常见安装位置——某些终端（如沙箱、
    未重启的旧会话）的 PATH 是快照，读不到新写入的注册表值，回退能保证可用。
    """
    global _GIT_EXE
    if _GIT_EXE:
        return _GIT_EXE

    found = shutil.which("git")
    if not found:
        for cand in CANDIDATE_GIT_PATHS:
            try:
                if cand and Path(cand).is_file():
                    found = str(cand)
                    warn(f"git 不在当前 PATH 中，回退使用：{found}")
                    break
            except OSError:
                continue

    if not found:
        raise PublishError(
            "未检测到 git。请先安装：https://git-scm.com/download/win "
            "（安装时保持默认选项，会自动加入 PATH），安装后重启终端再运行本脚本。"
        )

    _GIT_EXE = found
    return found


def _probe_git() -> bool:
    """静默探测 git 是否可用（不抛异常、不打印）。"""
    try:
        find_git()
        return True
    except PublishError:
        return False


def run_git(args: list[str], cwd: Path, dry_run: bool = False,
            extra_config: list[str] | None = None) -> str:
    """执行 git 命令。dry_run 模式下只打印不执行。"""
    cmd = [find_git()]
    if extra_config:
        for kv in extra_config:
            cmd += ["-c", kv]
    cmd += args

    printable = " ".join(cmd)
    if dry_run:
        print(f"    (dry-run) {printable}")
        return ""

    proc = subprocess.run(
        cmd, cwd=str(cwd),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise PublishError(f"git 命令失败：{printable}\n        {detail}")
    return (proc.stdout or "").strip()


def http_json(method: str, path: str, token: str | None = None,
              payload: dict | None = None) -> tuple[int, object]:
    """调用 GitHub REST API，返回 (状态码, 解析后的 JSON)。"""
    url = f"{GITHUB_API}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "resume-publish-script")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"message": body}
        return e.code, parsed
    except urllib.error.URLError as e:
        # 网络不通 / 代理拦截，归类为可预期的环境问题
        raise PublishError(f"无法访问 GitHub API（{url}）：{e.reason}")


def api_expect(status: int, data: object, ok_codes: set[int],
               action: str) -> dict:
    """统一处理 API 返回：不在预期状态码内就翻译成人话报错。"""
    if status in ok_codes:
        return data if isinstance(data, dict) else {}

    message = data.get("message", "未知错误") if isinstance(data, dict) else str(data)
    if status == 401:
        raise PublishError(f"{action}失败：token 无效或已过期（401）。请重新生成 Token。")
    if status == 403:
        raise PublishError(
            f"{action}失败：权限不足或触发速率限制（403）：{message}。"
            "请确认 Token 勾选了 repo 权限。"
        )
    if status == 404:
        raise PublishError(f"{action}失败：资源不存在（404）：{message}。")
    if status == 422:
        raise PublishError(f"{action}失败：参数被拒绝（422）：{message}。")
    raise PublishError(f"{action}失败：HTTP {status} —— {message}")


def resolve_token(cli_token: str | None) -> str | None:
    """优先用命令行传入，其次读环境变量。"""
    return cli_token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def has_ssh_key() -> bool:
    """
    判断本机是否已有 SSH 公钥（决定默认传输协议）。

    ~/.ssh 不可读/不存在时安全返回 False，不抛异常。
    """
    try:
        ssh_dir = Path.home() / ".ssh"
        if not ssh_dir.is_dir():
            return False
        return any(ssh_dir.glob("*.pub"))
    except OSError:
        return False


# ---------------------------------------------------------------- 体检

def cmd_check(args: argparse.Namespace) -> int:
    """只做环境体检，不修改任何文件。"""
    root: Path = args.dir
    info(f"项目目录：{root}")

    problems: list[str] = []

    # 1. 目录与必需文件
    if not root.is_dir():
        raise PublishError(f"项目目录不存在：{root}")
    for name in REQUIRED_FILES:
        mark = "✓" if (root / name).is_file() else "✗"
        print(f"    必需文件 {name:<12} {mark}")
        if mark == "✗":
            problems.append(f"缺少必需文件 {name}")

    # 2. git
    try:
        git_path = find_git()
        print(f"    git                         ✓  {git_path}")
    except PublishError as e:
        print("    git                         ✗  未安装")
        problems.append(str(e))

    # 3. 凭据
    token = resolve_token(args.token)
    ssh_ok = has_ssh_key()
    print(f"    SSH 公钥                     {'✓' if ssh_ok else '✗'}")
    print(f"    GitHub Token                {'✓ 已提供（内容不会打印）' if token else '✗ 未提供'}")
    if not token and not ssh_ok:
        problems.append("既无 SSH 公钥也无 Token，无法完成推送")

    # 4. 远端（若已初始化）
    if (root / ".git").is_dir():
        try:
            remote = run_git(["remote", "get-url", "origin"], root)
        except PublishError:
            remote = ""
        print(f"    远端 origin                 {remote or '（尚未配置）'}")
    else:
        print("    远端 origin                 （尚未 git init）")

    # 5. 占位符（提醒，不算硬错误）
    try:
        todo = (root / "RESUME.md").read_text(encoding="utf-8").count("【待补充")
        if todo:
            warn(f"RESUME.md 仍有 {todo} 处【待补充】占位符，对外分享前请清空")
    except OSError:
        pass

    if problems:
        print()
        for p in problems:
            fail(p)
        return 2

    ok("环境体检通过")
    return 0


# ---------------------------------------------------------------- 初始化与提交

def ensure_repo_dir(root: Path) -> None:
    if not root.is_dir():
        raise PublishError(f"项目目录不存在：{root}")


def git_init(root: Path, branch: str, dry_run: bool) -> None:
    """初始化仓库并把默认分支设为 main。"""
    if (root / ".git").is_dir():
        info("已存在 .git，跳过 git init")
        return
    run_git(["init", "-b", branch], root, dry_run)
    ok(f"已初始化仓库（默认分支 {branch}）")


def set_identity(root: Path, name: str, email: str, dry_run: bool) -> None:
    """写入仓库级 user.name / user.email，避免污染全局配置。"""
    run_git(["config", "user.name", name], root, dry_run)
    run_git(["config", "user.email", email], root, dry_run)
    ok(f"已设置提交身份：{name} <{email}>")


def commit_all(root: Path, message: str, dry_run: bool) -> bool:
    """暂存并提交；没有改动时返回 False 表示跳过。"""
    missing = [n for n in REQUIRED_FILES if not (root / n).is_file()]
    if missing:
        raise PublishError(f"缺少必需文件，拒绝提交：{', '.join(missing)}")

    run_git(["add", "-A"], root, dry_run)

    if dry_run:
        print("    (dry-run) git commit ...")
        return True

    status = run_git(["status", "--porcelain"], root)
    if not status:
        info("工作区干净，无需提交")
        return False

    run_git(["commit", "-m", message], root)
    ok("已创建提交")
    return True


# ---------------------------------------------------------------- 远端仓库与推送

def get_owner(token: str) -> str:
    """用 token 反查用户名，避免手写 owner 出错。"""
    status, data = http_json("GET", "/user", token)
    info_api = api_expect(status, data, {200}, "读取账号信息")
    login = info_api.get("login")
    if not login:
        raise PublishError("未能从 token 解析出用户名")
    return login


def ensure_remote_repo(owner: str, repo: str, token: str,
                       private: bool, dry_run: bool) -> tuple[bool, str]:
    """仓库不存在则创建。返回 (是否新建, html_url)。"""
    status, data = http_json("GET", f"/repos/{owner}/{repo}", token)

    if status == 200 and isinstance(data, dict) and data.get("html_url"):
        info(f"远端仓库已存在：{data['html_url']}")
        return False, data["html_url"]

    if status != 404:
        api_expect(status, data, {200}, "查询远端仓库")

    if dry_run:
        print(f"    (dry-run) POST /user/repos  name={repo} private={private}")
        return True, f"https://github.com/{owner}/{repo}"

    status, data = http_json("POST", "/user/repos", token, {
        "name": repo,
        "description": DEFAULT_DESC,
        "private": private,
        "auto_init": False,        # 本地已有文件，绝不能让 GitHub 生成 README/LICENSE
        "has_issues": False,
        "has_wiki": False,
        "has_projects": False,
    })
    created = api_expect(status, data, {201}, "创建远端仓库")
    ok(f"已创建远端仓库：{created.get('html_url')}")
    return True, created.get("html_url", f"https://github.com/{owner}/{repo}")


def set_remote(root: Path, owner: str, repo: str, use_ssh: bool, dry_run: bool) -> str:
    """配置 origin；已存在则复用。"""
    target = f"git@github.com:{owner}/{repo}.git" if use_ssh \
        else f"https://github.com/{owner}/{repo}.git"

    # 注意：这里必须判断「能否定位到 git」，而不是 shutil.which("git")。
    # 沙箱/旧终端的 PATH 是快照，git 可能已装但不在 PATH 中，此时 which 为 None
    # 会让下面的复用分支被整体跳过，进而误执行 remote add 导致 "origin already exists"。
    if (root / ".git").is_dir() and _probe_git():
        try:
            current = run_git(["remote", "get-url", "origin"], root)
        except PublishError:
            current = ""
        if current and current.strip() == target:
            info(f"origin 已正确配置：{current}")
            return target
        if current:
            warn(f"origin 当前为 {current}，将覆盖为 {target}")
            run_git(["remote", "set-url", "origin", target], root, dry_run)
            return target

    run_git(["remote", "add", "origin", target], root, dry_run)
    ok(f"已配置 origin：{target}")
    return target


def _auth_extra(token: str | None) -> list[str] | None:
    """
    构造 git over HTTPS 的认证头。

    用 Basic(base64(token:x-oauth-basic)) 而非 Bearer：git 的 HTTPS 传输走的是
    git-remote-https（libcurl），GitHub 在该通道上不接受 Bearer，会直接回
    "remote: invalid credentials"。Basic 是官方推荐写法。
    """
    if not token:
        return None
    basic = base64.b64encode(f"{token}:x-oauth-basic".encode("utf-8")).decode("ascii")
    return [f"http.extraHeader=Authorization: Basic {basic}"]


def push(root: Path, branch: str, token: str | None, dry_run: bool) -> None:
    """
    推送到 origin。凭据只通过 -c 传给单次命令，不写入 .git/config。

    首次用默认 TLS 后端（OpenSSL）尝试；失败则回退 Windows 原生 schannel 后端重试一次。
    回退原因：Git for Windows 的 OpenSSL 后端在某些代理环境下做 CONNECT 会被网关
    返回 502（实测 "CONNECT tunnel failed, response 502"），而 schannel 后端可正常握手。
    """
    extra = _auth_extra(token)

    try:
        run_git(["push", "-u", "origin", branch], root, dry_run, extra_config=extra)
    except PublishError as first_err:
        if extra is None or not _looks_like_transport_error(first_err):
            raise
        warn("默认 TLS 后端推送失败，改用 Windows schannel 后端重试一次")
        run_git(["push", "-u", "origin", branch], root, dry_run,
                extra_config=extra + ["http.sslBackend=schannel"])

    ok(f"已推送到 origin/{branch}")


def _looks_like_transport_error(err: Exception) -> bool:
    """判断是否为传输层/代理层错误（这类错误值得换 TLS 后端重试）。"""
    text = str(err)
    keys = ("CONNECT tunnel failed", "Empty reply from server",
            "Failed to connect", "OpenSSL", "SSL connect error",
            "aborted session", "could not connect", "Failed to connect")
    return any(k.lower() in text.lower() for k in keys)


# ---------------------------------------------------------------- GitHub Pages

def enable_pages(owner: str, repo: str, token: str, branch: str,
                 dry_run: bool, wait: bool) -> None:
    """开启 Pages；已开启则跳过。随后可选轮询构建状态。"""
    url = f"https://{owner}.github.io" if repo.lower() == f"{owner.lower()}.github.io" \
        else f"https://{owner}.github.io/{repo}/"

    status, data = http_json("GET", f"/repos/{owner}/{repo}/pages", token)
    if status == 200:
        info("Pages 已开启，跳过创建")
    elif status == 404:
        if dry_run:
            print(f"    (dry-run) POST /repos/{owner}/{repo}/pages  source={branch}/")
        else:
            status, data = http_json("POST", f"/repos/{owner}/{repo}/pages", token, {
                "source": {"branch": branch, "path": "/"}
            })
            api_expect(status, data, {201, 204}, "开启 Pages")
            ok("已开启 GitHub Pages")
    else:
        api_expect(status, data, {200}, "查询 Pages 状态")

    ok(f"访问地址：{url}")

    if not wait or dry_run:
        info("提示：首次发布需 1–3 分钟生效，可用 --wait 让脚本轮询等待")
        return

    # 轮询最新一次构建，直到 status 变为 built（或超时）
    deadline = time.time() + PAGES_POLL_TIMEOUT
    info("等待 Pages 构建完成…")
    while time.time() < deadline:
        s, d = http_json("GET", f"/repos/{owner}/{repo}/pages/builds/latest", token)
        if s == 200 and isinstance(d, dict):
            state = d.get("status")
            if state == "built":
                ok("Pages 构建完成，站点已上线")
                return
            info(f"  当前状态：{state}")
        elif s == 404:
            info("  尚未产生构建记录，继续等待")
        time.sleep(PAGES_POLL_INTERVAL)

    warn(f"超过 {PAGES_POLL_TIMEOUT} 秒仍未完成，请稍后手动访问确认：{url}")


# ---------------------------------------------------------------- 组合命令

def cmd_publish(args: argparse.Namespace) -> int:
    root: Path = args.dir
    ensure_repo_dir(root)

    # dry-run 允许在无 git 环境下预演，仅提示；实际执行必须要有 git
    if args.dry_run:
        if not shutil.which("git"):
            warn("dry-run：本机未安装 git，实际执行时会在此步失败")
    else:
        find_git()

    token = resolve_token(args.token)
    use_ssh = args.ssh or (not token and has_ssh_key())

    owner = args.owner
    if owner is None:
        if token:
            owner = get_owner(token)
        elif args.dry_run:
            # 预演时使用占位符，保证无凭据也能完整看到命令序列
            owner = "<owner>"
            warn("dry-run：未指定 --owner 且无 token，用 <owner> 占位预演")
        else:
            raise PublishError("未指定 --owner 且没有 token，无法推断仓库归属。"
                               "请加 --owner eyiming，或设置 GITHUB_TOKEN。")
    info(f"目标仓库：{owner}/{args.repo}")

    git_init(root, args.branch, args.dry_run)
    set_identity(root, args.user_name, args.user_email, args.dry_run)
    commit_all(root, args.message, args.dry_run)

    if token:
        ensure_remote_repo(owner, args.repo, token, args.private, args.dry_run)
    else:
        warn("未提供 token，跳过自动建仓；请确保远端仓库已存在")

    set_remote(root, owner, args.repo, use_ssh, args.dry_run)
    push(root, args.branch, token, args.dry_run)

    if args.dry_run:
        info("dry-run 结束，未做任何实际改动")
    return 0


def cmd_pages(args: argparse.Namespace) -> int:
    token = resolve_token(args.token)
    if not token:
        raise PublishError("开启 Pages 需要 token，请设置 GITHUB_TOKEN 环境变量。")

    owner = args.owner or get_owner(token)
    enable_pages(owner, args.repo, token, args.branch, args.dry_run, args.wait)
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    rc = cmd_check(args)
    if rc != 0:
        return rc
    rc = cmd_publish(args)
    if rc != 0:
        return rc
    return cmd_pages(args)


# ---------------------------------------------------------------- CLI

def add_common_options(parser: argparse.ArgumentParser, suppress: bool = False) -> None:
    """
    注册公共参数。

    suppress=True 时所有默认值设为 argparse.SUPPRESS：用于子命令，
    这样「参数写在子命令后面」也能生效，同时不会覆盖主命令已解析出的值。
    """
    def d(value):
        return argparse.SUPPRESS if suppress else value

    parser.add_argument("--dir", type=Path, default=d(Path(__file__).resolve().parent.parent),
                        help="项目根目录，默认为本脚本的上级目录")
    parser.add_argument("--repo", default=d(DEFAULT_REPO), help=f"仓库名，默认 {DEFAULT_REPO}")
    parser.add_argument("--branch", default=d(DEFAULT_BRANCH), help="分支名，默认 main")
    parser.add_argument("--owner", default=d(None), help="GitHub 用户名，缺省时用 token 反查")
    parser.add_argument("--token", default=d(None), help="GitHub Token，建议改用环境变量")
    parser.add_argument("--user-name", default=d("eyiming"), help="git user.name")
    parser.add_argument("--user-email", default=d("942873406@qq.com"), help="git user.email")
    parser.add_argument("--message", default=d(DEFAULT_COMMIT), help="提交信息")
    parser.add_argument("--ssh", action="store_true", default=d(False), help="强制使用 SSH 传输")
    parser.add_argument("--private", action="store_true", default=d(False),
                        help="建为私有仓库（Pages 需付费版）")
    parser.add_argument("--wait", action="store_true", default=d(False),
                        help="开启 Pages 后轮询等待构建完成")
    parser.add_argument("--dry-run", action="store_true", default=d(False),
                        help="只打印将执行的命令，不实际执行")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="publish.py",
        description="简历站点一键发布工具（体检 / 提交 / 推送 / 开启 Pages）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python scripts/publish.py check\n"
            "  python scripts/publish.py publish --dry-run\n"
            "  python scripts/publish.py all --wait\n"
        ),
    )
    add_common_options(parser, suppress=False)

    sub = parser.add_subparsers(dest="command", required=True)
    # 子命令同样注册公共参数（SUPPRESS），使 `publish --dry-run` 这种写法可用
    for name, help_text, func in (
        ("check", "环境体检，不修改任何文件", cmd_check),
        ("publish", "初始化、提交并推送", cmd_publish),
        ("pages", "开启 GitHub Pages", cmd_pages),
        ("all", "依次执行 check → publish → pages", cmd_all),
    ):
        p = sub.add_parser(name, help=help_text)
        add_common_options(p, suppress=True)
        p.set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_io()
    args = build_parser().parse_args(argv)

    # dry-run 时把待执行目录一并打印，便于确认作用范围
    if args.dry_run:
        warn(f"dry-run 模式：不会做任何实际改动（作用目录 {args.dir}）")

    try:
        return args.func(args)
    except PublishError as e:
        fail(str(e))
        return 1
    except KeyboardInterrupt:
        warn("已中断")
        return 1
    except Exception as e:                       # 兜底：未预期异常也给可读提示
        fail(f"未预期的错误：{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
