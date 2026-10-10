# 🚀 发布上手指引

> 本文件提供完整操作序列，按顺序执行即可把简历仓库推送到 GitHub 并发布成在线网页。

> ✅ **当前状态（2026-10-11 更新：已上线）**
> - `eyiming` GitHub 账号**已注册**（创建时间 2026-10-10 22:51 CST）
> - 本地 **Git 已安装**（MinGit 2.55.0.windows.5，位于 `%LOCALAPPDATA%\Programs\Git`）
> - ✅ 仓库 `https://github.com/eyiming/eyiming.github.io` **已创建并已提交**
> - ✅ GitHub Pages **已开启并构建完成**
> - 🌐 **在线地址：https://eyiming.github.io**
>
> 后续更新内容只需重跑「第 5 步 B 方案」的 `deploy_api.py`，或直接 `git push`。
>
> ⚠️ 部署用的 Personal Access Token **用完请立即删除**：
> https://github.com/settings/tokens → 找到 `resume-deploy` → Delete

---

## 第 0 步（推荐）：代理网络下的发布方式 —— `deploy_api.py`

**如果你所在网络（校园网 / 公司代理）下 `git push` 报下面这类错误，请直接用本方案：**

```
fatal: unable to access 'https://github.com/...': CONNECT tunnel failed, response 502
fatal: unable to access 'https://github.com/...': Failed to connect ... Could not connect to server
```

原因是 git 的 HTTPS 传输（git-remote-https + libcurl）无法通过代理建立 CONNECT 隧道，
而 Python 走同一套代理访问 `api.github.com` 却正常。本方案因此改用 GitHub 官方
**Git Data REST API**（blobs → tree → commit → ref）提交文件，全程不调用 git 的网络功能。

```powershell
$env:GITHUB_TOKEN = "ghp_xxx"                       # 只选 repo 权限
python scripts/deploy_api.py --dry-run              # 先看将要上传哪些文件
python scripts/deploy_api.py --wait                 # 上传 + 开 Pages + 等构建完成
```

要点：

- 自动排除 `.git` / `.workbuddy` / `__pycache__` 等目录，不会把本地私有笔记传上去
- 仓库为空时会先用 Contents API 落地第一个文件完成初始化，再批量提交（GitHub 不允许对空仓库直接建 blob，会返回 409）
- 全部文件合并为**一个 commit**，提交历史干净
- 幂等：重复执行会把最新内容提交到 `main`，不会重复创建分支

---

## 第 1 步：注册 GitHub 账号（用户名 `eyiming`）

**此步已完成**（2026-10-10 22:51）。若你尚未完成，请打开 https://github.com/signup 用用户名 `eyiming` 注册。

> ⚠️ **安全提醒**：只认 `https://github.com` 与 `https://eyiming.github.io`。
> 任何在 `github.io` 后面多出字符的域名（例如 `xn--io-223a` 这类 punycode 尾巴）都是仿冒，一律不要访问。

## 第 2 步：确认 Git 可用

本机已安装 MinGit 2.55.0.windows.5（在 `%LOCALAPPDATA%\Programs\Git`），理论上已加入用户 PATH。若终端里 `git` 找不到，用完整路径：

```powershell
C:\Users\鄂一铭\AppData\Local\Programs\Git\cmd\git.exe --version
```

未安装时再去 https://git-scm.com/download/win 下载完整版。

## 第 3 步：配置身份与凭据（二选一）

### 方案 A：SSH 密钥（推荐，一次配置长期有效）

```bash
# 生成密钥，一路回车
ssh-keygen -t ed25519 -C "942873406@qq.com"

# 复制公钥内容（输出到终端后全选复制）
cat ~/.ssh/id_ed25519.pub
```

将公钥粘贴到 GitHub → **Settings → SSH and GPG keys → New SSH key**。

测试连通：

```bash
ssh -T git@github.com
```

### 方案 B：Personal Access Token（HTTPS）

1. GitHub → **Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. 生成新 token，勾选 `repo` 权限
3. 推送时用户名填 `eyiming`，密码栏粘贴该 token（**不要填登录密码**）

## 第 4 步：在 GitHub 创建公开仓库

点击 https://github.com/new ，填写：

| 字段 | 值 |
| :--- | :--- |
| Repository name | **`eyiming.github.io`** ⚠️ 必须与用户名完全一致，否则 Pages 地址会带子路径 |
| Description | `鄂一铭 的在线简历 · 大数据管理与应用方向` |
| 可见性 | ✅ **Public（公开）** — Pages 免费版仅对公开仓库生效 |
| 初始化选项 | **全部不勾选**（不要生成 README / .gitignore / LICENSE，本地已有） |

## 第 5 步：本地初始化并推送

> 💡 **更快的方式**：仓库内已自带两个一键脚本，可自动完成第 4–6 步：
> ```bash
> # A 方案（推荐，代理网络首选）：走 GitHub API，不依赖 git 网络栈
> python scripts/deploy_api.py --dry-run
> python scripts/deploy_api.py --wait
>
> # B 方案：走 git push（已内置 Basic 认证 + schannel 回退重试）
> python scripts/publish.py check           # 先体检
> python scripts/publish.py all --wait      # 建仓 + 推送 + 开 Pages
> ```
> 两者都只依赖 Python 标准库。想看清每一步再决定，就按下面手动执行。

在本仓库目录下执行：

```bash
git init
git config user.name  "eyiming"
git config user.email "942873406@qq.com"

git add .
git commit -m "feat: 初始化在线简历站点（index.html + RESUME.md + README）"

git branch -M main
git remote add origin git@github.com:eyiming/eyiming.github.io.git     # SSH 方案
# git remote add origin https://github.com/eyiming/eyiming.github.io.git  # HTTPS 方案

git push -u origin main
```

推送成功后访问：https://github.com/eyiming/eyiming.github.io

---

## 第 6 步：开启 GitHub Pages（一次性配置）

仓库 **Settings → Pages → Build and deployment**：

| 配置项 | 值 |
| :--- | :--- |
| Source | `Deploy from a branch` |
| Branch | `main` / `/ (root)` |

保存后等待 1–3 分钟，访问 **https://eyiming.github.io** 即可看到网页版简历。

> 本站点的 `index.html` 是**纯静态单文件、零外部依赖**，不需要 Jekyll、不需要构建步骤，Pages 会原样托管。

---

## ✅ 推送前检查清单

- [ ] `RESUME.md` 中所有 `【待补充：…】` 已替换为真实内容
- [ ] `index.html` 中所有 `class="todo"` 黄色高亮块已补齐
- [ ] `index.html` 中的 `.draft-notice` 草稿提示块已删除（文件内已标注删除范围）
- [ ] 全文搜索确认**不含**手机号、身份证号、家庭住址、微信号
- [ ] 项目经历与实践经历均已填写**量化成果**
- [ ] `RESUME.md` 末尾的「最后更新」日期已同步修改
