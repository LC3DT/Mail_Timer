# 📧 邮件定时发送程序

按指定日期时间自动发送邮件的 Python 程序，支持**单次定时**与**周期定时**两种模式。

---

## 功能特性

- ✅ **单次定时发送**：指定具体日期和时间（精确到秒），到时自动发送
- ✅ **周期定时发送**：基于 Cron 表达式，支持"每月25号"等重复规则
- ✅ **抄送（CC）**：支持配置抄送人列表
- ✅ **双格式正文**：同时支持 Plain Text 和 HTML
- ✅ **多收件人**：逗号分隔配置多个收件人
- ✅ **附件支持**：可添加多个本地文件作为附件
- ✅ **密码认证**：直接使用邮箱登录密码，无需额外申请 SMTP 授权码
- ✅ **低资源占用**：零 CPU 轮询等待，默认不写磁盘日志，静默运行
- ✅ **完善异常处理**：覆盖认证失败、网络超时、文件缺失等场景

---

## 目录结构

```
Mail_Timer/
├── email_scheduler.py     # 主程序
├── .env.example           # 单任务配置模板
├── tasks.json.example     # 多任务配置模板
├── start.sh / stop.sh     # Linux 启停脚本
├── start.bat / stop.bat   # Windows 启停脚本
├── mail-scheduler.service # systemd 服务模板（Linux 生产环境）
├── requirements.txt       # 依赖清单
├── README.md              # 使用文档
└── email_scheduler.log    # 运行日志（仅在配置 LOG_FILE 时生成）
```

---

## 快速开始

### 单任务模式（.env）

适合：只需定时发送一封邮件。

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入邮箱信息
python email_scheduler.py
```

### 多任务模式（tasks.json）

适合：需要同时管理多封不同邮件（如月报 + 周报），一个进程统一调度。

```bash
pip install -r requirements.txt
cp tasks.json.example tasks.json
# 编辑 tasks.json，在 defaults 中填入 SMTP 信息，在 tasks 中配置各邮件
python email_scheduler.py    # 自动检测 tasks.json 进入多任务模式
```

> **自动检测逻辑**：程序优先检测 `tasks.json`，存在则进入多任务模式；不存在则回退到 `.env` 单任务模式。
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填写你的邮箱信息
```

### 3. 运行程序

```bashk
python email_scheduler.py
```

---

## 配置说明

编辑 `.env` 文件，各字段含义如下：

### 基础配置

| 配置项 | 说明 | 示例 |
|---|---|---|
| `SMTP_SERVER` | SMTP 服务器地址 | `smtp.laobanmail.com` |
| `SMTP_PORT` | SMTP 端口（Bossmail 推荐 465） | `465` |
| `SMTP_USE_TLS` | 是否启用 STARTTLS（465 端口设 False） | `False` |
| `SENDER_EMAIL` | 发件人邮箱（需完整地址） | `name@company.com` |
| `SENDER_PASSWORD` | 邮箱登录密码 | `your_password` |
| `RECIPIENTS` | 收件人（逗号分隔） | `a@qq.com,b@163.com` |
| `CC` | 抄送人（逗号分隔，可选） | `cc1@qq.com,cc2@163.com` |
| `SUBJECT` | 邮件主题 | `每月报表` |
| `BODY_TEXT_FILE` | **（推荐）** 纯文本正文文件路径 | `./body.txt` |
| `BODY_HTML_FILE` | **（推荐）** HTML 正文文件路径 | `./body.html` |
| `BODY_TEXT` | 内联纯文本正文（文件方式优先） | `你好！...` |
| `BODY_HTML` | 内联 HTML 正文（文件方式优先） | `<html>...</html>` |
| `SIGNATURE` | 邮箱签名，附在正文末尾 | `张三 \| 技术部 \| XX公司` |
| `SIGNATURE_HTML` | HTML 格式签名（可选，支持图片） | `<div>...</div>` |
| `SHOW_SEND_TIME` | 是否在正文中显示发送时间（True/False） | `True` |
| `ATTACHMENTS` | 附件路径（逗号分隔，可选） | `./report.pdf` |

> **正文编写建议**：推荐使用 `BODY_TEXT_FILE` / `BODY_HTML_FILE` 从外部文件加载正文。HTML 文件可用 Word 另存为 HTML、VS Code 编辑、或任意富文本编辑器创建。文件内容完全替换对应的内联配置项。

