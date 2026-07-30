#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件定时发送程序
功能：
  - 单次定时发送（指定日期时间）
  - 周期定时发送（Cron 表达式，如每月25号发送）
  - 抄送（CC）、多收件人、附件
  - 低资源占用、静默运行
"""

import os
import sys
import json
import time
import atexit
import logging
import threading
import smtplib
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email import utils as email_utils

# ============================================================
# 日志配置（终端输出，默认不写文件以降低磁盘 I/O）
# ============================================================
if sys.stdout.encoding.lower() in ("gbk", "cp936", "cp1252"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_LOG_FILE = os.getenv("LOG_FILE", "")

_handlers: list = [logging.StreamHandler(sys.stdout)]
if _LOG_FILE and _LOG_FILE.lower() != "false":
    _handlers.append(logging.FileHandler(_LOG_FILE, encoding="utf-8"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=_handlers,
)
logger = logging.getLogger(__name__)


# ============================================================
# 工具函数
# ============================================================
def _parse_list(raw: str) -> List[str]:
    """将逗号分隔的字符串解析为列表，自动去除空白与空项。"""
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


# ============================================================
# 配置加载
# ============================================================
def load_config() -> dict:
    """从 .env 文件加载所有配置项，返回字典。"""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        raise FileNotFoundError(
            f"配置文件未找到：{env_path}\n"
            f"请参考 .env.example 创建 .env 文件并填写必要信息。"
        )

    load_dotenv(env_path)

    config = {
        # SMTP 服务器
        "smtp_server": os.getenv("SMTP_SERVER"),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "smtp_use_tls": os.getenv("SMTP_USE_TLS", "True").lower() in ("true", "1", "yes"),
        # 发件人
        "sender_email": os.getenv("SENDER_EMAIL"),
        "sender_password": os.getenv("SENDER_PASSWORD"),
        # 收件人 / 抄送
        "recipients": _parse_list(os.getenv("RECIPIENTS", "")),
        "cc": _parse_list(os.getenv("CC", "")),
        # 邮件内容
        "subject": os.getenv("SUBJECT", "无主题"),
        "body_text": os.getenv("BODY_TEXT", ""),
        "body_html": os.getenv("BODY_HTML", ""),
        "body_text_file": os.getenv("BODY_TEXT_FILE", ""),
        "body_html_file": os.getenv("BODY_HTML_FILE", ""),
        "signature": os.getenv("SIGNATURE", ""),
        "signature_html": os.getenv("SIGNATURE_HTML", ""),
        "show_send_time": os.getenv("SHOW_SEND_TIME", "True").lower() in ("true", "1", "yes"),
        # 附件
        "attachments": _parse_list(os.getenv("ATTACHMENTS", "")),
        # 调度模式
        "schedule_type": os.getenv("SCHEDULE_TYPE", "once").lower(),
        "schedule_time": os.getenv("SCHEDULE_TIME", ""),
        "schedule_cron": os.getenv("SCHEDULE_CRON", ""),
        # 预览模式
        "dry_run": os.getenv("DRY_RUN", "False").lower() in ("true", "1", "yes"),
    }

    return config


# ============================================================
# 多任务 JSON 配置
# ============================================================
def _normalize_config_keys(d: dict) -> dict:
    """
    将常见大写键名（兼容 .env 命名习惯）映射到规范小写键名。
    用户既可用 JSON 小写键名，也可用与 .env 一致的大写键名。
    """
    KEY_MAP = {
        "SCHEDULE_TIME": "schedule_time", "SCHEDULE_CRON": "schedule_cron",
        "SCHEDULE_TYPE": "schedule_type", "SMTP_SERVER": "smtp_server",
        "SMTP_PORT": "smtp_port", "SMTP_USE_TLS": "smtp_use_tls",
        "SENDER_EMAIL": "sender_email", "SENDER_PASSWORD": "sender_password",
        "RECIPIENTS": "recipients", "CC": "cc",
        "SUBJECT": "subject", "BODY_TEXT": "body_text",
        "BODY_HTML": "body_html", "BODY_TEXT_FILE": "body_text_file",
        "BODY_HTML_FILE": "body_html_file", "SIGNATURE": "signature",
        "SIGNATURE_HTML": "signature_html", "SHOW_SEND_TIME": "show_send_time",
        "ATTACHMENTS": "attachments", "DRY_RUN": "dry_run",
        "LOG_FILE": "log_file", "NAME": "name",
    }
    for old, new in KEY_MAP.items():
        if old in d and new not in d:
            d[new] = d.pop(old)
    return d


def load_tasks_json(filepath: str = "tasks.json") -> list:
    """
    从 JSON 文件加载多任务配置。
    支持 defaults 段（被各 task 继承），每个 task 可覆盖任意字段。
    键名兼容大写（如 SCHEDULE_TIME）和小写（如 schedule_time）。
    返回 list[dict]，每个 dict 为合并后的完整配置。
    """
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"任务配置文件未找到：{path.resolve()}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    defaults = _normalize_config_keys(data.get("defaults", {}))
    tasks = data.get("tasks", [])

    if not tasks:
        raise ValueError("tasks.json 中 tasks 列表不能为空。")

    result = []
    for i, task in enumerate(tasks):
        task = _normalize_config_keys(task)
        merged = deepcopy(defaults)
        merged.update(task)
        # 确保必要字段有默认值
        merged.setdefault("name", f"task-{i + 1}")
        merged.setdefault("subject", "无主题")
        merged.setdefault("body_text", "")
        merged.setdefault("body_html", "")
        merged.setdefault("body_text_file", "")
        merged.setdefault("body_html_file", "")
        merged.setdefault("signature", "")
        merged.setdefault("signature_html", "")
        merged.setdefault("show_send_time", True)
        merged.setdefault("cc", [])
        merged.setdefault("attachments", [])
        merged.setdefault("schedule_type", "once")
        merged.setdefault("schedule_time", "")
        merged.setdefault("schedule_cron", "")
        merged.setdefault("dry_run", False)
        merged.setdefault("smtp_use_tls", False)
        result.append(merged)

    return result


# ============================================================
# 正文文件加载
# ============================================================
def resolve_body_files(config: dict) -> None:
    """
    如果配置了 BODY_TEXT_FILE / BODY_HTML_FILE，从外部文件加载正文内容。
    文件内容优先级高于内联 BODY_TEXT / BODY_HTML。

    规则：
      - 指定了文件 → 用文件内容覆盖对应内联值
      - 未指定文件 → 保留内联值作为回退
      - 只指定一边文件时，自动清空另一边的内联回退值，避免意外混入 HTML/文本
    """
    has_text_file = bool(config["body_text_file"])
    has_html_file = bool(config["body_html_file"])

    if has_text_file:
        path = Path(config["body_text_file"])
        if not path.is_file():
            raise FileNotFoundError(f"正文文本文件不存在：{path.resolve()}")
        config["body_text"] = path.read_text(encoding="utf-8")
        logger.info(f"已从文件加载纯文本正文：{path.name}（{len(config['body_text'])} 字符）")

    if has_html_file:
        path = Path(config["body_html_file"])
        if not path.is_file():
            raise FileNotFoundError(f"正文 HTML 文件不存在：{path.resolve()}")
        config["body_html"] = path.read_text(encoding="utf-8")
        logger.info(f"已从文件加载 HTML 正文：{path.name}（{len(config['body_html'])} 字符）")

    # 只指定了一边文件时，清空另一边的内联回退值，避免意外混入
    if has_text_file and not has_html_file:
        if config["body_html"]:
            logger.info("已忽略内联 BODY_HTML（仅使用文本文件正文）。")
        config["body_html"] = ""
    elif has_html_file and not has_text_file:
        if config["body_text"]:
            logger.info("已忽略内联 BODY_TEXT（仅使用 HTML 文件正文）。")
        config["body_text"] = ""


# ============================================================
# 配置校验
# ============================================================
def validate_config(config: dict) -> None:
    """校验必要配置项是否存在，不合法则抛出 ValueError。"""
    required = [
        ("SMTP_SERVER", config["smtp_server"]),
        ("SMTP_PORT", config["smtp_port"]),
        ("SENDER_EMAIL", config["sender_email"]),
        ("SENDER_PASSWORD", config["sender_password"]),
        ("RECIPIENTS", config["recipients"]),
    ]

    missing = [name for name, value in required if not value]
    if missing:
        raise ValueError(f"缺少必要配置项：{', '.join(missing)}，请检查 .env 文件。")

    # 正文至少有一个
    if not config["body_text"] and not config["body_html"]:
        raise ValueError("BODY_TEXT 与 BODY_HTML 不能同时为空，请至少提供一个。")

    # 调度模式校验
    schedule_type = config["schedule_type"]
    if schedule_type == "once":
        if not config["schedule_time"]:
            raise ValueError("once 模式下 SCHEDULE_TIME 不能为空。")
        try:
            datetime.strptime(config["schedule_time"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise ValueError(
                f"调度时间格式错误：{config['schedule_time']}，"
                f"正确格式为 YYYY-MM-DD HH:MM:SS"
            )
    elif schedule_type == "cron":
        if not config["schedule_cron"]:
            raise ValueError("cron 模式下 SCHEDULE_CRON 不能为空。")
        # 尝试解析 cron 表达式
        try:
            CronTrigger.from_crontab(config["schedule_cron"])
        except (ValueError, AttributeError) as e:
            raise ValueError(
                f"Cron 表达式无效：{config['schedule_cron']}（{e}）\n"
                f"正确格式示例：0 9 25 * *（每月25号上午9点）"
            )
    else:
        raise ValueError(
            f"SCHEDULE_TYPE 只能是 'once' 或 'cron'，当前值：{schedule_type}"
        )

    # 附件文件存在性校验
    for att in config["attachments"]:
        p = Path(att)
        if not p.is_file():
            raise FileNotFoundError(f"附件文件不存在：{p.resolve()}")

    logger.info("配置校验通过。")


# ============================================================
# 邮件构建
# ============================================================
def build_message(
    sender: str,
    recipients: List[str],
    cc: List[str],
    subject: str,
    body_text: str,
    body_html: str,
    attachments: List[str],
    signature: str = "",
    signature_html: str = "",
    show_send_time: bool = True,
) -> MIMEMultipart:
    """构建完整的 MIME 邮件对象（含抄送、签名、发送时间、正文、附件）。"""
    # 发送时间戳
    send_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if show_send_time else ""

    # 构建纯文本正文：原始正文 + 签名 + 发送时间
    final_text = body_text
    if signature or send_time_str:
        final_text += "\n\n---"
        if signature:
            final_text += f"\n{signature}"
        if send_time_str:
            final_text += f"\n发送时间：{send_time_str}"

    # 构建 HTML 正文：原始正文 + 签名（HTML） + 发送时间
    # 注意：仅当用户确实提供了 HTML 正文时才构建 HTML 签名/时间脚注
    final_html = body_html
    if body_html:
        html_sig = signature_html or (f"<p>{signature}</p>" if signature else "")
        html_time = f'<p style="color:#888;font-size:12px;">发送时间：{send_time_str}</p>' if send_time_str else ""

        footer_html = ""
        if html_sig or html_time:
            footer_html = (
                '\n<hr style="border:none;border-top:1px solid #ccc;margin-top:20px;">\n'
                f'<div style="color:#666;font-size:13px;">{html_sig}{html_time}</div>'
            )

        if footer_html:
            if "</body>" in final_html:
                final_html = final_html.replace("</body>", f"{footer_html}\n</body>")
            else:
                final_html += footer_html

    msg = MIMEMultipart("mixed")
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = email_utils.formatdate(localtime=True)

    # 正文：仅当同时有纯文本和 HTML 时才用 multipart/alternative 包装
    # 若只有单种格式，直接附加 MIMEText，避免部分客户端（如 Bossmail）不渲染
    has_text = bool(final_text)
    has_html = bool(final_html)

    if has_text and has_html:
        body_part: object = MIMEMultipart("alternative")
        body_part.attach(MIMEText(final_text, "plain", "utf-8"))
        body_part.attach(MIMEText(final_html, "html", "utf-8"))
        msg.attach(body_part)
    elif has_html:
        msg.attach(MIMEText(final_html, "html", "utf-8"))
    elif has_text:
        msg.attach(MIMEText(final_text, "plain", "utf-8"))

    # 附件
    for file_path in attachments:
        _attach_file(msg, file_path)

    # 若无附件且只有一种正文格式，去掉多余的 multipart/mixed 外层，直接返回纯 MIMEText
    if not attachments and (has_text != has_html):  # XOR — 只有一种正文
        # 提取 msg 中唯一的正文部分直接返回
        payload = msg.get_payload()
        if isinstance(payload, list) and len(payload) == 1:
            return payload[0]

    return msg


def _attach_file(msg: MIMEMultipart, file_path: str) -> None:
    """添加单个附件到邮件。"""
    path = Path(file_path)
    with open(path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{path.name}"')
    msg.attach(part)
    logger.info(f"已添加附件：{path.name}")


# ============================================================
# SMTP 发送
# ============================================================
def send_email(config: dict) -> bool:
    """连接 SMTP 服务器并发送邮件。返回 True/False。"""
    logger.info("=" * 50)
    logger.info("开始构建邮件...")

    msg = build_message(
        sender=config["sender_email"],
        recipients=config["recipients"],
        cc=config["cc"],
        subject=config["subject"],
        body_text=config["body_text"],
        body_html=config["body_html"],
        attachments=config["attachments"],
        signature=config.get("signature", ""),
        signature_html=config.get("signature_html", ""),
        show_send_time=config.get("show_send_time", True),
    )

    # 信封收件人 = To + Cc（SMTP 实际投递对象）
    all_recipients = list(config["recipients"])
    if config["cc"]:
        all_recipients.extend(config["cc"])

    log_detail = (
        f"邮件信息：发件人={config['sender_email']}, "
        f"收件人={config['recipients']}, "
        f"抄送={config['cc'] if config['cc'] else '无'}, "
        f"主题={config['subject']}, "
        f"附件数量={len(config['attachments'])}"
    )
    logger.info(log_detail)

    server: Optional[smtplib.SMTP] = None
    try:
        logger.info(
            f"连接 SMTP 服务器 {config['smtp_server']}:{config['smtp_port']} ..."
        )

        # 端口 465 → SMTP_SSL；其他端口 → SMTP + 可选 STARTTLS
        if config["smtp_port"] == 465:
            server = smtplib.SMTP_SSL(
                config["smtp_server"], config["smtp_port"], timeout=30
            )
        else:
            server = smtplib.SMTP(
                config["smtp_server"], config["smtp_port"], timeout=30
            )
            if config["smtp_use_tls"]:
                server.starttls()

        # 使用邮箱密码直接登录
        server.login(config["sender_email"], config["sender_password"])
        logger.info("SMTP 登录成功。")

        server.sendmail(config["sender_email"], all_recipients, msg.as_string())
        logger.info("[OK] 邮件发送成功！")
        return True

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP 认证失败：{e}")
        logger.error("请检查 SENDER_EMAIL 和 SENDER_PASSWORD（邮箱密码）是否正确。")
        return False
    except smtplib.SMTPConnectError as e:
        logger.error(f"SMTP 连接失败：{e}")
        logger.error("请检查 SMTP_SERVER 和 SMTP_PORT 是否正确，以及网络是否可达。")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP 发送异常：{e}")
        return False
    except OSError as e:
        logger.error(f"网络/系统错误：{e}")
        return False
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass


# ============================================================
# 预览模式
# ============================================================
def dry_run_preview(config: dict) -> None:
    """预览邮件完整内容（不连接 SMTP，不发送）。"""
    logger.info("=" * 50)
    logger.info("[Preview] DRY_RUN 预览模式 —— 不会实际发送邮件")
    logger.info("=" * 50)

    msg = build_message(
        sender=config["sender_email"],
        recipients=config["recipients"],
        cc=config["cc"],
        subject=config["subject"],
        body_text=config["body_text"],
        body_html=config["body_html"],
        attachments=config["attachments"],
        signature=config.get("signature", ""),
        signature_html=config.get("signature_html", ""),
        show_send_time=config.get("show_send_time", True),
    )

    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + "   📧 邮件预览（DRY RUN）".ljust(48) + "║")
    print("╠" + "═" * 58 + "╣")
    print(f"║  发件人: {config['sender_email']}".ljust(49) + "║")
    print(f"║  收件人: {', '.join(config['recipients'])}".ljust(49) + "║")
    if config["cc"]:
        print(f"║  抄  送: {', '.join(config['cc'])}".ljust(49) + "║")
    print(f"║  主  题: {config['subject']}".ljust(49) + "║")
    print(f"║  附  件: {len(config['attachments'])} 个".ljust(49) + "║")
    if config["attachments"]:
        for a in config["attachments"]:
            print(f"║         - {a}".ljust(49) + "║")
    print("╠" + "═" * 58 + "╣")

    # 展示纯文本正文
    if config["body_text"]:
        print("║  [纯文本正文]".ljust(49) + "║")
        print("╟" + "─" * 58 + "╢")
        for line in config["body_text"].split("\n"):
            # 截断过长行
            display = line[:55] + "..." if len(line) > 55 else line
            print(f"║  {display}".ljust(49) + "║")
        print("╟" + "─" * 58 + "╢")

    # 展示 HTML 正文大小
    if config["body_html"]:
        html_len = len(config["body_html"])
        print(f"║  [HTML 正文] 共 {html_len} 字符".ljust(49) + "║")
        if html_len <= 500:
            print("╟" + "─" * 58 + "╢")
            for line in config["body_html"].split("\n")[:15]:
                display = line[:55] + "..." if len(line) > 55 else line
                print(f"║  {display}".ljust(49) + "║")
        print("╟" + "─" * 58 + "╢")

    print("║  以上为预览内容，邮件未实际发送。".ljust(49) + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    logger.info("[Preview] 预览完成。确认内容无误后，将 DRY_RUN 设为 False 即可正式发送。")


# ============================================================
# 运行模式
# ============================================================

# 用于 cron 模式的优雅退出信号
_stop_event = threading.Event()


def _send_and_exit(config: dict) -> None:
    """once 模式回调：发送邮件后退出。"""
    logger.info("[Trigger] 到达预定时间，开始执行发送任务...")
    success = send_email(config)
    sys.exit(0 if success else 1)


def _send_and_continue(config: dict) -> None:
    """cron 模式回调：发送邮件后继续等待下一次触发。"""
    task_name = config.get("name", "")
    logger.info(f"[Trigger] [{task_name}] Cron 触发，开始执行发送任务...")
    success = send_email(config)
    if success:
        logger.info(f"[{task_name}] 本次发送完成，等待下一次 cron 触发...")
    else:
        logger.error(f"[{task_name}] 本次发送失败，等待下一次 cron 触发...")


def _send_once_no_exit(config: dict) -> None:
    """多任务 once 模式回调：发送邮件但不退出进程（其他任务可能还在运行）。"""
    task_name = config.get("name", "")
    logger.info(f"[Trigger] [{task_name}] 到达预定时间，开始执行发送任务...")
    success = send_email(config)
    if success:
        logger.info(f"[{task_name}] 单次任务发送完成。")
    else:
        logger.error(f"[{task_name}] 单次任务发送失败。")


def _run_once_mode(config: dict) -> None:
    """单次定时发送模式。"""
    schedule_time = datetime.strptime(config["schedule_time"], "%Y-%m-%d %H:%M:%S")
    now = datetime.now()

    if schedule_time <= now:
        logger.warning(
            f"指定的发送时间 {schedule_time} 已过期，将立即发送邮件。"
        )
        success = send_email(config)
        sys.exit(0 if success else 1)

    wait_seconds = (schedule_time - now).total_seconds()
    logger.info(
        f"邮件已排程，将于 {schedule_time} 发送"
        f"（还需等待约 {wait_seconds:.0f} 秒 / {wait_seconds / 60:.1f} 分钟）。"
    )

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _send_and_exit,
        trigger=DateTrigger(run_date=schedule_time),
        args=[config],
        id="email_once",
    )
    scheduler.start()
    logger.info("调度器已启动，静默等待触发...")

    # 高效等待：每 5 分钟输出一次心跳，其余时间阻塞 sleep
    heartbeat_interval = 300  # 5 分钟
    next_heartbeat = now.timestamp() + min(heartbeat_interval, wait_seconds)
    try:
        while scheduler.running:
            time.sleep(1)  # 每秒检查一次是否到了心跳时间（CPU 接近零）
            if datetime.now().timestamp() >= next_heartbeat:
                remaining = (schedule_time - datetime.now()).total_seconds()
                if remaining > 0:
                    logger.info(
                        f"[Wait] 距发送还有 {remaining:.0f} 秒 "
                        f"（{remaining / 60:.1f} 分钟）..."
                    )
                    next_heartbeat += heartbeat_interval
                else:
                    break
        time.sleep(2)  # 给回调一点时间执行
    except KeyboardInterrupt:
        logger.info("用户中断，程序退出。")
        scheduler.shutdown(wait=False)
        sys.exit(0)


def _run_cron_mode(config: dict) -> None:
    """周期定时发送模式（Cron 表达式）。"""
    cron_expr = config["schedule_cron"]
    logger.info(f"Cron 模式已启动，表达式：{cron_expr}")
    logger.info("程序将持续运行，按 cron 周期自动发送邮件。按 Ctrl+C 停止。")

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _send_and_continue,
        trigger=CronTrigger.from_crontab(cron_expr),
        args=[config],
        id="email_cron",
    )
    scheduler.start()
    logger.info("调度器已启动，静默等待触发...")

    # 零 CPU 阻塞等待，由后台调度器自动触发
    try:
        _stop_event.wait()  # 阻塞主线程，CPU 占用 0%
    except KeyboardInterrupt:
        logger.info("用户中断，程序退出。")
    finally:
        scheduler.shutdown(wait=False)


# ============================================================
# 多任务模式
# ============================================================
def _run_multi_mode(tasks: list) -> None:
    """多任务调度：一个调度器管理所有任务，共享进程。"""
    logger.info(f"多任务模式：共加载 {len(tasks)} 个任务")
    for t in tasks:
        logger.info(
            f"  - [{t['name']}] "
            f"收件人={t['recipients']}, "
            f"模式={t['schedule_type']}, "
            f"{'cron=' + t['schedule_cron'] if t['schedule_type'] == 'cron' else '时间=' + t['schedule_time']}"
        )

    scheduler = BackgroundScheduler()
    now = datetime.now()
    has_pending_once = False

    for i, task in enumerate(tasks):
        job_id = f"task_{i}_{task['name']}"

        if task["schedule_type"] == "cron":
            scheduler.add_job(
                _send_and_continue,
                trigger=CronTrigger.from_crontab(task["schedule_cron"]),
                args=[task],
                id=job_id,
                name=f"[{task['name']}] cron",
            )
        else:
            schedule_time = datetime.strptime(task["schedule_time"], "%Y-%m-%d %H:%M:%S")
            if schedule_time <= now:
                logger.warning(f"[{task['name']}] 指定时间 {schedule_time} 已过期，将立即发送。")
                _send_once_no_exit(task)
            else:
                has_pending_once = True
                scheduler.add_job(
                    _send_once_no_exit,
                    trigger=DateTrigger(run_date=schedule_time),
                    args=[task],
                    id=job_id,
                    name=f"[{task['name']}] once",
                )
                wait_s = (schedule_time - now).total_seconds()
                logger.info(f"[{task['name']}] 已排程，将于 {schedule_time} 发送（{wait_s / 60:.0f} 分钟后）。")

    scheduler.start()
    logger.info("调度器已启动，静默等待触发...")

    if not has_pending_once:
        # 全部已发送或无定时任务，仅 cron 在跑
        pass

    # 零 CPU 阻塞等待
    try:
        _stop_event.wait()
    except KeyboardInterrupt:
        logger.info("用户中断，程序退出。")
    finally:
        scheduler.shutdown(wait=False)


# ============================================================
# 主入口
# ============================================================
# PID 文件（用于后台运行管理）
_PID_FILE = Path(__file__).resolve().parent / "email_scheduler.pid"


def _write_pid() -> None:
    """写入当前进程 PID 到文件。"""
    _PID_FILE.write_text(str(os.getpid()))


def _cleanup_pid() -> None:
    """删除 PID 文件。"""
    try:
        if _PID_FILE.is_file():
            _PID_FILE.unlink()
    except Exception:
        pass


def main() -> None:
    """程序入口。自动检测 tasks.json（多任务）或 .env（单任务）。"""
    _write_pid()
    atexit.register(_cleanup_pid)
    logger.info("=" * 50)
    logger.info("[Mail] 邮件定时发送程序 启动")

    # 检测多任务配置文件
    tasks_json_path = Path(__file__).resolve().parent / "tasks.json"
    if tasks_json_path.is_file():
        # --- 多任务模式 ---
        try:
            tasks = load_tasks_json(str(tasks_json_path))
            for task in tasks:
                resolve_body_files(task)
                validate_config(task)
        except (FileNotFoundError, ValueError) as e:
            logger.error(str(e))
            sys.exit(1)

        # DRY_RUN 预览
        dry_tasks = [t for t in tasks if t.get("dry_run")]
        if dry_tasks:
            for task in dry_tasks:
                logger.info(f"\n{'=' * 50}")
                logger.info(f"预览任务：{task['name']}")
                dry_run_preview(task)
            # 如果所有任务都是 dry_run，预览后退出
            if len(dry_tasks) == len(tasks):
                sys.exit(0)

        # 过滤掉 dry_run 的任务，运行其余
        active_tasks = [t for t in tasks if not t.get("dry_run")]
        if not active_tasks:
            logger.info("所有任务均为 DRY_RUN 模式，无实际发送任务，退出。")
            sys.exit(0)
        _run_multi_mode(active_tasks)
        return

    # --- 单任务模式（.env） ---
    try:
        config = load_config()
        logger.info("配置文件加载成功。")
        resolve_body_files(config)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    try:
        validate_config(config)
    except (ValueError, FileNotFoundError) as e:
        logger.error(f"配置校验失败：{e}")
        sys.exit(1)

    if config["dry_run"]:
        dry_run_preview(config)
        sys.exit(0)

    if config["schedule_type"] == "cron":
        _run_cron_mode(config)
    else:
        _run_once_mode(config)


if __name__ == "__main__":
    # 缺少依赖时的友好提示
    try:
        import dotenv       # noqa: F401
        import apscheduler  # noqa: F401
    except ImportError as e:
        print(f"缺少依赖：{e}")
        print("请运行：pip install -r requirements.txt")
        sys.exit(1)

    main()
