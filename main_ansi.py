#!/usr/bin/env python3
"""
Neon Echoes - ANSI版本主程序

这个模块是游戏的入口点，使用ANSI转义序列进行渲染。
"""

# 版本号定义
__version__ = "0.2.0"

import sys
import os
import time
import select
import logging
import traceback
import datetime
import platform
import gc
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

# 优化：调整GC参数，减少随机卡顿
# 增加GC阈值，让GC不那么频繁地执行
gc.set_threshold(700, 10, 10)

# 导入多线程输入处理器
from input_handler import ThreadedInputHandler, InputEvent

# 启动时错误处理 - 在任何模块导入之前设置
def handle_startup_error(exc_type, exc_value, exc_traceback):
    """处理启动时的未捕获异常"""
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))

    # 尝试创建错误报告
    try:
        # 确保logs目录存在
        logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(logs_dir, exist_ok=True)

        # 创建错误日志
        error_log_path = os.path.join(logs_dir, 'startup_error.log')
        with open(error_log_path, 'w', encoding='utf-8') as f:
            f.write(f"时间: {datetime.datetime.now()}\n")
            f.write(f"版本: {__version__}\n")
            f.write(f"错误类型: {exc_type.__name__}\n")
            f.write(f"错误信息: {exc_value}\n")
            f.write(f"堆栈跟踪:\n{error_msg}\n")

            # 系统信息
            f.write("\n=== 系统信息 ===\n")
            f.write(f"操作系统: {platform.system()} {platform.version()}\n")
            f.write(f"Python版本: {platform.python_version()}\n")
            f.write(f"工作目录: {os.getcwd()}\n")

    except Exception as e:
        # 静默处理，避免终端输出
        pass

# 设置全局异常处理器
sys.excepthook = handle_startup_error

# 导入其他模块
from save_manager import SaveManager

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入游戏组件
from game_engine import GameState, NoteType, Difficulty, JudgementResult
from ansi_renderer import ANSIRenderer
from audio_manager import AudioManager
from ansi_tui_manager import ANSITUIManager
from config_manager import ConfigManager
from chart_parser import get_available_charts, load_chart_by_id
from error_reporter import ErrorReporter


