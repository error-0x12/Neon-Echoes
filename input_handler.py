#!/usr/bin/env python3
"""
Neon Echoes - 多线程输入处理模块

将输入检测放到独立线程中，避免阻塞主线程的渲染。
支持 Windows (msvcrt + Win32 API) 和 Linux/macOS (termios + select)。
"""

import threading
import queue
import time
import logging
import os
import sys
from typing import Optional, Set, Dict, Callable
from collections import deque

# 配置日志
logger = logging.getLogger('NeonEchoes.InputHandler')


class InputEvent:
    """输入事件类"""
    KEY_DOWN = 'down'
    KEY_UP = 'up'

    def __init__(self, event_type: str, key: str, timestamp: float):
        self.event_type = event_type
        self.key = key
        self.timestamp = timestamp


class ThreadedInputHandler:
    """多线程输入处理器 - 跨平台支持 Windows / Linux / macOS"""

    def __init__(self, key_mapping: Dict[str, int], vk_keys_cache: Dict[str, int]):
        """
        初始化输入处理器

        Args:
            key_mapping: 按键到轨道索引的映射
            vk_keys_cache: VK键码缓存 (Windows only, Linux下不使用)
        """
        self.key_mapping = key_mapping
        self.vk_keys_cache = vk_keys_cache

        # 线程安全的输入事件队列
        self.event_queue: queue.Queue[InputEvent] = queue.Queue()

        # 当前按下的键集合（线程安全）
        self._pressed_keys: Set[str] = set()
        self._pressed_keys_lock = threading.Lock()

        # 输入处理线程
        self._input_thread: Optional[threading.Thread] = None
        self._running = False

        # 回调函数
        self.on_key_down: Optional[Callable[[str, int], None]] = None
        self.on_key_up: Optional[Callable[[str, int], None]] = None

        # 性能监控
        self._last_check_time = time.time()
        # 优化：降低轮询频率到120Hz（8.33ms间隔），减少CPU占用
        # 120Hz对于音游输入已经足够，500Hz会造成过多的系统调用开销
        self._check_interval = 0.0083  # 8.3ms检查间隔（约120Hz轮询率）
        self._menu_check_interval = 0.033  # 菜单状态下30Hz（33ms）足够
        self._current_interval = self._check_interval

        # 游戏状态感知
        self._game_state = 'menu'  # 'menu' 或 'gameplay'

        # 平台检测
        self._is_windows = (os.name == 'nt')

        # Linux: 按键自动释放超时 (秒)
        # 如果按键在此时间内未再次出现，则认为已释放
        # 设置为 60ms，略大于典型终端按键重复间隔 (~33ms)
        self._linux_key_release_timeout = 0.06

        logger.info(f"ThreadedInputHandler 初始化完成 (平台: {'Windows' if self._is_windows else 'Linux/macOS'})")

    def start(self) -> None:
        """启动输入处理线程"""
        if self._running:
            return

        self._running = True
        if self._is_windows:
            self._input_thread = threading.Thread(target=self._input_loop_windows, daemon=True)
        else:
            self._input_thread = threading.Thread(target=self._input_loop_linux, daemon=True)
        self._input_thread.start()
        logger.info(f"输入处理线程已启动 ({'Windows' if self._is_windows else 'Linux/macOS'} 模式)")

    def stop(self) -> None:
        """停止输入处理线程"""
        self._running = False
        if self._input_thread and self._input_thread.is_alive():
            self._input_thread.join(timeout=0.5)
        logger.info("输入处理线程已停止")

    def set_game_state(self, state: str) -> None:
        """
        设置游戏状态，动态调整轮询频率

        Args:
            state: 'menu' 或 'gameplay'
        """
        if state != self._game_state:
            self._game_state = state
            if state == 'gameplay':
                self._current_interval = self._check_interval  # 120Hz
                logger.debug("输入轮询切换到高频模式 (120Hz)")
            else:
                self._current_interval = self._menu_check_interval  # 30Hz
                logger.debug("输入轮询切换到低频模式 (30Hz)")

    # ═══════════════════════════════════════════════════════════════════
    # Windows 输入处理
    # ═══════════════════════════════════════════════════════════════════

    def _input_loop_windows(self) -> None:
        """Windows 输入处理主循环（在独立线程中运行）"""
        import msvcrt
        import ctypes

        user32 = ctypes.windll.user32

        # 记录每个键的最后状态
        key_states: Dict[str, bool] = {}

        while self._running:
            loop_start = time.time()

            # 检查新按键输入（非阻塞）
            while msvcrt.kbhit():
                try:
                    ch = msvcrt.getch()
                    key = None

                    if ch in [b'\x00', b'\xe0']:
                        # 特殊键
                        special_key = msvcrt.getch()
                        # 将特殊键映射到对应的键码
                        special_keys = {
                            b'H': '\x1b[A',  # 上箭头
                            b'P': '\x1b[B',  # 下箭头
                            b'K': '\x1b[D',  # 左箭头
                            b'M': '\x1b[C',  # 右箭头
                            b'S': '\x7f',    # Delete键
                            b'G': '\x1b',    # ESC键
                            b'O': '\r',      # 回车键（小键盘）
                            b'I': '\t',      # Tab键
                            b';': '\x1b[2~', # Insert键
                            b'Q': '\x1b[5~', # Page Up键
                            b'R': '\x1b[6~', # Page Down键
                            b'k': '\x1b[H',  # Home键
                            b'm': '\x1b[F',  # End键
                        }
                        key = special_keys.get(special_key)
                    else:
                        # 普通键
                        try:
                            key = ch.decode('utf-8')
                        except UnicodeDecodeError:
                            key = ch.decode('latin-1')

                    # 处理所有按键（包括映射过的和特殊键）
                    if key:
                        timestamp = time.time()
                        self.event_queue.put(InputEvent(InputEvent.KEY_DOWN, key, timestamp))

                        # 只将映射过的键添加到pressed_keys
                        if key in self.key_mapping:
                            with self._pressed_keys_lock:
                                self._pressed_keys.add(key)
                            key_states[key] = True

                            # 调用回调
                            if self.on_key_down:
                                track_index = self.key_mapping[key]
                                self.on_key_down(key, track_index)
                except Exception as e:
                    logger.error(f"处理键盘输入时出错: {e}")

            # 检查已按下键的释放状态
            with self._pressed_keys_lock:
                keys_to_check = list(self._pressed_keys)

            for key in keys_to_check:
                if key in self.vk_keys_cache:
                    # 检查键是否释放
                    is_pressed = (user32.GetAsyncKeyState(self.vk_keys_cache[key]) & 0x8000) != 0

                    if not is_pressed and key_states.get(key, False):
                        # 键已释放
                        timestamp = time.time()
                        self.event_queue.put(InputEvent(InputEvent.KEY_UP, key, timestamp))
                        with self._pressed_keys_lock:
                            self._pressed_keys.discard(key)
                        key_states[key] = False

                        # 调用回调
                        if self.on_key_up:
                            track_index = self.key_mapping[key]
                            self.on_key_up(key, track_index)

            # 控制轮询频率 - 使用动态间隔
            elapsed = time.time() - loop_start
            sleep_time = self._current_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    # ═══════════════════════════════════════════════════════════════════
    # Linux / macOS 输入处理
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _parse_linux_escape_sequence(first_byte: str, stdin_fd) -> Optional[str]:
        """
        解析 Linux 终端转义序列。

        在 raw 模式下，特殊键会发送多字节转义序列:
          - 上箭头: \\x1b[A
          - 下箭头: \\x1b[B
          - 右箭头: \\x1b[C
          - 左箭头: \\x1b[D
          - Home:    \\x1b[H 或 \\x1b[1~
          - End:     \\x1b[F 或 \\x1b[4~
          - Delete:  \\x1b[3~
          - PageUp:  \\x1b[5~
          - PageDown:\\x1b[6~
          - Insert:  \\x1b[2~
          - F1-F4:   \\x1bOP, \\x1bOQ, \\x1bOR, \\x1bOS

        Args:
            first_byte: 第一个字节 (应为 '\\x1b')
            stdin_fd: stdin 文件描述符

        Returns:
            解析后的键字符串，如果无法解析则返回 None
        """
        import select

        # 检查是否有后续字节可用（短超时以区分 ESC 和转义序列）
        ready, _, _ = select.select([stdin_fd], [], [], 0.001)
        if not ready:
            # 单独的 ESC 键
            return '\x1b'

        try:
            second = stdin_fd.read(1)
        except (IOError, OSError):
            return '\x1b'

        if second != '[' and second != 'O':
            # 不是标准转义序列，返回 ESC + 后续字符
            return None  # 这种情况下返回 ESC，后续字符留待下次读取

        # 读取序列的其余部分
        try:
            ready, _, _ = select.select([stdin_fd], [], [], 0.005)
            if ready:
                third = stdin_fd.read(1)
            else:
                third = ''
        except (IOError, OSError):
            third = ''

        # 解析常见转义序列
        if second == '[':
            escape_map = {
                'A': '\x1b[A',      # 上箭头
                'B': '\x1b[B',      # 下箭头
                'C': '\x1b[C',      # 右箭头
                'D': '\x1b[D',      # 左箭头
                'H': '\x1b[H',      # Home
                'F': '\x1b[F',      # End
            }
            if third in escape_map:
                return escape_map[third]

            # 处理带 ~ 的序列 (如 \x1b[3~ = Delete)
            if third in '123456':
                try:
                    ready, _, _ = select.select([stdin_fd], [], [], 0.003)
                    if ready:
                        fourth = stdin_fd.read(1)
                        if fourth == '~':
                            tilde_map = {
                                '1': '\x1b[H',   # Home (alternate)
                                '2': '\x1b[2~',  # Insert
                                '3': '\x7f',     # Delete → map to DEL
                                '4': '\x1b[F',   # End (alternate)
                                '5': '\x1b[5~',  # Page Up
                                '6': '\x1b[6~',  # Page Down
                            }
                            return tilde_map.get(third)
                except (IOError, OSError):
                    pass

        elif second == 'O':
            # F1-F4: \x1bOP, \x1bOQ, \x1bOR, \x1bOS
            fkey_map = {
                'P': '\x1bOP',  # F1
                'Q': '\x1bOQ',  # F2
                'R': '\x1bOR',  # F3
                'S': '\x1bOS',  # F4
            }
            if third in fkey_map:
                return fkey_map[third]

        return None

    @staticmethod
    def _setup_linux_terminal():
        """
        配置 Linux 终端为 raw 模式以进行逐字符输入。
        返回旧的终端设置以便恢复。

        Returns:
            old_settings: 旧的终端设置，用于恢复
            fd: stdin 文件描述符
        """
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        tty.setraw(fd)
        return old_settings, fd

    @staticmethod
    def _restore_linux_terminal(old_settings, fd):
        """
        恢复 Linux 终端设置。

        Args:
            old_settings: 旧的终端设置
            fd: stdin 文件描述符
        """
        import termios
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass

    def _input_loop_linux(self) -> None:
        """
        Linux / macOS 输入处理主循环（在独立线程中运行）。

        使用 termios raw 模式 + select 实现非阻塞键盘输入检测。
        由于终端不报告按键释放事件，使用基于超时的自动释放机制：
        - 当按键在 stdin 上出现时，记录时间戳并触发 KEY_DOWN
        - 当按键在 KEY_RELEASE_TIMEOUT 内未再次出现（终端按键重复停止），
          则认为按键已释放，触发 KEY_UP

        这种机制利用了一个事实：当用户在终端中按住一个键时，
        终端会以固定间隔 (~30Hz) 重复发送该字符。
        """
        import select
        import termios
        import tty

        # 保存并配置终端
        fd = sys.stdin.fileno()
        try:
            old_settings = termios.tcgetattr(fd)
        except termios.error:
            # stdin 不是终端（例如被重定向），退化到无输入模式
            logger.warning("stdin 不是终端，输入处理将在有限模式下运行")
            while self._running:
                time.sleep(0.1)
            return

        try:
            tty.setraw(fd)

            # 记录每个按键的最后一次按下时间（用于自动释放检测）
            key_press_times: Dict[str, float] = {}

            while self._running:
                loop_start = time.time()

                # 使用 select 进行非阻塞轮询 (1ms 超时)
                try:
                    ready, _, _ = select.select([sys.stdin], [], [], 0.001)
                except (ValueError, OSError):
                    # stdin 可能已关闭或无效
                    time.sleep(0.01)
                    continue

                current_time = time.time()

                if ready:
                    try:
                        data = sys.stdin.read(1)
                    except (IOError, OSError):
                        data = ''

                    if data:
                        key = None

                        if data == '\x1b':
                            # 可能是 ESC 键或转义序列的开始
                            key = self._parse_linux_escape_sequence(data, sys.stdin)
                            if key is None:
                                # 解析失败，视为 ESC
                                key = '\x1b'
                        elif data == '\r':
                            # 在 raw 模式下，Enter 发送 \r，统一为 \n
                            key = '\r'
                        elif data == '\t':
                            key = '\t'
                        elif data == '\x7f':
                            # 退格键
                            key = '\x7f'
                        else:
                            # 普通可打印字符
                            key = data

                        if key:
                            # 触发 KEY_DOWN 事件
                            timestamp = current_time
                            self.event_queue.put(InputEvent(InputEvent.KEY_DOWN, key, timestamp))

                            # 只跟踪映射过的按键
                            key_lower = key.lower()
                            if key_lower in self.key_mapping:
                                with self._pressed_keys_lock:
                                    self._pressed_keys.add(key_lower)
                                key_press_times[key_lower] = timestamp

                                # 调用回调
                                if self.on_key_down:
                                    track_index = self.key_mapping[key_lower]
                                    self.on_key_down(key_lower, track_index)

                # 检查自动释放：如果按键在超时时间内未再次出现，则视为已释放
                with self._pressed_keys_lock:
                    held_keys = list(self._pressed_keys)

                for key in held_keys:
                    last_press = key_press_times.get(key, 0)
                    if current_time - last_press >= self._linux_key_release_timeout:
                        # 按键已释放
                        timestamp = current_time
                        self.event_queue.put(InputEvent(InputEvent.KEY_UP, key, timestamp))
                        with self._pressed_keys_lock:
                            self._pressed_keys.discard(key)
                        key_press_times.pop(key, None)

                        # 调用回调
                        if self.on_key_up:
                            track_index = self.key_mapping[key]
                            self.on_key_up(key, track_index)

                # 控制轮询频率 - 使用动态间隔
                elapsed = time.time() - loop_start
                sleep_time = self._current_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        finally:
            # 恢复终端设置
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════════════════
    # 公共 API
    # ═══════════════════════════════════════════════════════════════════

    def get_pressed_keys(self) -> Set[str]:
        """获取当前按下的键集合（线程安全）"""
        with self._pressed_keys_lock:
            return self._pressed_keys.copy()

    def process_events(self) -> None:
        """处理所有待处理的输入事件（在主线程中调用）"""
        while not self.event_queue.empty():
            try:
                event = self.event_queue.get_nowait()
                # 事件已经在_input_loop中处理，这里可以添加额外的处理逻辑
            except queue.Empty:
                break

    def is_key_pressed(self, key: str) -> bool:
        """检查指定键是否被按下"""
        with self._pressed_keys_lock:
            return key in self._pressed_keys


class InputBuffer:
    """输入缓冲区 - 用于平滑输入处理"""

    def __init__(self, buffer_size: int = 10):
        self.buffer_size = buffer_size
        self.press_times: Dict[str, deque] = {}
        self.release_times: Dict[str, deque] = {}

    def record_press(self, key: str, timestamp: float) -> None:
        """记录按键按下时间"""
        if key not in self.press_times:
            self.press_times[key] = deque(maxlen=self.buffer_size)
        self.press_times[key].append(timestamp)

    def record_release(self, key: str, timestamp: float) -> None:
        """记录按键释放时间"""
        if key not in self.release_times:
            self.release_times[key] = deque(maxlen=self.buffer_size)
        self.release_times[key].append(timestamp)

    def get_press_count(self, key: str, time_window: float) -> int:
        """获取指定时间窗口内的按键次数"""
        if key not in self.press_times:
            return 0

        current_time = time.time()
        count = 0
        for press_time in self.press_times[key]:
            if current_time - press_time <= time_window:
                count += 1
        return count
