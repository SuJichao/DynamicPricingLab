"""
【程序目的】
KNN 预测管道基类。
提取 独飞航班 和 小份额航班 在人数预测 的公共骨架：
  clean_data / knn_est 管道 / worker / run（单/多进程调度）。

子类只需覆盖 data_deal() 和 predict_write_back() 即可。

使用方式：
  from model.KNNBasePredictor import KNNBasePredictor

  class MyPredictor(KNNBasePredictor):
      KNN_MODEL_CLASS = MyKnnModel
      DEFAULT_K = 3
      ...
      def data_deal(self, data): ...
      def predict_write_back(self, y_pred, target_index, knn_list): ...
"""

import copy
import importlib
import logging
import multiprocessing as mp
from multiprocessing import Pool
from types import SimpleNamespace

import pandas as pd
from sklearn.preprocessing import StandardScaler

from common.database_oracle import get_data, delete_data, insert_data
from common.basic_helper_fuction import is_multiprocessing_enabled
from model.DataFetchRules import fetch_train_data, fetch_predict_data
from config.pricing_constants import (
    MP_MAX_WORKERS,MP_MAX_TASKS_PER_CHILD
)


# ============================================================
# 模块级多进程 worker（解决 Windows spawn 模式下绑定方法不可 pickle 的问题）
# ============================================================
def _mp_worker(args):
    """多进程 worker（模块级函数，可被 pickle 序列化）。

    在 Windows spawn 模式下，子进程会重新导入所有模块。
    本函数接收简单参数，在子进程中重新创建预测器实例并调用其 worker 方法，
    避免跨进程序列化绑定方法（self.worker）导致的 pickle 错误。

    Args:
        args: (predictor_cls_path, config_dict, i) 三元组
              - predictor_cls_path: 预测器类的完整路径，如
                'blocks.SoloPartFlight.SoloBkdPredictKNN.SoloFlightNumberIncreaseKNN'
              - config_dict: argparse.Namespace 的 vars() 字典（仅含基本类型值）
              - i: 预测列表中待处理的行索引
    Returns:
        pd.DataFrame: 预测结果数据（可能为空）
    """
    predictor_cls_path, config_dict, i = args

    # 从字符串路径动态导入预测器类
    module_path, class_name = predictor_cls_path.rsplit('.', 1)
    mod = importlib.import_module(module_path)
    predictor_cls = getattr(mod, class_name)

    # 用字典重建配置对象（避免 Namespace 中潜在的非 pickle 字段）
    config = SimpleNamespace(**config_dict)

    # 在子进程中创建全新的预测器实例
    # 各子进程会独立初始化 database_oracle 连接池、日志等资源
    predictor = predictor_cls(config)

    # 调用原有的实例级 worker 方法
    # 注：get_data() 内部已做 .copy()，返回数据不持有 Oracle 缓冲区引用
    return predictor.worker(i)


