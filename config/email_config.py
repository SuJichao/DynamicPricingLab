"""
【程序目的】
邮件服务配置（从 config.py 拆分）。
密码优先从环境变量 DP_EMAIL_PASSWORD 读取，未设置时 fallback 硬编码值。
"""
import os

EMAIL_USERNAME = 'ps_rms@xiamenair.com'
EMAIL_PASSWORD = os.environ.get('DP_EMAIL_PASSWORD', '!111qqqq08')

EMAIL_SMTP_HOST = 'mail.xiamenair.com.cn'
EMAIL_POP_HOST = 'mail.xiamenair.com.cn'
EMAIL_IMAP_HOST = 'mail.xiamenair.com.cn'

EMAIL_SENT_KEEP_DAYS = 30
"""发件箱邮件默认保留天数"""

EMAIL_SENT_KEEP_MAX = 200
"""发件箱邮件默认保留最大封数"""
