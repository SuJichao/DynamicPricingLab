import os
import sys
# 确保项目根目录在 sys.path 中（支持直接运行此文件）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from blocks.SoloPartFlight.SoloBkdPredictKNN import solo_knn_est_run
from blocks.SoloPartFlight.SoloBkdSharpRise import bkd_sharp_rise

def solo_part_flight_advice_price(args):
    """独飞航线定价流水线入口。

    4 个步骤：
      1. 利用 KNN 预测剩余销售期人数增量
      2. 订座突增检测（基于订座增量 + 客座率阈值）
      3. 基于航班销售进度和销售速度进行建议价格计算
      4. 规则后处理（航线底价等其他业务规则）
    """
    # 1 利用KNN算法计算剩余销售期内的人数增量情况
    data = solo_knn_est_run(args)
    # 2 订座突增检测（基于订座增量 + 客座率阈值）
    data = bkd_sharp_rise(data)
    # 3 基于航班销售进度和销售速度进行建议价格计算
    data = solo_advice_price(args, result_data)
    # 4 规则后处理
    result_data = true_price_up_down(args, 'SOLO_PART', result_data)
    return result_data

if __name__ == '__main__':
    from config.runtime_args import get_argparse
    solo_part_flight_advice_price(get_argparse())