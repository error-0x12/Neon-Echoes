#!/usr/bin/env python3
"""
Neon Echoes - ANSI TUI管理器模块

这个模块负责管理游戏的终端用户界面，使用ANSI转义序列绘制界面元素。
"""

import os
import sys
import re
import logging
from typing import Dict, List, Optional, Callable

# 配置日志
logger = logging.getLogger('NeonEchoes.ANSITUIManager')
logger.setLevel(logging.DEBUG)

# 清除现有的处理器
if logger.handlers:
    logger.handlers.clear()

# 创建文件处理器 - 使用覆盖模式('w')
log_file = os.path.join(os.path.dirname(__file__), 'logs', 'tui_manager_log.log')
file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

# 设置日志格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# 添加处理器到logger
logger.addHandler(file_handler)
logger.info("ANSITUIManager 日志系统初始化完成")


class ANSITUIManager:
    """ANSI TUI管理器类 - 负责管理游戏的所有终端用户界面"""
    
    # 颜色定义 (使用ANSI颜色代码)
    COLOR_CODES = {
        'background': '',           # 默认背景色
        'foreground': '\033[37m',   # 白色
        'highlight': '\033[33m',    # 黄色
        'title': '\033[36m',        # 青色
        'info': '\033[32m',         # 绿色
        'error': '\033[31m',        # 红色
        'success': '\033[32m',      # 绿色
        'menu_item': '\033[37m',    # 白色
        'menu_selected': '\033[30;47m',  # 黑色文字，白色背景
        'reset': '\033[0m',         # 重置颜色
    }
    
    # ASCII艺术字 - Neon Echoes
    TRG_ASCII_ART = [
        " ███╗   ██╗███████╗ ██████╗ ███╗   ██╗    ███████╗ ██████╗██╗  ██╗ ██████╗ ███████╗███████╗ ",
        " ████╗  ██║██╔════╝██╔═══██╗████╗  ██║    ██╔════╝██╔════╝██║  ██║██╔═══██╗██╔════╝██╔════╝ ",
        " ██╔██╗ ██║█████╗  ██║   ██║██╔██╗ ██║    █████╗  ██║     ███████║██║   ██║█████╗  ███████╗ ",
        " ██║╚██╗██║██╔══╝  ██║   ██║██║╚██╗██║    ██╔══╝  ██║     ██╔══██║██║   ██║██╔══╝  ╚════██║ ",
        " ██║ ╚████║███████╗╚██████╔╝██║ ╚████║    ███████╗╚██████╗██║  ██║╚██████╔╝███████╗███████║ ",
        " ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═══╝    ╚══════╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝ "
    ]
    
    # 界面状态枚举
    class UIState:
        MAIN_MENU = 0
        GAME_PLAY = 1
        GAME_PAUSED = 2
        GAME_RESULT = 3
        SETTINGS = 4
    
    def __init__(self, settings: Optional[Dict] = None):
        """
        初始化ANSI TUI管理器
        
        Args:
            settings: 游戏设置字典
        """
        logger.info("=" * 60)
        logger.info("ANSITUIManager 初始化开始")
        logger.info("=" * 60)
        
        # 获取终端尺寸
        self.screen_height, self.screen_width = self._get_terminal_size()
        logger.info(f"终端尺寸: {self.screen_width}x{self.screen_height}")
        
        # 设置初始UI状态
        self.current_state = self.UIState.MAIN_MENU
        logger.info(f"初始UI状态: MAIN_MENU ({self.UIState.MAIN_MENU})")
        
        # 设置相关属性
        self.settings = settings if settings else {
            'music_volume': 0.7,      # 音乐音量 (0.0-1.0)
            'sfx_volume': 0.8,        # 音效音量 (0.0-1.0)
            'music_delay': 100,         # 音乐延迟 (ms, -1000 到 1000)
            'fps': 60,                # 帧率 (30, 60, 120, 144)
            'key_bindings': {         # 按键绑定
                'track_0': 'd',
                'track_1': 'f',
                'track_2': 'j',
                'track_3': 'k',
                'pause': ' '
            },
            'autoplay': False         # 自动判定模式
        }
        logger.debug(f"设置加载完成: music_volume={self.settings['music_volume']}, "
                    f"sfx_volume={self.settings['sfx_volume']}, "
                    f"fps={self.settings['fps']}, "
                    f"autoplay={self.settings['autoplay']}")
        
        # 设置界面选项
        self.setting_options = [
            "音乐音量",
            "音效音量",
            "音乐延迟",
            "帧率设置",
            "AutoPlay",
            "调试计时器",
            "错误报告",
            "清空数据",
            "返回主菜单"
        ]
        logger.debug(f"设置选项数量: {len(self.setting_options)}")
        
        # 初始化设置选项的值显示格式
        self._update_setting_value_formats()
        logger.debug("设置选项值显示格式初始化完成")
        
        # 清空数据确认状态
        self.confirming_clear_data = False
        
        # 初始化自动判定状态
        self.autoplay_enabled = self.settings.get('autoplay', False)
        logger.info(f"自动判定模式: {'开启' if self.autoplay_enabled else '关闭'}")
        
        # 选谱菜单状态
        self.selected_chart_index = 0
        self.current_page = 0
        self.charts_per_page = 4  # 修改为每页最多4个条目
        self.available_charts = []
        logger.debug(f"选谱菜单初始化: charts_per_page={self.charts_per_page}")
        
        # 设置界面选项
        self.selected_setting_option = 0  # 当前选中的设置选项
        logger.debug(f"设置界面选项索引初始化: {self.selected_setting_option}")
        
        # 暂停菜单选项
        self.pause_menu_options = [
            "继续游戏",
            "重新开始",
            "返回主菜单"
        ]
        self.selected_pause_option = 0
        logger.debug(f"暂停菜单选项: {self.pause_menu_options}")
        
        # 结算界面数据
        self.game_result_data = {
            'score': 0,
            'perfect': 0,
            'good': 0,
            'miss': 0,
            'max_combo': 0,
            'accuracy': 0.0
        }
        logger.debug("结算界面数据初始化完成")
        
        # 回调函数
        self.on_chart_select = None  # 选择谱面的回调
        self.on_pause_action = None  # 暂停菜单操作的回调
        self.on_settings_changed = None  # 设置更改的回调
        self.on_result_action = None  # 结算界面操作的回调
        logger.debug("回调函数初始化完成")
        
        # 优化：添加脏标记机制，避免不必要的重绘
        self._dirty_flags = {
            'main_menu': True,      # 主菜单需要重绘
            'game_paused': True,    # 暂停菜单需要重绘
            'game_result': True,    # 结算界面需要重绘
            'settings': True,       # 设置界面需要重绘
        }
        self._last_state = None  # 上次渲染的状态
        logger.debug("脏标记机制初始化完成")
        
        logger.info("=" * 60)
        logger.info("ANSITUIManager 初始化完成")
        logger.info("=" * 60)
    
    def _get_terminal_size(self) -> tuple:
        """
        获取终端尺寸（跨平台）。

        尝试顺序:
        1. Unix: stty size 命令
        2. Windows: Win32 Console API
        3. 通用回退: shutil.get_terminal_size()
        4. 硬编码默认值
        """
        logger.debug("获取终端尺寸...")
        try:
            if os.name != 'nt':
                # Unix/Linux/macOS: 使用 stty size
                try:
                    with os.popen('stty size', 'r') as f:
                        result = f.read().strip()
                    if result:
                        rows, columns = result.split()
                        size = (int(rows), int(columns))
                        logger.info(f"Unix 终端尺寸 (stty): {size[1]}x{size[0]}")
                        return size
                except Exception:
                    logger.debug("stty size 失败，尝试 shutil 回退")

                # Unix 回退: 使用 Python 内置方法
                import shutil
                try:
                    ts = shutil.get_terminal_size()
                    size = (ts.lines, ts.columns)
                    logger.info(f"Unix 终端尺寸 (shutil): {size[1]}x{size[0]}")
                    return size
                except Exception:
                    pass
            else:
                # Windows: 使用 Windows API 获取实际终端尺寸
                try:
                    import ctypes
                    from ctypes import wintypes

                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE

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

                    rows = csbi.srWindow.Bottom - csbi.srWindow.Top + 1
                    columns = csbi.srWindow.Right - csbi.srWindow.Left + 1
                    size = (rows, columns)
                    logger.info(f"Windows 终端尺寸: {size[1]}x{size[0]}")
                    return size
                except Exception:
                    logger.debug("Win32 API 失败，尝试 shutil 回退")

                    # Windows 回退: 使用 Python 内置方法
                    import shutil
                    try:
                        ts = shutil.get_terminal_size()
                        size = (ts.lines, ts.columns)
                        logger.info(f"Windows 终端尺寸 (shutil): {size[1]}x{size[0]}")
                        return size
                    except Exception:
                        pass

        except Exception:
            pass

        # 最终回退: 使用默认值
        logger.warning("所有终端尺寸检测方法均失败，使用默认值 40x160")
        return 40, 160
    
    def _update_setting_value_formats(self) -> None:
        """
        更新设置选项的值显示格式
        """
        self.setting_value_formats = [
            lambda: f"{self.settings['music_volume']:.1f}",
            lambda: f"{self.settings['sfx_volume']:.1f}",
            lambda: f"{self.settings.get('music_delay', 0)}ms",
            lambda: f"{self.settings['fps']} FPS",
            lambda: "开启" if self.settings.get('autoplay', False) else "关闭",
            lambda: "开启" if self.settings.get('debug_timer', False) else "关闭",
            lambda: "开启" if self.settings.get('error_reporting', True) else "关闭",
            lambda: "确认清空" if self.confirming_clear_data else "警告！",
            lambda: ""
        ]
    
    def _adjust_setting_value(self, option_index: int, direction: int) -> None:
        """
        调整设置选项的值
        
        Args:
            option_index: 选项索引
            direction: 调整方向 (-1 减少, 1 增加)
        """
        option_name = self.setting_options[option_index] if 0 <= option_index < len(self.setting_options) else "未知"
        logger.debug(f"调整设置: option_index={option_index} ({option_name}), direction={direction}")
        
        if option_index == 0:  # 音乐音量
            old_value = self.settings['music_volume']
            self.settings['music_volume'] = max(0.0, min(1.0, self.settings['music_volume'] + 0.1 * direction))
            logger.info(f"音乐音量: {old_value:.1f} -> {self.settings['music_volume']:.1f}")
        elif option_index == 1:  # 音效音量
            old_value = self.settings['sfx_volume']
            self.settings['sfx_volume'] = max(0.0, min(1.0, self.settings['sfx_volume'] + 0.1 * direction))
            logger.info(f"音效音量: {old_value:.1f} -> {self.settings['sfx_volume']:.1f}")
        elif option_index == 2:  # 音乐延迟（每10ms为步长，范围-1000到1000）
            old_value = self.settings.get('music_delay', 0)
            new_delay = old_value + 10 * direction
            self.settings['music_delay'] = max(-1000, min(1000, new_delay))
            logger.info(f"音乐延迟: {old_value}ms -> {self.settings['music_delay']}ms")
        elif option_index == 3:  # 帧率设置
            fps_options = [30, 60, 120, 144]
            old_fps = self.settings['fps']
            current_fps_index = fps_options.index(old_fps) if old_fps in fps_options else 1
            new_fps_index = max(0, min(len(fps_options) - 1, current_fps_index + direction))
            self.settings['fps'] = fps_options[new_fps_index]
            logger.info(f"帧率设置: {old_fps} FPS -> {self.settings['fps']} FPS")
        elif option_index == 4:  # 自动判定模式
            # 切换自动判定模式状态
            old_value = self.settings.get('autoplay', False)
            self.settings['autoplay'] = not old_value
            self.autoplay_enabled = self.settings['autoplay']
            logger.info(f"自动判定模式: {'开启' if old_value else '关闭'} -> {'开启' if self.autoplay_enabled else '关闭'}")
        elif option_index == 6:  # 错误报告
            # 切换错误报告状态
            old_value = self.settings.get('error_reporting', True)
            self.settings['error_reporting'] = not old_value
            logger.info(f"错误报告: {'开启' if old_value else '关闭'} -> {'开启' if self.settings['error_reporting'] else '关闭'}")
            
        # 通知设置已更改
        self._notify_settings_changed()
        
    def _notify_settings_changed(self) -> None:
        """
        通知设置已更改
        """
        if self.on_settings_changed:
            logger.debug("触发设置更改回调")
            self.on_settings_changed(self.settings)
        else:
            logger.debug("设置已更改，但没有注册回调函数")
    
    def set_charts(self, charts: List[Dict[str, str]]) -> None:
        """
        设置可用的谱面列表
        
        Args:
            charts (List[Dict[str, str]]): 谱面列表，每个谱面包含name、maker、level等信息
        """
        self.available_charts = charts
        self.selected_chart_index = 0
        self.current_page = 0
        logger.info(f"设置谱面列表: 共 {len(charts)} 个谱面")
        for i, chart in enumerate(charts):
            logger.debug(f"  谱面 {i+1}: {chart.get('name', 'Unknown')} - Level {chart.get('level', 'N/A')}")
    
    def _get_visible_charts(self) -> List[Dict[str, str]]:
        """
        获取当前页面可见的谱面
        
        Returns:
            List[Dict[str, str]]: 当前页面可见的谱面列表
        """
        start_idx = self.current_page * self.charts_per_page
        end_idx = start_idx + self.charts_per_page
        visible = self.available_charts[start_idx:end_idx]
        logger.debug(f"获取可见谱面: 页面 {self.current_page + 1}, 显示 {len(visible)} 个谱面 (索引 {start_idx} 到 {end_idx})")
        return visible
    
    def previous_chart_page(self) -> None:
        """翻到上一页谱面"""
        if self.current_page > 0:
            old_page = self.current_page
            self.current_page -= 1
            # 更新选中的索引到当前页面的第一个，方便用户连续翻页浏览
            self.selected_chart_index = 0
            logger.info(f"翻到上一页: {old_page + 1} -> {self.current_page + 1}")
        else:
            logger.debug("已经在第一页，无法继续翻页")
    
    def next_chart_page(self) -> None:
        """翻到下一页谱面"""
        total_pages = max(1, (len(self.available_charts) + self.charts_per_page - 1) // self.charts_per_page)
        if self.current_page < total_pages - 1:
            old_page = self.current_page
            self.current_page += 1
            # 更新选中的索引到当前页面的第一个
            self.selected_chart_index = 0
            logger.info(f"翻到下一页: {old_page + 1} -> {self.current_page + 1} (共 {total_pages} 页)")
        else:
            logger.debug(f"已经在最后一页 ({total_pages})，无法继续翻页")
    
    def _get_display_width(self, text: str) -> int:
        """
        计算文本在终端中的显示宽度
        中文字符占2个宽度，英文字符占1个宽度
        
        Args:
            text (str): 要计算的文本
            
        Returns:
            int: 文本的显示宽度
        """
        width = 0
        for char in text:
            if '\u4e00' <= char <= '\u9fff':  # 中文字符范围
                width += 2
            else:
                width += 1
        return width
    
    def _draw_trg_title(self, y: int, x: int) -> None:
        """
        绘制TRG标题ASCII艺术字
        
        Args:
            y (int): 起始Y坐标
            x (int): 起始X坐标
        """
        for i, line in enumerate(self.TRG_ASCII_ART):
            # 确保不会超出屏幕边界
            if y + i < self.screen_height:
                # 居中显示标题
                title_x = max(0, x)
                # 输出带颜色的标题行
                self._print_at(y + i, title_x, self.COLOR_CODES['title'] + line + self.COLOR_CODES['reset'])
    
    def _print_at(self, y: int, x: int, text: str) -> None:
        """
        在指定位置打印文本
        
        Args:
            y (int): Y坐标
            x (int): X坐标
            text (str): 要打印的文本
        """
        if 0 <= y < self.screen_height:
            # 移动光标到指定位置并打印文本
            sys.stdout.write(f"\033[{y + 1};{x + 1}H{text}")
    
    def _clear_screen(self) -> None:
        """清屏"""
        sys.stdout.write('\033[2J\033[H')  # ANSI清屏和光标回到左上角
    
    def draw_main_menu(self, save_manager=None) -> None:
        """绘制主菜单界面"""
        # 优化：检查是否需要重绘
        if not self._dirty_flags['main_menu'] and self._last_state == self.UIState.MAIN_MENU:
            return
        
        self._dirty_flags['main_menu'] = False
        self._last_state = self.UIState.MAIN_MENU
        
        # 清屏
        self._clear_screen()
        
        # 计算整体布局居中
        content_width = max(len(self.TRG_ASCII_ART[0]), 40)  # 标题宽度或谱面列表宽度
        content_start_x = max(0, (self.screen_width - content_width) // 2)
        
        # 绘制TRG标题居中
        title_y = 2
        title_x = max(0, content_start_x + (content_width - len(self.TRG_ASCII_ART[0])) // 2)
        self._draw_trg_title(title_y, title_x)
        
        # 绘制谱面列表居中
        charts_start_x = max(0, content_start_x + (content_width - 40) // 2)  # 谱面列表起始X坐标
        charts_y = title_y + len(self.TRG_ASCII_ART) + 2
        visible_charts = self._get_visible_charts()
        
        # 绘制谱面列表标题
        list_title = "谱面列表"
        list_title_x = max(0, charts_start_x + (40 - len(list_title)) // 2)
        self._print_at(charts_y - 1, list_title_x, self.COLOR_CODES['title'] + list_title + self.COLOR_CODES['reset'])
        
        # 绘制谱面列表
        for i, chart in enumerate(visible_charts):
            y_pos = charts_y + i
            if y_pos >= self.screen_height - 10:  # 为底部帮助信息和选中谱面详情留出更多空间
                break
                
            # 选择颜色（选中的谱面使用高亮色）
            color = self.COLOR_CODES['menu_selected'] if i == self.selected_chart_index else self.COLOR_CODES['menu_item']
            
            # 格式化谱面信息
            chart_info = f"{chart['name']:<20}"
            self._print_at(y_pos, charts_start_x, color + chart_info + self.COLOR_CODES['reset'])
            
            # 显示等级
            # 从chart中获取难度等级和名称信息
            level = chart['level']
            # 尝试从difficulty字段中提取难度名称，如果没有则使用默认值
            difficulty_name = "未知"
            if 'difficulty' in chart:
                # difficulty字段格式为 "等级 (难度名称)"
                match = re.search(r'\(([^)]+)\)', chart['difficulty'])
                if match:
                    difficulty_name = match.group(1)
            # 格式化为 "难度名称-等级"
            level_text = f"{difficulty_name}-{level}"
            self._print_at(y_pos, charts_start_x + 25, color + level_text + self.COLOR_CODES['reset'])
            
            # 如果有最高成绩，显示等级在选项旁边
            if save_manager and 'id' in chart:
                best_score = save_manager.get_best_score_raw(chart['id'])
                if best_score and 'grade' in best_score:
                    grade_text = f"[{best_score['grade']}]"
                    self._print_at(y_pos, charts_start_x + 35, color + grade_text + self.COLOR_CODES['reset'])
        
        # 绘制选中谱面的详细信息
            if visible_charts and 0 <= self.selected_chart_index < len(visible_charts):
                selected_chart = visible_charts[self.selected_chart_index]
                # 调整info_y计算方式，确保有足够空间显示信息
                info_y = min(charts_y + len(visible_charts) + 1, self.screen_height - 5)  # 确保至少保留5行空间
                
                try:
                    # 简化详细信息显示，适应不同屏幕尺寸
                    # 获取难度信息
                    level = selected_chart['level']
                    difficulty_name = "未知"
                    if 'difficulty' in selected_chart:
                        match = re.search(r'\(([^)]+)\)', selected_chart['difficulty'])
                        if match:
                            difficulty_name = match.group(1)
                    # 格式化为 "难度名称-等级"
                    level_text = f"{difficulty_name}-{level}"
                    basic_info_text = f"选中: {selected_chart['name']} | {level_text}"
                    basic_info_x = max(0, (self.screen_width - len(basic_info_text)) // 2)  # 居中显示
                    self._print_at(info_y, basic_info_x, self.COLOR_CODES['info'] + basic_info_text + self.COLOR_CODES['reset'])
                    
                    # 添加更多基本信息（如果有空间）
                    if info_y + 1 < self.screen_height - 4:
                        maker_info_text = f"谱面: {selected_chart['maker']} | 音乐: {selected_chart.get('song_maker', '未知')}"
                        maker_info_x = max(0, (self.screen_width - len(maker_info_text)) // 2)  # 居中显示
                        self._print_at(info_y + 1, maker_info_x, self.COLOR_CODES['info'] + maker_info_text + self.COLOR_CODES['reset'])
                    
                    # 显示最高成绩（如果有空间）
                    if save_manager and info_y + 2 < self.screen_height - 3:
                        chart_id = selected_chart.get('id', '')
                        try:
                            best_score = save_manager.get_best_score_raw(chart_id)
                            
                            # 应用颜色到文本
                            best_score_title = "最高成绩:"
                            best_score_title_x = max(0, (self.screen_width - len(best_score_title)) // 2)  # 居中显示
                            self._print_at(info_y + 2, best_score_title_x, self.COLOR_CODES['highlight'] + best_score_title + self.COLOR_CODES['reset'])
                            if best_score:
                                score = best_score.get('score', 0)
                                grade = best_score.get('grade', '无')
                                
                                # 格式化分数显示
                                formatted_score = f"{score:,}"  # 添加千位分隔符
                                
                                # 只显示总分和等级
                                score_text = f"{grade} - {formatted_score}"
                                score_text_x = max(0, (self.screen_width - len(score_text)) // 2)  # 居中显示
                                self._print_at(info_y + 3, score_text_x, self.COLOR_CODES['highlight'] + score_text + self.COLOR_CODES['reset'])
                            else:
                                no_record_text = "暂无成绩记录"
                                no_record_x = max(0, (self.screen_width - len(no_record_text)) // 2)  # 居中显示
                                self._print_at(info_y + 3, no_record_x, self.COLOR_CODES['foreground'] + no_record_text + self.COLOR_CODES['reset'])
                        except Exception as e:
                            # 如果获取成绩出错，仍然显示基本信息
                            pass
                except Exception as e:
                    # 即使发生错误，也尝试显示最基本的选中信息
                    try:
                        basic_info_text = f"选中: {selected_chart['name']}"
                        basic_info_x = max(0, (self.screen_width - len(basic_info_text)) // 2)  # 居中显示
                        self._print_at(info_y, basic_info_x, self.COLOR_CODES['info'] + basic_info_text + self.COLOR_CODES['reset'])
                    except:
                        pass
        
        # 绘制翻页指示器
        total_pages = max(1, (len(self.available_charts) + self.charts_per_page - 1) // self.charts_per_page)
        if total_pages > 1:
            page_info_y = info_y + 4  # 在详细信息下方显示页码
            if page_info_y < self.screen_height - 3:
                page_text = f"页码: {self.current_page + 1}/{total_pages}"
                page_x = max(0, (self.screen_width - len(page_text)) // 2)  # 居中显示
                self._print_at(page_info_y, page_x, self.COLOR_CODES['highlight'] + page_text + self.COLOR_CODES['reset'])
        
        # 绘制底部帮助信息
        help_y = self.screen_height - 2
        if help_y > 0:
            help_text = "上下方向键:选择谱面 | 左右方向键:翻页 | 回车键:开始游戏 | ESC键:退出 | DEL键:设置"
            help_x = max(0, (self.screen_width - self._get_display_width(help_text)) // 2)
            self._print_at(help_y, help_x, self.COLOR_CODES['foreground'] + help_text + self.COLOR_CODES['reset'])
        
        # 刷新输出
        sys.stdout.flush()
    
    def draw_game_result(self) -> None:
        """绘制游戏结算界面"""
        # 清屏
        self._clear_screen()
        
        # 绘制标题 - 根据autoplay状态显示不同的标题
        if self.autoplay_enabled:
            title_text = "AutoPlay"
        else:
            title_text = "游戏结算"
        title_y = 2
        title_x = max(0, (self.screen_width - len(title_text)) // 2)
        self._print_at(title_y, title_x, self.COLOR_CODES['title'] + title_text + self.COLOR_CODES['reset'])
        
        # 获取等级
        grade = self._get_grade_by_score(self.game_result_data['score'])
        
        # 绘制结算信息
        result_y = title_y + 3
        
        # 总成绩（等级和分数）
        score_text = f"总成绩: {grade} - {self.game_result_data['score']:,} "
        score_x = max(0, (self.screen_width - len(score_text)) // 2)
        self._print_at(result_y, score_x, self.COLOR_CODES['highlight'] + score_text + self.COLOR_CODES['reset'])
        
        # 判定统计
        stats_y = result_y + 2
        stats = [
            f"Perfect: {self.game_result_data['perfect']}",
            f"Good: {self.game_result_data['good']}",
            f"Bad: {self.game_result_data['bad']}",
            f"Miss: {self.game_result_data['miss']}",
            f"最大连击: {self.game_result_data['max_combo']}",
            f"准确率: {self.game_result_data['accuracy']:.2f}%"
        ]
        
        for i, stat in enumerate(stats):
            stat_y = stats_y + i
            if stat_y < self.screen_height - 3:  # 为底部帮助信息留出空间
                stat_x = max(0, (self.screen_width - len(stat)) // 2)
                self._print_at(stat_y, stat_x, self.COLOR_CODES['info'] + stat + self.COLOR_CODES['reset'])
        
        # 绘制底部帮助信息
        help_y = self.screen_height - 2
        if help_y > 0:
            help_text = "按回车键返回主界面"
            help_x = max(0, (self.screen_width - len(help_text)) // 2)
            self._print_at(help_y, help_x, self.COLOR_CODES['foreground'] + help_text + self.COLOR_CODES['reset'])
        
        # 刷新输出
        sys.stdout.flush()
    
    def draw_settings(self) -> None:
        """绘制设置界面"""
        # 清屏
        self._clear_screen()
        
        # 绘制标题
        title_text = "游戏设置"
        title_y = 1
        title_x = max(0, (self.screen_width - len(title_text)) // 2)
        self._print_at(title_y, title_x, self.COLOR_CODES['title'] + title_text + self.COLOR_CODES['reset'])
        
        # 检查是否处于确认清空数据状态
        if self.confirming_clear_data:
            # 显示二次确认界面
            confirm_y = self.screen_height // 2 - 3
            confirm_text = "⚠️  警告：清空所有数据 ⚠️"
            confirm_x = max(0, (self.screen_width - len(confirm_text)) // 2)
            self._print_at(confirm_y, confirm_x, self.COLOR_CODES['error'] + confirm_text + self.COLOR_CODES['reset'])
            
            # 确认提示
            prompt1 = "此操作将删除所有谱面的最高分记录"
            prompt2 = "此操作不可撤销！"
            prompt1_x = max(0, (self.screen_width - len(prompt1)) // 2)
            prompt2_x = max(0, (self.screen_width - len(prompt2)) // 2)
            self._print_at(confirm_y + 2, prompt1_x, self.COLOR_CODES['highlight'] + prompt1 + self.COLOR_CODES['reset'])
            self._print_at(confirm_y + 3, prompt2_x, self.COLOR_CODES['error'] + prompt2 + self.COLOR_CODES['reset'])
            
            # 操作提示，包含具体的确认键
            confirm_key = getattr(self, 'clear_data_confirm_key', '?')
            action1 = f"是：请按[{confirm_key}]"
            action2 = "否：请按[0]"
            action1_x = max(0, (self.screen_width - len(action1)) // 2)
            action2_x = max(0, (self.screen_width - len(action2)) // 2)
            self._print_at(confirm_y + 5, action1_x, self.COLOR_CODES['info'] + action1 + self.COLOR_CODES['reset'])
            self._print_at(confirm_y + 6, action2_x, self.COLOR_CODES['info'] + action2 + self.COLOR_CODES['reset'])
            
            # 底部帮助信息
            help_y = self.screen_height - 2
            if help_y > 0:
                help_text = "按ESC键也可取消操作"
                help_x = max(0, (self.screen_width - len(help_text)) // 2)
                self._print_at(help_y, help_x, self.COLOR_CODES['foreground'] + help_text + self.COLOR_CODES['reset'])
        else:
            # 正常显示设置选项
            # 绘制设置选项
            options_start_y = title_y + 2
            for i, option in enumerate(self.setting_options):
                y_pos = options_start_y + i
                if y_pos >= self.screen_height - 2:  # 为底部帮助信息留出空间
                    break
                    
                # 选择颜色（选中的选项使用高亮色）
                color = self.COLOR_CODES['menu_selected'] if i == self.selected_setting_option else self.COLOR_CODES['menu_item']
                
                # 为清空数据选项添加特殊颜色
                if i == 7:  # 清空数据选项
                    color = self.COLOR_CODES['error'] if i == self.selected_setting_option else color
                # 为AutoPlay选项添加特殊颜色
                elif option == "AutoPlay":
                    color = self.COLOR_CODES['info'] if i == self.selected_setting_option else color
                
                # 获取选项值
                try:
                    value = self.setting_value_formats[i]()
                except:
                    value = ""
                
                # 格式化显示
                display_text = f"{option:<30} {value}"
                self._print_at(y_pos, 4, color + display_text + self.COLOR_CODES['reset'])
            
            # 绘制底部帮助信息
            help_y = self.screen_height - 2
            if help_y > 0:
                help_text = "上下键选择选项, 左右键调整参数, Enter确认, ESC返回主界面"
                help_x = max(0, (self.screen_width - len(help_text)) // 2)
                self._print_at(help_y, help_x, self.COLOR_CODES['foreground'] + help_text + self.COLOR_CODES['reset'])
        
        # 刷新输出
        sys.stdout.flush()
    
    def draw_game_paused(self) -> None:
        """绘制游戏暂停界面"""
        # 清屏
        self._clear_screen()
        
        # 绘制暂停标题
        pause_text = "游戏已暂停"
        title_y = self.screen_height // 2 - 3
        title_x = max(0, (self.screen_width - len(pause_text)) // 2)
        self._print_at(title_y, title_x, self.COLOR_CODES['title'] + pause_text + self.COLOR_CODES['reset'])
        
        # 绘制暂停菜单选项
        menu_start_y = title_y + 2
        for i, option in enumerate(self.pause_menu_options):
            y_pos = menu_start_y + i
            if y_pos >= self.screen_height:
                break
                
            # 选择颜色（选中的选项使用高亮色）
            color = self.COLOR_CODES['menu_selected'] if i == self.selected_pause_option else self.COLOR_CODES['menu_item']
            
            # 居中显示选项
            option_x = max(0, (self.screen_width - len(option)) // 2)
            self._print_at(y_pos, option_x, color + option + self.COLOR_CODES['reset'])
        
        # 绘制底部帮助信息
        help_y = self.screen_height - 2
        if help_y > 0:
            help_text = "使用 W/S 键或上下方向键选择选项, 回车键确认"
            help_x = max(0, (self.screen_width - len(help_text)) // 2)
            self._print_at(help_y, help_x, self.COLOR_CODES['foreground'] + help_text + self.COLOR_CODES['reset'])
        
        # 刷新输出
        sys.stdout.flush()
    
    def draw_chart_settings(self) -> None:
        """绘制谱面设置界面"""
        # 清屏
        self._clear_screen()
        
        # 绘制标题
        title_text = "游戏设置"
        title_y = 1
        title_x = max(0, (self.screen_width - len(title_text)) // 2)
        self._print_at(title_y, title_x, self.COLOR_CODES['title'] + title_text + self.COLOR_CODES['reset'])
        
        # 绘制设置选项
        options_start_y = title_y + 2
        for i, option in enumerate(self.setting_options):
            y_pos = options_start_y + i
            if y_pos >= self.screen_height - 2:  # 为底部帮助信息留出空间
                break
                
            # 选择颜色（选中的选项使用高亮色）
            color = self.COLOR_CODES['menu_selected'] if i == self.selected_setting_option else self.COLOR_CODES['menu_item']
            
            # 获取选项值
            try:
                value = self.setting_value_formats[i]()
            except:
                value = ""
            
            # 格式化显示
            display_text = f"{option:<30} {value}"
            self._print_at(y_pos, 4, color + display_text + self.COLOR_CODES['reset'])
        
        # 绘制底部帮助信息
        help_y = self.screen_height - 2
        if help_y > 0:
            help_text = "使用 W/S 键选择选项, A/D 键调整数值, 回车键确认, ESC键返回"
            help_x = max(0, (self.screen_width - len(help_text)) // 2)
            self._print_at(help_y, help_x, self.COLOR_CODES['foreground'] + help_text + self.COLOR_CODES['reset'])
        
        # 刷新输出
        sys.stdout.flush()
    
    def set_state(self, state: 'UIState') -> None:
        """
        设置当前UI状态
        
        Args:
            state (UIState): 要设置的UI状态
        """
        state_names = {
            self.UIState.MAIN_MENU: "MAIN_MENU",
            self.UIState.GAME_PLAY: "GAME_PLAY",
            self.UIState.GAME_PAUSED: "GAME_PAUSED",
            self.UIState.GAME_RESULT: "GAME_RESULT",
            self.UIState.SETTINGS: "SETTINGS"
        }
        old_state = state_names.get(self.current_state, "UNKNOWN")
        new_state = state_names.get(state, "UNKNOWN")
        self.current_state = state
        logger.info(f"UI状态切换: {old_state} -> {new_state}")
        
        # 修复：切换状态时设置对应脏标记，确保界面被重绘
        if state == self.UIState.MAIN_MENU:
            self._dirty_flags['main_menu'] = True
        elif state == self.UIState.GAME_PAUSED:
            self._dirty_flags['game_paused'] = True
        elif state == self.UIState.GAME_RESULT:
            self._dirty_flags['game_result'] = True
        elif state == self.UIState.SETTINGS:
            self._dirty_flags['settings'] = True
    
    def set_on_chart_select_callback(self, callback: Callable) -> None:
        """
        设置选择谱面的回调函数
        
        Args:
            callback (Callable): 回调函数
        """
        self.on_chart_select = callback
    
    def set_on_pause_action_callback(self, callback: Callable) -> None:
        """
        设置暂停菜单操作的回调函数
        
        Args:
            callback (Callable): 回调函数
        """
        self.on_pause_action = callback
    
    def set_on_result_action_callback(self, callback: Callable) -> None:
        """
        设置结算界面操作的回调函数
        
        Args:
            callback (Callable): 回调函数
        """
        self.on_result_action = callback
    
    def set_game_result_data(self, score: int, perfect: int, good: int, bad: int, miss: int, max_combo: int, accuracy: float) -> None:
        """
        设置结算界面数据
        
        Args:
            score (int): 游戏分数
            perfect (int): Perfect判定数量
            good (int): Good判定数量
            bad (int): Bad判定数量
            miss (int): Miss判定数量
            max_combo (int): 最大连击数
            accuracy (float): 准确率
        """
        self.game_result_data = {
            'score': score,
            'perfect': perfect,
            'good': good,
            'bad': bad,
            'miss': miss,
            'max_combo': max_combo,
            'accuracy': accuracy
        }
        logger.info("=" * 60)
        logger.info("游戏结算数据")
        logger.info("=" * 60)
        logger.info(f"分数: {score:,}")
        logger.info(f"Perfect: {perfect}, Good: {good}, Bad: {bad}, Miss: {miss}")
        logger.info(f"最大连击: {max_combo}")
        logger.info(f"准确率: {accuracy:.2f}%")
        logger.info("=" * 60)
    
    def _get_grade_by_score(self, score: int) -> str:
        """
        根据分数获取等级
        
        Args:
            score (int): 游戏分数
            
        Returns:
            str: 等级
        """
        if score >= 1000000:
            return "AP"
        elif score >= 950000:
            return "V"
        elif score >= 920000:
            return "S"
        elif score >= 880000:
            return "A"
        elif score >= 820000:
            return "B"
        elif score >= 720000:
            return "C"
        else:
            return "F"
    
    def _calculate_track_dimensions_for_animation(self, screen_width: int) -> tuple:
        """
        根据窗口尺寸动态计算轨道宽度和间距
        与 ANSIRenderer._calculate_track_dimensions 使用相同的逻辑
        
        Args:
            screen_width: 屏幕宽度
            
        Returns:
            tuple: (track_width, track_spacing, start_x)
        """
        num_tracks = 10
        
        # 确保屏幕宽度有效
        if screen_width <= 0:
            return 4, 2, 0
        
        # 计算可用总宽度（留出一点余量）
        total_width_needed = screen_width - 4
        
        # 轨道间距数量 = 轨道数量 - 1
        spacing_count = num_tracks - 1
        min_spacing = 2
        
        # 计算基础轨道宽度
        available_track_width = total_width_needed - (spacing_count * min_spacing)
        base_track_width = available_track_width // num_tracks
        
        # 根据屏幕宽度动态调整轨道宽度
        if screen_width >= 120:
            track_width = max(5, base_track_width)
        elif screen_width >= 80:
            track_width = max(4, base_track_width)
        else:
            track_width = max(3, base_track_width)
        
        # 重新计算轨道间距
        actual_total_width = num_tracks * track_width
        remaining_space = total_width_needed - actual_total_width
        
        if spacing_count > 0:
            track_spacing = min_spacing + (remaining_space // spacing_count)
            track_spacing = max(min_spacing, track_spacing)
        else:
            track_spacing = 0
        
        # 减小2格轨道宽度，使整体居中更好
        track_width = max(2, track_width - 2)
        
        # 计算居中偏移量
        total_tracks_width = num_tracks * track_width + (num_tracks - 1) * track_spacing
        start_x = (screen_width - total_tracks_width) // 2
        start_x = max(0, start_x)
        
        return track_width, track_spacing, start_x
    
    def play_chart_load_animation(self, renderer, game_state, audio_manager) -> None:
        """
        播放谱面加载动画
        主界面整体快速右移直到完全出画面，同时从左侧划入谱面（轨道和判定线）
        等待完全划入2秒后才开始谱面
        
        Args:
            renderer: ANSIRenderer实例，用于绘制游戏画面
            game_state: GameState实例
            audio_manager: AudioManager实例
        """
        import time
        import sys
        
        logger.info("开始播放谱面加载动画")
        
        # 获取终端尺寸
        screen_height = self.screen_height
        screen_width = self.screen_width
        
        # 动画参数
        animation_duration = 0.8  # 动画持续时间（秒）
        settle_duration = 2.0     # 完全划入后等待时间（秒）
        fps = 60                  # 动画帧率
        frame_time = 1.0 / fps
        
        # 计算每帧移动的像素数
        total_frames = int(animation_duration * fps)
        
        # 根据窗口尺寸动态计算轨道尺寸（与渲染器使用相同的逻辑）
        track_width, track_spacing, start_x = self._calculate_track_dimensions_for_animation(screen_width)
        num_tracks = 10
        
        # 计算轨道区域的总宽度和结束位置
        total_tracks_width = num_tracks * track_width + (num_tracks - 1) * track_spacing
        end_x = start_x + total_tracks_width - 1
        
        logger.info(f"动画轨道尺寸: width={track_width}, spacing={track_spacing}, start_x={start_x}, end_x={end_x}")
        
        frame_count = 0
        
        # 动画主循环
        while frame_count < total_frames:
            frame_start = time.time()
            
            # 清屏
            sys.stdout.write('\033[2J\033[H')
            
            # 动画进度 (0.0 - 1.0)
            progress = frame_count / total_frames
            
            # 主界面向右滑出的偏移量（从0到screen_width）
            main_slide_out = int(screen_width * progress)
            
            # 谱面向左滑入的偏移量（从 -screen_width 到 0）
            chart_slide_in = int(-screen_width * (1 - progress))
            
            # ========== 第一部分：绘制向右滑出的主界面（完整版） ==========
            main_color = self.COLOR_CODES['title']
            reset_color = self.COLOR_CODES['reset']
            
            # 计算整体布局居中
            content_width = max(len(self.TRG_ASCII_ART[0]) if self.TRG_ASCII_ART else 0, 40)
            content_start_x = max(0, (screen_width - content_width) // 2 + main_slide_out)
            
            # 1. 绘制完整的TRG艺术字标题
            title_y = 2
            title_x = max(0, content_start_x + (content_width - len(self.TRG_ASCII_ART[0])) // 2) if self.TRG_ASCII_ART else content_start_x
            for i, line in enumerate(self.TRG_ASCII_ART):
                if title_x < screen_width and title_y + i < screen_height:
                    visible_start = max(0, -title_x)
                    visible_end = min(len(line), screen_width - title_x)
                    if visible_start < visible_end:
                        visible_text = line[visible_start:visible_end]
                        draw_x = max(0, title_x)
                        self._print_at(title_y + i, draw_x, main_color + visible_text + reset_color)
            
            # 2. 绘制谱面列表标题
            charts_start_x = max(0, content_start_x + (content_width - 40) // 2)
            charts_y = title_y + len(self.TRG_ASCII_ART) + 2
            list_title = "谱面列表"
            list_title_x = max(0, charts_start_x + (40 - len(list_title)) // 2)
            if list_title_x < screen_width and charts_y - 1 < screen_height:
                self._print_at(charts_y - 1, list_title_x, self.COLOR_CODES['title'] + list_title + reset_color)
            
            # 3. 绘制谱面列表（显示当前选中的谱面和周围几个）
            visible_charts = self._get_visible_charts()
            for i, chart in enumerate(visible_charts):
                y_pos = charts_y + i
                if y_pos >= screen_height - 10 or y_pos < 0:
                    break
                
                # 选择颜色（选中的谱面使用高亮色）
                color = self.COLOR_CODES['menu_selected'] if i == self.selected_chart_index else self.COLOR_CODES['menu_item']
                
                # 格式化谱面信息
                chart_info = f"{chart['name']:<20}"
                if charts_start_x < screen_width:
                    visible_start = max(0, -charts_start_x)
                    visible_end = min(len(chart_info), screen_width - charts_start_x)
                    if visible_start < visible_end:
                        visible_text = chart_info[visible_start:visible_end]
                        draw_x = max(0, charts_start_x)
                        self._print_at(y_pos, draw_x, color + visible_text + reset_color)
                
                # 显示等级
                level = chart['level']
                difficulty_name = "未知"
                if 'difficulty' in chart:
                    match = re.search(r'\(([^)]+)\)', chart['difficulty'])
                    if match:
                        difficulty_name = match.group(1)
                level_text = f"{difficulty_name}-{level}"
                level_x = charts_start_x + 25
                if level_x < screen_width:
                    visible_start = max(0, -level_x)
                    visible_end = min(len(level_text), screen_width - level_x)
                    if visible_start < visible_end:
                        visible_text = level_text[visible_start:visible_end]
                        draw_x = max(0, level_x)
                        self._print_at(y_pos, draw_x, color + visible_text + reset_color)
            
            # 4. 绘制选中谱面的详细信息
            if visible_charts and 0 <= self.selected_chart_index < len(visible_charts):
                selected_chart = visible_charts[self.selected_chart_index]
                info_y = min(charts_y + len(visible_charts) + 1, screen_height - 5)
                
                if info_y > 0 and info_y < screen_height:
                    # 基本信息
                    level = selected_chart['level']
                    difficulty_name = "未知"
                    if 'difficulty' in selected_chart:
                        match = re.search(r'\(([^)]+)\)', selected_chart['difficulty'])
                        if match:
                            difficulty_name = match.group(1)
                    level_text = f"{difficulty_name}-{level}"
                    basic_info_text = f"选中: {selected_chart['name']} | {level_text}"
                    basic_info_x = max(0, (screen_width - len(basic_info_text)) // 2 + main_slide_out)
                    if basic_info_x < screen_width:
                        visible_start = max(0, -basic_info_x)
                        visible_end = min(len(basic_info_text), screen_width - basic_info_x)
                        if visible_start < visible_end:
                            visible_text = basic_info_text[visible_start:visible_end]
                            draw_x = max(0, basic_info_x)
                            self._print_at(info_y, draw_x, self.COLOR_CODES['info'] + visible_text + reset_color)
                    
                    # 制作者信息
                    if info_y + 1 < screen_height - 4:
                        maker_info_text = f"谱面: {selected_chart['maker']} | 音乐: {selected_chart.get('song_maker', '未知')}"
                        maker_info_x = max(0, (screen_width - len(maker_info_text)) // 2 + main_slide_out)
                        if maker_info_x < screen_width:
                            visible_start = max(0, -maker_info_x)
                            visible_end = min(len(maker_info_text), screen_width - maker_info_x)
                            if visible_start < visible_end:
                                visible_text = maker_info_text[visible_start:visible_end]
                                draw_x = max(0, maker_info_x)
                                self._print_at(info_y + 1, draw_x, self.COLOR_CODES['info'] + visible_text + reset_color)
            
            # 5. 绘制底部帮助信息
            help_y = screen_height - 2
            if help_y > 0 and help_y < screen_height:
                help_text = "上下方向键:选择谱面 | 左右方向键:翻页 | 回车键:开始游戏 | ESC键:退出 | DEL键:设置"
                help_x = max(0, (screen_width - len(help_text)) // 2 + main_slide_out)
                if help_x < screen_width:
                    visible_start = max(0, -help_x)
                    visible_end = min(len(help_text), screen_width - help_x)
                    if visible_start < visible_end:
                        visible_text = help_text[visible_start:visible_end]
                        draw_x = max(0, help_x)
                        self._print_at(help_y, draw_x, self.COLOR_CODES['foreground'] + visible_text + reset_color)
            
            # ========== 第二部分：绘制向左滑入的谱面 ==========
            # 绘制轨道（从左侧划入效果）
            border_char = '|'
            track_color = '\033[37m'  # 白色
            judgement_color = '\033[31m'  # 红色
            
            judgement_line_y = screen_height - 5
            
            # 计算当前轨道区域的范围（用于绘制连续的判定线）
            current_start_x = start_x + chart_slide_in
            current_end_x = end_x + chart_slide_in
            
            # 绘制轨道边界
            for i in range(num_tracks):
                track_left = start_x + i * (track_width + track_spacing) + chart_slide_in
                track_right = track_left + track_width - 1
                
                # 只绘制在屏幕范围内的部分
                if track_right < 0 or track_left >= screen_width:
                    continue
                
                # 绘制轨道边界
                for y in range(screen_height):
                    if 0 <= track_left < screen_width:
                        sys.stdout.write(f"\033[{y + 1};{track_left + 1}H{track_color}{border_char}{reset_color}")
                    if 0 <= track_right < screen_width:
                        sys.stdout.write(f"\033[{y + 1};{track_right + 1}H{track_color}{border_char}{reset_color}")
            
            # 绘制连续的判定线（贯穿所有轨道）
            if 0 <= judgement_line_y < screen_height:
                line_start = max(0, current_start_x)
                line_end = min(screen_width - 1, current_end_x)
                for x in range(line_start, line_end + 1):
                    sys.stdout.write(f"\033[{judgement_line_y + 1};{x + 1}H{judgement_color}={reset_color}")
            
            # 绘制加载提示
            loading_text = "Loading..."
            loading_x = (screen_width - len(loading_text)) // 2
            loading_y = screen_height // 2
            sys.stdout.write(f"\033[{loading_y + 1};{loading_x + 1}H\033[33m{loading_text}\033[0m")
            
            sys.stdout.flush()
            
            # 控制帧率
            frame_count += 1
            elapsed = time.time() - frame_start
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        # 动画完成，完全显示游戏界面
        # 清屏并绘制完整的游戏界面
        sys.stdout.write('\033[2J\033[H')
        
        # 绘制完整的轨道和判定线
        judgement_line_y = screen_height - 5
        
        # 绘制轨道边界
        for i in range(num_tracks):
            track_left = start_x + i * (track_width + track_spacing)
            track_right = track_left + track_width - 1
            
            # 绘制轨道边界
            for y in range(screen_height):
                sys.stdout.write(f"\033[{y + 1};{track_left + 1}H\033[37m|\033[0m")
                sys.stdout.write(f"\033[{y + 1};{track_right + 1}H\033[37m|\033[0m")
        
        # 绘制连续的判定线（贯穿所有轨道）
        for x in range(start_x, end_x + 1):
            sys.stdout.write(f"\033[{judgement_line_y + 1};{x + 1}H\033[31m=\033[0m")
        
        # 显示"Ready"提示
        ready_text = "Ready!"
        ready_x = (screen_width - len(ready_text)) // 2
        ready_y = screen_height // 2 - 2
        sys.stdout.write(f"\033[{ready_y + 1};{ready_x + 1}H\033[32m{ready_text}\033[0m")
        
        sys.stdout.flush()
        
        # 等待2秒
        logger.info(f"谱面加载动画完成，等待 {settle_duration} 秒")
        time.sleep(settle_duration)
        
        # 最后清屏，准备开始游戏
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()
        
        logger.info("谱面加载动画结束")