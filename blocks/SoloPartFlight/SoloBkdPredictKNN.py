"""
【程序目的】
实现对独飞航线剩余销售期内的人数增量预测功能。
继承 KNNBasePredictor，仅保留独飞特有的 data_deal / predict_write_back。

特色：
  - get_data() 由 DataFetchRules 规则链统一管理
  - clean_data / worker / run 由 KNNBasePredictor 统一管理
"""

import logging
import os
import sys
import numpy as np
import pandas as pd
# 确保项目根目录在 sys.path 中（支持直接运行此文件）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.pricing_constants import (SOLO_FLT_KNN_NORMAL_K, SOLO_FLT_KNN_HOLIDAY_K, SOLO_FLT_KNN_SPRING_FESTIVAL_K, SOLO_KNN_FEATURE_COLS, SOLO_KNN_TARGET_COLS)
from config.db_queries import (SOLO_ADVICE_PRICE_TRAIN_TABLE, SOLO_ADVICE_PRICE_PREDICT_TABLE, SOLO_ADVICE_PRICE_KNN_LIST)
from common.database_oracle import insert_data
from model.KNeighborsRegressor import SoloFltKnnRegressorFunction
from model.KNNBasePredictor import KNNBasePredictor
from model.DataFetchRules import SOLO_FLT_FETCH_CONTEXT



# 独飞KNN预测器
class SoloFlightNumberIncreaseKNN(KNNBasePredictor):
    """独飞航线 KNN 预测器"""

    # === 类级配置 ===
    KNN_MODEL_CLASS = SoloFltKnnRegressorFunction
    DEFAULT_K = SOLO_FLT_KNN_NORMAL_K
    HOLIDAY_K = SOLO_FLT_KNN_HOLIDAY_K
    SPRING_FESTIVAL_K = SOLO_FLT_KNN_SPRING_FESTIVAL_K
    MULTIPROCESS_THRESHOLD = 40
    FETCH_CONTEXT = SOLO_FLT_FETCH_CONTEXT

    def __init__(self, config):
        super().__init__(config)

        # 独飞特有的属性
        self.X_label_col = list(SOLO_KNN_FEATURE_COLS)
        self.Y_label_col = list(SOLO_KNN_TARGET_COLS)

        logging.info(
            f"【SoloFlightNumberIncreaseKNN】{config.version_number} 程序开始！")

    # --- 表名获取 ---
    def _get_train_table(self):
        return SOLO_ADVICE_PRICE_TRAIN_TABLE

    def _get_predict_table(self):
        return SOLO_ADVICE_PRICE_PREDICT_TABLE

    def _get_list_table(self):
        return SOLO_ADVICE_PRICE_KNN_LIST
    
    def _get_flt_type(self):
        return 'SOLO_PART'

    def _get_cleanup_sql(self):
        # return
        return "DELETE FROM SOLO_FLIGHT_KNN_TARGET"

    # --- 特征工程 ---
    def data_deal(self, data):
        """独飞特征：deptime_sin/cos + date_sin/cos + chunjie_sin"""
        data['FLT_DATE'] = pd.to_datetime(data['FLT_DATE'])
        data['DEP_TIME'] = data['DEP_HOUR'] + data['DEP_MINUTE'] / 60
        data.loc[:, 'FLT_YEAR'] = data['FLT_DATE'].dt.year
        data.loc[:, 'FLT_MONTH'] = data['FLT_DATE'].dt.month

        # 离港时间的正余弦函数
        data['deptime_sin'] = np.sin(2 * np.pi * data['DEP_TIME'] / 23.0)
        data['deptime_cos'] = np.cos(2 * np.pi * data['DEP_TIME'] / 23.0)
        # 按日期顺序的正余弦函数
        data['date_sin'] = data['FLT_DATE'].apply(lambda x: x.timetuple().tm_yday)
        data['date_sin'] = np.sin(2 * np.pi * data['date_sin'] / 366.0)
        data['date_cos'] = data['FLT_DATE'].apply(lambda x: x.timetuple().tm_yday)
        data['date_cos'] = np.cos(2 * np.pi * data['date_cos'] / 366.0)
        data['chunjie_sin'] = np.sin(2 * np.pi * data['HOLIDAY_RANGE'] / 30.0)
        return data

    # --- 特征覆盖（春运） ---
    def _override_features(self, knn_list):
        """春运期间使用不同的特征列"""
        if knn_list.get('HOLIDAY_SPRING_FESTIVAL') == 1:
            self.X_label_col = ['HOLIDAY_RANGE', 'deptime_sin', 'deptime_cos', 'HXJG_FLAG']

    # --- 预测写回 ---
    def predict_write_back(self, y_pred, target_index, knn_list):
        """独飞特有的写回逻辑：插入 SOLO_FLIGHT_KNN_TARGET + D0 特殊处理"""

        # 插入近邻样本数据
        target_data = self.train_data.iloc[target_index].copy()
        target_data['CREATE_TIME'] = self.config.create_time
        # target_data = target_data.iloc[:, :43]
        target_data.loc[:, 'HX'] = knn_list[0]
        insert_data("SOLO_FLIGHT_KNN_TARGET", target_data)

        # 将预测数据写回待预测数据
        for i, col in enumerate(self.Y_label_col):
            self.predict_data[col] = y_pred[:, i]
        self.tmp_data = self.predict_data

    # --- 后处理 ---
    def _post_process(self):
        """独飞后处理：SRS_ZL_LEFT 不低于 1"""
        self.result_data['SRS_ZL_LEFT'] = np.maximum(
            self.result_data['SRS_ZL_LEFT'], 1)


# ============================================================
# 对外入口
# ===========================================================
def solo_knn_est_run(args):
    """独飞 KNN 预测入口"""
    model = SoloFlightNumberIncreaseKNN(args)
    show_data = model.run()
    return show_data


if __name__ == '__main__':
    from config.runtime_args import get_argparse
    solo_knn_est_run(get_argparse())
