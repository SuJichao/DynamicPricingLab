import datetime
import logging
import uuid

from common.database_oracle import get_data, delete_data, insert_data
from config.db_queries import FLT_LIST_TABLE

# 数据存储模块
def data_storage(config, flt_type, data):
    """
    小份额和大份额航司的数据存储
    1 行业预测数据 RM_MXZ_IND_INC_EST | RM_MXZ_IND_INC_EST_COPY
    2.1 价格区间数据-汇总 MAX_MIN_PRICE_OTA_SUG | MAX_MIN_PRICE_OTA_SUG_COPY
    2.2 价格区间数据-明细 TMP_MXZ_DP_GF_REF_CHG
    3.1 当前价格选择概率结果 RM_IND_FLT_PSG_EST_OUTPUT | RM_IND_FLT_PSG_EST_OUTPUT_COPY
    3.2 扩展价格选择概率结果 TMP_ADVICE_PRICE_DETAIL | TMP_ADVICE_PRICE_DETAIL_COPY
    3.3 建议价格 TMP_MAX_RETURN_ADVICE_PRICE_V2（临时表） | MAX_RETURN_ADVICE_PRICE_COPY

    独飞航司的数据存储
    1 价格扩展结果
    2 预测结果
    """
    # 每周日上午10点清除累积表360天前的数据
    if config.weekday == 7 and config.file_create_hour == 10:
        delete_data("""DELETE FROM SOLO_FLT_ADVICE_DATA_COPY WHERE FLT_DATE<=TRUNC(SYSDATE)-360""")
        logging.info("清除累积表360天前的数据！")

    if flt_type == 'SMALL_PART' or flt_type == 'BIG_PART':
        # 1 建议价格
        tmp_sql = f"""
        SELECT CATCH_DATE,EX_DIF,TIME_PT,FLT_DATE,AIR_CODE,
               AIR_CODE||FLT_NO AS FLT_NO,FLT_SEGMENT,FLT_ROUTE,HXJG_FLAG AS IS_STOPOVER_FLT,
               DEP_HOUR,DEP_MINUTE,CASE WHEN CAP>210 THEN 1 ELSE 0 END AS WBD_ID,CAP,DISCAP,
               PRICE AS FULL_PRICE,BKD,AI_ADVICE_PRICE AS AVG_FARE_SK,0 AS AVG_FARE_SK_IND,0 AS AVG_FARE_DELTA,
               PSG_CHO_PROB,0 AS PROB_PRIOR,0 AS PSG_CHO_PROB_DELTA,0 AS MAX_DEP_HOUR,
               'MF8888' AS OBJECT_FLT,0 AS IND_BKD_ISSUED_NUM_INC,SRS_ZL_EST AS BKD_ISSUED_NUM_INC,0 AS EXPECTED_RETURN
        FROM SMALL_PART_ADVICE_PRICE_OUTPUT
        """
        flt_price_advice_result = get_data(tmp_sql)
        if config.data_source == 'oracle':
            flt_price_advice_result['CREATE_TIME'] = datetime.datetime.now()
            delete_data(
                f"""DELETE FROM TMP_MAX_RETURN_ADVICE_PRICE_V2 WHERE FLT_SEGMENT IN (SELECT FLT_SEGMENT FROM {FLT_LIST_TABLE} WHERE FLT_TYPE='{flt_type}')""")
            delete_data("""DELETE FROM TMPTMP_MAX_RETURN_ADVICE_PRICE""")
            insert_data("MAX_RETURN_ADVICE_PRICE_COPY", flt_price_advice_result)
            flt_price_advice_result['PID'] = uuid.uuid1()
            for i in range(len(flt_price_advice_result)):
                flt_price_advice_result.at[i, 'PID'] = uuid.uuid1()
            flt_price_advice_result['PID'] = flt_price_advice_result['PID'].astype('str')
            # 先插入临时表
            insert_data("TMPTMP_MAX_RETURN_ADVICE_PRICE", flt_price_advice_result)
            # 完成航段信息回溯
            tmp_sql = """
                SELECT B.CATCH_DATE,B.EX_DIF,B.TIME_PT,B.FLT_DATE,B.AIR_CODE,B.FLT_NO,A.DEP||A.ARR AS FLT_SEGMENT,B.FLT_ROUTE,
                B.IS_STOPOVER_FLT,B.DEP_HOUR,B.DEP_MINUTE,B.WEB_ID,B.CAP,B.DISCAP,B.FULL_PRICE,B.BKD,B.AVG_FARE_SK,B.AVG_FARE_SK_IND,B.AVG_FARE_DELTA,
                B.PSG_CHO_PROB,B.PROB_PRIOR,B.PSG_CHO_PROB_DELTA,B.MAX_DEP_HOUR,B.OBJECT_FLT,B.IND_BKD_ISSUED_NUM_INC,B.BKD_ISSUED_NUM_INC,
                B.EXPECTED_RETURN,B.CREATE_TIME,B.PID
                FROM
                (
                    SELECT *
                    FROM KD_FUTURE_TMP_SJC_NEW A
                    WHERE A.CARRIER IN ('MF','NS','RY')
                    OR (A.CARRIER='NS' AND REPLACE(REPLACE(DEP,'PEK','PKX'),'CTU','TFU')||REPLACE(REPLACE(ARR,'PEK','PKX'),'CTU','TFU') IN (SELECT FLT_SEGMENT FROM DP_FLT_LIST WHERE AIR_CODE='NS'))
                ) A
                LEFT JOIN TMPTMP_MAX_RETURN_ADVICE_PRICE B
                ON A.FLT_DATE=B.FLT_DATE AND A.CATCH_DATE=B.CATCH_DATE AND A.CARRIER||A.FLT_NO=B.FLT_NO AND REPLACE(REPLACE(A.DEP,'PEK','PKX'),'CTU','TFU')||REPLACE(REPLACE(A.ARR,'PEK','PKX'),'CTU','TFU')=B.FLT_SEGMENT
                WHERE B.FLT_DATE IS NOT NULL
                ORDER BY B.FLT_SEGMENT,B.FLT_DATE,B.DEP_HOUR
            """
            tmp_data = get_data(tmp_sql)
            insert_data("TMP_MAX_RETURN_ADVICE_PRICE_V2", tmp_data)

    elif flt_type == 'SOLO_PART':
        delete_data(f""" DELETE FROM TMP_MAX_RETURN_ADVICE_PRICE WHERE FLT_SEGMENT IN (SELECT FLT_SEGMENT FROM {FLT_LIST_TABLE} WHERE FLT_TYPE='{flt_type}')""")
        insert_data("TMP_MAX_RETURN_ADVICE_PRICE", data)