> **注意**：`BODY_TEXT` + `BODY_TEXT_FILE` 至少生效一个，`BODY_HTML` + `BODY_HTML_FILE` 同理。文件方式优先于内联方式。

### 多任务配置（tasks.json）

多任务模式使用 JSON 格式，`defaults` 中的公共配置（SMTP、签名等）会被所有任务继承，每个任务可覆盖任意字段：

```json
{
    "defaults": {
        "smtp_server": "smtp.weiyaauto.com",
        "smtp_port": 465,
        "sender_email": "name@company.com",
        "sender_password": "密码",
        "signature": "统一签名",
        "show_send_time": true
    },
    "tasks": [
        {
            "name": "月报",
            "subject": "月报主题",
            "recipients": ["a@t.com"],
            "cc": ["cc@t.com"],
            "body_text_file": "body.txt",
            "attachments": ["report.pdf"],
            "schedule_type": "cron",
            "schedule_cron": "0 9 25 * *"
        },
        {
            "name": "周报",
            "subject": "周报主题",
            "recipients": ["b@t.com"],
            "body_text": "内联正文...",
            "schedule_type": "cron",
            "schedule_cron": "0 9 * * 5"
        }
    ]
}
```

每任务字段与 `.env` 配置项完全对应（`name` 和 `recipients` 格式除外：JSON 中 `recipients`/`cc` 用数组而非逗号分隔字符串）。

### 推荐：使用外部文件编写邮件正文

直接在 `.env` 中写长文本或 HTML 很不方便。推荐使用外部文件：

**纯文本邮件**：

```bash
# 1. 用记事本创建 body.txt，编写邮件内容
# 2. 在 .env 中配置：
BODY_TEXT_FILE=body.txt
```

**富文本邮件**（推荐流程）：

```bash
# 1. 用 Word 编写邮件（支持加粗、颜色、表格等）
#    「文件」→「另存为」→ 选择「网页(.htm)」→ body.html
# 2. 或用 VS Code 直接编辑 body.html
# 3. 在 .env 中配置：
BODY_HTML_FILE=body.html
```

项目自带模板文件 `body.txt.example` 和 `body.html.example` 可作为起点。

### 调度模式

| 配置项 | 说明 | 示例 |
|---|---|---|
| `SCHEDULE_TYPE` | `once`（单次）或 `cron`（周期） | `cron` |

**单次模式**（`SCHEDULE_TYPE=once`）：

| 配置项 | 说明 | 示例 |
|---|---|---|
| `SCHEDULE_TIME` | 发送时间 `YYYY-MM-DD HH:MM:SS` | `2026-12-31 09:00:00` |

**周期模式**（`SCHEDULE_TYPE=cron`）：

| 配置项 | 说明 | 示例 |
|---|---|---|
| `SCHEDULE_CRON` | Cron 表达式 `分 时 日 月 周` | `0 9 25 * *` |

Cron 表达式示例：

| 表达式 | 含义 |
|---|---|
| `0 9 25 * *` | **每月25号上午9:00** |
| `30 8 * * 1-5` | 工作日（周一至周五）上午8:30 |
| `0 9 * * *` | 每天上午9:00 |
| `0 9 1 * *` | 每月1号上午9:00 |
| `0 14 * * 5` | 每周五下午2:00 |

### 日志配置

| 配置项 | 说明 | 示例 |
|---|---|---|
| `LOG_FILE` | 日志文件路径（留空不写文件，推荐） | `email_scheduler.log` |

---

## 获取邮箱服务器信息

### Bossmail（老板邮局）

