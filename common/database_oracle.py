"""
【程序目的】
    实现 Python 对 Oracle 数据库数据的增、删、改、查等功能。

【设计要点】
    1. 连接池（SessionPool）：复用数据库连接，避免频繁创建/销毁 TCP 连接的开销。
    2. 上下文管理器（with 语句）：自动管理连接的获取和释放，无需手动 close。
    3. 多进程兼容：使用 spawn 模式启动子进程时，每个子进程独立初始化自己的连接池，
       不会出现连接共享冲突问题。
    4. 集中配置：数据库凭据、Instant Client 路径、连接池大小均通过 config/db_config.ini
       统一管理，不再硬编码在代码中。

【使用方式】
    from common.database_oracle import get_data, insert_data, verify_connection

    # 查询数据
    df = get_data("SELECT * FROM my_table")

    # 插入数据
    insert_data("my_table", my_df)

    # 验证连接
    result = verify_connection()
"""
import configparser
import logging
import os
import sys

import cx_Oracle
import pandas as pd


# ---------------------------------------------------------------------------
# 模块级变量声明
# ---------------------------------------------------------------------------
# _config：数据库配置字典，由 _load_db_config() 加载 db_config.ini 后填充。
#          初始为 None，首次使用时惰性加载，加载后包含 user/password/dsn 等字段。
# _pool  ：cx_Oracle 连接池对象（SessionPool），由 _get_pool() 按需创建。
#          在 spawn 多进程模式下，每个子进程都会拥有自己独立的 _pool 实例。
# ---------------------------------------------------------------------------
_config = None
_pool = None


# ---------------------------------------------------------------------------
# 内部工具函数：配置文件查找、加载、Oracle 客户端初始化、连接池管理
# ---------------------------------------------------------------------------

def _find_config_path():
    """
    查找 db_config.ini 配置文件的完整路径。

    查找优先级（按顺序尝试，找到即返回）：
        1. 环境变量 DB_CONFIG_PATH 指定的路径
        2. PyInstaller 打包后的 exe 同级目录
        3. 开发环境下的项目 config/ 目录

    Returns:
        str: 配置文件的完整路径

    Raises:
        FileNotFoundError: 所有查找方式均未找到配置文件时抛出
    """
    # ---- 方式1：环境变量显式指定 ----
    # 适用于生产部署时灵活指定配置文件位置的场景
    env_path = os.environ.get('DB_CONFIG_PATH')
    if env_path and os.path.isfile(env_path):
        return env_path

    # ---- 方式2：PyInstaller 打包后的 exe 同级目录 ----
    # sys.frozen 为 True 表示当前运行在 PyInstaller 打包后的环境中
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        candidate = os.path.join(exe_dir, 'db_config.ini')
        if os.path.isfile(candidate):
            return candidate

    # ---- 方式3：开发环境，相对于本文件定位 ----
    # 本文件路径：common/database_oracle.py
    # 向上一级到项目根目录，再进入 config/ 目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.abspath(
        os.path.join(script_dir, '..', 'config', 'db_config.ini')
    )
    if os.path.isfile(candidate):
        return candidate

    # ---- 所有方式均失败 ----
    raise FileNotFoundError(
        f"找不到 db_config.ini 配置文件。\n"
        f"  请通过环境变量 DB_CONFIG_PATH 指定路径，\n"
        f"  或将配置文件放在可执行文件同级目录下。"
    )


