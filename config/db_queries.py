"""
【程序目的】
数据库表名与 SQL 查询常量。
按航线模块分组，替代 config.py 中伪装成 argparse 参数的 SQL/表名。

使用方式：
    from config.db_queries import SMALL_PART_KNN_TRAIN_TABLE, ...
"""

# ============================================================
# 通用模块 (UniversalModule / 跨模块)
# ============================================================

FLT_LIST_TABLE = 'FLT_SEG_LIST'


# ============================================================
# 小份额航线 (SmallPartFlight)
# ============================================================

SMALL_PART_KNN_IDENTIFIER = '【SmallFlightKnn】'
"""日志标识字符串"""

SMALL_PART_KNN_TRAIN_TABLE = 'HIS_FUT_FLT_DATA'

SMALL_PART_KNN_PREDICT_TABLE = 'SMALL_FUT_EST_INPUT'

SMALL_PART_KNN_PREDICT_LIST = 'SMALL_FLT_KNN_LIST'

SMALL_PART_KNN_LOG_TABLE = 'SmallFlightKnnLog'

SMALL_PART_MAX_MIN_PRICE_SQL = (
    "SELECT FLT_DATE,AIR_CODE,FLT_NO,FLT_SEGMENT,MAX_PRICE,MIN_PRICE "
    "FROM SMALL_PART_MAX_MIN_PRICE"
)


# ============================================================
# 独飞航线 (SoloPartFlight)
# ============================================================
SOLO_ADVICE_PRICE_IDENTIFIER = '【SoloFlightKnn】'

SOLO_ADVICE_PRICE_TRAIN_TABLE = 'HIS_FUT_SOLO_FLT_DATA'

SOLO_ADVICE_PRICE_PREDICT_TABLE = 'SOLO_FUT_EST_INPUT'

SOLO_ADVICE_PRICE_KNN_LIST = 'SOLO_FLT_KNN_LIST'

SOLO_PREVIOUS_PRICE_TABLE = 'TMP_SOLO_FLT_OLD_DATA'

