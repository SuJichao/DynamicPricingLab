# 辅助主程序的包

import logging
import time
import schedule

# 辅助主程序的相关子模块
from common.get_logger import get_logger
from config.runtime_args import get_argparse
from common.send_mail import clean_sent_mails
from common.database_oracle import callproc, delete_data
from common.data_storage import data_storage
from common.DataTemporaryProcessing import advice_price_output, delete_deduplication_data
from common.basic_helper_fuction import _init_multiprocessing, _alert_error, _show_menu, should_run, catch_data_timeliness, data_timeliness, getpredictdata
from config.db_queries import (FLT_LIST_TABLE, TO_RM_SYSDATE_RESULT_DATA, EST_DATA_PROCEDURE_NAME)

# 主要业务场景
from blocks.SmallPartFlight.SmallPartFlightAdvicePriceLine import small_part_flight_advice_price
from blocks.SoloPartFlight.SoloPartFlightAdvicePriceLine import solo_part_flight_advice_price

# 航班类型 → 预测执行函数 dispatch 表
_FLIGHT_TYPE_HANDLERS = {
    'SMALL_PART': small_part_flight_advice_price,
    'SOLO_PART': solo_part_flight_advice_price,
}

# =============================================================
# 1 基础辅助型函数
# =============================================================
def _execute_manual_run(refresh_data=False):
    """执行单次手动定价（菜单 1 和 2 共用）。

    Args:
        args: argparse 命名空间（已创建）
        refresh_data: True 时先调用 DP_EST_DATA_CHG 刷新数据
    """
    args = get_argparse()
    logging.info(
        f'<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<【航班动态定价托管】{args.version_number} 程序开始！>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>')
    if refresh_data:
        callproc(f'{EST_DATA_PROCEDURE_NAME}')
    run(args)
    delete_deduplication_data()

def _start_scheduler_loop():
    """注册定时任务并进入 schedule 轮询循环。

    注册三个定时任务：
      - 每分钟 :00 执行 timeliness_assessment，判断最新的采集数据是否到位
      - 每小时 :00 执行 catch_data_timeliness，判断采集数据是否有出现长时间没到位的情况
      - 每天 03:00 清理发件箱
    通过 schedule.run_pending() 轮询触发，支持 Ctrl+C 优雅退出。
    """
    schedule.every(1).minutes.at(":00").do(timeliness_assessment)
    schedule.every(1).hour.at(":00").do(catch_data_timeliness)
    schedule.every().day.at("03:00").do(clean_sent_mails)

    logging.info("定时任务已注册，进入轮询模式...")
    while True:
        schedule.run_pending()
        time.sleep(1)

# =============================================================
# 2 基础功能型函数
# =============================================================
def _process_flight_type(args, flt_type, data_set):
    """验证数据完整性，执行预测，写入存储。

    Args:
        args: argparse 命名空间
        flt_type: 航班类型（'SMALL_PART' / 'SOLO_PART'）
        data_set: _getpredictdata 返回的字典，按 flt_type 索引
    """
    predict_func = _FLIGHT_TYPE_HANDLERS.get(flt_type)
    if predict_func is None:
        logging.warning(f"未知航线类型 {flt_type}，跳过。")
        return

    if data_set[flt_type]['predict_data'].empty:
        delete_data(
            f"DELETE FROM {TO_RM_SYSDATE_RESULT_DATA} WHERE FLT_SEGMENT IN "
            f"(SELECT FLT_SEGMENT FROM {FLT_LIST_TABLE} WHERE FLT_TYPE='{flt_type}')")
        logging.warning(f"{flt_type}航线待预测数据缺失，程序跳过不予执行！")
        return

    result_data = predict_func(args)
    data_storage(args, flt_type, result_data)
    logging.info(f'==============={flt_type}航班价格建议完成！===============')

# =============================================================
# 主函数
# =============================================================
def run(args):
    mp_enabled = _init_multiprocessing()
    if not mp_enabled:
        logging.info("多进程已禁用，程序将以单进程模式运行")
    # 1 获取待预测数据
    data_set, flt_list = getpredictdata(args)
    # 2 根据不同类型的航班进行处理
    for tmp_flt_list in flt_list:
        flt_type = tmp_flt_list[0]
        try:
            _process_flight_type(args, flt_type, data_set)
        except Exception as e:
            _alert_error(e)
            delete_data(
                f"DELETE FROM {TO_RM_SYSDATE_RESULT_DATA} WHERE FLT_SEGMENT IN (SELECT FLT_SEGMENT FROM {FLT_LIST_TABLE})")
            logging.warning('航班动态定价托管程序执行失败！')

    # 建议价格数据输出和处理
    try:
        pass
        advice_price_output()
    except Exception as e:
        _alert_error(e)


def timeliness_assessment():
    mp_enabled = _init_multiprocessing()
    args = get_argparse()
    if not mp_enabled:
        logging.info("多进程已禁用，程序将以单进程模式运行")
    # 判断为真，说明最新批次的数据已经到位，否则不予执行
    if not data_timeliness(args):
        # logging.warning('===数据过期，自动跳过本次程序执行！！！===')
        return
    logging.info(f'<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<【航班动态定价托管】{args.version_number} 程序开始！>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>')
    try:
        callproc(f'{EST_DATA_PROCEDURE_NAME}')
    except Exception as e:
        _alert_error(e)

    if should_run(args.create_time):
        run(args)


if __name__ == '__main__':
    _init_multiprocessing()
    get_logger()
    choice = _show_menu()
    if choice in (1, 2):
        _execute_manual_run(refresh_data=(choice == 2))
        _start_scheduler_loop()
    elif choice == 3:
        _start_scheduler_loop()
    elif choice == 4:
        clean_sent_mails()
    else:
        logging.warning(f"无效的菜单选项: {choice}")