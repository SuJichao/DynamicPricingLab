"""
【程序目的】
对独飞航线建议价格进行规则后处理：
  - 情况6：NS 航班行李门槛（29-31折之间提价到31折）
  - 情况8：航线兜底底价设置
  - 输出格式化
"""

import uuid
import numpy as np
import pandas as pd

from config.pricing_constants import (
    SOLO_FLT_BOTTOM_DISCOUNT,
    SOLO_FLT_PRICE_FLOOR_ABSOLUTE,
    SOLO_NS_BAGGAGE_LOWER_DISCOUNT,
    SOLO_NS_BAGGAGE_TARGET_DISCOUNT,
    round_to_10,
)
from config.db_queries import FLIGHT_PRICE_BOTTOM_SQL
from common.database_oracle import get_data


# ============================================================
# 辅助函数
# ============================================================

def _apply_ns_baggage_rule(df):
    """情况6：NS 航班（不含 PKX 进出港）在 29-31 折之间提价到 31 折（含行李）。"""
    mask = (
        (df['AIR_CODE'] == 'NS')
        & ~(df['FLT_ROUTE'].str.contains('PKX'))
        & (df['ADVICE_PRICE'] / df['PRICE'] >= SOLO_NS_BAGGAGE_LOWER_DISCOUNT)
        & (df['ADVICE_PRICE'] / df['PRICE'] < SOLO_NS_BAGGAGE_TARGET_DISCOUNT)
    )
    df['ADVICE_PRICE'] = np.where(
        mask,
        df['PRICE'] * SOLO_NS_BAGGAGE_TARGET_DISCOUNT,
        df['ADVICE_PRICE']
    )
    return df


def _apply_route_floor_price(df):
    """情况8：航线兜底底价设置。

    1. 获取航线自定义底价（MXZ_DP_PRICE_CONTRAL 表）
    2. 筛选在有效期内的记录
    3. 未设置底价的航线使用默认底价：max(全票价 × 1折, 200)
    4. 最终建议价格不低于底价且不高于全票价
    """
    # 获取航线兜底价格数据
    df = pd.merge(df, get_data(f"SELECT * FROM {FLIGHT_PRICE_BOTTOM_SQL}"),
                  on=['FLT_SEGMENT', 'AIR_CODE', 'FLT_NO'], how='left')

    # 分离无底价记录，筛选有效期内的有底价记录
    no_floor = df[df['PRICE_BOTTOM'].isna()].copy()
    df = df[(df['FLT_DATE'] >= df['BEGIN_DATE']) & (df['FLT_DATE'] <= df['END_DATE'])]
    df = pd.concat([df, no_floor], ignore_index=True)

    # 未设置底价的航线：按折扣计算（不低于绝对底价 200）
    df['PRICE_BOTTOM'].fillna(
        np.maximum(round_to_10(df['PRICE'] * SOLO_FLT_BOTTOM_DISCOUNT),
                   SOLO_FLT_PRICE_FLOOR_ABSOLUTE),
        inplace=True
    )

    # 最终建议价格：底价 ≤ ADVICE_PRICE ≤ 全票价，取整到10
    df['ADVICE_PRICE'] = np.maximum(df['ADVICE_PRICE'], df['PRICE_BOTTOM'])
    df['ADVICE_PRICE'] = df['ADVICE_PRICE'].astype(float)
    df['ADVICE_PRICE'] = np.minimum(round_to_10(df['ADVICE_PRICE']), df['PRICE'])
    return df


def _format_output(df, config):
    """格式化输出：选择列、重命名、添加占位列、固定列序。"""

    output = df[['CATCH_DATE', 'TIME_PT', 'EX_DIF', 'DOW', 'FLT_DATE', 'AIR_CODE', 'FLT_NO', 'FLT_SEGMENT', 'FLT_ROUTE',
        'HXJG_FLAG', 'DEP_HOUR', 'DEP_MINUTE', 'CAP', 'DISCAP', 'BKD', 'PRICE_OTA', 'PRICE', 'PJPJ_FINAL', 'SRS_SALES',
        'PJPJ_SALES', 'BKD_PLF_EST', 'SRS_ZL_LEFT', 'T_FLAG', 'ADVICE_PRICE', 'CREATE_TIME'
    ]].copy()

    output.rename(columns={
        'HXJG_FLAG': 'IS_STOPOVER_FLT',
        'PRICE': 'FULL_PRICE',
        'BKD_INCOME_LEFT': 'EXPECTED_RETURN',
        'SRS_ZL_LEFT': 'BKD_ISSUED_NUM_INC',
        'ADVICE_PRICE': 'AVG_FARE_SK'

    }, inplace=True)
    output.reset_index(drop=True, inplace=True)

    # 占位列（保持与其他航线模块的列对齐）
    output['FLT_NO'] = output['AIR_CODE'] +output['FLT_NO']
    output['WBD_ID'] = 0
    output['AVG_FARE_SK_IND'] = 0
    output['AVG_FARE_DELTA'] = 0
    output['PSG_CHO_PROB'] = 0
    output['PROB_PRIOR'] = 0
    output['PSG_CHO_PROB_DELTA'] = 0
    output['MAX_DEP_HOUR'] = 0
    output['OBJECT_FLT'] = 'MF8888'
    output['IND_BKD_ISSUED_NUM_INC'] = 0
    output['PID'] = [str(uuid.uuid1()) for _ in range(len(output))]
    output['EXPECTED_RETURN'] = 0

    # 固定列序
    result = output[[
        'CATCH_DATE', 'EX_DIF', 'TIME_PT', 'FLT_DATE', 'AIR_CODE', 'FLT_NO',
        'FLT_SEGMENT', 'FLT_ROUTE', 'IS_STOPOVER_FLT', 'DEP_HOUR', 'DEP_MINUTE',
        'WBD_ID', 'CAP', 'DISCAP', 'FULL_PRICE', 'BKD', 'AVG_FARE_SK',
        'AVG_FARE_SK_IND', 'AVG_FARE_DELTA', 'PSG_CHO_PROB', 'PROB_PRIOR',
        'PSG_CHO_PROB_DELTA', 'MAX_DEP_HOUR', 'OBJECT_FLT',
        'IND_BKD_ISSUED_NUM_INC', 'BKD_ISSUED_NUM_INC', 'EXPECTED_RETURN',
        'CREATE_TIME', 'PID',
    ]]
    return result


# ============================================================
# 主函数
# ============================================================

def rule_post_processing(config, data):
    """独飞航线定价规则后处理入口。

    依次应用：
      1. NS 航班行李门槛规则
      2. 航线兜底底价规则
      3. 输出格式化
    """
    # logging.info("【SoloFltPriceUpDown】%s 程序开始！", config.version_number)
    df = data.copy()
    df = _apply_ns_baggage_rule(df)
    df = _apply_route_floor_price(df)
    result = _format_output(df, config)

    return result
