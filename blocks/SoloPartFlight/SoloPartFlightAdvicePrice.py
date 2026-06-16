import os
import sys
# 确保项目根目录在 sys.path 中（支持直接运行此文件）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from blocks.SoloPartFlight.SoloFlightNumberIncreaseKNN import solo_knn_est_run


def solo_part_flight_advice_price(args):
    # 1 利用KNN算法计算剩余销售期内的人数增量情况
    result_data = solo_knn_est_run(args)
    # 2 进行价格扩展并给出航班建议价格
    result_data = solo_advice_price(args, result_data)
    # 3 修正建议价格
    result_data = true_price_up_down(args, 'SOLO_PART', result_data)
    return result_data

if __name__ == '__main__':
    from config.runtime_args import get_argparse
    solo_part_flight_advice_price(get_argparse())