1. SMTP 服务器默认为 `smtp.laobanmail.com`，端口 `465`
2. 企业自有域名的服务器地址可能为 `smtp.<你的域名>.com`
3. 不确定服务器地址时可访问官方查询页面：[https://www.laobanmail.com/help?type=62](https://www.laobanmail.com/help?type=62)
4. **直接使用邮箱登录密码**作为 `SENDER_PASSWORD`，无需申请 SMTP 授权码
5. 邮箱账户名必须填写**完整地址**（`name@company.com`），不可只填用户名
6. 如果提示 **"unsupported remote IP"**，进入网页版「设置」→「账号中心」→ 添加「信任登录地址」

### QQ 邮箱

1. 登录 [QQ 邮箱](https://mail.qq.com) → 点击**设置** → **账户**
2. 找到「POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV 服务」
3. 开启 **SMTP 服务**，按提示发送短信验证获取 **16 位授权码**
4. SMTP 服务器：`smtp.qq.com`，端口：`587` 或 `465`

### 163 邮箱

1. 登录 [163 邮箱](https://mail.163.com) → 点击**设置** → **POP3/SMTP/IMAP**
2. 开启 **SMTP 服务**，按提示设置**授权密码**
3. SMTP 服务器：`smtp.163.com`，端口：`587` 或 `465`

### Gmail

1. 登录 [Google 账户](https://myaccount.google.com) → **安全性**
2. 开启**两步验证** → 生成**应用专用密码**（App Passwords）
3. 使用应用专用密码作为 `SENDER_PASSWORD`
4. SMTP 服务器：`smtp.gmail.com`，端口：`587` 或 `465`

---

## SMTP 端口说明

| 端口 | 协议 | 说明 |
|---|---|---|
| **465** | SSL/TLS（Bossmail 推荐） | 直接 SSL 加密连接 |
| **587** | STARTTLS（QQ/163/Gmail 常用） | 连接后升级加密 |
| 25 | 明文（不推荐） | 通常被 ISP 封锁 |

---

## 运行示例

### 单次定时模式

```
$ python email_scheduler.py

2026-07-29 14:00:00 [INFO] ==================================================
2026-07-29 14:00:00 [INFO] [Mail] 邮件定时发送程序 启动
2026-07-29 14:00:00 [INFO] 配置文件加载成功。
2026-07-29 14:00:00 [INFO] 配置校验通过。
2026-07-29 14:00:00 [INFO] 邮件已排程，将于 2026-07-29 18:00:00 发送（还需等待约 14400 秒 / 240.0 分钟）。
2026-07-29 14:00:00 [INFO] 调度器已启动，静默等待触发...
2026-07-29 14:05:00 [INFO] [Wait] 距发送还有 14100 秒（235.0 分钟）...
2026-07-29 14:10:00 [INFO] [Wait] 距发送还有 13800 秒（230.0 分钟）...
...
2026-07-29 18:00:00 [INFO] [Trigger] 到达预定时间，开始执行发送任务...
2026-07-29 18:00:00 [INFO] 开始构建邮件...
2026-07-29 18:00:00 [INFO] 邮件信息：发件人=noreply@company.com, 收件人=['it@company.com'], 抄送=['manager@company.com'], ...
2026-07-29 18:00:00 [INFO] 连接 SMTP 服务器 smtp.weiyaauto.com:465 ...
2026-07-29 18:00:01 [INFO] SMTP 登录成功。
2026-07-29 18:00:02 [INFO] [OK] 邮件发送成功！
```

### 周期定时模式（每月25号）

```
$ python email_scheduler.py

2026-07-29 14:00:00 [INFO] ==================================================
2026-07-29 14:00:00 [INFO] [Mail] 邮件定时发送程序 启动
2026-07-29 14:00:00 [INFO] 配置文件加载成功。
2026-07-29 14:00:00 [INFO] 配置校验通过。
2026-07-29 14:00:00 [INFO] Cron 模式已启动，表达式：0 9 25 * *
2026-07-29 14:00:00 [INFO] 程序将持续运行，按 cron 周期自动发送邮件。按 Ctrl+C 停止。
2026-07-29 14:00:00 [INFO] 调度器已启动，静默等待触发...
```

> **说明**：cron 模式下程序持续运行不退出，每次 cron 触发时执行发送并输出日志，然后继续等待下一次触发。按 `Ctrl+C` 停止程序。

---

## 资源占用说明

| 指标 | 说明 |
|---|---|
| **CPU** | 等待期间 CPU 占用 ≈ 0%（使用 `Event.wait()` 阻塞，无轮询） |
| **内存** | 约 30-50 MB（Python 解释器基础开销） |
| **磁盘** | 默认不写日志文件，仅在配置 `LOG_FILE` 时才写入 |
| **网络** | 仅发送邮件时有短暂网络连接 |

---

## 常见问题

**Q: Bossmail 提示「SMTP 认证失败」？**

A: 请逐一排查：
1. `SENDER_PASSWORD` 填写的是**邮箱登录密码**（Bossmail 不需要 SMTP 授权码）
2. `SENDER_EMAIL` 必须填写**完整地址**（含 `@` 及域名），不可只填用户名前缀
3. `SMTP_PORT` 设为 `465`，`SMTP_USE_TLS` 设为 `False`

**Q: Bossmail 提示「unsupported remote IP」？**

A: 登录网页版邮箱 → 「设置」→「账号中心」→ 添加「信任登录地址」，将当前 IP 所在城市加入信任地点。

**Q: 单次模式下指定时间已过期？**

A: 程序会输出警告并立即发送邮件。

**Q: 如何添加抄送？**

A: 在 `.env` 中配置 `CC` 字段（逗号分隔多个抄送人地址），留空则不抄送。

**Q: 如何设置每月固定日期发送？**

A: 设置 `SCHEDULE_TYPE=cron`，并配置 `SCHEDULE_CRON=0 9 25 * *`（每月25号上午9点）。

**Q: 如何降低系统资源占用？**

A: 程序已默认优化：
- 等待期间使用系统级阻塞，不消耗 CPU
- 默认不写日志文件（减少磁盘 I/O）
- cron 模式下无心跳日志（真正静默运行）

如需进一步降低，可在任务管理器中设为"低优先级"。

---

## 服务器部署（Ubuntu / Debian）

### 方案一：Shell 脚本后台运行（推荐，最简单）

```bash
# 1. 上传项目到服务器
scp -r Mail_Timer user@server:/opt/

# 2. 安装依赖
cd /opt/Mail_Timer
pip3 install -r requirements.txt

# 3. 配置
cp .env.example .env        # 单任务
# 或
cp tasks.json.example tasks.json  # 多任务

# 4. 后台启动（nohup 保证关终端不中断）
./start.sh

# 5. 管理
./status.sh    # 查看状态 + 最近日志
./stop.sh      # 停止程序
```

### 方案二：systemd 服务（生产环境推荐，开机自启）

```bash
# 1. 编辑服务文件中的路径
sudo nano mail-scheduler.service
# 确认 WorkingDirectory=/opt/Mail_Timer 与实际路径一致

# 2. 安装服务
sudo cp mail-scheduler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mail-scheduler    # 开机自启
sudo systemctl start mail-scheduler     # 立即启动

# 3. 日常管理
sudo systemctl status mail-scheduler    # 查看状态
sudo journalctl -u mail-scheduler -f    # 实时日志
sudo systemctl stop mail-scheduler      # 停止
sudo systemctl restart mail-scheduler   # 重启
```

### 方案三：crontab 定时触发（适合 once 单次模式）

```bash
# 每天 9:00 执行一次发送
crontab -e
0 9 * * * cd /opt/Mail_Timer && /usr/bin/python3 email_scheduler.py
```

---

## 服务器部署（Windows Server）

程序需要持续运行（尤其是 cron 模式），关闭远程桌面窗口会导致进程终止。以下方案任选其一：

### 方案一：bat 脚本后台运行（推荐，最简单）

```bash
# 启动（无命令行窗口，关闭远程桌面不影响）
双击 start.bat

# 查看状态
双击 status.bat

# 停止
双击 stop.bat
```

原理：`start.bat` 使用 `pythonw.exe` 启动程序（无控制台窗口），PID 写入 `email_scheduler.pid` 文件。`stop.bat` 读取 PID 并终止进程。关闭远程桌面窗口不影响后台进程。

### 方案二：Windows 任务计划程序（适合 once 单次模式）

1. 打开「任务计划程序」→「创建基本任务」
2. 触发器：按需求设置时间（如每天 9:00）
3. 操作：启动程序 → `pythonw.exe`，参数填 `email_scheduler.py`，起始于程序目录
4. 勾选「不管用户是否登录都要运行」
5. 这样服务器重启后也会自动按计划触发

### 方案三：设为 Windows 服务（适合 cron 模式 + 开机自启）

```bash
# 1. 下载 NSSM (https://nssm.cc/download)
# 2. 安装服务
nssm install MailScheduler
#    路径: C:\Python313\pythonw.exe
#    参数: email_scheduler.py
#    起始目录: D:\Mail_Timer

# 3. 管理
nssm start MailScheduler     # 启动
nssm stop MailScheduler      # 停止
nssm status MailScheduler    # 状态
```

### 服务器重启后自动恢复

无论哪种方案，建议配合：
- 方案一 + 任务计划程序（触发器设为「系统启动时」执行 `start.bat`）
- 方案三：服务自动随系统启动
