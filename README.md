# 📄 eyiming.github.io

> 鄂一铭 的在线简历 · 大数据管理与应用方向 · GitHub Pages 站点仓库

[![Website](https://img.shields.io/badge/在线简历-eyiming.github.io-4f46e5?style=flat-square)](https://eyiming.github.io)
[![Source](https://img.shields.io/badge/简历源文件-Markdown-0969da?style=flat-square)](./RESUME.md)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](./LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/eyiming/eyiming.github.io?style=flat-square)](https://github.com/eyiming/eyiming.github.io/commits)

---

## 🌐 在线访问

**https://eyiming.github.io**

> 仓库之所以命名为 `eyiming.github.io`（与用户名完全一致），正是为了让 GitHub Pages 直接把站点发布到**根域名**，
> 而不是 `https://eyiming.github.io/<仓库名>/` 这样的子路径。

---

## 📌 仓库简介

一个仓库同时承担两件事：

- **网页版简历** — `index.html`，纯静态单文件，无外部依赖，Pages 直接托管
- **简历源文件** — `RESUME.md`，Markdown 单一事实来源，便于版本管理与 ATS 解析

这样设计的好处：

- 🔍 **招聘系统友好** — Markdown 纯文本可被绝大多数 ATS（简历解析系统）稳定读取
- 🕓 **完整变更历史** — 每次投递迭代都留有 commit 记录，可随时回溯版本
- 📱 **一处修改，全网生效** — 改完推送，线上页面几分钟内自动更新
- 🖨 **随时打印** — 网页版内置打印样式，浏览器 `Ctrl + P` 即可获得排版干净的纸质/PDF 版本

---

## 📂 文件结构

```
eyiming.github.io/
├── index.html         # 网页版简历（Pages 首页，单文件、零依赖）
├── RESUME.md          # 简历正文（Markdown，内容单一来源）
├── scripts/
│   └── publish.py     # 一键发布脚本（体检 / 提交 / 推送 / 开启 Pages）
├── README.md          # 本文件：仓库说明与维护规范
├── DEPLOY.md          # 首次发布到 GitHub 的完整操作指引
└── LICENSE            # 开源许可（MIT）
```

---

## 👤 简历摘要

| 项目 | 内容 |
| :--- | :--- |
| 姓名 | 鄂一铭 |
| 性别 | 男 |
| 学历 | 本科（在读，2023 级） |
| 院校专业 | 大连财经学院 · 管理学院 · 大数据管理与应用 |
| 求职方向 | 数据分析 / 数据运营 / 商业分析 |
| 技术栈 | Python、SQL、MySQL、pandas、Tableau / Power BI、Spark（了解） |
| 联系方式 | 942873406@qq.com |

> 完整内容：网页版 👉 https://eyiming.github.io ｜ 源文件 👉 [`RESUME.md`](./RESUME.md)

---

## 🚀 快速开始

### 本地预览网页版

```bash
git clone https://github.com/eyiming/eyiming.github.io.git
cd eyiming.github.io

# 直接双击 index.html，或起一个本地服务
python -m http.server 8000     # 然后访问 http://localhost:8000
```

### 修改简历内容

1. 编辑 `RESUME.md`（Markdown，改内容）
2. 同步编辑 `index.html`（网页版，改显示）
3. 提交推送，Pages 自动更新

### 开启 GitHub Pages

推送完成后只需一次配置：

仓库 **Settings → Pages → Build and deployment**

| 配置项 | 值 |
| :--- | :--- |
| Source | `Deploy from a branch` |
| Branch | `main` / `/ (root)` |

保存后约 1–3 分钟生效，访问 **https://eyiming.github.io** 即可看到网页版简历。

### 首次发布到 GitHub

**方式一：一键脚本（推荐）**

```bash
python scripts/publish.py check                  # 环境体检，不改动任何文件
python scripts/publish.py publish --dry-run      # 预演，只看命令不执行
python scripts/publish.py all --wait             # 体检 → 提交 → 推送 → 开 Pages 并等待上线
```

脚本仅依赖 Python 标准库，会自动创建远端仓库、配置 origin、推送并开启 Pages。
凭据用 SSH 公钥，或设置环境变量 `GITHUB_TOKEN`（脚本不会把 token 写入 `.git/config`）。

**方式二：手动执行**

完整步骤见 👉 [`DEPLOY.md`](./DEPLOY.md)（账号注册 → Git 安装 → SSH/Token 配置 → 建仓 → 推送 → 开启 Pages）。

---

## ✍️ 维护规范

1. **单一事实来源** — 所有简历内容只在此仓库维护；`RESUME.md` 与 `index.html` 需保持同步。
2. **占位符约定** — 未确定的信息在 `RESUME.md` 中写作 `【待补充：…】`、在 `index.html` 中带 `class="todo"` 黄色高亮；**对外分享前必须清空**。
3. **隐私红线** — 公开仓库中**不出现**手机号、身份证号、家庭住址、微信/QQ 号等敏感信息；对外联系仅保留邮箱与 GitHub。
4. **内容取舍** — 本简历不收录竞赛获奖与奖学金条目，重点呈现**项目经历与实践经历**。
5. **提交信息** — 采用约定式提交，例如 `feat(resume): 新增 Spark 日志分析项目`、`fix(resume): 修正实习时间区间`。
6. **版本号** — 每次结构性调整后递增 `RESUME.md` 末尾的文件版本。
7. **删除草稿提示** — 内容补齐后，删除 `index.html` 中的 `.draft-notice` 整块（文件内已用注释标明范围）。

---

## 📮 联系方式

- 📧 Email：942873406@qq.com
- 🐙 GitHub：https://github.com/eyiming
- 🌐 在线简历：https://eyiming.github.io

---

## 📄 许可

简历文本内容版权归作者所有，转载请注明出处；站点结构与样式部分遵循 [MIT License](./LICENSE)。

---

<sub>最后更新：2026-10-10</sub>
