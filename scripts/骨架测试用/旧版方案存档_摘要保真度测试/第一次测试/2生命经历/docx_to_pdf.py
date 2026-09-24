"""
DOCX 转 PDF 转换器 - 高速版（改进版）
支持在 Windows 文件资源管理器中批量转换 .docx 文件为 .pdf 文件
优化版本：复用 Word 实例 + 多线程 + 性能优化 + 稳定性修复

改进点：
1. 多线程模式下正确初始化/释放 COM（pythoncom.CoInitialize/CoUninitialize）
2. 使用 Path.with_suffix 生成 PDF 路径，避免字符串 replace 误替换
3. 使用 try/finally 确保 Word 进程一定会被清理，不留后台残留
4. 异常信息包含异常类型，便于排查问题
5. 已存在同名 PDF 时默认跳过，并给出 --overwrite 选项
6. 支持简单的失败重试机制
"""

import os
import sys
import argparse
from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


class WordConverter:
    """Word 转换器类 - 复用 Word 实例以提高性能"""

    def __init__(self):
        self.word = None
        self.initialized = False

    def initialize(self):
        """初始化 Word 应用程序（仅一次）"""
        if self.initialized:
            return True

        try:
            import win32com.client

            self.word = win32com.client.Dispatch("Word.Application")

            # 性能优化设置
            self.word.Visible = False       # 不显示窗口
            self.word.DisplayAlerts = 0     # 不显示警告弹窗

            # 禁用自动保存（部分版本可能不支持，忽略即可）
            try:
                self.word.Options.SaveInterval = 0
                self.word.Options.BackgroundSave = False
            except Exception:
                pass

            self.initialized = True
            return True

        except Exception as e:
            print(f"✗ 启动 Word 失败: {type(e).__name__}: {str(e)}")
            return False

    def convert_file(self, docx_path, overwrite=True):
        """
        转换单个文件

        参数:
            docx_path: .docx 文件的完整路径
            overwrite: 若目标 PDF 已存在，是否覆盖

        返回:
            (success: bool, message: str, elapsed: float)
        """
        start_time = time.time()
        filename = os.path.basename(docx_path)

        # 用 Path 安全生成目标路径，避免字符串 replace 误伤
        pdf_path = str(Path(docx_path).with_suffix(".pdf"))

        if not overwrite and os.path.exists(pdf_path):
            elapsed = time.time() - start_time
            return (True, f"⊘ {filename} - 已跳过（PDF 已存在）", elapsed)

        doc = None
        try:
            doc = self.word.Documents.Open(
                docx_path,
                False,  # ConfirmConversions
                True,   # ReadOnly
                False,  # AddToRecentFiles
            )

            # 格式代码 17 表示 PDF
            doc.SaveAs(pdf_path, FileFormat=17)

            elapsed = time.time() - start_time
            return (True, f"✓ {filename} ({elapsed:.1f}秒)", elapsed)

        except Exception as e:
            elapsed = time.time() - start_time
            return (False, f"✗ {filename} - {type(e).__name__}: {str(e)}", elapsed)

        finally:
            # 无论成功失败都尝试关闭文档，避免残留占用
            if doc is not None:
                try:
                    doc.Close(False)
                except Exception:
                    pass

    def cleanup(self):
        """清理资源 - 关闭 Word"""
        if self.word:
            try:
                self.word.Quit()
            except Exception:
                pass
            self.word = None
            self.initialized = False


def convert_batch_single_thread(docx_files, overwrite=True):
    """
    单线程批量转换（复用 Word 实例）
    适用于文件数量较少或系统资源有限的情况
    """
    converter = WordConverter()
    success_list = []
    fail_list = []

    if not converter.initialize():
        return [], docx_files[:]  # 全部视为失败

    print(f"开始转换 {len(docx_files)} 个文件...\n")

    try:
        for i, docx_file in enumerate(docx_files, 1):
            print(f"[{i}/{len(docx_files)}] 正在转换: {os.path.basename(docx_file)}")
            success, message, elapsed = converter.convert_file(docx_file, overwrite=overwrite)

            if success:
                success_list.append(docx_file)
            else:
                fail_list.append(docx_file)

            print(f"    {message}")
    finally:
        # 确保 Word 进程一定被关闭，即使循环中途异常
        converter.cleanup()
        print("\n✓ Word 已关闭")

    return success_list, fail_list


