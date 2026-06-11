"""
【程序目的】
实现预测结果对厦航收益管理系统（生产环境）和（测试环境）的数据传输。
"""
import requests
from hashlib import sha256
import hmac
import datetime
import pytz
import base64

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import hashlib

# 固定密钥（建议在生产环境中使用更安全的密钥管理方式）
SECRET_PASSWORD = "mysecretpassword".encode()  # 转换为字节

# 生成固定长度的AES密钥（32字节对应AES-256）
key = hashlib.sha256(SECRET_PASSWORD).digest()

def encrypt_string(plaintext):
    # 转换为字节
    data = plaintext.encode('utf-8')

    # 创建AES加密器（ECB模式）
    cipher = AES.new(key, AES.MODE_ECB)

    # 加密并返回16进制字符串
    encrypted_data = cipher.encrypt(pad(data, AES.block_size))
    return encrypted_data.hex()

def decrypt_string(encrypted_hex):
    # 创建AES解密器
    cipher = AES.new(key, AES.MODE_ECB)

    # 解密并去除填充
    decrypted_data = unpad(cipher.decrypt(bytes.fromhex(encrypted_hex)), AES.block_size)
    return decrypted_data.decode('utf-8')


# 生产环境
def advicePriceUpdate(json_data):
    url = 'http://rpsergo.xiamenair.com.cn/rmapi/advicePrice/updateAdvicePrice'
    appusename = "60009750"       #这里输入提供的app_key

    # 加密操作
    # 十六进制字符串
    encrypted = '12729a9c58b4242f100e9861328dea7cd03ca5d74fbdfa219f1c7e261ba60e2117525a8db7c945a424615cc44543737a'
    appsecret = decrypt_string(encrypted)  #这里输入提供的app_secret

    us = pytz.timezone('GMT')
    hdate = datetime.datetime.now(us).strftime("%a, %d %b %Y %H:%M:%S %Z")
    # hdate = datetime.datetime.now(us).strftime("%Y-%m-%d %H:%M:%S")
    # print (hdate)
    content = "date: " + hdate
    signature = base64.b64encode(hmac.new(appsecret.encode('utf-8'), content.encode('utf-8'), digestmod=sha256).digest()).decode()
    authorization = "hmac username=\"" + appusename + "\", algorithm=\"hmac-sha256\", headers=\"date\", signature=" + "\"" + signature + "\"";
    # print (authorization)
    headers = {
        'authorization': '25xds42v*',
        'date': hdate,
        'authorization': authorization
    }
    json = {
        "reqAdvicePriceDTOList": json_data
    }
    t1 = 'AIR_CODE AVG_FARE_DELTA AVG_FARE_SK AVG_FARE_SK_IND BKD BKD_ISSUED_NUM_INC CAP CATCH_DATE DEP_HOUR ' \
         'DEP_MINUTE DISCAP EX_DIF EXPECTED_RETURN FLT_DATE FLT_NO FLT_ROUTE FLT_SEGMENT FULL_PRICE CREATE_TIME ' \
         'IND_BKD_ISSUED_NUM_INC IS_STOPOVER_FLT MAX_DEP_HOUR OBJECT_FLT PID PROB_PRIOR PSG_CHO_PROB PSG_CHO_PROB_DELTA TIME_PT WBD_ID'
    t2 = 'airCode avgFareDelta avgFareSk avgFareSkInd bkd bkdIssuedNumInc cap catchDate depHour ' \
         'depMinute discap exDif expectedReturn fltDate fltNo fltRoute fltSegment fullPrice createTime ' \
         'indBkdIssuedNumInc isStopoverFlt maxDepHour objectFlt pid probPrior psgChoProb psgChoProbDelta timePt webId'
    json['reqAdvicePriceDTOList'] = [dict(zip(t2.split(), [i[k] for k in t1.split()])) for i in json['reqAdvicePriceDTOList']]
    response = requests.post(url=url, headers=headers, json=json)
    page_text = response.text
    return response

# 测试环境
import requests
from common.get_logger import *

def advicePriceUpdate_test(json_data):
    url = 'http://11.22.11.55:9002/advicePrice/updateAdvicePrice'
    headers = {
        'authorization': '25xds42v*'
    }
    json = {
        "reqAdvicePriceDTOList": json_data
    }
    t1 = 'AIR_CODE AVG_FARE_DELTA AVG_FARE_SK AVG_FARE_SK_IND BKD BKD_ISSUED_NUM_INC CAP CATCH_DATE DEP_HOUR ' \
         'DEP_MINUTE DISCAP EX_DIF EXPECTED_RETURN FLT_DATE FLT_NO FLT_ROUTE FLT_SEGMENT FULL_PRICE CREATE_TIME ' \
         'IND_BKD_ISSUED_NUM_INC IS_STOPOVER_FLT MAX_DEP_HOUR OBJECT_FLT PID PROB_PRIOR PSG_CHO_PROB PSG_CHO_PROB_DELTA TIME_PT WBD_ID'
    t2 = 'airCode avgFareDelta avgFareSk avgFareSkInd bkd bkdIssuedNumInc cap catchDate depHour ' \
         'depMinute discap exDif expectedReturn fltDate fltNo fltRoute fltSegment fullPrice createTime ' \
         'indBkdIssuedNumInc isStopoverFlt maxDepHour objectFlt pid probPrior psgChoProb psgChoProbDelta timePt webId'
    json['reqAdvicePriceDTOList'] = [dict(zip(t2.split(), [i[k] for k in t1.split()])) for i in json['reqAdvicePriceDTOList']]
    response = requests.post(url=url, headers=headers, json=json)
    page_text = response.text
    return response

