"""
【程序目的】
实现建议价格传输值收益管理系统和小星星的相关操作。
"""
import logging

from common.database_oracle import get_data, delete_data, insert_data
from common.request import advicePriceUpdate

def advice_price_output():
    rm_dp_data = get_data(f"SELECT * FROM TMP_MAX_RETURN_ADVICE_PRICE").copy()
    # 1 先将数据传输至收益管理系统
    rm_dp_data['FLT_DATE'] = rm_dp_data['FLT_DATE'].astype('str')
    rm_dp_data['CATCH_DATE'] = rm_dp_data['CATCH_DATE'].astype('str')
    rm_dp_data['CREATE_TIME'] = rm_dp_data['CREATE_TIME'].astype('str')
    json_flt_price_advice_result = rm_dp_data.to_dict(orient='records')
    response = advicePriceUpdate(json_flt_price_advice_result)
    # response_test = advicePriceUpdate_test(json_flt_price_advice_result)
    logging.info(f'生产环境接口：{response}')#===测试环境接口：{response_test}
    '''
    当接口返回的信息不是<Response [200]>时，大概率是数据重复，利用如下代码进行排查：
    SELECT FLT_DATE,FLT_SEGMENT,FLT_NO,COUNT(*)
    FROM TMP_MAX_RETURN_ADVICE_PRICE_V2
    GROUP BY FLT_DATE,FLT_SEGMENT,FLT_NO
    HAVING COUNT(*)>1
    '''



def delete_deduplication_data():
    delete_data(
        """
        DELETE FROM KD_FUTURE_TMP_SJC_NEW_COPY A WHERE ROWID NOT IN (SELECT MAX(B.ROWID) FROM KD_FUTURE_TMP_SJC_NEW_COPY B 
        WHERE A.CATCH_DATE=B.CATCH_DATE AND A.CATCH_TIME = B.CATCH_TIME AND A.CATCH_DIF =B.CATCH_DIF  AND A.FLT_DATE =B.FLT_DATE AND A.CARRIER = B.CARRIER AND A.FLT_NO =B.FLT_NO 
        AND A.DEP =B.DEP  AND A.ARR = B.ARR AND A.ROUTE=B.ROUTE AND A.UP_DATE=B.UP_DATE)
        """)
    delete_data(
        """
        DELETE FROM MAX_RETURN_ADVICE_PRICE_COPY A WHERE ROWID NOT IN (SELECT MAX(B.ROWID) FROM MAX_RETURN_ADVICE_PRICE_COPY B 
        WHERE A.CATCH_DATE=B.CATCH_DATE AND A.EX_DIF = B.EX_DIF AND A.TIME_PT =B.TIME_PT  AND A.FLT_DATE =B.FLT_DATE AND A.FLT_NO = B.FLT_NO AND A.FLT_SEGMENT =B.FLT_SEGMENT)
        """)
    logging.warning(f"程序临时执行，删除由此产生的重复数据！")