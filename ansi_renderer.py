#!/usr/bin/env python3
"""
Neon Echoes - ANSI渲染器模块

这个模块负责使用ANSI转义序列在终端中绘制游戏画面，包括背景、音符、判定线和用户界面元素。
"""

import os
import sys
import logging
from typing import Optional, Dict, List, Tuple
from game_engine import GameState, JudgementResult, NoteType

# 配置日志
logger = logging.getLogger('NeonEchoes.ANSIRenderer')
logger.setLevel(logging.DEBUG)

# 清除现有的处理器
if logger.handlers:
    logger.handlers.clear()

# 创建文件处理器 - 使用覆盖模式('w')
log_file = os.path.join(os.path.dirname(__file__), 'logs', 'renderer_log.log')
file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

# 设置日志格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# 添加处理器到logger
logger.addHandler(file_handler)
logger.info("ANSIRenderer 日志系统初始化完成")


class ANSIRenderer:
    """ANSI渲染器类 - 使用ANSI转义序列在终端中绘制游戏画面"""
    
    # 颜色定义和配置 (使用ANSI颜色代码)
    COLOR_CODES = {
        'background': '',           # 默认背景色
        'foreground': '\033[37m',   # 白色
        'note_normal': '\033[32m',  # 绿色
        'note_hold': '\033[34m',    # 蓝色
        'judgement_perfect': '\033[32m',  # 绿色
        'judgement_great': '\033[36m',    # 青色
        'judgement_good': '\033[33m',     # 黄色
        'judgement_miss': '\033[31m',     # 红色
        'track': '\033[37m',        # 白色
        'combo': '\033[35m',        # 紫色
        'score': '\033[33m',        # 黄色
        'track_active': '\033[32m', # 绿色
        'judgement_line': '\033[31m', # 红色
        'debug': '\033[35m',        # 紫色
        'reset': '\033[0m',         # 重置颜色
    }
    
    # 字符配置
    CHAR_CONFIG = {
        'note_normal': '######',  # 普通音符字符
        'note_hold': '██████',    # 长按音符字符
        'note_drag': '$$$$$$',    # 拖动音符字符
        'note_hold_fill': '██████', # 长按音符填充字符
        'track_border': '|', # 轨道边界字符
        'judgement_line': '=', # 判定线字符
        'debug': '┼',       # 调试辅助线字符
    }
    
    def __init__(self, game_state: GameState):
        """
        初始化ANSI渲染器
        
        Args:
            game_state (GameState): 游戏状态对象的引用
        """
        logger.info("=" * 60)
        logger.info("ANSIRenderer 初始化开始")
        logger.info("=" * 60)
        
        self.game_state = game_state
        logger.debug(f"游戏状态对象已绑定: {type(game_state).__name__}")
        
        # 获取终端尺寸
        self.screen_height, self.screen_width = self._get_terminal_size()
        logger.info(f"终端尺寸: {self.screen_width}x{self.screen_height}")
        
        # 游戏区域配置
        self.num_tracks = 10  # 轨道数量
        self.judgement_line_y = self.screen_height - 5  # 判定线的y坐标
        logger.debug(f"游戏区域配置: num_tracks={self.num_tracks}, judgement_line_y={self.judgement_line_y}")
        
        # 动态计算轨道宽度和间距，使总宽度与屏幕宽度相等
        self._calculate_track_dimensions()
        logger.info(f"轨道尺寸: track_width={self.track_width}, track_spacing={self.track_spacing}")
        
        # 音符配置
        self.note_visible_time = 2000  # 音符在屏幕上显示的总时间（毫秒）
        self.time_offset = 0  # 时间偏移量，用于微调音符显示位置（毫秒）
        logger.debug(f"音符配置: note_visible_time={self.note_visible_time}ms, time_offset={self.time_offset}ms")
        
        # 判定窗口可视化配置
        self.show_judgement_windows = False  # 是否显示判定窗口范围
        
        # 缓存轨道位置信息
        self._cache_track_positions()
        logger.debug(f"轨道位置缓存完成: {len(self.track_positions)} 个轨道")
        
        # 屏幕缓冲区
        self.screen_buffer = [[' ' for _ in range(self.screen_width)] for _ in range(self.screen_height)]
        self.color_buffer = [[self.COLOR_CODES['reset'] for _ in range(self.screen_width)] for _ in range(self.screen_height)]
        logger.debug(f"屏幕缓冲区初始化: {self.screen_width}x{self.screen_height}")
        
        # 优化：预计算HOLD音符渐变颜色，避免每帧重复计算
        self._hold_gradient_colors = self._precompute_hold_gradient_colors()
        logger.debug("HOLD音符渐变颜色预计算完成")
        
        logger.info("=" * 60)
        logger.info("ANSIRenderer 初始化完成")
        logger.info("=" * 60)
    
    def _precompute_hold_gradient_colors(self) -> Dict[str, str]:
        """
        预计算HOLD音符的渐变颜色
        返回两个字典：正常颜色和暗色（用于渐变效果）
        """
        hold_color = self.COLOR_CODES['note_hold']
        # 预计算两种颜色状态：正常亮度和暗亮度
        # 使用ANSI转义序列的亮度控制
        # \033[2m 是暗亮度，\033[22m 是正常亮度
        return {
            'normal': hold_color,
            'dim': '\033[2m' + hold_color,
        }
    
    def _get_terminal_size(self) -> Tuple[int, int]:
        """获取终端尺寸"""
        logger.debug("获取终端尺寸...")
        try:
            if os.name != 'nt':
                # Unix/Linux/Mac
                rows, columns = os.popen('stty size', 'r').read().split()
                size = (int(rows), int(columns))
                logger.info(f"Unix/Linux/Mac 终端尺寸: {size[1]}x{size[0]}")
                return size
            else:
                # Windows
                import ctypes
                from ctypes import wintypes
                
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
                
                # 定义 CONSOLE_SCREEN_BUFFER_INFO 结构
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
                
                # 计算窗口尺寸
                rows = csbi.srWindow.Bottom - csbi.srWindow.Top + 1
                columns = csbi.srWindow.Right - csbi.srWindow.Left + 1
                size = (rows, columns)
                logger.info(f"Windows 终端尺寸: {size[1]}x{size[0]}")
                return size
        except Exception as e:
            # 如果获取失败，返回较大的默认值
            logger.warning(f"获取终端尺寸失败: {e}, 使用默认值 160x40")
            return 40, 160

    def update_terminal_size(self) -> None:
        """更新终端尺寸"""
        logger.info("更新终端尺寸...")
        old_width, old_height = self.screen_width, self.screen_height
        self.screen_height, self.screen_width = self._get_terminal_size()
        
        if old_width != self.screen_width or old_height != self.screen_height:
            logger.info(f"终端尺寸变化: {old_width}x{old_height} -> {self.screen_width}x{self.screen_height}")
        else:
            logger.debug("终端尺寸未变化")
            
        self.judgement_line_y = self.screen_height - 5
        self._calculate_track_dimensions()
        self._cache_track_positions()
        # 重新初始化屏幕缓冲区
        self.screen_buffer = [[' ' for _ in range(self.screen_width)] for _ in range(self.screen_height)]
        self.color_buffer = [[self.COLOR_CODES['reset'] for _ in range(self.screen_width)] for _ in range(self.screen_height)]
        logger.debug("屏幕缓冲区已重新初始化")
    
    def _calculate_track_dimensions(self) -> None:
        """动态计算轨道宽度和间距，使总宽度与屏幕宽度相等或相近"""
        # 确保屏幕宽度有效
        if self.screen_width <= 0:
            logger.warning(f"屏幕宽度无效 ({self.screen_width})，使用默认轨道尺寸")
            self.track_width = 6
            self.track_spacing = 2
            return

        # 计算可用总宽度（减去边界占用的字符）
        total_width_needed = self.screen_width - 4  # 留出一点余量
        logger.debug(f"计算轨道尺寸: screen_width={self.screen_width}, total_width_needed={total_width_needed}")

        # 计算轨道宽度：总宽度减去所有轨道间距后的平均宽度
        # 轨道间距数量 = 轨道数量 - 1
        spacing_count = self.num_tracks - 1

        # 每个轨道间距至少为2个字符
        min_spacing = 2

        # 计算基础轨道宽度
        available_track_width = total_width_needed - (spacing_count * min_spacing)
        base_track_width = available_track_width // self.num_tracks
        logger.debug(f"基础轨道宽度计算: available_track_width={available_track_width}, base_track_width={base_track_width}")

        # 根据屏幕宽度动态调整轨道宽度
        if self.screen_width >= 120:
            # 大窗口：使用较宽的轨道
            self.track_width = max(5, base_track_width)
            logger.debug(f"大窗口模式: track_width={self.track_width}")
        elif self.screen_width >= 80:
            # 中等窗口：使用中等宽度
            self.track_width = max(4, base_track_width)
            logger.debug(f"中等窗口模式: track_width={self.track_width}")
        else:
            # 小窗口：使用较窄的轨道
            self.track_width = max(3, base_track_width)
            logger.debug(f"小窗口模式: track_width={self.track_width}")

        # 重新计算轨道间距，使总宽度与屏幕宽度尽量接近
        actual_total_width = self.num_tracks * self.track_width
        remaining_space = total_width_needed - actual_total_width
        logger.debug(f"轨道间距计算: actual_total_width={actual_total_width}, remaining_space={remaining_space}")

        if spacing_count > 0:
            # 在轨道之间均匀分配剩余空间
            self.track_spacing = min_spacing + (remaining_space // spacing_count)
            # 确保间距至少为最小值
            self.track_spacing = max(min_spacing, self.track_spacing)
        else:
            self.track_spacing = 0
        
        # 减小2格轨道宽度，使整体居中更好
        self.track_width = max(2, self.track_width - 2)
        
        logger.debug(f"轨道尺寸计算完成: track_width={self.track_width}, track_spacing={self.track_spacing}")
    
    def _cache_track_positions(self) -> None:
        """缓存轨道位置信息，提高渲染性能"""
        # 首先重新计算轨道尺寸
        self._calculate_track_dimensions()
        
        # 计算所有轨道的总宽度
        total_tracks_width = self.num_tracks * self.track_width + (self.num_tracks - 1) * self.track_spacing
        
        # 计算居中偏移量
        start_x = (self.screen_width - total_tracks_width) // 2
        start_x = max(0, start_x)  # 确保不为负数
        
        logger.debug(f"轨道居中计算: total_tracks_width={total_tracks_width}, screen_width={self.screen_width}, start_x={start_x}")
        
        self.track_positions = []
        for i in range(self.num_tracks):
            track_left = start_x + i * (self.track_width + self.track_spacing)
            track_right = track_left + self.track_width - 1
            track_center = (track_left + track_right) // 2
            
            self.track_positions.append({
                'left': track_left,
                'right': track_right,
                'center': track_center,
                'inner_left': track_left + 1,
                'inner_right': track_right - 1
            })
        
        logger.debug(f"轨道位置缓存完成: {len(self.track_positions)} 个轨道, 起始位置={start_x}")
    
    def _time_to_y_position(self, note_time: int) -> Optional[int]:
        """
        将音符时间戳映射到屏幕Y坐标
        
        实现原理：
        - 计算音符与当前时间的时间差
        - 根据时间差和谱面速度计算Y坐标
        - 谱面速度影响音符下落速度
        - 当时间差为负（已错过）时，不显示
        - 当时间差为0时，音符在判定线上
        - 当时间差为正（即将到达）时，音符在判定线上方
        
        Args:
            note_time (int): 音符的时间戳（毫秒）
            
        Returns:
            Optional[int]: 音符在屏幕上的Y坐标，如果不在可视范围内则返回None
        """
        # 计算时间差，应用时间偏移
        adjusted_note_time = note_time + self.time_offset
        time_diff = adjusted_note_time - self.game_state.current_time_ms
        
        # 如果音符已经错过判定窗口，则不显示
        if time_diff < -200:  # 200ms是MISS判定窗口
            return None
        
        # 计算可见范围（从顶部到底部判定线）
        visible_range = self.judgement_line_y - 1
        
        # 如果可见范围无效，返回None
        if visible_range <= 0:
            return None
        
        # 获取谱面速度设置，如果没有则使用默认值5.0
        chart_speed = getattr(self.game_state, 'speed', 5.0) if hasattr(self.game_state, 'speed') else 5.0
        
        # 设置一个基础预显示时间，但让流速影响音符的下落速度
        # 基础预显示时间为3秒，流速越高，音符下落越快
        base_pre_display_ms = 3000
        
        # 根据谱面速度调整预显示时间
        # 速度越高，预显示时间越短，音符下落越快
        pre_display_time_ms = int(base_pre_display_ms * (5.0 / chart_speed))
        
        # 计算音符应该出现的最早时间
        earliest_display_time = note_time - pre_display_time_ms
        
        # 如果当前时间还没到音符应该出现的时间，则不显示
        if self.game_state.current_time_ms < earliest_display_time:
            return None
        
        # 将时间差映射到屏幕Y坐标
        # 当时间差为pre_display_time_ms时，音符在屏幕顶部
        # 当时间差为0时，音符在判定线上
        progress = min(1.0, max(0.0, time_diff / pre_display_time_ms))
        y_pos = int(self.judgement_line_y - (progress * visible_range))
        
        # 确保Y坐标在有效范围内
        if y_pos < 0 or y_pos >= self.screen_height:
            return None
        
        return y_pos
    
    def _clear_screen_buffer(self) -> None:
        """清空屏幕缓冲区 - 优化版本：直接重置内容，避免重新创建列表"""
        reset_color = self.COLOR_CODES['reset']
        space_char = ' '
        
        for y in range(self.screen_height):
            row = self.screen_buffer[y]
            color_row = self.color_buffer[y]
            for x in range(self.screen_width):
                row[x] = space_char
                color_row[x] = reset_color
    
    def _set_char(self, y: int, x: int, char: str, color: str = '') -> None:
        """
        在屏幕缓冲区中设置字符和颜色
        
        Args:
            y (int): Y坐标
            x (int): X坐标
            char (str): 要设置的字符
            color (str): ANSI颜色代码
        """
        if 0 <= y < self.screen_height and 0 <= x < self.screen_width:
            self.screen_buffer[y][x] = char
            self.color_buffer[y][x] = color
    
    def draw_background(self) -> None:
        """绘制游戏背景，包括4条固定轨道的边界 - 优化版本：直接操作缓冲区"""
        border_char = self.CHAR_CONFIG['track_border']
        
        # 绘制轨道背景和边界
        for i, track_pos in enumerate(self.track_positions):
            # 获取轨道颜色（如果轨道被激活则使用激活颜色）
            track_color = self.COLOR_CODES['track_active'] if (i < len(self.game_state.tracks) and self.game_state.tracks[i].activated) else self.COLOR_CODES['track']
            
            left = track_pos['left']
            right = track_pos['right']
            
            # 优化：直接操作缓冲区，减少函数调用开销
            for y in range(self.screen_height):
                row_buffer = self.screen_buffer[y]
                color_row = self.color_buffer[y]
                # 左边界
                row_buffer[left] = border_char
                color_row[left] = track_color
                # 右边界
                row_buffer[right] = border_char
                color_row[right] = track_color
    
    def draw_notes(self) -> None:
        """绘制当前活跃的音符 - 优化版本：预过滤时间窗口内的音符"""
        # 获取谱面速度设置
        chart_speed = getattr(self.game_state, 'speed', 5.0) if hasattr(self.game_state, 'speed') else 5.0
        base_pre_display_ms = 3000
        pre_display_time_ms = int(base_pre_display_ms * (5.0 / chart_speed))
        
        # 计算时间窗口：只处理即将显示和正在显示的音符
        current_time = self.game_state.current_time_ms
        time_window_start = current_time - 500  # 稍微提前一点，处理刚刚过去的音符
        time_window_end = current_time + pre_display_time_ms + 500  # 预显示时间 + 缓冲
        
        # 快速过滤需要处理的音符
        # 修复：对于HOLD音符，需要考虑其持续时间
        notes_to_render = []
        for note in self.game_state.notes:
            # 普通音符：检查perfect_time是否在窗口内
            # HOLD音符：检查整个持续时间段是否与窗口重叠
            if note.type == NoteType.HOLD:
                # HOLD音符的开始和结束时间
                hold_start = note.perfect_time
                hold_end = note.perfect_time + note.duration
                # 检查HOLD音符的时间段是否与渲染窗口重叠
                if hold_start <= time_window_end and hold_end >= time_window_start:
                    notes_to_render.append(note)
            else:
                # 普通音符和DRAG音符：只检查perfect_time
                if time_window_start <= note.perfect_time <= time_window_end:
                    notes_to_render.append(note)
        
        note_count = len(self.game_state.notes)
        visible_count = 0
        
        for note in notes_to_render:
            # 计算音符的Y坐标
            # 修复：对于HOLD音符，只有已击中且头部过了判定窗口时才固定在判定线
            if note.type == NoteType.HOLD:
                # 先正常计算Y坐标
                y_pos = self._time_to_y_position(note.perfect_time)
                # 只有已击中的HOLD音符头部过了判定窗口才固定显示
                if y_pos is None and note.hit:
                    y_pos = self.judgement_line_y
            else:
                y_pos = self._time_to_y_position(note.perfect_time)
            
            # 如果音符不在可视范围内，跳过
            if y_pos is None:
                continue
            
            visible_count += 1
            
            # 选择音符颜色和字符
            if note.type == NoteType.HOLD:
                color_code = self.COLOR_CODES['note_hold']
                note_char = self.CHAR_CONFIG['note_hold']
                fill_char = self.CHAR_CONFIG['note_hold_fill']
            elif note.type == NoteType.DRAG:
                color_code = self.COLOR_CODES['note_normal']
                note_char = self.CHAR_CONFIG['note_drag']
                fill_char = note_char
            else:
                color_code = self.COLOR_CODES['note_normal']
                note_char = self.CHAR_CONFIG['note_normal']
                fill_char = note_char
            
            # 为音符的每个轨道绘制音符
            for track_idx in note.tracks:
                # 获取轨道位置信息
                if track_idx < 0 or track_idx >= len(self.track_positions):
                    continue  # 无效的轨道索引
                
                track_pos = self.track_positions[track_idx]
                
                # 计算音符在轨道中的显示
                if note.type == NoteType.HOLD:
                    # 修复：HOLD音符高度直接由duration_ms决定
                    # duration_ms是谱面中定义的长度（毫秒）
                    # 游戏使用固定的视觉速度来显示音符下落
                    # 视觉速度：每1000ms显示speed行
                    visual_speed = getattr(self.game_state, 'speed', 5.0) if hasattr(self.game_state, 'speed') else 5.0
                    
                    if note.duration > 0:
                        # duration_ms毫秒 ÷ 1000 × visual_speed = 应该渲染的行数
                        # 例如：duration=2000ms, speed=5行/秒 → 显示10行
                        note_height = max(1, int((note.duration / 1000.0) * visual_speed))
                        # 移除最大高度限制，让谱面制作者完全控制长度
                        # 但保留一个合理的上限避免内存问题
                        max_height = self.screen_height - 2  # 最多屏幕高度-2
                        note_height = min(note_height, max_height)
                    else:
                        note_height = 1
                    
                    # 优化：使用预计算的渐变颜色，避免每帧重复计算
                    gradient_colors = self._hold_gradient_colors
                    
                    # 修复：HOLD音符应该像普通音符一样居中显示，而不是填满整个轨道
                    # 计算HOLD音符的居中起始位置
                    hold_start_x = track_pos['center'] - (len(note_char) // 2)
                    
                    # 优化：计算渐变阈值行（30%位置）
                    dim_threshold = max(1, int(note_height * 0.3))
                    
                    inner_left = track_pos['inner_left']
                    inner_right = track_pos['inner_right']
                    
                    # 修复：计算已按住的部分的高度
                    hold_progress = min(note.held_time / note.duration, 1.0) if note.duration > 0 else 0.0
                    hold_height = int(hold_progress * note_height)
                    
                    # 判断是否是BAD/MISS（只有BAD/MISS才向下延伸）
                    is_bad_miss = note.judgement in [JudgementResult.BAD, JudgementResult.MISS]
                    
                    # HOLD音符的显示逻辑
                    # 未击中：整个音符正常下落
                    # 已击中GOOD/PERFECT：只需要音符尾部收缩，不向下延伸
                    # 已击中BAD/MISS：已按住部分向下延伸
                    if note.hit:
                        # 计算音符尾部（未按住部分）的显示高度
                        tail_height = note_height - hold_height
                        
                        # 绘制音符尾部（从头部门置向上）
                        if tail_height > 0:
                            for h in range(tail_height):
                                current_y = y_pos - 1 - h
                                if current_y < 0:
                                    break
                                
                                gradient_color = gradient_colors['normal'] if (h + hold_height) < dim_threshold else gradient_colors['dim']
                                
                                row_buffer = self.screen_buffer[current_y]
                                color_row = self.color_buffer[current_y]
                                for i, char in enumerate(note_char):
                                    x_pos = hold_start_x + i
                                    if inner_left <= x_pos <= inner_right:
                                        row_buffer[x_pos] = char
                                        color_row[x_pos] = gradient_color
                        
                        # 只有BAD/MISS才向下延伸
                        if is_bad_miss:
                            for h in range(hold_height):
                                hold_y = y_pos + h
                                if hold_y >= self.screen_height:
                                    break
                                
                                gradient_color = gradient_colors['normal'] if h < dim_threshold else gradient_colors['dim']
                                
                                row_buffer = self.screen_buffer[hold_y]
                                color_row = self.color_buffer[hold_y]
                                for i, char in enumerate(fill_char):
                                    x_pos = hold_start_x + i
                                    if inner_left <= x_pos <= inner_right:
                                        row_buffer[x_pos] = char
                                        color_row[x_pos] = gradient_color
                    else:
                        # 未击中：整个音符正常下落
                        for h in range(note_height):
                            current_y = y_pos - h
                            if current_y < 0:
                                break
                            
                            gradient_color = gradient_colors['normal'] if h < dim_threshold else gradient_colors['dim']
                            
                            row_buffer = self.screen_buffer[current_y]
                            color_row = self.color_buffer[current_y]
                            for i, char in enumerate(note_char):
                                x_pos = hold_start_x + i
                                if inner_left <= x_pos <= inner_right:
                                    row_buffer[x_pos] = char
                                    color_row[x_pos] = gradient_color
                else:
                    # 普通音符和拖动音符显示完整的多字符样式
                    # 计算起始位置，使音符居中显示在轨道内
                    start_x = track_pos['center'] - (len(note_char) // 2)
                    
                    # 优化：直接操作缓冲区，减少函数调用开销
                    row_buffer = self.screen_buffer[y_pos]
                    color_row = self.color_buffer[y_pos]
                    inner_left = track_pos['inner_left']
                    inner_right = track_pos['inner_right']
                    
                    # 绘制每个字符，确保不超出轨道边界
                    for i, char in enumerate(note_char):
                        x_pos = start_x + i
                        # 确保字符在轨道范围内
                        if inner_left <= x_pos <= inner_right:
                            row_buffer[x_pos] = char
                            color_row[x_pos] = color_code
        
        # 优化：移除每帧的debug日志，避免频繁创建临时字符串对象
        # if note_count > 0:
        #     logger.debug(f"音符绘制统计: 总数 {note_count}, 可见 {visible_count}")
    
    def draw_hud(self) -> None:
        """绘制游戏顶部的HUD（平视显示器），显示分数、连击数 - 优化版本：减少临时对象创建"""
        # 获取要显示的信息
        score = self.game_state.score
        combo = self.game_state.combo
        max_combo = self.game_state.max_combo
        
        hud_y = 0
        
        # 优化：直接绘制，避免创建临时列表和字典对象
        # 绘制分数 - 左侧
        score_text = f"SCORE: {score:,}"
        score_color = self.COLOR_CODES['score']
        for i, char in enumerate(score_text):
            if i < self.screen_width:
                self._set_char(hud_y, i, char, score_color)
        
        # 绘制连击数 - 居中
        if hasattr(self.game_state, 'autoplay') and self.game_state.autoplay:
            combo_text = f"AutoPlay: {combo} (MAX: {max_combo})"
        else:
            combo_text = f"COMBO: {combo} (MAX: {max_combo})"
        combo_color = self.COLOR_CODES['combo']
        combo_x = max(0, (self.screen_width - len(combo_text)) // 2)
        for i, char in enumerate(combo_text):
            if combo_x + i < self.screen_width:
                self._set_char(hud_y, combo_x + i, char, combo_color)
        
        # 绘制调试计时器 - 最右侧（如果启用）
        if hasattr(self.game_state, 'debug_timer') and self.game_state.debug_timer:
            current_time = self.game_state.current_time_ms
            minutes = current_time // 60000
            seconds = (current_time % 60000) // 1000
            milliseconds = current_time % 1000
            timer_text = f"TIME: {minutes:02d}:{seconds:02d}.{milliseconds:03d}"
            timer_color = self.COLOR_CODES['debug']
            timer_x = max(0, self.screen_width - len(timer_text) - 1)
            for i, char in enumerate(timer_text):
                if timer_x + i < self.screen_width:
                    self._set_char(hud_y, timer_x + i, char, timer_color)
    
    def draw_judgement_line(self) -> None:
        """绘制底部的判定线"""
        # 计算轨道区域的起始和结束位置
        if self.track_positions:
            track_start = self.track_positions[0]['left']
            track_end = self.track_positions[-1]['right']
            line_length = track_end - track_start + 1
            start_x = track_start
        else:
            # 如果没有轨道位置缓存，使用默认计算
            line_length = min(self.screen_width, self.num_tracks * (self.track_width + self.track_spacing) - self.track_spacing)
            start_x = 0
        
        judgement_line = self.CHAR_CONFIG['judgement_line'] * line_length
        
        # 绘制判定线
        color = self.COLOR_CODES['judgement_line']
        for i, char in enumerate(judgement_line):
            self._set_char(self.judgement_line_y, start_x + i, char, color)
    
    def draw_track_judgements(self) -> None:
        """绘制每个轨道判定线下方的判定结果"""
        # 检查game_state是否有轨道判定数据
        if not hasattr(self.game_state, 'track_judgements') or not hasattr(self.game_state, 'track_judgement_times'):
            return
        
        # 判定结果显示在判定线下方一行
        judgement_y = self.judgement_line_y + 1
        
        # 检查是否在有效范围内
        if judgement_y >= self.screen_height:
            return
        
        current_time = self.game_state.current_time_ms
        display_ms = getattr(self.game_state, 'track_judgement_display_ms', 500)
        
        # 为每个轨道绘制判定结果
        for track_idx, track_pos in enumerate(self.track_positions):
            if track_idx >= len(self.game_state.track_judgements):
                break
            
            judgement = self.game_state.track_judgements[track_idx]
            judgement_time = self.game_state.track_judgement_times[track_idx]
            
            # 检查判定结果是否在显示时间内
            if judgement is None or (current_time - judgement_time) > display_ms:
                continue
            
            # 获取判定结果文本和颜色
            judgement_text = judgement.value
            judgement_color_key = f'judgement_{judgement.value.lower()}'
            judgement_color = self.COLOR_CODES.get(judgement_color_key, self.COLOR_CODES['reset'])
            
            # 计算居中位置
            track_center = track_pos['center']
            start_x = track_center - (len(judgement_text) // 2)
            
            # 绘制判定结果
            for i, char in enumerate(judgement_text):
                x_pos = start_x + i
                # 确保在轨道范围内
                if track_pos['left'] <= x_pos <= track_pos['right']:
                    self._set_char(judgement_y, x_pos, char, judgement_color)
    
    def draw_key_bindings(self) -> None:
        """绘制判定线下方的键位提示"""
        # 定义每个轨道的键位（与main_ansi.py中的key_mapping对应）
        track_keys = [
            ['Q', 'A', 'Z'],
            ['W', 'S', 'X'],
            ['E', 'D', 'C'],
            ['R', 'F', 'V'],
            ['T', 'G', 'B'],
            ['Y', 'H', 'N'],
            ['U', 'J', 'M'],
            ['I', 'K', ','],
            ['O', 'L', '.'],
            ['P', ';', "'"]
        ]
        
        # 键位显示在判定线下方两行
        keys_y = self.judgement_line_y + 2
        
        # 检查是否在有效范围内
        if keys_y >= self.screen_height:
            return
        
        # 为每个轨道绘制键位
        color = self.COLOR_CODES['foreground']
        for track_idx, track_pos in enumerate(self.track_positions):
            if track_idx >= len(track_keys):
                break
            
            # 获取该轨道的三个键
            keys = track_keys[track_idx]
            
            # 计算键位字符串（三个键用/分隔）
            keys_text = '/'.join(keys)
            
            # 计算居中位置
            track_center = track_pos['center']
            start_x = track_center - (len(keys_text) // 2)
            
            # 绘制键位
            for i, char in enumerate(keys_text):
                x_pos = start_x + i
                # 确保在轨道范围内
                if track_pos['left'] <= x_pos <= track_pos['right']:
                    self._set_char(keys_y, x_pos, char, color)
    
    def draw_text_events(self) -> None:
        """绘制当前应该显示的文字事件"""
        if not hasattr(self.game_state, 'text_events'):
            return
        
        # 文字显示位置：判定线下方两行
        text_y = self.judgement_line_y + 2
        
        # 检查是否在有效范围内
        if text_y >= self.screen_height:
            return
        
        # 获取当前需要显示的文字事件
        current_texts = []
        for event in self.game_state.text_events:
            if event['start_time'] <= self.game_state.current_time_ms <= event['start_time'] + event['duration']:
                current_texts.append(event['content'])
        
        # 如果有多个文字事件，将它们合并显示
        if current_texts:
            display_text = ' '.join(current_texts)
            # 从终端最左侧开始显示文字
            text_x = 0
            
            # 首先清除该行的所有轨道分割线（用空格覆盖）
            for x in range(self.screen_width):
                self._set_char(text_y, x, ' ', self.COLOR_CODES['background'])
            
            # 绘制文字
            for i, char in enumerate(display_text):
                if text_x + i < self.screen_width:
                    self._set_char(text_y, text_x + i, char, self.COLOR_CODES['foreground'])
    
    def refresh(self) -> None:
        """刷新整个游戏画面 - 优化版本：降低终端尺寸检查频率"""
        try:
            # 优化：每30帧检查一次终端尺寸（约每0.5秒@60fps），而不是每帧都检查
            if not hasattr(self, '_frame_counter'):
                self._frame_counter = 0
            self._frame_counter += 1
            
            if self._frame_counter >= 30:
                self._frame_counter = 0
                
                # 重新获取屏幕尺寸（以防用户调整了终端窗口大小）
                new_height, new_width = self._get_terminal_size()
                
                # 如果屏幕尺寸发生变化，更新配置
                if new_height != self.screen_height or new_width != self.screen_width:
                    logger.info(f"检测到终端尺寸变化: {self.screen_width}x{self.screen_height} -> {new_width}x{new_height}")
                    self.screen_height, self.screen_width = new_height, new_width
                    self.judgement_line_y = self.screen_height - 5  # 更新判定线位置
                    self._cache_track_positions()  # 重新缓存轨道位置
                    
                    # 重新创建缓冲区
                    self.screen_buffer = [[' ' for _ in range(self.screen_width)] for _ in range(self.screen_height)]
                    self.color_buffer = [[self.COLOR_CODES['reset'] for _ in range(self.screen_width)] for _ in range(self.screen_height)]
            
            # 清空屏幕缓冲区
            self._clear_screen_buffer()
            
            # 绘制所有游戏元素
            self.draw_background()
            self.draw_notes()
            self.draw_judgement_line()
            self.draw_track_judgements()
            self.draw_key_bindings()
            self.draw_text_events()
            self.draw_hud()
            
            # 输出到终端
            self._render_to_terminal()
            
        except Exception as e:
            # 错误处理，确保程序不会崩溃
            logger.error(f"刷新画面时发生错误: {e}", exc_info=True)
    
    def _render_to_terminal(self) -> None:
        """将屏幕缓冲区渲染到终端 - 优化版本：使用预分配缓冲区，避免频繁创建对象"""
        # 使用预分配的字符串列表（在实例初始化时创建）
        if not hasattr(self, '_output_buffer'):
            # 预分配输出缓冲区
            self._output_buffer = [''] * (self.screen_height + 1)
            self._line_buffer = [''] * (self.screen_width * 2 + 10)  # 预留足够空间
        
        # 清屏和光标复位
        self._output_buffer[0] = '\033[2J\033[H'
        
        # 渲染每一行
        for y in range(self.screen_height):
            buffer_idx = 0
            current_color = ''
            
            for x in range(self.screen_width):
                char_color = self.color_buffer[y][x]
                if char_color != current_color:
                    self._line_buffer[buffer_idx] = char_color
                    buffer_idx += 1
                    current_color = char_color
                self._line_buffer[buffer_idx] = self.screen_buffer[y][x]
                buffer_idx += 1
            
            # 添加行尾
            self._line_buffer[buffer_idx] = self.COLOR_CODES['reset']
            buffer_idx += 1
            if y < self.screen_height - 1:
                self._line_buffer[buffer_idx] = '\n'
                buffer_idx += 1
            
            # 构建行字符串
            self._output_buffer[y + 1] = ''.join(self._line_buffer[:buffer_idx])
        
        # 一次性输出所有内容
        sys.stdout.write(''.join(self._output_buffer[:self.screen_height + 1]))
        sys.stdout.flush()
    
    def draw_game_result(self, perfect: int, good: int, miss: int, accuracy: float, score: int, max_combo: int, autoplay: bool = False) -> None:
        """
        绘制结算界面
        
        Args:
            perfect (int): Perfect判定数量
            good (int): Good判定数量
            miss (int): Miss判定数量
            accuracy (float): 准确率
            score (int): 分数
            max_combo (int): 最大连击数
            autoplay (bool): 是否启用了自动判定模式
        """
        # 清空屏幕缓冲区
        self._clear_screen_buffer()
        
        # 绘制标题 - 根据autoplay状态显示不同的标题
        title = "AutoPlay" if autoplay else "游戏结算"
        title_color = self.COLOR_CODES['combo']
        title_x = max(0, (self.screen_width - len(title)) // 2)
        title_y = 2
        
        for i, char in enumerate(title):
            self._set_char(title_y, title_x + i, char, title_color)
        
        # 绘制分隔线
        separator = "=" * min(self.screen_width, 40)
        separator_x = max(0, (self.screen_width - len(separator)) // 2)
        separator_y = title_y + 2
        
        for i, char in enumerate(separator):
            self._set_char(separator_y, separator_x + i, char, title_color)
        
        # 绘制各项数据
        result_items = [
            f"Score: {score:,}",
            f"Max Combo: {max_combo}",
            f"Perfect: {perfect}",
            f"Good: {good}",
            f"Miss: {miss}",
            f"Accuracy: {accuracy:.2f}%"
        ]
        
        # 计算数据起始位置
        data_start_y = separator_y + 2
        data_color = self.COLOR_CODES['score']
        
        # 绘制每一项数据
        for i, item in enumerate(result_items):
            item_x = max(0, (self.screen_width - len(item)) // 2)
            item_y = data_start_y + i
            
            for j, char in enumerate(item):
                self._set_char(item_y, item_x + j, char, data_color)
        
        # 绘制提示信息
        hint = "Press ENTER to return to main menu"
        hint_color = self.COLOR_CODES['foreground']
        hint_x = max(0, (self.screen_width - len(hint)) // 2)
        hint_y = min(self.screen_height - 2, data_start_y + len(result_items) + 2)
        
        for i, char in enumerate(hint):
            self._set_char(hint_y, hint_x + i, char, hint_color)
        
        # 输出到终端
        self._render_to_terminal()