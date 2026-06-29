"""
【程序目的】
针对独飞航线，在订座突增检测完成后进行基础定价（ADVICE_PRICE）。
输入需已含 BKD_PLF_EST 和突增检测结果（ADVICE_PRICE、PRICE_INCREASE）。
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
    round_to_10,
)
from common.database_oracle import get_data, insert_data


# ============================================================
# 输出列名常量
# ============================================================

OUTPUT_COLS = [
    'CATCH_DATE', 'TIME_PT', 'EX_DIF', 'DOW', 'FLT_DATE',
    'AIR_CODE', 'FLT_NO', 'FLT_SEGMENT', 'FLT_ROUTE', 'HXJG_FLAG', 'DEP_HOUR',
    'DEP_MINUTE', 'CAP', 'DISCAP', 'BKD', 'PRICE_OTA', 'PRICE',
    'PJPJ_FINAL', 'SRS_SALES', 'PJPJ_SALES', 'PRICE_INCREASE',
    'BKD_PLF_EST', 'SRS_ZL_LEFT', 'T_FLAG', 'ADVICE_PRICE'
]


# ============================================================
# SoloFltAdvicePrice
# ============================================================

class SoloFltAdvicePrice(object):
    """独飞航线基础定价。

    前置条件：输入 DataFrame 需已包含 BKD_PLF_EST、ADVICE_PRICE、PRICE_INCREASE
    （由编排层分别在 KNN 预测后和订座突增检测后设置）。
    """

    def __init__(self, config, data):
        self.config = config
        self.data = data

        logging.info("【SoloFltAdvicePrice】程序开始！")
        self.compute_advice_price()

    # ----------------------------------------------------------
    # 主流程
    # ----------------------------------------------------------

    def compute_advice_price(self):
        """基础定价主流程：准备数据 → 计算建议价格 → 持久化。"""
        self._prepare_data()
        self._price_decision_making_chain()
        self._persist_result()

    # ----------------------------------------------------------
    # 数据准备
    # ----------------------------------------------------------

    def _prepare_data(self):
        """填充缺失值、合并历史销售数据（销售速度快、慢标签）、计算辅助特征。"""
        df = self.data
        df['PRICE'].fillna(SOLO_FLT_FULL_PRICE_FALLBACK, inplace=True)

        # 合并独飞历史销售数据
        hist_sales = get_data(
            'SELECT FLT_DATE,AIR_CODE,FLT_NO,FLT_SEGMENT,SRS_SALES,PJPJ_SALES,T_FLAG '
            'FROM SOLO_FLT_SRS_HIS_TFLAG'
        )
        df = pd.merge(df, hist_sales,
                      on=['FLT_DATE', 'AIR_CODE', 'FLT_NO', 'FLT_SEGMENT'])
        df['PJPJ_SALES'].fillna(0, inplace=True)

        self.data = df

    # ----------------------------------------------------------
    # 定价策略
    # ----------------------------------------------------------

    def _price_decision_making_chain(self):
        """计算 ADVICE_PRICE。

        4 条策略分支，优先级从高到低：
          1. PRICE_INCREASE > 0  → 保留突增价格 (ADVICE_PRICE)
          2. EX_DIF > 29        → 取历史成交均价与当前 OTA 价的较小值
          3. T_FLAG >= 0         → 销售偏快/正常，客座率乘数 × (成交价 + T_FLAG折补)
          4. T_FLAG < 0          → 销售偏慢，客座率乘数 × 折后成交价，限制区间
        """
        df = self.data
        conds = [
            df['PRICE_INCREASE'] > 0,
            df['EX_DIF'] > 29,
            df['T_FLAG'] >= 0,
            df['T_FLAG'] < 0,
        ]
        choices = [
            df['ADVICE_PRICE'],
            np.minimum(df['PJPJ_FINAL'], df['PRICE_OTA']),
            self._price_tflag_positive(df),
            self._price_tflag_negative(df),
        ]
        df['ADVICE_PRICE'] = np.select(conds, choices, default=df['ADVICE_PRICE'])
        self.result_data = df

    def _price_tflag_positive(self, df):
        """T_FLAG >= 0（销售偏快）的定价公式。

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
        )a
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
        tmp_data = self.result_data[OUTPUT_COLS].copy()
        tmp_data['ADVICE_PRICE'] = round_to_10(tmp_data['ADVICE_PRICE'])
        tmp_data.loc[:, 'CREATE_TIME'] = self.config.create_time
        insert_data("SOLO_FLT_ADVICE_DATA_COPY", tmp_data)
        self.result_data = tmp_data