class NeonEchoes:
    """Neon Echoes主游戏类 - 负责协调游戏的各个组件"""
    
    def __init__(self, use_ansi: bool = True):
        """
        初始化Neon Echoes游戏实例

        Args:
            use_ansi (bool): 是否使用ANSI颜色渲染，默认为True
        """
        # 是否使用ANSI颜色
        self.use_ansi = use_ansi

        # 初始化游戏组件
        self.game_state = GameState(difficulty=Difficulty.NORMAL)  # 默认使用NORMAL难度
        
        # 初始化配置管理器
        self.config_manager = ConfigManager()
        self.settings = self.config_manager.load_config()
        
        self.renderer = ANSIRenderer(self.game_state)
        self.audio_manager = AudioManager()
        self.tui_manager = ANSITUIManager(self.settings)
        
        # 初始化存档管理器
        self.save_manager = SaveManager()

        # 初始化错误报告器
        self.error_reporter = ErrorReporter()

        # 游戏循环参数
        self.fps = self.settings.get('fps', 60)  # 目标帧率
        self.frame_time = 1.0 / self.fps  # 每帧的时间（秒）
        self.is_paused = False  # 游戏暂停状态
        self._should_exit = False  # 修复：添加退出标志位
        
        # 初始化logger
        self.logger = logging.getLogger('NeonEchoes.MainANSI')
        self.logger.setLevel(logging.INFO)
        
        # 应用自动判定设置
        self.game_state.set_autoplay(self.settings.get('autoplay', False))
        
        # 键盘配置 - 10个轨道的按键分组
        self.key_mapping = {
            # 轨道0: qaz
            'q': 0,
            'a': 0,
            'z': 0,
            # 轨道1: wsx
            'w': 1,
            's': 1,
            'x': 1,
            # 轨道2: edc
            'e': 2,
            'd': 2,
            'c': 2,
            # 轨道3: rfv
            'r': 3,
            'f': 3,
            'v': 3,
            # 轨道4: tgb
            't': 4,
            'g': 4,
            'b': 4,
            # 轨道5: yhn
            'y': 5,
            'h': 5,
            'n': 5,
            # 轨道6: ujm
            'u': 6,
            'j': 6,
            'm': 6,
            # 轨道7: ik,
            'i': 7,
            'k': 7,
            ',': 7,
            # 轨道8: ol.
            'o': 8,
            'l': 8,
            '.': 8,
            # 轨道9: p;'
            'p': 9,
            ';': 9,
            "'": 9,
            # 空格用于触发大note和暂停/继续游戏
            ' ': 10
        }
        
        # 按键状态跟踪
        self.pressed_keys = set()  # 记录当前按下的轨道按键
        self.no_input_frames = 0  # 连续没有按键输入的帧数
        
        # 缓存VK键码，避免每次调用都重新定义
        self._vk_keys_cache = {
            'q': 0x51, 'a': 0x41, 'z': 0x5A,
            'w': 0x57, 's': 0x53, 'x': 0x58,
            'e': 0x45, 'd': 0x44, 'c': 0x43,
            'r': 0x52, 'f': 0x46, 'v': 0x56,
            't': 0x54, 'g': 0x47, 'b': 0x42,
            'y': 0x59, 'h': 0x48, 'n': 0x4E,
            'u': 0x55, 'j': 0x4A, 'm': 0x4D,
            'i': 0x49, 'k': 0x4B, ',': 0xBC,
            'o': 0x4F, 'l': 0x4C, '.': 0xBE,
            'p': 0x50, ';': 0xBA, "'": 0xDE,
            ' ': 0x20
        }
        
        # 当前选中的谱面
        self.selected_chart = None
        
        # 初始化多线程输入处理器
        self.input_handler = ThreadedInputHandler(self.key_mapping, self._vk_keys_cache)
        self.input_handler.on_key_down = self._on_key_down
        self.input_handler.on_key_up = self._on_key_up
        
        # 设置TUI管理器的回调函数
        self.tui_manager.set_on_chart_select_callback(self.on_chart_selected)
        self.tui_manager.set_on_pause_action_callback(self.on_pause_action)
        self.tui_manager.set_on_result_action_callback(self.on_result_action)
        
        # 设置保存回调
        self.tui_manager.on_settings_changed = self.on_settings_changed
        
        # 加载可用谱面
        self._load_available_charts()
    
    def _load_available_charts(self) -> None:
        """
        加载可用的谱面列表
        """
        # 从charts目录加载所有可用的谱面文件
        available_charts = get_available_charts()
        self.tui_manager.set_charts(available_charts)
    
    def load_chart(self, chart_id: str) -> bool:
        """
        加载谱面文件
        
        Args:
            chart_id (str): 谱面唯一ID
            
        Returns:
            bool: 加载是否成功
        """
        try:
            self.logger.info(f"开始加载谱面ID: {chart_id}")
            # 首先停止任何正在播放的音频
            self.audio_manager.stop()
            
            chart_data = load_chart_by_id(chart_id)
            if not chart_data:
                self.logger.warning(f"未找到谱面ID: {chart_id}")
                return False
            
            self.game_state.load_chart(chart_data)
            
            # 加载对应的音频文件
            # 修复：同时检查'audio_file'和'audio'键名
            audio_file = None
            if 'audio_file' in chart_data and chart_data['audio_file']:
                audio_file = chart_data['audio_file']
                self.logger.info(f"在chart文件中找到音频文件(audio_file): {audio_file}")
            elif 'audio' in chart_data and chart_data['audio']:
                audio_file = chart_data['audio']
                self.logger.info(f"在chart文件中找到音频文件(audio): {audio_file}")
                
            if audio_file:
                # 构建基础路径
                base_dir = os.path.dirname(os.path.abspath(__file__))
                audio_dir = os.path.join(base_dir, 'audio')
                
                # 尝试直接加载
                audio_path = os.path.join(audio_dir, audio_file)
                self.logger.info(f"尝试加载路径: {audio_path}")
                
                # 如果文件不存在，尝试去掉"audio-"前缀
                if not os.path.exists(audio_path) and audio_file.startswith("audio-"):
                    alt_audio_file = audio_file[6:]  # 去掉"audio-"前缀
                    audio_path = os.path.join(audio_dir, alt_audio_file)
                    self.logger.info(f"文件不存在，尝试去掉前缀后的路径: {audio_path}")
                
                if os.path.exists(audio_path):
                    self.logger.info(f"音频文件存在，尝试加载...")
                    # 记录音频初始化状态
                    self.logger.info(f"音频系统初始化状态: {self.audio_manager.audio_available}")
                    success = self.audio_manager.load_music(audio_path)
                    self.logger.info(f"音频加载结果: {'成功' if success else '失败'}")
                else:
                    self.logger.warning(f"音频文件不存在 - {audio_path}")
                    # 当音频文件不存在时，停止之前播放的音频
                    self.audio_manager.stop()
                    # 列出audio目录中的文件，帮助诊断
                    if os.path.exists(audio_dir):
                        self.logger.info(f"audio目录中的文件: {os.listdir(audio_dir)}")
                    else:
                        self.logger.error(f"audio目录不存在")
            else:
                self.logger.info("chart文件中未指定音频文件")
                # 当谱面没有音频文件时，停止之前播放的音频
                self.audio_manager.stop()
            
            return True
        except Exception as e:
            self.logger.error(f"加载谱面失败: {e}", exc_info=True)
            return False
    
    def on_chart_selected(self, chart: Dict[str, str]) -> None:
        """
        选择谱面的回调函数
        
        Args:
            chart (Dict[str, str]): 选中的谱面信息
        """
        import threading
        
        self.logger.info(f"选择谱面: {chart}")
        self.selected_chart = chart
        
        # 加载选中的谱面
        if chart and 'id' in chart:
            self.logger.info(f"尝试加载谱面ID: {chart['id']}")
            
            # 保存加载结果的共享变量
            load_result = {'success': False}
            
            # 创建加载线程
            def load_thread_func():
                load_result['success'] = self.load_chart(chart['id'])
                if load_result['success']:
                    # 确保应用当前的auto play和调试计时器设置
                    self.game_state.set_autoplay(self.settings.get('autoplay', False))
                    self.game_state.set_debug_timer(self.settings.get('debug_timer', False))
            
            # 启动加载线程
            load_thread = threading.Thread(target=load_thread_func)
            load_thread.start()
            
            # 播放谱面加载动画（主界面右移+谱面左滑入）
            self.logger.info("播放谱面加载动画")
            self.tui_manager.play_chart_load_animation(
                self.renderer, 
                self.game_state, 
                self.audio_manager
            )
            
            # 等待加载完成（如果动画结束但加载还没完成）
            load_thread.join()
            
            # 检查加载结果
            if load_result['success']:
                # 加载成功，进入游戏界面
                self.logger.info("谱面加载成功，进入游戏界面")
                self.tui_manager.set_state(ANSITUIManager.UIState.GAME_PLAY)
                self.game_state.start_game()
                self.audio_manager.play()
            else:
                self.logger.error("谱面加载失败")
        
    def on_pause_action(self, action: int) -> None:
        """
        暂停菜单操作的回调函数
        
        Args:
            action (int): 操作索引（0: 继续, 1: 重新开始, 2: 返回主菜单）
        """
        if action == 0:  # 继续游戏
            self.tui_manager.set_state(ANSITUIManager.UIState.GAME_PLAY)
            self.is_paused = False
            self.game_state.resume_game()
            self.audio_manager.resume()
        elif action == 1:  # 重新开始
            # 保存当前的auto play和调试计时器设置
            current_autoplay = self.settings.get('autoplay', False)
            current_debug_timer = self.settings.get('debug_timer', False)
            
            # 重新加载当前谱面
            if self.selected_chart and 'id' in self.selected_chart:
                self.game_state = GameState(difficulty=Difficulty.NORMAL)
                # 应用保存的设置
                self.game_state.set_autoplay(current_autoplay)
                self.game_state.set_debug_timer(current_debug_timer)
                
                self.renderer = ANSIRenderer(self.game_state)
                self.load_chart(self.selected_chart['id'])
                self.game_state.start_game()
                self.audio_manager.play()
                self.is_paused = False
                self.tui_manager.set_state(ANSITUIManager.UIState.GAME_PLAY)
        elif action == 2:  # 返回主菜单
            # 保存当前的auto play和调试计时器设置
            current_autoplay = self.settings.get('autoplay', False)
            current_debug_timer = self.settings.get('debug_timer', False)
            
            # 清理当前游戏状态
            self.game_state = GameState(difficulty=Difficulty.NORMAL)
            # 应用保存的设置
            self.game_state.set_autoplay(current_autoplay)
            self.game_state.set_debug_timer(current_debug_timer)
            
            self.renderer = ANSIRenderer(self.game_state)
            self.audio_manager.stop()
            self.is_paused = False
            self.tui_manager.set_state(ANSITUIManager.UIState.MAIN_MENU)

    def on_settings_changed(self, new_settings: Dict[str, Any]) -> None:
        """
        设置更改回调
        
        Args:
            new_settings (Dict[str, Any]): 新的设置
        """
        self.settings = new_settings
        self.fps = self.settings.get('fps', 60)
        self.frame_time = 1.0 / self.fps
        
        # 保存设置到配置文件
        self.config_manager.save_config(self.settings)
        
        # 应用音量设置
        if 'music_volume' in self.settings:
            self.audio_manager.set_music_volume(self.settings['music_volume'])
        if 'sfx_volume' in self.settings:
            self.audio_manager.set_sfx_volume(self.settings['sfx_volume'])
            
        # 应用音乐延迟设置
        if 'music_delay' in self.settings:
            self.audio_manager.set_music_delay(self.settings['music_delay'])
            
        # 应用自动判定设置
        if 'autoplay' in self.settings:
            self.game_state.set_autoplay(self.settings['autoplay'])
        
        # 应用调试计时器设置
        if 'debug_timer' in self.settings:
            self.game_state.set_debug_timer(self.settings['debug_timer'])
    
    def _on_key_down(self, key: str, track_index: int) -> None:
        """
        多线程输入处理器的按键按下回调
        
        Args:
            key (str): 按下的键
            track_index (int): 对应的轨道索引
        """
        # 添加到已按下键集合
        self.pressed_keys.add(key)
        
        # 如果在游戏状态，处理按键
        if self.tui_manager.current_state == ANSITUIManager.UIState.GAME_PLAY:
            if track_index < 10:  # 轨道按键
                self.game_state.down(track_index)
    
    def _on_key_up(self, key: str, track_index: int) -> None:
        """
        多线程输入处理器的按键释放回调
        
        Args:
            key (str): 释放的键
            track_index (int): 对应的轨道索引
        """
        # 从已按下键集合中移除
        self.pressed_keys.discard(key)
        
        # 如果在游戏状态，处理按键释放
        if self.tui_manager.current_state == ANSITUIManager.UIState.GAME_PLAY:
            if track_index < 10:  # 轨道按键
                self.game_state.up(track_index)
    
    def _on_game_over(self, stats):
        """游戏结束回调"""
        # 保存成绩
        self._save_current_score()
        
        # 已经在run方法中处理了结算界面设置，这里不再重复
        
    def on_result_action(self) -> None:
        """结算界面操作回调"""
        # 保存当前的auto play和调试计时器设置
        current_autoplay = self.settings.get('autoplay', False)
        current_debug_timer = self.settings.get('debug_timer', False)
        
        # 返回主菜单
        self.game_state = GameState(difficulty=Difficulty.NORMAL)
        # 应用保存的设置
        self.game_state.set_autoplay(current_autoplay)
        self.game_state.set_debug_timer(current_debug_timer)
        
        self.renderer = ANSIRenderer(self.game_state)
        self.audio_manager.stop()
        self.is_paused = False
        self.tui_manager.set_state(ANSITUIManager.UIState.MAIN_MENU)
    
    def start_with_chart(self, chart_id: str) -> None:
        """
        使用指定谱面直接开始游戏
        
        Args:
            chart_id (str): 谱面ID
        """
        # 加载指定谱面
        if self.load_chart(chart_id):
            # 确保应用当前的auto play和调试计时器设置
            self.game_state.set_autoplay(self.settings.get('autoplay', False))
            self.game_state.set_debug_timer(self.settings.get('debug_timer', False))
            
            # 加载成功，进入游戏界面
            self.tui_manager.set_state(ANSITUIManager.UIState.GAME_PLAY)
            self.game_state.start_game()
            self.audio_manager.play()
            # 运行游戏循环
            self.run()
        else:
            self.logger.error(f"无法加载谱面: {chart_id}")

    def _check_input_menu(self) -> Optional[str]:
        """
        检查菜单界面的用户输入（非阻塞）
        
        Returns:
            Optional[str]: 用户按下的键，如果没有输入则返回None
        """
        if os.name == 'nt':  # Windows
            import msvcrt
            
            # 检查是否有新的按键输入
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                # 检查是否是特殊键（第一个字节是0x00或0xe0）
                if ch in [b'\x00', b'\xe0']:
                    # 读取第二个字节来识别特殊键
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
                    return special_keys.get(special_key, '')
                else:
                    # 普通键，尝试UTF-8解码
                    try:
                        return ch.decode('utf-8')
                    except UnicodeDecodeError:
                        # 如果UTF-8解码失败，尝试使用latin-1解码
                        return ch.decode('latin-1')
            
            return None
        else:  # Unix/Linux
            ready, _, _ = select.select([sys.stdin], [], [], 0)
            if ready:
                return sys.stdin.read(1)
            return None
    
    def run(self) -> None:
        """运行游戏主循环"""
        # 创建日志记录器
        import logging
        self.logger = logging.getLogger('NeonEchoes.Main')
        self.logger.setLevel(logging.INFO)
        
        # 配置文件日志 - 使用覆盖模式('w')
        log_file = os.path.join(os.path.dirname(__file__), 'logs', 'main_log.log')
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # 记录版本号
        self.logger.info(f"Neon Echoes 版本 {__version__}")
        
        # 添加游戏结束处理
        original_should_game_end = self.game_state.should_game_end
        def wrapped_should_game_end():
            result = original_should_game_end()
            if result and hasattr(self, '_on_game_over'):
                # 准备游戏结束数据
                perfect_count = self.game_state.judgement_system.judgement_counts[JudgementResult.PERFECT]
                good_count = self.game_state.judgement_system.judgement_counts[JudgementResult.GOOD]
                bad_count = self.game_state.judgement_system.judgement_counts[JudgementResult.BAD]
                miss_count = self.game_state.judgement_system.judgement_counts[JudgementResult.MISS]
                total_notes = perfect_count + good_count + bad_count + miss_count
                accuracy = (perfect_count * 1.0 + good_count * 0.65) / total_notes * 100 if total_notes > 0 else 0
                
                stats = {
                    'score': self.game_state.score,
                    'judgements': {
                        'PERFECT': perfect_count,
                        'GOOD': good_count,
                        'BAD': bad_count,
                        'MISS': miss_count
                    },
                    'max_combo': self.game_state.max_combo,
                    'accuracy': accuracy
                }
                self._on_game_over(stats)
            return result
        
        self.game_state.should_game_end = wrapped_should_game_end
        
        try:
            self.logger.info("Neon Echoes 启动")
            
            # 启动多线程输入处理器
            self.input_handler.start()
            
            # 初始化性能监控
            self._frame_times = []
            
            while not self._should_exit:
                # 记录帧开始时间
                frame_start_time = time.time()
                try:
                    # 修复：检查退出标志位
                    if self._should_exit:
                        break
                    
                    # 处理输入事件（从多线程输入处理器）
                    # 获取所有待处理的输入事件
                    # 处理输入事件（多线程输入处理器 - Windows）
                    while not self.input_handler.event_queue.empty():
                        try:
                            event = self.input_handler.event_queue.get_nowait()
                            if event.event_type == InputEvent.KEY_DOWN:
                                self._handle_input(event.key)
                                if self._should_exit:
                                    break
                        except:
                            break

                    # 注：Linux/macOS 输入现在由 ThreadedInputHandler 的
                    # _input_loop_linux() 方法在后台线程中处理，
                    # 不再需要在此处直接读取 stdin。
                    # 修复：再次检查退出标志位
                    if self._should_exit:
                        break
                    
                    # 根据当前状态更新界面
                    if self.tui_manager.current_state == ANSITUIManager.UIState.MAIN_MENU:
                        # 优化：通知输入处理器切换到菜单模式（降低轮询频率）
                        self.input_handler.set_game_state('menu')
                        self.tui_manager.draw_main_menu(save_manager=self.save_manager)
                    elif self.tui_manager.current_state == ANSITUIManager.UIState.GAME_PLAY:
                        # 优化：通知输入处理器切换到游戏模式（提高轮询频率）
                        self.input_handler.set_game_state('gameplay')
                        # 获取当前音频播放时间并更新游戏状态
                        current_audio_time = self.audio_manager.get_position()
                        # 确保即使没有音频或音频时间为0，也能正确更新游戏时间
                        # 注意：get_position()已经返回毫秒，不需要再次乘以1000
                        self.game_state.current_time_ms = int(current_audio_time)
                            
                        # 计算帧时间增量（毫秒）
                        self.game_state.update(int(self.frame_time * 1000))
                        
                        # 渲染游戏画面
                        self.renderer.refresh()
                        
                        # 检查游戏是否结束
                        if self.game_state.should_game_end():
                            # 保存成绩
                            self._save_current_score()
                            
                            # 设置结算数据
                            perfect_count = self.game_state.judgement_system.judgement_counts[JudgementResult.PERFECT]
                            good_count = self.game_state.judgement_system.judgement_counts[JudgementResult.GOOD]
                            bad_count = self.game_state.judgement_system.judgement_counts[JudgementResult.BAD]
                            miss_count = self.game_state.judgement_system.judgement_counts[JudgementResult.MISS]
                            
                            # 计算准确率
                            total_notes = perfect_count + good_count + bad_count + miss_count
                            accuracy = (perfect_count * 1.0 + good_count * 0.65) / total_notes * 100 if total_notes > 0 else 0
                            
                            self.tui_manager.set_game_result_data(
                                score=self.game_state.score,
                                perfect=perfect_count,
                                good=good_count,
                                bad=bad_count,
                                miss=miss_count,
                                max_combo=self.game_state.max_combo,
                                accuracy=accuracy
                            )
                            # 停止音乐播放
                            self.audio_manager.stop()
                            # 切换到结算界面
                            self.tui_manager.set_state(ANSITUIManager.UIState.GAME_RESULT)
                    elif self.tui_manager.current_state == ANSITUIManager.UIState.GAME_PAUSED:
                        # 暂停时也使用低频轮询
                        self.input_handler.set_game_state('menu')
                        self.tui_manager.draw_game_paused()
                    elif self.tui_manager.current_state == ANSITUIManager.UIState.GAME_RESULT:
                        # 结算界面使用低频轮询
                        self.input_handler.set_game_state('menu')
                        self.tui_manager.draw_game_result()
                    elif self.tui_manager.current_state == ANSITUIManager.UIState.SETTINGS:
                        # 设置界面使用低频轮询
                        self.input_handler.set_game_state('menu')
                        self.tui_manager.draw_settings()
                    
                    # 控制帧率 - 优化：使用忙等待+sleep混合策略提高精度
                    elapsed = time.time() - frame_start_time
                    sleep_time = self.frame_time - elapsed
                    if sleep_time > 0:
                        # 优化：对于大于2ms的等待，先sleep大部分，再忙等待剩余部分
                        # 这样可以减少CPU占用，同时保持较高的定时精度
                        if sleep_time > 0.002:
                            time.sleep(sleep_time - 0.001)
                        # 忙等待剩余时间（1ms以内），确保精确的帧率
                        target_time = frame_start_time + self.frame_time
                        while time.time() < target_time:
                            pass
                    
                    # 记录帧时间用于性能监控
                    frame_end_time = time.time()
                    actual_frame_time = frame_end_time - frame_start_time
                    if hasattr(self, '_frame_times'):
                        self._frame_times.append(actual_frame_time)
                        if len(self._frame_times) > 60:  # 只保留最近60帧
                            self._frame_times.pop(0)
                    
                except Exception as frame_error:
                    # 捕获每帧的错误，记录日志并继续
                    import traceback
                    error_info = traceback.format_exc()
                    self.logger.error(f"帧循环错误: {frame_error}\n{error_info}")

                    # 检查是否启用错误报告
                    if self.settings.get('error_reporting', True):
                        # 创建错误报告
                        report_path = self.error_reporter.create_error_report(
                            error_message=str(frame_error),
                            traceback_info=error_info
                        )
                        if report_path:
                            # 记录到日志
                            user_instructions = self.error_reporter.get_user_instructions(report_path)
                            self.logger.info(f"错误报告已创建: {user_instructions}")
                    else:
                        self.logger.error(f"发生错误（错误报告已禁用）: {frame_error}")

                    # 尝试恢复到安全状态
                    if self.tui_manager.current_state == ANSITUIManager.UIState.GAME_PLAY:
                        self.tui_manager.set_state(ANSITUIManager.UIState.GAME_RESULT)
                        self.logger.info("游戏已暂停并切换到结算界面")
                        
        except KeyboardInterrupt:
            self.logger.info("用户中断 Neon Echoes")
        except Exception as e:
            import traceback
            error_info = traceback.format_exc()
            self.logger.critical(f"游戏严重错误: {e}\n{error_info}")

            # 检查是否启用错误报告
            if self.settings.get('error_reporting', True):
                # 创建错误报告
                report_path = self.error_reporter.create_error_report(
                    error_message=str(e),
                    traceback_info=error_info
                )
                if report_path:
                    # 记录到日志
                    user_instructions = self.error_reporter.get_user_instructions(report_path)
                    self.logger.info(f"错误报告已创建: {user_instructions}")
            else:
                self.logger.error(f"游戏严重错误（错误报告已禁用）: {e}")
        finally:
            # 停止多线程输入处理器
            if hasattr(self, 'input_handler'):
                self.input_handler.stop()
            self.logger.info("Neon Echoes 结束")
