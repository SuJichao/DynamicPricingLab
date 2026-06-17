"""
【程序目的】
针对独飞航线，在订座突增检测完成后进行基础定价（AI_ADVICE_PRICE）。
输入需已含 BKD_PLF_EST 和突增检测结果（AVG_FARE_SK、PRICE_INCREASE）。
"""
import logging

import numpy as np
import pandas as pd

from config.runtime_args import get_argparse
from config.pricing_constants import (
    SOLO_FLT_BOTTOM_DISCOUNT,
    SOLO_FLT_DISCOUNT_PER_TFLAG,
    SOLO_FLT_FULL_PRICE_FALLBACK,
    SOLO_FLT_PRICE_MULTIPLIER_MAX,
    SOLO_FLT_PRICE_MULTIPLIER_MIN,
    SOLO_FLT_TARGET_LOAD_FACTOR,
)
from config.db_queries import SOLO_SALES_RATIO_SQL
from common.database_oracle import get_data, insert_data


# ============================================================
# 输出列名常量
# ============================================================

OUTPUT_COLS = [
    'CATCH_DATE', 'CATCH_TIME', 'TIME_PT', 'EX_DIF', 'DOW', 'FLT_DATE',
    'CARRIER', 'FLT_NO', 'FLT_SEGMENT', 'ROUTE', 'HXJG_FLAG', 'DEP_HOUR',
    'DEP_MINUTE', 'CAP', 'DISCAP', 'BKD', 'PRICE_OTA', 'PRICE', 'UP_DATE',
    'PJPJ_MIN', 'PJPJ_RATIO', 'SRS_ZL_DETR_LEFT', 'PJPJ_FINAL',
    'HOL_BEFORE_TWO_DAY', 'HOL_BEFORE_ONE_DAY', 'HOL_AFTER_ONE_DAY',
    'HOL_AFTER_TWO_DAY', 'HOLIDAY_EXACT_DAY', 'HOLIDAY_SPRING_FESTIVAL',
    'HOLIDAY_RANGE', 'HOLIDAY_BEFORE_AND_AFTER', 'HOL_FALG', 'HOL_LAST',
    'LATITUDE_DEP', 'LONGITUDE_DEP', 'LATITUDE_ARR', 'LONGITUDE_ARR',
    'BKD_DEP', 'BKD_ARR', 'CREATE_TIME', 'DEP_TIME', 'YEAR', 'MF_ZL_AHEAD',
    'SRS_SALES', 'PJPJ_SALES', 'T_FLAG', 'BKD_PLF_EST', 'SYZW_PLF',
    'SRS_ZL_LEFT', 'BKD_INCOME_LEFT', 'AI_ADVICE_PRICE',
]


# ============================================================
# SoloFltAdvicePrice
# ============================================================