def _load_db_config():
    """
    读取 db_config.ini 配置文件，返回数据库连接参数字典。

    配置文件格式（INI）：
        [oracle]
        user = 数据库用户名
        password = 数据库密码
        dsn = 连接描述符（如 host:port/service_name）
        instantclient_dir = Oracle Instant Client 目录路径
        pool_min = 连接池最小连接数（默认 1）
        pool_max = 连接池最大连接数（默认 3）
        pool_inc = 连接池增长步长（默认 1）

    Returns:
        dict: 包含 user, password, dsn, instantclient_dir, pool_min,
              pool_max, pool_inc 等键的配置字典
    """
    cp = configparser.ConfigParser()
    cp.read(_find_config_path(), encoding='utf-8')

    return {
        'user': cp.get('oracle', 'user'),
        'password': cp.get('oracle', 'password'),
        'dsn': cp.get('oracle', 'dsn'),
        'instantclient_dir': cp.get('oracle', 'instantclient_dir'),
        'pool_min': cp.getint('oracle', 'pool_min', fallback=1),
        'pool_max': cp.getint('oracle', 'pool_max', fallback=3),
        'pool_inc': cp.getint('oracle', 'pool_inc', fallback=1),
    }


def _init_oracle():
    """
    初始化 Oracle Instant Client 环境。

    功能：
        1. 如果 _config 尚未加载，调用 _load_db_config() 加载配置
        2. 调用 cx_Oracle.init_oracle_client() 加载 Instant Client 动态库
        3. 如果已初始化过（同一进程内重复调用），捕获 AlreadyInitialized 异常跳过

    设计说明：
        - 采用惰性初始化方式，在首次需要数据库操作时才加载配置和客户端
        - 避免在模块导入时就连接数据库，有利于多进程 spawn 模式下的独立初始化
        - cx_Oracle.init_oracle_client() 是官方推荐的初始化方式，
          比手动修改 os.environ['path'] 更专业可靠

    注意：
        本函数必须在任何 cx_Oracle 连接操作之前调用一次。
        在多进程 spawn 模式下，每个子进程首次调用时会各自初始化一次。
    """
    global _config
    if _config is None:
        _config = _load_db_config()
    try:
        cx_Oracle.init_oracle_client(lib_dir=_config['instantclient_dir'])
    except cx_Oracle.AlreadyInitialized:
        # 同一进程中重复调用时忽略，避免程序中断
        pass


def _get_pool():
    """
    获取（或创建）Oracle 连接池 SessionPool。

    连接池机制：
        - 模块级单例模式：全局只维护一个连接池实例
        - 惰性创建：首次调用时由 _init_oracle() 加载配置后创建
        - 线程安全：通过 threaded=True 启用连接池的线程安全模式
        - 自动伸缩：池中连接不足时按 increment 步长增长，但不超过 max

    多进程兼容性说明（重要）：
        在 run.py 中通过 mp.set_start_method('spawn', force=True) 启动子进程时，
        每个子进程会重新导入本模块，因此 _pool 在各进程中独立创建，
        不存在连接共享或竞争问题。

    Returns:
        cx_Oracle.SessionPool: 数据库连接池对象
    """
    global _pool
    if _config is None:
        _init_oracle()
    # 断言确保配置加载成功，避免后续 _config 解包报错
    assert _config is not None, "数据库配置加载失败"
    if _pool is None:
        _pool = cx_Oracle.SessionPool(
            _config['user'],         # 数据库用户名
            _config['password'],     # 数据库密码
            _config['dsn'],          # 连接描述符
            min=_config['pool_min'], # 池中至少保持的连接数
            max=_config['pool_max'], # 池中最多允许的连接数
            increment=_config['pool_inc'],  # 连接不足时每次新增数量
            threaded=True,           # 启用线程安全模式
        )
    return _pool


# ---------------------------------------------------------------------------
# Oracle 数据库操作封装类
# ---------------------------------------------------------------------------
# 提供基础的增、删、改、查操作，支持 with 语句上下文管理器。
# 每次进入 with 块时从连接池获取一个连接，退出时自动释放回连接池。
#
# 使用示例：
#     with Oracle() as db:
#         data = db.queryAll("SELECT * FROM users")
#         db.insertBatch("INSERT INTO logs VALUES(:1, :2)", log_tuples)
# ---------------------------------------------------------------------------