def convert_batch_multi_thread(docx_files, max_workers=3, overwrite=True):
    """
    多线程批量转换（每个线程一个 Word 实例）
    适用于文件数量较多的情况

    参数:
        docx_files: 文件列表
        max_workers: 最大线程数（建议 2-4，太多会占用过多内存）
        overwrite: 是否覆盖已存在的 PDF
    """
    success_list = []
    fail_list = []

    print(f"开始多线程转换 {len(docx_files)} 个文件（{max_workers} 个并发线程）...\n")

    def convert_worker(file_path):
        """工作线程函数 —— 必须在线程内初始化/释放 COM"""
        import pythoncom
        pythoncom.CoInitialize()
        converter = WordConverter()
        try:
            if not converter.initialize():
                return (False, f"✗ {os.path.basename(file_path)} - 无法启动 Word", 0)
            return converter.convert_file(file_path, overwrite=overwrite)
        finally:
            converter.cleanup()
            pythoncom.CoUninitialize()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(convert_worker, f): f for f in docx_files}

        completed = 0
        for future in as_completed(future_to_file):
            file_path = future_to_file[future]
            completed += 1

            try:
                success, message, elapsed = future.result()
                print(f"[{completed}/{len(docx_files)}] {message}")

                if success:
                    success_list.append(file_path)
                else:
                    fail_list.append(file_path)

            except Exception as e:
                fail_list.append(file_path)
                print(f"[{completed}/{len(docx_files)}] ✗ {os.path.basename(file_path)} "
                      f"- 异常: {type(e).__name__}: {str(e)}")

    return success_list, fail_list


def retry_failed(fail_list, overwrite=True):
    """对失败的文件用单线程模式重试一次（更稳定）"""
    if not fail_list:
        return [], []

    print(f"\n正在重试 {len(fail_list)} 个失败的文件（单线程模式）...\n")
    return convert_batch_single_thread(fail_list, overwrite=overwrite)


def main():
    parser = argparse.ArgumentParser(description="DOCX 转 PDF 批量转换器")
    parser.add_argument("files", nargs="*", help=".docx 文件路径")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=True,
        help="覆盖已存在的同名 PDF（默认开启）",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="若目标 PDF 已存在则跳过（覆盖 --overwrite 的默认行为）",
    )
    parser.add_argument(
        "--no-retry",
        action="store_true",
        help="失败后不自动重试",
    )
    args = parser.parse_args()

    overwrite = not args.skip_existing

    print("=" * 70)
    print("DOCX 转 PDF 转换器 - 高速版（改进版）")
    print("=" * 70)

    # 检查依赖
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        print("\n错误：缺少必要的库 'pywin32'")
        print("请在命令提示符中运行以下命令安装：")
        print("  pip install pywin32")
        input("\n按回车键退出...")
        sys.exit(1)

    if not args.files:
        print("\n使用方法：")
        print("1. 在文件资源管理器中选中一个或多个 .docx 文件")
        print("2. 右键点击 -> '发送到' -> 选择此程序")
        print("或者")
        print("3. 将 .docx 文件拖放到此程序图标上")
        print("\n可选参数：")
        print("  --skip-existing   若 PDF 已存在则跳过，不覆盖")
        print("  --no-retry        失败后不自动重试")
        input("\n按回车键退出...")
        sys.exit(0)

    # 收集所有 .docx 文件（去重、校验存在性）
    docx_files = []
    seen = set()
    for arg in args.files:
        if os.path.isfile(arg) and arg.lower().endswith(".docx"):
            abs_path = os.path.abspath(arg)
            if abs_path not in seen:
                seen.add(abs_path)
                docx_files.append(abs_path)

    if not docx_files:
        print("\n错误：没有找到 .docx 文件")
        input("\n按回车键退出...")
        sys.exit(1)

    print(f"\n找到 {len(docx_files)} 个文件待转换")
    if not overwrite:
        print("模式：已存在的 PDF 将被跳过（--skip-existing）")

    start_time = time.time()

    if len(docx_files) <= 5:
        print("使用模式：单线程高速转换\n")
        success_list, fail_list = convert_batch_single_thread(docx_files, overwrite=overwrite)
    else:
        print("使用模式：多线程并行转换\n")
        max_workers = min(4, max(2, len(docx_files) // 3))
        success_list, fail_list = convert_batch_multi_thread(
            docx_files, max_workers=max_workers, overwrite=overwrite
        )

    # 自动重试失败的文件（单线程更稳定，很多失败是并发抢占导致的）
    if fail_list and not args.no_retry:
        retried_success, still_failed = retry_failed(fail_list, overwrite=overwrite)
        success_list.extend(retried_success)
        fail_list = still_failed

    total_time = time.time() - start_time

    print("\n" + "=" * 70)
    print("转换完成！")
    print(f"总耗时: {total_time:.1f} 秒")
    if docx_files:
        print(f"平均速度: {total_time / len(docx_files):.1f} 秒/文件")
    print(f"成功: {len(success_list)} 个文件")

    if fail_list:
        print(f"失败: {len(fail_list)} 个文件")
        print("\n失败的文件：")
        for f in fail_list:
            print(f"  - {os.path.basename(f)}")

    print("=" * 70)

    if fail_list:
        # 有失败文件时停留，方便查看是哪些文件出了问题
        input("\n按回车键退出...")
    else:
        # 全部成功，自动关闭窗口
        print("全部转换成功，窗口将自动关闭。")
        time.sleep(1.5)


if __name__ == "__main__":
    main()
