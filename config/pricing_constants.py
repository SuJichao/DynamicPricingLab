"""
【程序目的】
集中管理所有定价策略中的魔法数字，降低维护成本、提升可读性。
每个常量都配有业务含义说明，方便后续调整参数时理解上下文。

使用方式：
    from config.pricing_constants import *
"""

# ============================================================
# 小份额航线 (SMALL_PART) 定价参数
# ============================================================

SMALL_FLT_PRICE_UP_ARTIFICIAL_PCT = 0.10
"""有人工库存时提价上限 10% —— 航班有人工预留座位时，提价空间更大"""

SMALL_FLT_PRICE_UP_NORMAL_PCT = 0.05
"""无人工资库存时提价上限 5% —— 常规场景下提价不超过 5%"""

SMALL_FLT_PRICE_DOWN_PCT = 0.05
"""销售偏慢时降价幅度 5% —— 每次降价不超过 5%"""

SMALL_FLT_PRICE_FLOOR_RATIO = 0.9
"""降价时最低不低于 PJPJ 的 90% —— 防止降价过度"""

SMALL_FLT_PRICE_FLOOR_ABSOLUTE = 200
"""无自定义底价时，最低价 200 元（约 1-2 折）"""


# ============================================================
# 独飞航线 (SOLO_PART) 定价参数
# ============================================================

SOLO_FLT_TARGET_LOAD_FACTOR = 0.95
"""目标客座率 95% —— 当预计客座率 / 0.95 >= 1 时认为满客可提价"""

SOLO_FLT_PRICE_MULTIPLIER_MAX = 1.5
"""提价系数上限 1.5 —— 销售再快收舱幅度也不超过 1.5 """

SOLO_FLT_PRICE_MULTIPLIER_MIN = 0.9
"""降价系数下限 0.9 —— 销售再慢放舱幅度也不低于 0.9 """

SOLO_FLT_DISCOUNT_PER_TFLAG = 0.1
"""T_FLAG 每档对应 1 折 —— T_FLAG 每增加 1，价格上浮 1 折"""

SOLO_FLT_FULL_PRICE_FALLBACK = 1000
"""全票价数据缺失时默认值 1000 元，防止计算异常"""

SOLO_FLT_SPRING_FESTIVAL_MIN_DISCOUNT_1 = 0.3
"""春运第一阶段最低折扣 30%（适用于春运前特定时段）"""

SOLO_FLT_SPRING_FESTIVAL_MIN_DISCOUNT_2 = 0.4
"""春运第二阶段最低折扣 40%（适用于春运高峰时段）"""

SOLO_FLT_SPRING_FESTIVAL_PRICE_FLOOR = 200
"""春运期间反向航线最低价 200 元"""


# ----- 独飞订座突增参数 -----

SOLO_BKD_SURGE_D0_DIVISOR = 5
"""D0-1 天：每多订 5 人视为 1 档突增，加 1 折"""

SOLO_BKD_SURGE_D2_D7_DIVISOR = 3
"""D2-7 天：每多订 3 人视为 1 档突增，加 1 折"""

SOLO_BKD_SURGE_D8_DIVISOR = 1
"""D8+ 天：每多订 1 人视为 1 档突增，加 1 折"""

SOLO_BKD_SURGE_STEP_CAP = 1
"""突增加价封顶 1 折 —— 防止订座偶然波动导致价格跳涨"""

SOLO_BKD_SURGE_LOAD_THRESHOLD = 0.9
"""预计客座率超过 90% 才触发突增定价，防止低位时误操作"""


# ----- NS 航班行李门槛 -----

SOLO_NS_BAGGAGE_LOWER_DISCOUNT = 0.29
"""NS 航班建议价格低于 29 折时不调价（不含行李票价区段）"""

SOLO_NS_BAGGAGE_TARGET_DISCOUNT = 0.31
"""NS 航班建议价格在 29-31 折之间时，统一提到 31 折（含行李）"""


# ----- MF 航班 D0-2 最低价保护 -----

SOLO_MF_HIGH_LOAD_THRESHOLD = 0.70
"""MF 客座率高低分界线 70%（高于此值为高客座率）"""

SOLO_MF_HIGH_LOAD_MIN_DISCOUNT = 0.30
"""MF 高客座率 (BKD/CAP > 70%) 最低折扣 3 折"""

SOLO_MF_HIGH_LOAD_MIN_PRICE = 500
"""MF 高客座率 (BKD/CAP > 70%) 最低票价 500 元"""

