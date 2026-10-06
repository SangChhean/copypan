# -*- coding: utf-8 -*-
"""启动后端，并把控制台输出同时写进 logs/backend-YYYYMMDD.log。

用法（在 back_mic/backend 下，等同于原来的 uvicorn main:app --host 0.0.0.0 --port 8000）：
    python run_backend.py
可选：--app main:app --host 0.0.0.0 --port 8000 --app-dir <目录>

除了 uvicorn 与业务代码打出来的日志，还会额外记录“后端为什么停了”：
  - 启动时间、进程号、父进程号
  - 控制台事件：窗口被关闭（CTRL_CLOSE_EVENT）、Ctrl+C、Ctrl+Break、注销/关机
  - 未捕获的异常（含线程里的）
  - 进程退出
  - 每 5 分钟一行心跳；进程被强行结束时不会有任何“退出”记录，
    此时看最后一条心跳/日志的时间，就能知道大约是几点没的
"""
import argparse
import atexit
import ctypes
import datetime
import os
import sys
import threading
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG_DIR = HERE / "logs"
HEARTBEAT_SECONDS = 300

_fh = None


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def note(msg: str) -> None:
    """只写启动器自己的记录（同时打到控制台与文件）。"""
    line = f"{_now()} [run_backend] {msg}\n"
    try:
        sys.__stderr__.write(line)
        sys.__stderr__.flush()
    except Exception:
        pass
    if _fh:
        try:
            _fh.write(line)
            _fh.flush()
        except Exception:
            pass


class Tee:
    """把写入同时送到原控制台流和日志文件。"""

    def __init__(self, stream, fh):
        self._stream = stream
        self._fh = fh

    def write(self, s):
        try:
            self._stream.write(s)
        except Exception:
            pass
        try:
            self._fh.write(s)
            self._fh.flush()
        except Exception:
            pass
        return len(s)

    def flush(self):
        for t in (self._stream, self._fh):
            try:
                t.flush()
            except Exception:
                pass

    def isatty(self):
        return False

    def fileno(self):
        return self._stream.fileno()

    @property
    def encoding(self):
        return getattr(self._stream, "encoding", "utf-8")

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _install_console_handler() -> None:
    if os.name != "nt":
        return
    events = {
        0: "CTRL_C_EVENT（Ctrl+C）",
        1: "CTRL_BREAK_EVENT（Ctrl+Break）",
        2: "CTRL_CLOSE_EVENT（控制台窗口被关闭）",
        5: "CTRL_LOGOFF_EVENT（用户注销）",
        6: "CTRL_SHUTDOWN_EVENT（系统关机）",
    }
    handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

    def _handler(event):
        note(f"收到控制台事件：{events.get(event, event)}")
        return False  # 不拦截，交给后面的处理器（uvicorn 会正常关闭）

    # 必须保存引用，否则会被垃圾回收导致崩溃
    global _console_handler
    _console_handler = handler_type(_handler)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_handler, True)


def _heartbeat() -> None:
    stop = threading.Event()
    while not stop.wait(HEARTBEAT_SECONDS):
        note("心跳：仍在运行")


def main() -> None:
    global _fh
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default=os.environ.get("BACKEND_APP", "main:app"))
    ap.add_argument("--host", default=os.environ.get("BACKEND_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("BACKEND_PORT", "8000")))
    ap.add_argument("--app-dir", default=str(HERE))
    args = ap.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"backend-{datetime.date.today():%Y%m%d}.log"
    _fh = open(log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = Tee(sys.__stdout__, _fh)
    sys.stderr = Tee(sys.__stderr__, _fh)

    note(f"===== 启动 pid={os.getpid()} 父进程={os.getppid()} app={args.app} {args.host}:{args.port} =====")
    note(f"日志文件：{log_path}")

    def _excepthook(tp, val, tb):
        note("未捕获的异常：\n" + "".join(traceback.format_exception(tp, val, tb)))

    sys.excepthook = _excepthook
    threading.excepthook = lambda a: note(
        f"线程 {getattr(a.thread, 'name', '?')} 未捕获的异常：\n"
        + "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback))
    )
    atexit.register(lambda: note(f"进程退出 pid={os.getpid()}"))
    _install_console_handler()
    threading.Thread(target=_heartbeat, name="heartbeat", daemon=True).start()

    os.chdir(args.app_dir)
    sys.path.insert(0, args.app_dir)

    import uvicorn

    try:
        uvicorn.run(args.app, host=args.host, port=args.port, app_dir=args.app_dir, use_colors=False)
        note("uvicorn.run 正常返回（服务已停止）")
    except SystemExit as e:
        note(f"SystemExit code={e.code}")
        raise
    except BaseException:
        note("uvicorn.run 抛出异常：\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
