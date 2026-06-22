import os
import sys
# 确保项目根目录在 sys.path 中（支持直接运行此文件）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from blocks.SoloPartFlight.SoloBkdPredictKNN import solo_knn_est_run
from blocks.SoloPartFlight.SoloBkdSharpRise import bkd_sharp_rise
from blocks.SoloPartFlight.SoloAdvicePrice import SoloFltAdvicePrice
from blocks.SoloPartFlight.SoloRulePostProcessing import rule_post_processing

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
    data = bkd_sharp_rise(args, data)
    # 3 基于航班销售进度和销售速度进行建议价格计算
    data = SoloFltAdvicePrice(args, data)
    # 4 规则后处理
    data = rule_post_processing(args, data.result_data)
    return data

if __name__ == '__main__':
    from config.runtime_args import get_argparse
    solo_part_flight_advice_price(get_argparse())