#╭─────────╮
#│ 此面向敌 │
#╰─┬─────┬─╯
# ╱       ╲
    def _handle_input(self, key: str) -> None:
        """
        处理用户输入
        
        Args:
            key (str): 用户按下的键
        """
        # 根据当前状态处理输入
        if self.tui_manager.current_state == ANSITUIManager.UIState.MAIN_MENU:
            self._handle_main_menu_input(key)
        elif self.tui_manager.current_state == ANSITUIManager.UIState.GAME_PLAY:
            self._handle_game_play_input(key)
        elif self.tui_manager.current_state == ANSITUIManager.UIState.GAME_PAUSED:
            self._handle_game_paused_input(key)
        elif self.tui_manager.current_state == ANSITUIManager.UIState.GAME_RESULT:
            self._handle_game_result_input(key)
        elif self.tui_manager.current_state == ANSITUIManager.UIState.SETTINGS:
            self._handle_settings_input(key)
    
    def _handle_main_menu_input(self, key: str) -> None:
        """处理主菜单输入"""
        need_redraw = False
        
        # 调试：记录按键值
        # self.logger.debug(f"主菜单按键: repr={repr(key)}, hex={key.encode().hex() if key else 'None'}")
        
        if key.lower() == 'w' or key == '\x1b[A':  # 上移 (W键或上箭头)
            self.tui_manager.selected_chart_index = max(0, self.tui_manager.selected_chart_index - 1)
            need_redraw = True
        elif key.lower() == 's' or key == '\x1b[B':  # 下移 (S键或下箭头)
            visible_charts = self.tui_manager._get_visible_charts()
            self.tui_manager.selected_chart_index = min(len(visible_charts) - 1, self.tui_manager.selected_chart_index + 1)
            need_redraw = True
        elif key.lower() == 'a' or key == '\x1b[D':  # 上一页 (A键或左箭头)
            self.tui_manager.previous_chart_page()
            need_redraw = True
        elif key.lower() == 'd' or key == '\x1b[C':  # 下一页 (D键或右箭头)
            self.tui_manager.next_chart_page()
            need_redraw = True
        elif key == '\r' or key == '\n':  # 回车键
            # 选择当前谱面并开始游戏
            visible_charts = self.tui_manager._get_visible_charts()
            if visible_charts and 0 <= self.tui_manager.selected_chart_index < len(visible_charts):
                selected_chart = visible_charts[self.tui_manager.selected_chart_index]
                # 直接设置selected_chart，确保_save_current_score方法能正确获取谱面ID
                self.selected_chart = selected_chart
                if self.tui_manager.on_chart_select:
                    self.tui_manager.on_chart_select(selected_chart)
        elif key == '\x7f':  # DEL键
            # 进入设置界面
            self.tui_manager.set_state(ANSITUIManager.UIState.SETTINGS)
            need_redraw = True
        elif key.lower() == 'q' or key == '\x1b':  # ESC或Q键退出
            # 修复：使用标志位优雅退出，而不是直接sys.exit
            self._should_exit = True
        
        # 优化：如果需要重绘，设置脏标记
        if need_redraw:
            self.tui_manager._dirty_flags['main_menu'] = True
    
    def _handle_game_play_input(self, key: str) -> None:
        """处理游戏进行中输入"""
        key_lower = key.lower()
        if key_lower in self.key_mapping:
            track_index = self.key_mapping[key_lower]
            if track_index < 10:  # 轨道按键
                # 确保每个轨道独立处理，按键按下时：
                # 1. 调用down方法激活对应轨道
                self.game_state.down(track_index)
                # 2. 尝试击中该轨道上的音符
                self.game_state.hit_note(track_index)
                # 3. 将按键添加到已按下集合中，用于跟踪松开事件
                # 注意：使用小写键作为统一标识，确保大小写不敏感
                self.pressed_keys.add(key_lower)
            elif track_index == 10:  # 暂停键
                self.is_paused = True
                self.game_state.pause_game()
                self.audio_manager.pause()
                self.tui_manager.set_state(ANSITUIManager.UIState.GAME_PAUSED)
    
    def _handle_key_release(self, key: str) -> None:
        """
        处理按键松开事件
        在Windows非阻塞输入模式下，我们需要特殊处理按键松开
        
        Args:
            key: 松开的按键
        """
        key_lower = key.lower()
        if key_lower in self.pressed_keys:
            # 从已按下集合中移除该键
            self.pressed_keys.remove(key_lower)
            # 调用对应轨道的up方法，释放轨道
            if key_lower in self.key_mapping:
                track_index = self.key_mapping[key_lower]
                if track_index < 10:  # 轨道按键
                    self.game_state.up(track_index)
    
    def _handle_game_paused_input(self, key: str) -> None:
        """处理游戏暂停输入"""
        if key.lower() == 'w' or key == '\x1b[A':  # 上移 (W键或上箭头)
            self.tui_manager.selected_pause_option = max(0, self.tui_manager.selected_pause_option - 1)
        elif key.lower() == 's' or key == '\x1b[B':  # 下移 (S键或下箭头)
            self.tui_manager.selected_pause_option = min(len(self.tui_manager.pause_menu_options) - 1, self.tui_manager.selected_pause_option + 1)
        elif key == '\r' or key == '\n':  # 回车键
            # 执行选中的操作
            if self.tui_manager.on_pause_action:
                self.tui_manager.on_pause_action(self.tui_manager.selected_pause_option)
        elif key.lower() == 'q' or key == '\x1b':  # ESC键返回游戏
            self.tui_manager.set_state(ANSITUIManager.UIState.GAME_PLAY)
            self.is_paused = False
            self.game_state.resume_game()
            self.audio_manager.resume()
    
    def _handle_game_result_input(self, key: str) -> None:
        """处理结算界面输入"""
        if key == '\r' or key == '\n':  # 回车键
            # 返回主菜单
            if self.tui_manager.on_result_action:
                self.tui_manager.on_result_action()
    
    def _save_current_score(self):
        """保存当前游戏成绩"""
        # 如果启用了自动播放模式，不保存成绩
        if self.game_state.autoplay:
            if hasattr(self, 'logger'):
                self.logger.info("自动播放模式，不保存成绩")
            return
        try:
            # 获取游戏统计信息
            perfect_count = self.game_state.judgement_system.judgement_counts[JudgementResult.PERFECT]
            good_count = self.game_state.judgement_system.judgement_counts[JudgementResult.GOOD]
            bad_count = self.game_state.judgement_system.judgement_counts[JudgementResult.BAD]
            miss_count = self.game_state.judgement_system.judgement_counts[JudgementResult.MISS]
            
            # 计算准确率
            total_notes = perfect_count + good_count + bad_count + miss_count
            accuracy = (perfect_count * 1.0 + good_count * 0.65) / total_notes * 100 if total_notes > 0 else 0
            
            # 根据分数计算等级
            score = self.game_state.score
            if score >= 1000000:
                grade = 'AP'
            elif score >= 950000:
                grade = 'V'
            elif score >= 920000:
                grade = 'S'
            elif score >= 880000:
                grade = 'A'
            elif score >= 820000:
                grade = 'B'
            elif score >= 720000:
                grade = 'C'
            else:
                grade = 'F'
            
            # 准备成绩数据字典
            score_data = {
                'score': score,
                'grade': grade,
                'max_combo': self.game_state.max_combo,
                'perfect_count': perfect_count,
                'good_count': good_count,
                'miss_count': miss_count + bad_count,  # 将BAD和MISS合并为miss_count
                'difficulty': self.game_state.difficulty.name,
                'game_speed': self.game_state.game_speed,
                'accuracy': accuracy
            }
            
            # 保存成绩 - 按照SaveManager API要求的格式
            chart_id = self.selected_chart['id'] if self.selected_chart else 'unknown'
            success = self.save_manager.save_score(chart_id, score_data)
            
            # 安全地记录日志，避免logger不存在的问题
            if hasattr(self, 'logger'):
                if success:
                    self.logger.info(f"成功保存成绩: {score} (Grade: {grade})")
                else:
                    self.logger.error("保存成绩失败")
                
        except Exception as e:
            # 安全地记录日志
            if hasattr(self, 'logger'):
                self.logger.error(f"保存成绩时出错: {e}")
    
    def _handle_settings_input(self, key: str) -> None:
        """处理设置界面输入"""
        # 处理清空数据的确认状态
        if self.tui_manager.confirming_clear_data:
            # 检查是否按下了确认键（1-9的随机键）
            if hasattr(self.tui_manager, 'clear_data_confirm_key') and key == self.tui_manager.clear_data_confirm_key:
                # 执行清空数据操作
                success = self.save_manager.clear_all_scores()
                if success and hasattr(self, 'logger'):
                    self.logger.info("所有数据已清空")
                # 退出确认状态
                self.tui_manager.confirming_clear_data = False
            elif key == '0' or key.lower() == 'q' or key == '\x1b':
                # 取消清空操作
                self.tui_manager.confirming_clear_data = False
            # 其他键也取消操作
            else:
                self.tui_manager.confirming_clear_data = False
            return
        
        if key.lower() == 'w' or key == '\x1b[A':  # 上移 (W键或上箭头)
            self.tui_manager.selected_setting_option = max(0, self.tui_manager.selected_setting_option - 1)
        elif key.lower() == 's' or key == '\x1b[B':  # 下移 (S键或下箭头)
            self.tui_manager.selected_setting_option = min(len(self.tui_manager.setting_options) - 1, self.tui_manager.selected_setting_option + 1)
        elif key.lower() == 'a' or key == '\x1b[D':  # 减小数值 (A键或左箭头)
            self._adjust_setting_value(-1)
        elif key.lower() == 'd' or key == '\x1b[C':  # 增大数值 (D键或右箭头)
            self._adjust_setting_value(1)
        elif key == '\r' or key == '\n':  # 回车键
            # 检查是否选中了"清空数据"选项
            # 假设这是倒数第二个选项（在"返回主菜单"之前）
            if self.tui_manager.selected_setting_option == len(self.tui_manager.setting_options) - 2:
                # 进入确认状态
                self.tui_manager.confirming_clear_data = True
                # 生成1-9之间的随机确认键
                import random
                self.tui_manager.clear_data_confirm_key = str(random.randint(1, 9))
            # 如果是"返回主菜单"选项，则返回主菜单
            elif self.tui_manager.selected_setting_option == len(self.tui_manager.setting_options) - 1:
                self.tui_manager.set_state(ANSITUIManager.UIState.MAIN_MENU)
        elif key.lower() == 'q' or key == '\x1b':  # ESC键返回主菜单
            self.tui_manager.set_state(ANSITUIManager.UIState.MAIN_MENU)
    
    def _adjust_setting_value(self, direction: int) -> None:
        """
        调整设置选项的值
        
        Args:
            direction (int): 调整方向 (-1: 减小, 1: 增大)
        """
        option_index = self.tui_manager.selected_setting_option
        
        if option_index == 0:  # 音乐音量
            self.settings['music_volume'] = max(0.0, min(1.0, self.settings['music_volume'] + 0.1 * direction))
        elif option_index == 1:  # 音效音量
            self.settings['sfx_volume'] = max(0.0, min(1.0, self.settings['sfx_volume'] + 0.1 * direction))
        elif option_index == 2:  # 音乐延迟
            # 步长为10ms，范围-1000ms到1000ms
            self.settings['music_delay'] = max(-1000, min(1000, self.settings.get('music_delay', 0) + 10 * direction))
        elif option_index == 3:  # 帧率设置
            fps_options = [30, 60, 120, 144]
            current_fps = self.settings['fps']
            try:
                current_index = fps_options.index(current_fps)
                new_index = max(0, min(len(fps_options) - 1, current_index + direction))
                self.settings['fps'] = fps_options[new_index]
            except ValueError:
                self.settings['fps'] = 60
        elif option_index == 4:  # AutoPlay
            # 切换自动判定模式状态
            self.settings['autoplay'] = not self.settings.get('autoplay', False)
        elif option_index == 5:  # 调试计时器
            # 切换调试计时器状态
            self.settings['debug_timer'] = not self.settings.get('debug_timer', False)
        elif 5 <= option_index <= 9:  # 按键绑定
            # 这里应该实现按键绑定的修改逻辑
            pass
        
        # 通知设置已更改
        if self.tui_manager.on_settings_changed:
            self.tui_manager.on_settings_changed(self.settings)


