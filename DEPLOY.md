# 🚀 发布上手指引

> 本文件提供完整操作序列，按顺序执行即可把简历仓库推送到 GitHub 并发布成在线网页。

> ✅ **当前状态（2026-10-11 更新）**
> - `eyiming` GitHub 账号**已注册**（创建时间 2026-10-10 22:51 CST）
> - 本地 **Git 已安装**（MinGit 2.55.0.windows.5，位于 `%LOCALAPPDATA%\Programs\Git`）
> - ❌ `eyiming.github.io` 仓库**尚未创建**，因此 `https://eyiming.github.io/` 目前还不能访问
> - 下一步：创建仓库 → 推送 → 开启 Pages
>
> 连带结果：Pages 站点将是 `https://eyiming.github.io`（DNS 已指向 GitHub Pages 官方段 185.199.108~111.153）

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

> 💡 **更快的方式**：仓库内已自带一键脚本，可自动完成第 4–6 步：
> ```bash
> python scripts/publish.py check           # 先体检
> python scripts/publish.py all --wait      # 建仓 + 推送 + 开 Pages
> ```
> 仅依赖 Python 标准库。想看清每一步再决定，就按下面手动执行。

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