class KNNBasePredictor:
    """
    KNN 预测管道基类。

    子类必须覆盖的类属性：
      KNN_MODEL_CLASS:      KNN 模型类（如 SmallFltKnnRegressorFunction）
      DEFAULT_K:            普通日 K 值
      HOLIDAY_K:            节假日 K 值
      SPRING_FESTIVAL_K:    春运 K 值
      FETCH_CONTEXT:        DataFetchRules.FetchContext 实例
      MULTIPROCESS_THRESHOLD: 单/多进程切换阈值

    子类必须覆盖的方法：
      data_deal(data):              特征工程
      predict_write_back(y_pred, target_index, knn_list): 预测写回
      init_special():               子类特化初始化逻辑
    """

    # === 子类覆盖 ===
    KNN_MODEL_CLASS = None
    DEFAULT_K = 3
    HOLIDAY_K = 1
    SPRING_FESTIVAL_K = 1
    MULTIPROCESS_THRESHOLD = 10
    FETCH_CONTEXT = None       # DataFetchRules.FetchContext

    # === 子类可选覆盖 ===
    NEED_EST_DATA_SAME = False  # 小份额需要列对齐

    def __init__(self, config):
        self.config = config
        self.train_data = pd.DataFrame()
        self.predict_data = pd.DataFrame()
        self.tmp_data = None
        self.result_data = pd.DataFrame()
        self.X_label_col = []
        self.Y_label_col = []
        self._setup_context()

    def _setup_context(self):
        """创建 FETCH_CONTEXT 的实例级副本，避免修改模块级共享单例"""
        if self.FETCH_CONTEXT is None:
            raise ValueError("FETCH_CONTEXT must be defined in subclass or before initialization.")
        
        # 此时 Pylance 可能仍抱怨，因为 copy.copy 返回 Any 或原始类型
        # 使用 cast 或断言来辅助类型检查器，或者简单地忽略此处的严格检查
        self._ctx = copy.copy(self.FETCH_CONTEXT)
        
        # 确保 _ctx 不为 None 后再赋值属性
        if self._ctx is not None:
            self._ctx.train_table = self._get_train_table()
            self._ctx.predict_table = self._get_predict_table()
            self._ctx.list_table = self._get_list_table()
            self._ctx.flt_type = self._get_flt_type()
        else:
            # 理论上不会到达这里，因为上面已经检查了 FETCH_CONTEXT
            raise RuntimeError("Failed to copy FETCH_CONTEXT")

    # --- 子类覆盖：表名获取 ---
    def _get_train_table(self):
        raise NotImplementedError

    def _get_predict_table(self):
        raise NotImplementedError

    def _get_list_table(self):
        """返回预测列表的表名或配置键"""
        raise NotImplementedError
    def _get_flt_type(self):
        return NotImplementedError

    def _get_cleanup_sql(self):
        """返回 run() 开始时需清理的 DELETE SQL"""
        raise NotImplementedError

    # --- 特征工程（子类覆盖） ---
    def data_deal(self, data):
        """特征工程：sine/cosine 变换等"""
        raise NotImplementedError

    # --- 预测写回（子类覆盖） ---
    def predict_write_back(self, y_pred, target_index, knn_list):
        """预测结果写回 + 后处理"""
        raise NotImplementedError

    def _override_features(self, knn_list):
        """可选：根据 knn_list 覆盖特征列（如独飞春运）"""
        pass

    def _post_process(self):
        """可选：对 self.result_data 做最后的后处理"""
        pass
    
    def _load_knn_list(self):
        """加载预测列表"""
        return get_data(f"SELECT * FROM {self._get_list_table()} ORDER BY HX")

    # --- 公共方法 ---

    def fetch_train_data(self, tmp_list):
        """通过规则链获取训练数据"""
        return fetch_train_data(self._ctx, tmp_list)

    def fetch_predict_data(self, tmp_list):
        """获取待预测数据"""
        return fetch_predict_data(self._ctx, tmp_list)

    def clean_data(self, data):
        """公共数据清洗：重置索引 → 日期转换 → 特征工程 → 分离 X/Y"""
        data = data.copy()
        data.reset_index(drop=True, inplace=True)
        data['FLT_DATE'] = pd.to_datetime(data['FLT_DATE'])
        data = self.data_deal(data)
        Y = data[self.Y_label_col]
        X = data[self.X_label_col]
        return X, Y

    def _choose_k(self, knn_list):
        """根据节假日标志选择 K 值"""
        if knn_list.get('HOL_FALG') == 0:
            return self.DEFAULT_K
        elif knn_list.get('HOLIDAY_SPRING_FESTIVAL') == 1:
            return self.SPRING_FESTIVAL_K
        else:
            return self.HOLIDAY_K

    def knn_est(self, knn_list):
        """
        KNN 预测管道：
        override features → clean → scale → create model → fit → predict → write back
        """
        # 先覆盖特征列（如独飞春运），再 clean_data
        self._override_features(knn_list)

        X, Y = self.clean_data(self.train_data)

        # 标准化
        scaler_x = StandardScaler()
        x_train = scaler_x.fit_transform(X.to_numpy())
        y_train = Y.to_numpy()

        # 创建并训练模型
        k = self._choose_k(knn_list)
        knn = self.KNN_MODEL_CLASS(n_neighbors=k)
        knn.fit(x_train, y_train)

        # 预测
        X_predict, Y_predict = self.clean_data(self.predict_data)
        if self.NEED_EST_DATA_SAME:
            X_predict = self._est_data_same(X, X_predict)
        X_predict_std = scaler_x.transform(X_predict.to_numpy())

        y_pred, target_index = knn.predict(X_predict_std, Y_predict)

        # 写回（子类实现）
        self.predict_write_back(y_pred, target_index, knn_list)

    @staticmethod
    def _est_data_same(train_data, est_data):
        """确保预测数据与训练数据的列一致（小份额专用）"""
        train_columns = train_data.columns.values.tolist()
        miss_columns = set(train_columns) - set(est_data.columns)
        for col in miss_columns:
            est_data[col] = 0
        adu_columns = set(est_data.columns) - set(train_columns)
        est_data = est_data.drop(list(adu_columns), axis=1)
        est_data = est_data.reindex(train_columns, axis=1)
        return est_data

    def worker(self, i):
        """多进程 worker"""
        data = pd.DataFrame()
        tmp_sql = f"SELECT * FROM {self._get_list_table()} WHERE HX = {i + 1}"
        knn_list = get_data(tmp_sql).iloc[0]
        self.predict_data = self.fetch_predict_data(knn_list)
        self.train_data = self.fetch_train_data(knn_list)
        if len(self.train_data) > 0:
            self.knn_est(knn_list)
            data = self.tmp_data
        return data

    def _run_single_process(self, knn_list):
        """单进程处理：逐条遍历预测列表。

        此方法同时服务于：
        - 数据量低于阈值时的常规单进程路径
        - 多进程崩溃后的回退（fallback）路径

        Args:
            knn_list: DataFrame，预测列表
        """
        logging.info(
            f"【{self.__class__.__name__}】单进程模式，数据量：{len(knn_list)}"
        )
        results = []
        for idx, (_, row) in enumerate(knn_list.iterrows()):
            try:
                self.predict_data = self.fetch_predict_data(row)
                self.train_data = self.fetch_train_data(row)
                # logging.info(f"航班序号：{row['HX']}")
                if len(self.train_data) > 0:
                    self.knn_est(row)
                    results.append(self.tmp_data)
            except Exception as e:
                logging.error(
                    f"【{self.__class__.__name__}】单进程任务 {idx + 1} 失败: {e}",
                    exc_info=True
                )
        self.result_data = (
            pd.concat(results, ignore_index=True) if results else pd.DataFrame()
        )

    def run(self):
        """主执行入口：单进程/多进程调度。

        多进程模式下已内置多重防护：
        - 捕获 BrokenPipeError 等 IPC 异常后自动回退到单进程
        - 检查调试器附加状态 / 环境变量 DISABLE_MULTIPROCESSING 自动降级
        - get_data() 内 .copy() 断开 Oracle memoryview 引用，避免 GC 崩溃
        """
        logging.info(f"【{self.__class__.__name__}】程序开始！")

        # 清理临时表
        cleanup_sql = self._get_cleanup_sql()
        if cleanup_sql:
            delete_data(cleanup_sql)

        knn_list = self._load_knn_list()

        # 判断是否走多进程路径
        use_multiprocessing = (
            len(knn_list) <= self.MULTIPROCESS_THRESHOLD
<<<<<<< HEAD
            or is_multiprocessing_enabled()
=======
            and is_multiprocessing_enabled()
>>>>>>> 6873a42c47e65f3b9c5c468fbc9aeee2e7768786
        )

        if not use_multiprocessing:
            # 单进程模式（数据量不足 或 环境变量禁用了多进程）
            if not is_multiprocessing_enabled():
                logging.info(
                    f"【{self.__class__.__name__}】多进程已被环境变量禁用，"
                    f"使用单进程模式，数据量：{len(knn_list)}"
                )
            self._run_single_process(knn_list)
        else:
            # 多进程模式
            num_cores = min(mp.cpu_count(), MP_MAX_WORKERS)
            logging.info(
                f"【{self.__class__.__name__}】触发{num_cores}进程模式，"
                f"数据量：{len(knn_list)}"
            )

            # 构造参数：类路径（用于子进程动态导入）+ 配置字典 + 行索引
            class_path = (
                f"{self.__class__.__module__}."
                f"{self.__class__.__qualname__}"
            )
            config_dict = vars(self.config)
            task_args = [
                (class_path, config_dict, i)
                for i in range(len(knn_list))
            ]

            try:
                with Pool(processes=num_cores) as pool:
                    results = list(
                        pool.imap_unordered(_mp_worker, task_args)
                    )
                    if results:
                        self.result_data = pd.concat(
                            [r for r in results if r is not None and not r.empty],
                            ignore_index=True
                        )
                    else:
                        self.result_data = pd.DataFrame()
            except (BrokenPipeError, ConnectionResetError,
                    ConnectionAbortedError, ProcessLookupError) as e:
                # 子进程崩溃导致 IPC 异常 → 回退到单进程
                logging.error(
                    f"【{self.__class__.__name__}】多进程 IPC 异常，"
                    f"回退到单进程模式: {e}",
                    exc_info=True
                )
                self._run_single_process(knn_list)
            except Exception as e:
                logging.error(
                    f"【{self.__class__.__name__}】多进程处理失败，"
                    f"回退到单进程模式: {e}",
                    exc_info=True
                )
                self._run_single_process(knn_list)

        # 后处理
        if not self.result_data.empty:
            self.result_data = self.result_data.sort_values(
                by=['FLT_SEGMENT', 'FLT_DATE'], ascending=[True, True]
            )
            self.result_data.reset_index(drop=True, inplace=True)
        self._post_process()
        return self.result_data


