"""
【程序目的】
实现对每日Excel报表VBA程序的自动调用和执行。
"""
import win32com.client
import os
from config.config import get_argparse


def use_vba(vba_file_path, macro_name):
    """打开 Excel 文件并执行指定的 VBA 宏。

    Args:
        vba_file_path: Excel 文件的完整路径。
        macro_name:    要执行的 VBA 宏名称。
    Returns:
        bool: 是否成功执行。
    """
    xl_app = None
    try:
        xl_app = win32com.client.DispatchEx("Excel.Application")
        xl_app.Visible = False       # 后台执行，不弹窗
        xl_app.DisplayAlerts = False

        workbook = xl_app.Workbooks.Open(vba_file_path, False)
        workbook.RefreshAll()
        workbook.Application.Run(macro_name)
        workbook.Close(True)

        return True
    except Exception as e:
        print(f"VBA 执行失败: {e}")
        return False
    finally:
        if xl_app:
            try:
                xl_app.quit()
            except Exception:
                pass  # quit 阶段的异常无需关心


if __name__ == '__main__':
    args = get_argparse()

    use_vba(
        os.path.join(args.root_dir, 'doc', '（夜间实际托管）往返航线定价情况模板.xlsm'),
        'DP_data'
    )
    use_vba(
        os.path.join(args.root_dir, 'doc', '往返航线定价情况（发领导）.xlsm'),
        'DP_Data_Boss'
    )
