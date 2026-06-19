"""
【程序目的】
对独飞航班的订座突增进行检测，并在检测到突增时触发价格上涨。
作为 KNN 预测与基础定价之间的独立步骤运行。
"""
import logging
import uuid

import numpy as np
import pandas as pd

from config.pricing_constants import (
    SOLO_BKD_SURGE_D0_DIVISOR,
    SOLO_BKD_SURGE_D2_D7_DIVISOR,
    SOLO_BKD_SURGE_D8_DIVISOR,
    SOLO_BKD_SURGE_LOAD_THRESHOLD,
    SOLO_BKD_SURGE_STEP_CAP,
    SOLO_FLT_DISCOUNT_PER_TFLAG,
    round_to_10,
)
from config.db_queries import RB_OTA_DATA_SQL, SOLO_PREVIOUS_PRICE_TABLE
from common.database_oracle import get_data, delete_data, insert_data


# ============================================================
# 辅助函数
# ============================================================

def _fetch_previous_ota_prices():
    """获取上一采集时点的外放价格和订座人数。"""
    return get_data(
        f"SELECT FLT_DATE,CARRIER AS AIR_CODE,FLT_NO,FLT_SEGMENT,BKD_OLD FROM {SOLO_PREVIOUS_PRICE_TABLE}"
    )


def _calc_booking_increment(df):
    """计算订座增量 BKD_INC，防止多个连续时点未采集导致计算异常。"""
    df['BKD_INC'] = (
        (df['BKD'] - df['BKD_OLD'])/df['TIME_PT']
    )
    return df


def _calc_price_increase(df):
    """根据 EX_DIF 和 BKD_INC 计算涨价折数。D0-1:/5, D2-7:/3, D8+:/1, 封顶1折。"""
    bkd_inc = df['BKD_INC'].fillna(0)
    df['PRICE_INCREASE'] = np.select(
        [df['EX_DIF'] <= 1,
         (df['EX_DIF'] >= 2) & (df['EX_DIF'] <= 7),
         df['EX_DIF'] >= 8],
        [bkd_inc // SOLO_BKD_SURGE_D0_DIVISOR,
         bkd_inc // SOLO_BKD_SURGE_D2_D7_DIVISOR,
         bkd_inc // SOLO_BKD_SURGE_D8_DIVISOR],
        default=0
    )
    df['PRICE_INCREASE'] = df['PRICE_INCREASE'].fillna(0)
    df['PRICE_INCREASE'] = np.minimum(
        np.floor(df['PRICE_INCREASE']), SOLO_BKD_SURGE_STEP_CAP
    )
    return df


def _apply_surge(df):
    """对满足条件的航班应用突增提价。PRICE_INCREASE>=1 且客座率>阈值时触发。"""
    surge_mask = (df['PRICE_INCREASE'] >= 1) & (df['BKD_PLF_EST'] > SOLO_BKD_SURGE_LOAD_THRESHOLD)
    df['ADVICE_PRICE'] = np.where(
        surge_mask,
        df['PRICE_OTA'] + round_to_10(
            df['PRICE_INCREASE'] * df['PRICE'] * SOLO_FLT_DISCOUNT_PER_TFLAG
        ),
        df['PRICE_OTA']
    )
    surge_count = surge_mask.sum()
    logging.info("bkd_sharp_rise: 检测到 %d 条航班触发订座突增提价", surge_count)
    return df


def _persist_surge_records(config,df):
    """将触发突增的航班记录持久化到数据库，并删除旧的重复记录。"""
    surge_records = df[df['PRICE_INCREASE'] >= 1][
        ['CATCH_DATE', 'EX_DIF', 'FLT_DATE', 'TIME_PT', 'AIR_CODE',
         'FLT_NO', 'FLT_SEGMENT', 'ADVICE_PRICE', 'BKD_INC']
    ].copy()

    surge_records.reset_index(drop=True, inplace=True)

    if len(surge_records) == 0:
        return
    
    surge_records['CREATE_TIME'] = config.create_time
    surge_records['PID'] = [str(uuid.uuid1()) for _ in range(len(surge_records))]
    insert_data("BKD_SUDDEN_INCREASE_RECORD", surge_records)

    # 删除多次插入的旧突增数据，每条航班只保留最新一条
    delete_data("""
        DELETE FROM BKD_SUDDEN_INCREASE_RECORD S
        WHERE PID IN
        (
        SELECT PID
        FROM
        (
          SELECT A.*,ROW_NUMBER () OVER (PARTITION BY A.FLT_DATE,A.FLT_NO,A.FLT_SEGMENT ORDER BY A.CREATE_TIME DESC) RN
          FROM BKD_SUDDEN_INCREASE_RECORD A
        )WHERE RN!=1
        )
    """)


def _load_previous_surge_and_floor(df):
    """加载历史突增记录，确保当前建议价格不低于历史突增价格。"""
    surge_history = get_data(
        "SELECT CATCH_DATE,EX_DIF,FLT_DATE,CARRIER,FLT_NO,FLT_SEGMENT,ADVICE_PRICE AS SUDDEN_INCREASE_ADVICE_PRICE,PID "
        "FROM BKD_SUDDEN_INCREASE_RECORD"
    )
    df = pd.merge(df, surge_history, how='left',
                  left_on=['CATCH_DATE', 'EX_DIF', 'FLT_DATE', 'AIR_CODE', 'FLT_NO', 'FLT_SEGMENT'],
                  right_on=['CATCH_DATE', 'EX_DIF', 'FLT_DATE', 'CARRIER', 'FLT_NO', 'FLT_SEGMENT'])
    df['ADVICE_PRICE'] = np.where(
        df['SUDDEN_INCREASE_ADVICE_PRICE'] > 0,
        np.maximum(df['SUDDEN_INCREASE_ADVICE_PRICE'], df['PRICE_OTA']),
        df['PRICE_OTA']
    )
    return df


# ============================================================
# 主函数
# ============================================================

def bkd_sharp_rise(config, data):
    """订座突增检测与调价。

    输入需含以下列（来自 KNN 输出 + 编排层预计算的 BKD_PLF_EST）：
        FLT_DATE, CATCH_DATE, FLT_SEGMENT, EX_DIF, TIME_PT,
        CARRIER, FLT_NO, PRICE, BKD, BKD_PLF_EST

    返回增加 AVG_FARE_SK、PRICE_INCREASE、BKD_INC 列的 DataFrame。
    """
    # logging.info("bkd_sharp_rise: 开始处理，输入 %d 行", len(data))
    df = data.copy()
    df.reset_index(drop=True, inplace=True)
    # 计算预测客座率
    df['BKD_PLF_EST'] = (df['SRS_ZL_LEFT'] + df['BKD']) / df['CAP']

    # 1. 合并上一时点订座数据
    prev_prices = _fetch_previous_ota_prices()
    df = pd.merge(df, prev_prices, how='left',
                  on=['FLT_DATE', 'AIR_CODE', 'FLT_NO', 'FLT_SEGMENT'])

    # 2. 计算订座增量与涨价折数
    df = _calc_booking_increment(df)
    df = _calc_price_increase(df)

    # 3. 应用突增提价
    df = _apply_surge(df)

    # 4. 持久化突增记录
    _persist_surge_records(config, df)

    # 5. 加载历史突增，确保价格在一定时间内不回调
    df = _load_previous_surge_and_floor(df)

    # logging.info("bkd_sharp_rise: 处理完成，输出 %d 行", len(df))
    return df
