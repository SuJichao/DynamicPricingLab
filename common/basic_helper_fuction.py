import logging
import multiprocessing as mp
import os
import sys
import datetime
import time
import numpy as np
import schedule
from common.send_mail import send_mail
from common.get_logger import get_logger
from common.database_oracle import callproc, get_data
from config.runtime_args import get_argparse

from config.pricing_constants import (
    TIMING_MIN_EXECUTION_SECONDS,
    TIMING_SLEEP_SECONDS,
    TIMING_MAX_EXECUTION_SECONDS,
    ENV_DISABLE_MULTIPROCESSING,
)
from config.db_queries import (
    FLT_LIST_TABLE, 
    SMALL_PART_KNN_PREDICT_TABLE, 
    SOLO_ADVICE_PRICE_PREDICT_TABLE,
    )
# =============================================================
# 1 基础辅助型函数
# =============================================================
# 模块级多进程状态标志
_multiprocessing_enabled = True


def _is_debugger_attached():
    """检测当前进程是否在调试器（PyCharm / VSCode 等）中运行。

    原理：
        Python 调试器（pydevd / debugpy）通过 sys.settrace() 注入 trace function，
        因此 sys.gettrace() 返回非 None 即表示调试器已附加。

    Returns:
        bool: True 表示调试器已附加
    """
    return hasattr(sys, 'gettrace') and sys.gettrace() is not None


def _init_multiprocessing():
    """初始化多进程环境，并返回是否启用多进程。

    Windows 上设置 spawn 启动方式。
    以下情况会禁用多进程，强制使用单进程模式：
        - 调试器已附加（PyCharm / VSCode 等），避免断点导致子进程 pipe 阻塞崩溃
        - 环境变量 DISABLE_MULTIPROCESSING 已设置

    Returns:
        bool: True 表示多进程可用，False 表示已禁用（应使用单进程模式）
    """
    global _multiprocessing_enabled

    if _is_debugger_attached():
        logging.info("检测到调试器已附加，自动禁用多进程模式")
        _multiprocessing_enabled = False
        return False

    if os.environ.get(ENV_DISABLE_MULTIPROCESSING):
        logging.info("环境变量 %s 已设置，禁用多进程模式", ENV_DISABLE_MULTIPROCESSING)
        _multiprocessing_enabled = False
        return False

    if sys.platform.startswith('win'):
        mp.freeze_support()
        mp.set_start_method('spawn', force=True)

    _multiprocessing_enabled = True
    return True


def is_multiprocessing_enabled():
    """供其他模块查询多进程是否启用。

    Returns:
        bool: True 表示多进程可用，False 表示已禁用
    """
    return _multiprocessing_enabled

def _alert_error(error):
    """记录异常堆栈并发送报警邮件。
    Args:
        error: Exception 对象
    """
    logging.error(error, exc_info=True)
    send_mail('【动态定价程序报错】',
              f'动态定价程序报错！请及时前往云桌面检查。\n\n错误信息为：{error}')

def should_run(create_time):
    """根据进程已运行时长判断是否继续执行预测。

    Args:
        args: argparse 命名空间
    Returns:
        True 应执行 run()，False 应跳过
    """
    elapsed = (datetime.datetime.now() - create_time).total_seconds()
    if elapsed < TIMING_MIN_EXECUTION_SECONDS:
        logging.warning('===进程执行完毕后暂停10s！===')
        time.sleep(TIMING_SLEEP_SECONDS)
        return True
    if elapsed > TIMING_MAX_EXECUTION_SECONDS:
        logging.warning('===进程执行时间超过15分钟，自动跳过本次程序执行！===')
        return False
    return True

def catch_data_timeliness():
    """监控数据采集管道是否过期（超过 150 分钟发邮件报警）。
        Args:
        args: argparse 命名空间
    """
    args = get_argparse()
    now_create_time = get_data('SELECT MAX(UP_DATE) FROM KD_FUTURE_TMP_SJC_NEW').values[0][0]
    sysdate = np.datetime64(args.create_time)
    catch_time = np.datetime64(now_create_time)

    td_in_seconds = (sysdate - catch_time) / np.timedelta64(1, 's')
    td_in_minutes = td_in_seconds // 60

    if td_in_minutes > 150:
        logging.warning('动态定价采集程序过期超过150分钟，后续数据缺失，请注意检查相关程序！！！')
        send_mail('【动态定价采集程序报错】',
                  '动态定价采集程序过期超过150分钟！请及时前往云桌面检查。')

def data_timeliness(args):
    """检查数据时效性，判断最新批次数据是否已到位。

    Args:
        args: argparse 命名空间

    Returns:
        True 数据已到位可执行，False 数据过期应跳过
    """
    date = args.file_create_date
    hour = str(args.file_create_hour).zfill(2)
    minute = '00'

    # 采集数据最新批次
    now_catch_time = get_data('SELECT MAX(CATCH_TIME) FROM KD_FUTURE_TMP_SJC_NEW').values[0][0]

    # 根据当前应有时间戳查看采集源头表是否有数据
    catch_time = f'{hour}:{minute}'
    tmp_time_flag = get_data(
        f"SELECT * FROM TB_DAQ_LOG WHERE CATCH_DATE=DATE'{date}' "
        f"AND CATCH_TIME='{catch_time}' AND TITLE='已整合'")
    if tmp_time_flag.empty or now_catch_time == catch_time:
        return False
    return True

def _show_menu():
    """显示交互菜单，返回用户选择。无效输入返回 -1。"""
    _MENU_PROMPT = (
        "=====任务列表=====\n"
        "==【1】立即执行动态定价程序（不刷新数据）\n"
        "==【2】立即执行动态定价程序（刷新数据）\n"
        "==【3】定时执行动态定价程序（刷新数据）\n"
        "==【4】清理发件箱\n"
        "==输入序号选择要执行的任务："
    )
    try:
        return int(input(_MENU_PROMPT))
    except ValueError:
        return -1

# =============================================================
# 2 基础功能型函数
# =============================================================
def getpredictdata(args):
    """从数据库获取待预测数据，按航线类型整合后返回。
        Args:
        args: argparse 命名空间
    """
    # 1 获取小份额航线待预测数据
    predict_data = get_data(f"SELECT * FROM {SMALL_PART_KNN_PREDICT_TABLE}")
    small_part_flt_data = {
        'predict_data': predict_data
    }

    # 2 获取大份额航线待预测数据

    # 3 获取独飞航线待预测数据
    solo_flt_predict_data = get_data(f"SELECT * FROM {SOLO_ADVICE_PRICE_PREDICT_TABLE}")
    solo_part_flt_data = {
        'predict_data': solo_flt_predict_data
    }

    # 4 整合不同类型的数据
    data_set = {
        'SMALL_PART': small_part_flt_data,
        'SOLO_PART': solo_part_flt_data
    }

    # 获取所有航线类型
    flt_list = get_data(f"SELECT DISTINCT FLT_TYPE FROM {FLT_LIST_TABLE} WHERE FLT_TYPE='SOLO_PART'").values.tolist()

    return data_set, flt_list