def play_startup_animation(duration: float = 1.5) -> None:

    r"""
    播放启动动画 - 旋转字符 (/ - \ |)
    
    Args:
        duration: 动画持续时间（秒）
    """
    import sys
    import time
    
    # 清屏
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()
    
    # 旋转字符序列
    spinner_chars = ['/', '-', '\\', '|']
    
    # 获取终端尺寸以居中显示（跨平台）
    try:
        if os.name != 'nt':
            # Unix/Linux/macOS: 尝试 stty，失败则用 shutil
            try:
                with os.popen('stty size', 'r') as f:
                    result = f.read().strip()
                if result:
                    rows, columns = result.split()
                    screen_height, screen_width = int(rows), int(columns)
                else:
                    raise ValueError("stty size 返回空")
            except Exception:
                import shutil
                ts = shutil.get_terminal_size()
                screen_height, screen_width = ts.lines, ts.columns
        else:
            # Windows: 使用 Win32 Console API
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)

            class COORD(ctypes.Structure):
                _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

            class SMALL_RECT(ctypes.Structure):
                _fields_ = [("Left", wintypes.SHORT), ("Top", wintypes.SHORT),
                           ("Right", wintypes.SHORT), ("Bottom", wintypes.SHORT)]

            class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
                _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD),
                           ("wAttributes", wintypes.WORD), ("srWindow", SMALL_RECT),
                           ("dwMaximumWindowSize", COORD)]

            csbi = CONSOLE_SCREEN_BUFFER_INFO()
            kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(csbi))

            screen_height = csbi.srWindow.Bottom - csbi.srWindow.Top + 1
            screen_width = csbi.srWindow.Right - csbi.srWindow.Left + 1
    except Exception:
        screen_height, screen_width = 40, 160
    
    # 计算居中位置
    center_y = screen_height // 2
    center_x = screen_width // 2
    
    # 显示游戏名称
    title = "Neon Echoes"
    title_x = center_x - len(title) // 2
    sys.stdout.write(f"\033[{center_y - 1};{title_x + 1}H\033[36m{title}\033[0m")
    
    # 动画循环
    start_time = time.time()
    char_index = 0
    
    while time.time() - start_time < duration:
        # 在原地更新旋转字符
        sys.stdout.write(f"\033[{center_y + 1};{center_x + 1}H\033[33m{spinner_chars[char_index]}\033[0m")
        sys.stdout.flush()
        
        # 切换到下一个字符
        char_index = (char_index + 1) % len(spinner_chars)
        
        # 短暂延迟
        time.sleep(0.1)
    
    # 清屏
    sys.stdout.write('\033[2J\033[H')
    sys.stdout.flush()


