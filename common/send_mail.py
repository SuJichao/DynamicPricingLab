"""
【程序目的】
实现云桌面程序对外发送邮件的功能，包括发送报警邮件和定时清理发件箱。

【修改记录】
2026-06-06 重构：凭据外部化、参数规范化、添加错误处理/日志、新增发件箱清理功能
"""
import logging

import zmail

from config.config import (
    EMAIL_USERNAME, EMAIL_PASSWORD,
    EMAIL_POP_HOST, EMAIL_IMAP_HOST,
    EMAIL_SENT_KEEP_DAYS, EMAIL_SENT_KEEP_MAX,
)

logger = logging.getLogger('send_mail')

__all__ = ('send_mail', 'clean_sent_mails')


def send_mail(subject, content_text, recipients=None, content_html=None, attachments=None):
    """
    发送邮件。

    Args:
        subject: 邮件主题
        content_text: 纯文本内容
        recipients: 收件人列表或单个收件人字符串，默认 ['sujichao_123@163.com']
        content_html: HTML 内容（可选，传入字符串或字符串列表）
        attachments: 附件路径列表（可选）
    Returns:
        bool: 发送成功返回 True，失败返回 False
    """
    if recipients is None:
        recipients = ['sujichao_123@163.com']
    if isinstance(recipients, str):
        recipients = [recipients]
    if content_html is None:
        content_html = []
    elif isinstance(content_html, str):
        content_html = [content_html]
    if attachments is None:
        attachments = []
    elif isinstance(attachments, str):
        attachments = [attachments]

    try:
        # zmail 会根据 EMAIL_POP_HOST 自动推断 SMTP 地址
        server = zmail.server(
            username=EMAIL_USERNAME,
            password=EMAIL_PASSWORD,
            pop_host=EMAIL_POP_HOST,
        )

        mail = {
            'subject': subject,
            'content_text': content_text,
            'content_html': content_html,
            'attachments': attachments,
        }

        server.send_mail(recipients, mail)
        logger.info('邮件发送成功 | Subject=%s | Recipients=%s', subject, recipients)
        return True

    except Exception as e:
        logger.error('邮件发送失败 | Subject=%s | Recipients=%s | Error=%s',
                     subject, recipients, e, exc_info=True)
        return False


def _get_imap_connection():
    """
    尝试连接 IMAP 服务器，自动轮询多个地址和端口。
    Returns:
        (conn, host): 成功时返回 (IMAP4_SSL 对象, 主机名)，失败时返回 (None, None)
    """
    import imaplib
    import socket

    # 待尝试的 IMAP 服务器地址列表
    host_candidates = [
        EMAIL_IMAP_HOST,
        'imap.' + EMAIL_USERNAME.split('@')[1],
    ]
    # 去重
    seen = set()
    unique_hosts = []
    for h in host_candidates:
        if h and h not in seen:
            seen.add(h)
            unique_hosts.append(h)

    # 优先 SSL 993，降级 143
    port_ssl = 993
    port_plain = 143

    for host in unique_hosts:
        # 尝试 SSL 连接
        try:
            conn = imaplib.IMAP4_SSL(host=host, port=port_ssl, timeout=10)
            logger.info('IMAP 连接成功 | host=%s:%s', host, port_ssl)
            return conn, host
        except (imaplib.IMAP4.error, socket.error, OSError) as e:
            logger.debug('IMAP SSL 连接失败 | host=%s:%s | Error=%s', host, port_ssl, e)

        # 降级尝试普通连接 + STARTTLS
        try:
            conn = imaplib.IMAP4(host=host, port=port_plain, timeout=10)
            conn.starttls()
            logger.info('IMAP 连接成功（STARTTLS）| host=%s:%s', host, port_plain)
            return conn, host
        except (imaplib.IMAP4.error, socket.error, OSError) as e:
            logger.debug('IMAP STARTTLS 连接失败 | host=%s:%s | Error=%s', host, port_plain, e)

    logger.error('所有 IMAP 服务器均连接失败，请检查网络或服务器地址')
    return None, None


