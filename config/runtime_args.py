"""
【程序目的】
存储程序文件中的各类参数信息。
"""
import argparse
import datetime
import os
def get_argparse():
    parser = argparse.ArgumentParser(description='DynamicPricingPredictProject')

    # 1 basic config — 真正的 CLI / 运行时参数
    parser.add_argument('--data_source', type=str, default='oracle', help='data source')
    parser.add_argument('--version_number', type=str, default='7.0.0', help='version number')
    parser.add_argument('--file_create_date', type=str, default=datetime.datetime.now().strftime('%Y-%m-%d'),
                        help='file create date')
    parser.add_argument('--file_create_hour', type=int, default=int(datetime.datetime.now().strftime('%H')),
                        help='file create hour')
    parser.add_argument('--file_create_minute', type=int, default=int(datetime.datetime.now().strftime('%M')),
                        help='file create minute')
    parser.add_argument('--create_time', type=str, default=datetime.datetime.now(),
                        help='file create time')
    parser.add_argument('--weekday', type=str, default=datetime.datetime.now().isoweekday(),
                        help='weekday')

    args = parser.parse_args()
    return args


# 日志文件路径（所有模块统一从此读取）
LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs', 'app.log')