class Oracle(object):
    """
    Oracle 数据库操作封装，支持 with 语句自动释放连接。

    with Oracle() as db:
        db.queryExecute("UPDATE table SET col=:1 WHERE id=:2", {'param1': val1})
        data = db.queryAll("SELECT * FROM table")
    # 退出 with 块后连接自动释放回连接池，无需手动 close
    """

    def __init__(self):
        """
        从连接池获取一个连接，并创建游标对象。

        设计说明：
            - 每次 __init__ 都从 _get_pool() 返回的连接池中 acquire 一个连接
            - 多个 with Oracle() 之间可能获取到不同的物理连接（由连接池调度）
            - 但连接池保证了连接的复用，避免频繁建立新连接
        """
        pool = _get_pool()
        self._conn = pool.acquire()
        self.cursor = self._conn.cursor()

    def __enter__(self):
        """
        进入 with 语句块时返回自身实例。
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        退出 with 语句块时关闭游标并释放连接回连接池。

        注意：
            - 这里调用 close() 是将连接归还到连接池，而非真正关闭 TCP 连接
            - 连接池会维护连接的健康状态，自动重建已断开的连接
        """
        self.cursor.close()
        self._conn.close()

    # ---- 查询操作 ---------------------------------------------------------

    def queryExecute(self, sql, nameParams=None):
        """
        执行 SQL 语句并提交事务。

        适用于 INSERT、UPDATE、DELETE 等 DML 操作，执行后自动提交。

        Args:
            sql: SQL 语句字符串，可使用 :1、:name 等绑定变量语法
            nameParams: 绑定参数字典或元组，默认为空

        示例:
            db.queryExecute("UPDATE flt SET price=:1 WHERE id=:2", (100, 'FL001'))
        """
        nameParams = nameParams or {}
        if nameParams:
            self.cursor.execute(sql, nameParams)
        else:
            self.cursor.execute(sql)
        self._conn.commit()

    def queryTitle(self, sql, nameParams=None):
        """
        执行查询并返回结果集的列名列表。

        常用于获取 DataFrame 的列名，以便构造带列名的 DataFrame。

        Args:
            sql: 查询 SQL 语句
            nameParams: 绑定参数字典，默认为空

        Returns:
            list: 列名字符串列表，如 ['FLT_DATE', 'AIR_CODE', 'FLT_NO']
        """
        nameParams = nameParams or {}
        if nameParams:
            self.cursor.execute(sql, nameParams)
        else:
            self.cursor.execute(sql)

        return [desc[0] for desc in self.cursor.description]

    def queryAll(self, sql):
        """
        查询并返回所有结果行。

        Args:
            sql: 查询 SQL 语句

        Returns:
            list: 所有行组成的列表，每行是一个元组
        """
        self.cursor.execute(sql)
        return self.cursor.fetchall()

    def queryOne(self, sql):
        """
        查询并返回第一条结果行。

        适用于只需要单行结果的场景，如查询汇总值、检查记录是否存在等。

        Args:
            sql: 查询 SQL 语句

        Returns:
            tuple or None: 第一行数据的元组，无结果时返回 None
        """
        self.cursor.execute(sql)
        return self.cursor.fetchone()

    def queryBy(self, sql, nameParams=None):
        """
        带绑定参数查询并返回所有结果行。

        与 queryAll 的区别在于支持 SQL 绑定变量，可防止 SQL 注入。

        Args:
            sql: 带绑定变量的 SQL 语句
            nameParams: 绑定参数字典，如 {'param1': 'MF', 'param2': '2024-01-01'}

        Returns:
            list: 所有行组成的列表，每行是一个元组
        """
        nameParams = nameParams or {}
        if nameParams:
            self.cursor.execute(sql, nameParams)
        else:
            self.cursor.execute(sql)
        return self.cursor.fetchall()

    # ---- 写入操作 ---------------------------------------------------------

    def insertBatch(self, sql, nameParams=None):
        """
        批量插入数据（使用 executemany 提升性能）。

        适用于将 pandas DataFrame 转换为元组列表后批量写入的场景。
        相比逐条 INSERT，executemany 能大幅减少数据库交互次数。

        Args:
            sql: INSERT 语句，如 "INSERT INTO table VALUES(:1, :2, :3)"
            nameParams: 数据元组列表，如 [(val1, val2), (val3, val4)]

        示例:
            tuples = [tuple(x) for x in df.values]
            db.insertBatch("INSERT INTO TMP VALUES(:1, :2, :3, :4)", tuples)
        """
        nameParams = nameParams or []
        self.cursor.prepare(sql)
        self.cursor.executemany(None, nameParams)
        self._conn.commit()

    def deleteBatch(self, sql):
        """
        执行删除操作并提交事务。

        Args:
            sql: DELETE 语句
        """
        self.cursor.execute(sql)
        self._conn.commit()

    def commit(self):
        """
        手动提交当前事务。

        一般情况下事务由 queryExecute、insertBatch、deleteBatch 等方法自动提交。
        仅当需要在一个事务中组合多个操作（手动控制提交时机）时才使用此方法。
        """
        self._conn.commit()


