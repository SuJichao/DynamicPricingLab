import os
import sys
# 确保项目根目录在 sys.path 中（支持直接运行此文件）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# from blocks.SmallPartFlight.SmallBkdPredictKNN import small_knn_est_run


def small_part_flight_advice_price(args):
    """小份额航线定价流水线入口。

    4 个步骤：
      1. 利用 KNN 预测剩余销售期人数增量

      4. 规则后处理（航线底价等其他业务规则）
    """
    # 1 利用KNN算法计算剩余销售期内的人数增量情况
    data = small_knn_est_run(args)

    return data

if __name__ == '__main__':
    from config.runtime_args import get_argparse
    small_part_flight_advice_price(get_argparse())