class SoloFltAdvicePrice(object):
    """独飞航线基础定价。

    前置条件：输入 DataFrame 需已包含 BKD_PLF_EST、AVG_FARE_SK、PRICE_INCREASE
    （由编排层分别在 KNN 预测后和订座突增检测后设置）。
    """

    def __init__(self, config, data):
        self.config = config
        self.bottom_price_demand = data

        # 获取库存限制数据（目前只有 D0-2 的航班数据）
        sales_ratio = get_data(SOLO_SALES_RATIO_SQL)
        sales_ratio = sales_ratio[['FLT_DATE', 'EX_DIF', 'FLT_NO', 'FLT_SEGMENT', 'MF_ZL_AHEAD']]
        self.bottom_price_demand = pd.merge(
            self.bottom_price_demand, sales_ratio,
            on=['FLT_DATE', 'EX_DIF', 'FLT_NO', 'FLT_SEGMENT'], how='left'
        )
        self.bottom_price_demand['MF_ZL_AHEAD'].fillna(0, inplace=True)

        logging.info("【SoloFltAdvicePrice】%s 程序开始！", self.config.version_number)
        self.solo_flt_max_min_price()

    # ----------------------------------------------------------
    # 主流程
    # ----------------------------------------------------------

    def solo_flt_max_min_price(self):
        """基础定价主流程：准备数据 → 计算建议价格 → 持久化。"""
        self._prepare_data()
        self._compute_advice_price()
        self._persist_result()

    # ----------------------------------------------------------
    # 数据准备
    # ----------------------------------------------------------

    def _prepare_data(self):
        """填充缺失值、合并历史销售数据、计算辅助特征。"""
        df = self.bottom_price_demand
        df['PRICE'].fillna(SOLO_FLT_FULL_PRICE_FALLBACK, inplace=True)

        # 合并独飞历史1天销售数据
        hist_sales = get_data(
            'SELECT FLT_DATE,CARRIER,FLT_NO,FLT_SEGMENT,SRS_SALES,PJPJ_SALES,T_FLAG '
            'FROM TMP_DP_SOLO_SRS_HIS_PH'
        )
        df = pd.merge(df, hist_sales,
                      on=['FLT_DATE', 'CARRIER', 'FLT_NO', 'FLT_SEGMENT'])
        df['PJPJ_SALES'].fillna(0, inplace=True)

        # 剩余座位对应客座率
        df['SYZW_PLF'] = np.where(
            df['CAP'] - df['BKD'] > 0,
            df['SRS_ZL_DETR_LEFT'] / (df['CAP'] - df['BKD']),
            0
        )
        df['SRS_ZL_LEFT'] = df['SRS_ZL_DETR_LEFT']
        df['BKD_INCOME_LEFT'] = 0

        self.bottom_price_demand = df

    # ----------------------------------------------------------
    # 定价策略
    # ----------------------------------------------------------

    def _compute_advice_price(self):
        """计算 AI_ADVICE_PRICE。

        4 条策略分支，优先级从高到低：
          1. PRICE_INCREASE > 0  → 保留突增价格 (AVG_FARE_SK)
          2. EX_DIF >= 29        → 取历史成交均价与当前 OTA 价的较小值
          3. T_FLAG >= 0         → 销售偏快/正常，客座率乘数 × (成交价 + T_FLAG折补)
          4. T_FLAG < 0          → 销售偏慢，客座率乘数 × 折后成交价，限制区间
        """
        df = self.bottom_price_demand
        conds = [
            df['PRICE_INCREASE'] > 0,
            df['EX_DIF'] >= 29,
            df['T_FLAG'] >= 0,
            df['T_FLAG'] < 0,
        ]
        choices = [
            df['AVG_FARE_SK'],
            np.minimum(df['PJPJ_MIN'], df['PRICE_OTA']),
            self._price_tflag_positive(df),
            self._price_tflag_negative(df),
        ]
        df['AI_ADVICE_PRICE'] = np.select(conds, choices, default=df['AVG_FARE_SK'])
        self.bottom_price_demand = df

    def _price_tflag_positive(self, df):
        """T_FLAG >= 0（销售不慢）的定价公式。

        定价 = max(
            max(min(BKD_PLF_EST / 0.95, 1.5), 1) * (成交价 + T_FLAG × 0.1 × 全票价),
            OTA价格 - 全票价 × 0.1
        )
        """
        multiplier = np.maximum(
            np.minimum(df['BKD_PLF_EST'] / SOLO_FLT_TARGET_LOAD_FACTOR,
                       SOLO_FLT_PRICE_MULTIPLIER_MAX),
            1
        )
        base_price = (
            df['PJPJ_SALES']
            + df['T_FLAG'] * SOLO_FLT_DISCOUNT_PER_TFLAG * df['PRICE']
        )
        return np.maximum(
            multiplier * base_price,
            df['PRICE_OTA'] - df['PRICE'] * SOLO_FLT_DISCOUNT_PER_TFLAG
        )

    def _price_tflag_negative(self, df):
        """T_FLAG < 0（销售偏慢）的定价公式。

        定价 = clamp(
            min(max(min(BKD_PLF_EST, 1), 0.9), 1) * (1 + T_FLAG × 0.1) × 成交价,
            lower = OTA价格 - 全票价 × 0.1,
            upper = OTA价格
        )
        """
        multiplier = np.minimum(
            np.maximum(np.minimum(df['BKD_PLF_EST'], 1),
                       SOLO_FLT_PRICE_MULTIPLIER_MIN),
            1
        )
        price = (
            multiplier
            * (1 + df['T_FLAG'] * SOLO_FLT_DISCOUNT_PER_TFLAG)
            * df['PJPJ_SALES']
        )
        return np.maximum(
            np.minimum(price, df['PRICE_OTA']),
            df['PRICE_OTA'] - df['PRICE'] * SOLO_FLT_DISCOUNT_PER_TFLAG
        )

    # ----------------------------------------------------------
    # 结果输出
    # ----------------------------------------------------------

    def _persist_result(self):
        """选择输出列并持久化到数据库。"""
        self.result_data = self.bottom_price_demand
        tmp_data = self.bottom_price_demand[OUTPUT_COLS]
        insert_data("SOLO_FLIGHT_ADVICE_DATA_COPY", tmp_data)


if __name__ == '__main__':
    args = get_argparse()
    SoloFltAdvicePrice(args)