def main():
    """主函数"""
    import argparse
    
    # 创建参数解析器
    parser = argparse.ArgumentParser(description='Neon Echoes - 终端下落式音游')
    parser.add_argument('--chart', type=str, help='直接加载指定的谱面ID')
    parser.add_argument('-N', '--No_ANSI', action='store_true', help='不使用ANSI颜色渲染，只使用白色字符（提高兼容性）')
    parser.add_argument('--no-animation', action='store_true', help='跳过启动动画')
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # Unix/Linux: 设置终端为非规范模式，为 ANSI 渲染和输入处理做准备。
    # 注意：ThreadedInputHandler 在启动后会将终端设为 raw 模式，
    # 并在停止时恢复为当前设置。此处的 cbreak 设置作为中间层，
    # 确保启动动画（input handler 启动前）能正常显示，
    # 同时在 input handler 停止后提供安全的终端状态。
    if os.name != 'nt':  # Unix/Linux/macOS
        import tty, termios
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())

    try:
        # 播放启动动画
        if not args.no_animation:
            play_startup_animation(duration=1.5)

        # 创建并运行游戏
        use_ansi = not args.No_ANSI
        game = NeonEchoes(use_ansi=use_ansi)

        # 如果指定了谱面ID，直接开始游戏
        if args.chart:
            game.start_with_chart(args.chart)
        else:
            game.run()
    finally:
        # 恢复终端原始设置
        if os.name != 'nt':  # Unix/Linux/macOS
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


if __name__ == "__main__":
    main()