# ---------------------------------------------------------------------------
# 对外开放的便捷函数
# ---------------------------------------------------------------------------
# 这些函数封装了 Oracle 类的常见使用模式，保持与旧版本完全一致的函数签名，
# 以便所有调用方（blocks/ 目录下的业务模块）无需做任何修改即可直接使用。
#
# 迁移说明：
#     旧版代码：每个函数中手动修改 PATH → 创建连接 → 执行操作 → 手动 close
#     新版代码：with Oracle() as db 自动管理连接的获取和释放
# ---------------------------------------------------------------------------

def get_data(sql):
    """
    执行查询并将结果转换为 pandas DataFrame。

    这是最常用的查询函数，适用于：
        - SELECT 查询航班基础数据
        - 获取模型训练/预测所需的数据集
        - 从 Oracle 读取数据后进行 pandas 分析处理

    Args:
        sql: 查询 SQL 语句字符串

    Returns:
        pd.DataFrame: 包含查询结果的 DataFrame，列名自动从数据库取

    示例:
        df = get_data("SELECT * FROM DP_FLT_LIST")
    """
    with Oracle() as db:
        col_names = db.queryTitle(sql)
        data = pd.DataFrame(db.queryBy(sql), columns=col_names)
    return data


def get_predict_data_param(sql, param1):
    """
    带绑定参数查询，返回 pandas DataFrame。

    在 SQL 中使用 :param1 作为占位符，适用于动态查询条件。

    Args:
        sql: 带 :param1 占位符的 SQL 语句
        param1: 绑定参数值，将替换 SQL 中的 :param1

    Returns:
        pd.DataFrame: 查询结果 DataFrame

    示例:
        df = get_predict_data_param(
            "SELECT * FROM FLT WHERE CARRIER=:param1",
            "MF"
        )
    """
    with Oracle() as db:
        named_params = {'param1': param1}
        col_names = db.queryTitle(sql, named_params)
        data = pd.DataFrame(db.queryBy(sql, named_params), columns=col_names)
    return data


def insert_data(table_name, df):
    """
    将 DataFrame 自动写入 Oracle 表，无需手动编写 INSERT 语句。

    自动根据 DataFrame 的列名生成列名列表和 :1, :2, :3... 绑定变量占位符，
    省去手动数列数和写 VALUES(:1, :2, ..., :N) 的繁琐工作。

    注意：DataFrame 的列名必须与数据库表的列名完全一致，顺序一一对应。

    Args:
        table_name: 目标数据库表名（字符串）
        df: 待插入的 pandas DataFrame

    示例:
        insert_data("MAX_RETURN_ADVICE_PRICE_COPY", df)
    """
    # 根据 DataFrame 的列名和列数，自动拼接 INSERT 语句
    columns = ', '.join(df.columns)
    placeholders = ', '.join([f':{i + 1}' for i in range(len(df.columns))])
    sql = f"INSERT INTO {table_name} ({columns}) VALUES({placeholders})"

    with Oracle() as db:
        tuples = [tuple(x) for x in df.values]
        db.insertBatch(sql, tuples)