SOLO_MF_LOW_LOAD_MIN_DISCOUNT = 0.20
"""MF 低客座率 (BKD/CAP ≤ 70%) 最低折扣 2 折"""

SOLO_MF_LOW_LOAD_MIN_PRICE = 400
"""MF 低客座率 (BKD/CAP ≤ 70%) 最低票价 400 元"""


# ----- 独飞航线底价 -----

SOLO_FLT_PRICE_FLOOR_ABSOLUTE = 200
"""独飞航班未设置自定义底价时，最低价 200 元"""

SOLO_FLT_BOTTOM_DISCOUNT = 0.1
"""独飞航线底价折扣 1 折，用于全票价 * 折扣与绝对底价取最大值"""


# ============================================================
# 通用参数
# ============================================================

STOPOVER_FLT_ROUTE_LENGTH = 9
"""FLT_ROUTE 长度为 9 表示经停航线（如 XMN-PEK-SHA）"""

PRICE_ROUND_BASE = 10
"""价格取整基数（向上/向下取整到 10 的倍数）"""

EX_DIF_LONG_HAUL = 7
"""D7+ 的预测统一使用 TIME_PT=0"""


# ============================================================
# KNN 模型参数
# ============================================================

SMALL_FLT_KNN_NORMAL_K = 3
"""小份额航线普通日 K 值"""

SMALL_FLT_KNN_HOLIDAY_K = 1
"""小份额航线节假日 K 值"""

SOLO_FLT_KNN_NORMAL_K = 5
"""独飞航线普通日 K 值"""

SOLO_FLT_KNN_HOLIDAY_K = 1
"""独飞航线节假日（非春运）K 值"""

SOLO_FLT_KNN_SPRING_FESTIVAL_K = 1
"""独飞航线春运 K 值"""


# ----- KNN 特征/目标列名 -----

SMALL_PART_KNN_TARGET_COLS = ('KZL_ZL_MF', 'KZL_ZL_IND')
"""小份额航线 KNN 预测目标列"""

SMALL_PART_KNN_FEATURE_COLS = (
    'date_sin', 'date_cos', 'HOL_LAST', 'TIME_PT', 'DEP_HOUR',
    'CAP', 'BKD_SK', 'PJPJ', 'chunjie_sin',
)
"""小份额航线 KNN 特征列"""

SMALL_PART_KNN_OUTPUT_COLS = (
    'CATCH_DATE', 'FLT_DATE', 'EX_DIF', 'TIME_PT', 'AIR_CODE', 'FLT_NO',
    'FLT_SEGMENT', 'FLT_ROUTE', 'DEP_HOUR', 'DEP_MINUTE', 'CAP', 'DISCAP',
    'BKD_LEFT', 'BKD', 'GRS', 'BKD_SK', 'PJPJ', 'SZS_ZL', 'HXJG_FLAG',
    'DOW', 'CAP_FINAL', 'CAP_IND_FINAL', 'KZL_ZL_MF',
    'KZL_ZL_IND', 'PRICE', 'ARTIFICIAL_CAP_LEFT', 'CAP_LEFT',
)
"""小份额航线 KNN 输出列"""

SOLO_KNN_FEATURE_COLS = (
    'FLT_YEAR', 'FLT_MONTH', 'date_sin', 'date_cos', 'HOL_LAST', 'chunjie_sin',
)
"""独飞航线 KNN 特征列"""

SOLO_KNN_TARGET_COLS = (
    'PJPJ_LEFT','SRS_ZL_LEFT', 'PJPJ_FINAL', 'EX_DIF',
)
"""独飞航线 KNN 预测目标列"""


# ============================================================
# 进程执行时序控制
# ============================================================

TIMING_MIN_EXECUTION_SECONDS = 3
"""进程从参数解析到此处耗时少于此值，判定前序进程尚未结束，须等待"""

TIMING_SLEEP_SECONDS = 20
"""判定前序进程未结束时，暂停等待的秒数"""

TIMING_MAX_EXECUTION_SECONDS = 901
"""进程执行时间超过此值（约15分钟），自动跳过本次执行"""


# ============================================================
# 工具函数
# ============================================================

def round_to_10(value):
    """将价格取整到 10 的倍数（如 123 → 120, 128 → 130）"""
    return round(value / PRICE_ROUND_BASE) * PRICE_ROUND_BASE
