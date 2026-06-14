from blocks.SoloPartFlight.SoloFlightNumberIncreaseKNN import solo_knn_est_run
def solo_part_flight_advice_price(args):
    # 1 利用KNN算法计算剩余销售期内的人数增量情况
    result_data = solo_knn_est_run(config)
    # 2 进行价格扩展并给出航班建议价格
    result_data = SoloFltAdvicePrice(config, result_data).result_data
    # 3 修正建议价格
    result_data = true_price_up_down(config, 'SOLO_PART', result_data)
    return result_data