def delete_data(sql):
    """
    执行删除操作。

    Args:
        sql: DELETE 语句

    示例:
        delete_data("DELETE FROM TMP_DATA WHERE FLT_DATE < SYSDATE-30")
    """
    with Oracle() as db:
        db.deleteBatch(sql)


def callproc(proc_name):
    """
    调用 Oracle 存储过程（仅有输出参数，无输入参数）。

    用于调用收益管理系统的数据处理存储过程，如刷新预测输入数据等。

    Args:
        proc_name: 存储过程名称，如 'RM_DP_FLT_EST_INPUT_CHG'

    说明:
        存储过程的输出参数 p_flag 用于接收执行状态，
        但当前业务逻辑不依赖此返回值进行后续判断。
    """
    with Oracle() as db:
        p_flag = db.cursor.var(cx_Oracle.STRING)
        db.cursor.callproc(proc_name, [p_flag])
        db.commit()
    logging.info('%s进程执行完毕！', proc_name)


# ---------------------------------------------------------------------------
# 数据库连接验证工具
# ---------------------------------------------------------------------------
# 用于快速诊断数据库连接链路是否正常。
# 按顺序检测：配置文件 → Instant Client 加载 → 连接池获取连接 → 执行查询。
# 哪一步失败就能快速定位问题所在。
#
# 使用方式：
#     python -m common.database_oracle
#     或在代码中调用：
#     from common.database_oracle import verify_connection
#     result = verify_connection()
# ---------------------------------------------------------------------------

def verify_connection():
    """
    验证数据库连接整条链路是否正常。

    检测流程：
        第1步 - 配置文件检测：能否找到并正确读取 db_config.ini
        第2步 - Instant Client 检测：能否成功加载 Oracle Instant Client 动态库
        第3步 - 连接查询检测：能否从连接池获取连接并执行 SELECT 1 FROM DUAL

    Returns:
        dict: 包含以下键
            - status:  bool, True 表示连接正常, False 表示存在异常
            - message: str,  总体结论描述
            - detail:  list, 每步检测的详细信息列表

    示例输出（成功）:
        [OK] 配置文件: D:\CodeStarge\...\config\db_config.ini
        [OK] Oracle Instant Client: D:\CodeStarge\venvs\instantclient_19_9
        [OK] 数据库连接成功 (DSN: ..., 用户: ...)
        [OK] 测试查询结果: (1,)

    示例输出（失败）:
        [FAIL] 错误详情: ORA-12154: TNS:无法解析指定的连接标识符
    """
    result = {"status": False, "message": "", "detail": []}

    try:
        # ---- 第1步：验证配置文件 ----
        config_path = _find_config_path()
        result["detail"].append(f"[OK] 配置文件: {config_path}")

        # ---- 第2步：验证 Instant Client 加载 ----
        _init_oracle()
        assert _config is not None, "配置加载失败"
        result["detail"].append(
            f"[OK] Oracle Instant Client: {_config['instantclient_dir']}"
        )

        # ---- 第3步：验证连接池 + 执行查询 ----
        with Oracle() as db:
            db.cursor.execute("SELECT 1 FROM DUAL")
            row = db.cursor.fetchone()
            result["detail"].append(
                f"[OK] 数据库连接成功 (DSN: {_config['dsn']}, 用户: {_config['user']})"
            )
            result["detail"].append(f"[OK] 测试查询结果: {row}")

        result["status"] = True
        result["message"] = "数据库连接正常"

    except Exception as e:
        result["message"] = f"[FAIL] {e}"
        result["detail"].append(f"[FAIL] 错误详情: {e}")

    return result


if __name__ == '__main__':
    """
    当直接运行此模块时，执行数据库连接验证。

    用法：
        python -m common.database_oracle
    """
    res = verify_connection()
    print('\n'.join(res["detail"]))
    print(f'\n结果: {res["message"]}')
