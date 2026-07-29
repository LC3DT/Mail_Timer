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
import time
import logging
import threading
import smtplib
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
        # 附件
        "attachments": _parse_list(os.getenv("ATTACHMENTS", "")),
        # 调度模式
        "schedule_type": os.getenv("SCHEDULE_TYPE", "once").lower(),
        "schedule_time": os.getenv("SCHEDULE_TIME", ""),
        "schedule_cron": os.getenv("SCHEDULE_CRON", ""),
    }

    return config


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
) -> MIMEMultipart:
    """构建完整的 MIME 邮件对象（含抄送、正文、附件）。"""
    msg = MIMEMultipart("mixed")
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = email_utils.formatdate(localtime=True)

    # 正文（alternative：纯文本 / HTML）
    body_part = MIMEMultipart("alternative")
    if body_text:
        body_part.attach(MIMEText(body_text, "plain", "utf-8"))
    if body_html:
        body_part.attach(MIMEText(body_html, "html", "utf-8"))
    msg.attach(body_part)

    # 附件
    for file_path in attachments:
        _attach_file(msg, file_path)

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
    logger.info("[Trigger] Cron 触发，开始执行发送任务...")
    success = send_email(config)
    if success:
        logger.info("本次发送完成，等待下一次 cron 触发...")
    else:
        logger.error("本次发送失败，等待下一次 cron 触发...")


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
# 主入口
# ============================================================
def main() -> None:
    """程序入口。"""
    logger.info("=" * 50)
    logger.info("[Mail] 邮件定时发送程序 启动")

    # 加载 & 校验配置
    try:
        config = load_config()
        logger.info("配置文件加载成功。")
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    try:
        validate_config(config)
    except (ValueError, FileNotFoundError) as e:
        logger.error(f"配置校验失败：{e}")
        sys.exit(1)

    # 按模式运行
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
