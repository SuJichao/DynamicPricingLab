#!/usr/bin/env python
# coding:utf-8
"""
【程序目的】
实现程序的日志分级、输出和记录等相关功能。
"""

import logging
import os
from logging.handlers import RotatingFileHandler

__all__ = ['get_logger']


def get_logger(name=None, log_path=None, log_level=logging.INFO):
    """配置并返回 logger，同时输出到控制台和日志文件。

    === 用法 ===
        from common.get_logger import get_logger
        get_logger()              # 一行搞定，控制台 + 文件同时输出
        logging.info('任意信息')   # 直接用 logging 模块

    === 设计要点 ===
    1. 日志路径统一从 config.config.LOG_PATH 读取，一处修改全局生效
    2. 多次调用 get_logger() 是幂等的 —— 已在的 handler 不会重复添加
    3. 日志文件自动轮转（每个文件 10MB，保留 5 个备份），防止磁盘写满
    4. 日志目录不存在时自动创建，无需手动建文件夹

    Args:
        name:      Logger 名称。传 None 时配置 root logger（推荐，方便 logging.info() 直接使用）。
        log_path:  日志文件路径。传 None 时自动使用 config.config.LOG_PATH 的设定值。
        log_level: 日志级别，默认 logging.INFO（只输出 INFO 及以上级别）。
    Returns:
        logging.Logger 实例。
    """
    # 1. 获取 logger 实例（不传 name 则获取 root logger，与现有代码兼容）
    logger = logging.getLogger(name)
    # 2. 设定日志输出级别（低于此级别的日志不会输出）
    logger.setLevel(log_level)

    # 3. 定义日志输出格式：时间 文件名[行号] 级别 消息
    formatter = logging.Formatter(
        '%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s'
    )

    # ========== 添加控制台输出（StreamHandler）==========
    # 判断是否已存在 StreamHandler（但不包括 FileHandler，因为 FileHandler 也继承自 StreamHandler）
    has_stream = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in logger.handlers
    )
    if not has_stream:
        sh = logging.StreamHandler()
        sh.setLevel(log_level)
        sh.setFormatter(formatter)
        logger.addHandler(sh)

    # ========== 添加文件输出（RotatingFileHandler）==========
    # 如果调用时没传 log_path，则从 config 中读取统一配置的日志路径
    if log_path is None:
        try:
            from config.config import LOG_PATH
        except (ImportError, ModuleNotFoundError):
            _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            LOG_PATH = os.path.join(_project_root, 'logs', 'app.log')
        log_path = LOG_PATH

    # 自动创建日志目录（如果不存在的话）
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # 判断该路径的文件 handler 是否已存在，避免重复添加
    # 用 abspath 做绝对路径比较，防止相对路径写成 "./logs/app.log" 和 "logs/app.log" 被识别为两个 handler
    resolved = os.path.abspath(log_path)
    has_file = any(
        isinstance(h, RotatingFileHandler) and h.baseFilename == resolved
        for h in logger.handlers
    )
    if not has_file:
        # RotatingFileHandler：日志文件超过 maxBytes 时自动重命名归档，避免单个文件无限膨胀
        fh = RotatingFileHandler(log_path, encoding='utf-8', mode='a',
                                 maxBytes=10 * 1024 * 1024, backupCount=5)
        fh.setLevel(log_level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger


if __name__ == '__main__':
    # ========== 测试1：无参数调用 ==========
    # 验证默认行为：控制台输出 + 按 config.LOG_PATH 写日志文件
    log = get_logger()
    log.info('默认配置 - 基础信息')
    log.warning('默认配置 - 警告信息')
    log.error('默认配置 - 错误信息')

    # ========== 测试2：指定日志路径 ==========
    # 验证 log_path 参数可覆盖默认路径，且 DEBUG 级别的日志不输出（log_level 默认 INFO）
    log2 = get_logger(log_path='./logs/test.log')
    log2.info('指定路径 - 基础信息')
    log2.debug('指定路径 - 调试信息（不应显示）')
    log2.warning('指定路径 - 警告信息')
    log2.error('指定路径 - 错误信息')

    # ========== 测试3：连续调用幂等性 ==========
    # 验证再次调用 get_logger() 不会重复添加 handler，日志行不会重复输出
    log3 = get_logger()
    log3.info('连续调用测试 - 此行不应重复')
