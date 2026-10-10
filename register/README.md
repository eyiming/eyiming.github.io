# 注册功能 · 原地渲染结果示例

一个最小可运行的前后端示例：**提交注册表单后，结果直接渲染在当前页面，不跳转、不刷新。**

纯 Python 标准库 + 原生 JS，零依赖、零构建步骤。

## 运行

```bash
cd register
python server.py                 # 默认 http://127.0.0.1:8000
python server.py --port 8080     # 换端口
```

浏览器打开 `http://127.0.0.1:8000` 即可。用户数据落在 `register/data/users.json`（首次运行自动创建）。

## 为什么不会跳转/刷新

| 环节 | 做法 |
| :--- | :--- |
| 前端 | `form.addEventListener('submit', e => e.preventDefault())` —— 拦掉浏览器默认的表单提交行为 |
| 前端 | 用 `fetch()` 发异步请求，响应交给 JS 处理 |
| 后端 | `/api/register` 一律返回 **JSON**，绝不返回 302 重定向或整页 HTML |

三者缺一不可。只要后端返回重定向、或前端漏了 `preventDefault()`，页面就会跳走。

## 外网临时访问（localhost.run 隧道）

本地服务默认只监听 `127.0.0.1`，外网访问不了。需要临时给别人演示时，用 SSH 反向隧道，**免注册、自带 HTTPS、不用开防火墙入站端口**：

```powershell
# 1) 起本地服务
python server.py --port 8000 --host 127.0.0.1

# 2) 另开一个终端，建隧道（会打印一个 https://xxx.lhr.life 地址）
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL `
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 `
    -R 80:127.0.0.1:8000 nokey@localhost.run
```

- 地址形如 **`https://<随机串>.lhr.life`**，协议 HTTPS、端口 443，**每次重连都会变**
- 想固定子域名：注册 localhost.run 账号并添加 SSH key（免费版可长期保留一个名字）
- **用完立即关掉**：`Ctrl+C` 结束 ssh 进程，再结束 python 进程。隧道存在期间任何人都能访问你的本地服务

⚠️ 安全提醒：本服务**没有限流、没有鉴权、没有验证码**，只适合短时演示。若需长时间暴露或让真实用户填写，必须先加上限流与访问控制。

## 接口契约

`POST /api/register`，`Content-Type: application/json`

请求体：

```json
{ "username": "eyiming", "email": "a@b.com", "password": "abcd1234", "confirm": "abcd1234" }
```

成功 `201`：

```json
{ "ok": true, "code": "REGISTERED", "message": "注册成功，已为你创建账号",
  "data": { "id": 1, "username": "eyiming", "email": "a@b.com", "created_at": "..." } }
```

失败（状态码见下表）：

```json
{ "ok": false, "code": "USERNAME_TAKEN", "message": "该用户名已被占用",
  "errors": { "username": "换一个试试，例如加上数字后缀" } }
```

| 状态码 | code | 含义 |
| :--- | :--- | :--- |
| 201 | `REGISTERED` | 注册成功 |
| 400 | `VALIDATION_FAILED` | 字段校验失败，`errors` 给出逐字段原因 |
| 400 | `INVALID_JSON` / `INVALID_ENCODING` / `EMPTY_BODY` / `BAD_REQUEST` | 请求体有问题 |
| 409 | `USERNAME_TAKEN` / `EMAIL_TAKEN` | 用户名或邮箱已存在 |
| 413 | `PAYLOAD_TOO_LARGE` | 请求体超过 8 KB |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Content-Type 不是 application/json |
| 405 | `METHOD_NOT_ALLOWED` | 用了非 POST 方法 |
| 500 | `INTERNAL_ERROR` | 服务端异常 |

## 已覆盖的边界情况

请求体非 JSON / 根节点非对象 / 空体 / 超长 / 字段传成对象或数组 / 用户名含中文或符号 / 邮箱格式错误 / 密码过短或纯字母 / 两次密码不一致 / 用户名或邮箱重复 / 用 GET 调接口 / 访问不存在的路径 / 数据文件损坏 / 服务重启后判重仍生效。

口令用 PBKDF2-HMAC-SHA256（12 万轮 + 随机盐）存储，**响应体与日志均不含口令**。

## 接入你自己的项目

这是通用骨架，落到实际项目时替换两处即可：

- `server.py` 的 `UserStore` → 换成真实数据库（保持 `taken()` / `add()` 两个方法签名不变）
- `server.py` 的 `validate()` → 按你的业务规则调整校验

前端 `index.html` 里的 `renderSuccess()` / `renderFailure()` 决定结果长得什么样，改这两个函数即可，请求逻辑不用动。
