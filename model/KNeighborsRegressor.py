"""
【程序目的】
实现KNN机器学习算法的核心功能。
特色：
  - 基类包含完整的 predict 循环，子类仅覆盖 _aggregate() 方法
  - 修复了构造函数硬编码 n_neighbors=3 的 bug
  - 消除了 predict() 方法在 3 个类中的重复代码

使用方式：
  from model.KNeighborsRegressor import (
      SoloFltKnnRegressorFunction,
      SmallFltKnnRegressorFunction
  )
"""

import numpy as np
import pandas as pd
import statistics


# 欧氏距离
def distance(a, b):
    return np.sqrt(np.sum((a - b) ** 2, axis=1))


# ============================================================
# 基类：包含完整的 KNN 预测循环
# ============================================================
class KnnRegressorFunction:
    """KNN 回归基类 — predict 循环在基类实现，子类仅覆盖 _aggregate()"""

    def __init__(self, n_neighbors=3, dist_func=distance):
        self.n_neighbors = n_neighbors
        self.dist_func = dist_func

    def fit(self, x, y):
        """训练：存储训练数据"""
        self.x = x
        self.y = y

    def predict(self, x, y):
        """
        预测：遍历每个测试点 → 计算距离 → 排序 → 取 k 近邻 → 聚合
        返回 (预测值数组, 最后一个测试点的近邻索引)
        """
        # 初始化预测数组
        if isinstance(y, pd.DataFrame):
            y = np.zeros((y.shape[0], y.shape[1]), dtype=self.y.dtype)
        else:
            y = np.zeros((y.shape[0]), dtype=self.y.dtype)

        # 遍历输入的 x 数据点
        for i, x_test in enumerate(x):
            # x_test 跟所有的训练数据计算距离
            distances = self.dist_func(self.x, x_test)

            # 得到的距离按照由近到远排序，选取最近的 k 个点
            nn_index = np.argsort(distances)[:self.n_neighbors]
            nn_y = self.y[nn_index]

            # 调用子类的聚合方法（模板方法模式）
            y[i] = self._aggregate(nn_y)

        return y, nn_index

    def _aggregate(self, nn_y):
        """
        默认聚合策略：均值。
        子类可覆盖此方法实现不同的聚合逻辑。
        """
        return np.mean(nn_y, axis=0)


# ============================================================
# 独飞航线 KNN — 中位数+均值混合聚合
# ============================================================
class SoloFltKnnRegressorFunction(KnnRegressorFunction):
    """
    独飞航线 KNN 回归器。
    聚合策略：
      - 列0 (剩余人数增量): max(median, mean)
      - 列1 (最低均价):     当列2均值>=29 时取 max，否则取 mean
      - 列2 (EX_DIF):       mean
      - 列3 (最终均价):      mean
    """

    def _aggregate(self, nn_y):
        result = np.zeros(nn_y.shape[1])

        # 列0: 剩余人数增量 — max(median, mean)
        result[0] = np.maximum(
            statistics.median(nn_y[:, 0]),
            np.mean(nn_y[:, 0], axis=0)
        )

        # 列1: 最低均价 — 当 EX_DIF(列2)均值 >= 29 时取 max，否则取 mean
        result[1] = np.where(
            np.mean(nn_y[:, 2], axis=0) >= 29,
            np.max(nn_y[:, 1], axis=0),
            np.mean(nn_y[:, 1], axis=0)
        )

        # 列2: EX_DIF — mean
        result[2] = np.mean(nn_y[:, 2], axis=0)

        # 列3: 最终均价 — mean
        result[3] = np.mean(nn_y[:, 3], axis=0)

        return result


# ============================================================
# 小份额航线 KNN — 均值聚合
# ============================================================
class SmallFltKnnRegressorFunction(KnnRegressorFunction):
    """
    小份额航线 KNN 回归器。
    聚合策略：两列都取均值
      - 列0 (航班客座率 KZL_ZL_MF): mean
      - 列1 (行业客座率 KZL_ZL_IND): mean
    """

    def _aggregate(self, nn_y):
        result = np.zeros(nn_y.shape[1])

        # 列0: 航班客座率 — mean
        result[0] = np.mean(nn_y[:, 0], axis=0)

        # 列1: 行业客座率 — mean
        result[1] = np.mean(nn_y[:, 1], axis=0)

        return result