def _find_sent_folder(conn):
    """
    自动探测发件箱文件夹名称。
    Returns:
        str: 文件夹名称（带引号），未找到时返回 None
    """
    # 常见发件箱名称（按优先级排列）
    candidates = [
        '"Sent"',
        '"Sent Items"',
        '"Sent Messages"',
        '"已发送"',
        '"已发送邮件"',
    ]

    for folder in candidates:
        try:
            status, _ = conn.select(folder)
            if status == 'OK':
                logger.info('发件箱文件夹已定位 | folder=%s', folder)
                return folder
        except Exception:
            continue

    # 都未匹配时列出所有文件夹供排查
    try:
        status, folders = conn.list()
        if status == 'OK':
            folder_names = []
            for item in folders:
                decoded = item.decode('utf-8', errors='replace')
                folder_names.append(decoded)
            logger.warning('未找到发件箱文件夹，可用文件夹列表: %s', folder_names)
    except Exception as e:
        logger.warning('列出文件夹失败: %s', e)

    return None


def clean_sent_mails(keep_days=None, keep_max=None):
    """
    清理发件箱中的已发送邮件。

    支持按天数清理和按数量清理两种策略，同时指定时先按天数再按数量。
    都未指定时使用 config.py 中的默认值。

    Args:
        keep_days: 保留最近 N 天的邮件（None 使用默认值 30）
        keep_max: 保留最近 N 封邮件（None 使用默认值 200）
    Returns:
        bool: 操作成功返回 True，失败返回 False
    """
    if keep_days is None:
        keep_days = EMAIL_SENT_KEEP_DAYS
    if keep_max is None:
        keep_max = EMAIL_SENT_KEEP_MAX

    conn = None
    try:
        # 1. 连接 IMAP 服务器
        conn, _ = _get_imap_connection()
        if conn is None:
            return False

        # 2. 登录
        conn.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        logger.info('IMAP 登录成功 | user=%s', EMAIL_USERNAME)

        # 3. 定位发件箱文件夹
        sent_folder = _find_sent_folder(conn)
        if sent_folder is None:
            logger.error('无法定位发件箱文件夹，跳过清理')
            return False

        # 4. 按天数清理
        if keep_days > 0:
            try:
                from datetime import datetime, timedelta
                before_date = (datetime.now() - timedelta(days=keep_days)).strftime('%d-%b-%Y')
                status, msg_ids = conn.search(None, f'(BEFORE {before_date})')

                if status == 'OK' and msg_ids[0]:
                    ids = msg_ids[0].split()
                    delete_count = len(ids)
                    for msg_id in ids:
                        conn.store(msg_id, '+FLAGS', '\\Deleted')
                    conn.expunge()
                    logger.info('按天数清理完成 | keep_days=%s | 删除邮件数=%s', keep_days, delete_count)
                else:
                    logger.info('按天数清理：无需清理 | keep_days=%s', keep_days)

            except Exception as e:
                logger.error('按天数清理失败 | keep_days=%s | Error=%s', keep_days, e, exc_info=True)

        # 5. 按数量清理（在按天数清理之后执行）
        if keep_max > 0:
            try:
                status, msg_ids = conn.search(None, 'ALL')
                if status == 'OK' and msg_ids[0]:
                    all_ids = msg_ids[0].split()
                    total = len(all_ids)
                    if total > keep_max:
                        delete_count = total - keep_max
                        # 最旧的邮件 ID 最小，删除最旧的
                        ids_to_delete = all_ids[:delete_count]
                        for msg_id in ids_to_delete:
                            conn.store(msg_id, '+FLAGS', '\\Deleted')
                        conn.expunge()
                        logger.info('按数量清理完成 | keep_max=%s | 原邮件数=%s | 删除邮件数=%s',
                                    keep_max, total, delete_count)
                    else:
                        logger.info('按数量清理：无需清理 | keep_max=%s | 当前邮件数=%s', keep_max, total)

            except Exception as e:
                logger.error('按数量清理失败 | keep_max=%s | Error=%s', keep_max, e, exc_info=True)

        logger.info('发件箱清理完成 | keep_days=%s | keep_max=%s', keep_days, keep_max)
        return True

    except Exception as e:
        logger.error('发件箱清理失败 | Error=%s', e, exc_info=True)
        return False

    finally:
        if conn is not None:
            try:
                conn.close()
                conn.logout()
            except Exception:
                pass
