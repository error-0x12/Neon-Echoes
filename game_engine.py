#!/usr/bin/env python3
"""
Neon Echoes - 游戏引擎模块

这个模块包含游戏的核心逻辑类，负责管理游戏状态、音符判定和分数计算等功能。
"""

import json
import time
import math
from enum import Enum
from typing import List, Dict, Any, Optional, Set, Tuple, Callable, Union
import logging
import os

# 导入谱面解析器
from chart_parser import ChartParser, get_available_charts, load_chart_by_id
# 导入音频管理器
from audio_manager import AudioManager

# 配置日志
# 创建logger实例
logger = logging.getLogger('NeonEchoes.GameEngine')
logger.setLevel(logging.INFO)

# 清除现有的处理器
if logger.handlers:
    logger.handlers.clear()

# 创建文件处理器 - 使用覆盖模式('w')
log_file = os.path.join(os.path.dirname(__file__), 'logs', 'game_log.log')
file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
file_handler.setLevel(logging.INFO)

# 设置日志格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# 添加处理器到logger
logger.addHandler(file_handler)


class NoteType(Enum):
    """音符类型枚举"""
    NORMAL = "normal"  # 普通音符
    HOLD = "hold"      # 长按音符
    DRAG = "drag"      # 拖动音符


class JudgementResult(Enum):
    """判定结果枚举"""
    PERFECT = "PERFECT"      # 完美判定
    GOOD = "GOOD"            # 良好判定
    BAD = "BAD"              # 较差判定
    MISS = "MISS"            # 错失判定


class Difficulty(Enum):
    """游戏难度枚举"""
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    EXPERT = "expert"
    MASTER = "master"


class Note:
    """音符类 - 表示游戏中的单个音符"""
    
    _next_id = 0  # 类变量，用于生成唯一ID
    
    def __init__(self, track_index: int, note_type: NoteType, perfect_time: int, duration: int = 0, tracks: Optional[List[int]] = None):
        """
        初始化音符
        
        Args:
            track_index (int): 音符所属轨道索引 (0-9) - 主轨道
            note_type (NoteType): 音符类型
            perfect_time (int): 音符应该被击中的精确时间戳（毫秒）- 使用预计判定时间
            duration (int): 长按音符的持续时间（毫秒），普通音符为0
            tracks (Optional[List[int]]): 音符使用的所有轨道索引列表
        """
        self.id = Note._next_id  # 唯一标识符
        Note._next_id += 1
        
        self.track_index = track_index  # 主轨道索引
        self.type = note_type  # 音符类型
        self.perfect_time = perfect_time  # 最佳击中时间 - 使用预计判定时间
        self.duration = duration  # 长按持续时间
        self.tracks = tracks if tracks else [track_index]  # 音符使用的所有轨道
        
        # 内部状态
        self.hit = False  # 是否已被击中
        self.held_time = 0  # 已按住的时间（用于长按音符）
        self.judgement: Optional[JudgementResult] = None  # 判定结果
        self.start_hold_time: Optional[int] = None  # 开始按住的时间
        self.current_track = track_index  # 当前所在轨道（用于拖动音符）
    
    def update(self, current_time: int, activated: bool = False, current_track: int = -1) -> None:
        """
        根据当前游戏时间更新音符状态
        
        Args:
            current_time (int): 当前游戏时间（毫秒）
            activated (bool): 当前轨道是否被激活（用于长按音符）
            current_track (int): 当前所在轨道（用于拖动音符）
        """
        # 更新当前轨道（用于拖动音符）
        if current_track != -1:
            self.current_track = current_track
        
        # 如果是长按音符且已经被击中，则更新按住时间
        if self.type == NoteType.HOLD and self.hit and activated:
            # 如果是第一次按住，记录开始时间
            if self.start_hold_time is None:
                self.start_hold_time = current_time
            # 计算已按住的时间，不超过音符持续时间
            # 使用perfect_time（预计判定时间）作为计算基准
            self.held_time = min(current_time - self.perfect_time, self.duration)
    
    def is_complete(self, current_time: int) -> bool:
        """
        检查音符是否已完成（已击中或已错过）
        
        Args:
            current_time (int): 当前游戏时间（毫秒）
            
        Returns:
            bool: 音符是否已完成
        """
        # 使用perfect_time（预计判定时间）作为判定基准
        if self.type == NoteType.NORMAL or self.type == NoteType.DRAG:
            # 普通音符和拖动音符：已击中或时间超过判定窗口
            return self.hit or current_time > self.perfect_time + 200  # 200ms是MISS判定窗口
        else:
            # 修复：HOLD音符的完成条件
            # 1. 已击中且按住时间达到持续时间 → 完成
            # 2. 未击中且时间超过判定窗口 → MISS，完成
            # 3. 已击中但被判定为MISS/BAD → 完成（立即消失）
            # 4. 已击中且还在按住，时间未到持续时间 → 未完成
            if self.hit:
                # 已击中：检查是否完成整个按住过程或已被判定为MISS/BAD
                if self.judgement in [JudgementResult.MISS, JudgementResult.BAD]:
                    # MISS或BAD判定后立即完成
                    return True
                return self.held_time >= self.duration
            else:
                # 未击中：检查是否超过判定窗口
                return current_time > self.perfect_time + 200
    
    def is_within_judgement_window(self, current_time: int, window_ms: int = 200) -> bool:
        """
        检查当前时间是否在音符的判定窗口内
        
        Args:
            current_time (int): 当前游戏时间
            window_ms (int): 判定窗口大小（毫秒）
            
        Returns:
            bool: 是否在判定窗口内
        """
        time_diff = abs(current_time - self.perfect_time)
        return time_diff <= window_ms
    
    def get_hold_progress(self) -> float:
        """
        获取长按音符的按住进度
        
        Returns:
            float: 进度比例（0.0-1.0）
        """
        if self.duration == 0:
            return 0.0
        return min(self.held_time / self.duration, 1.0)


class Track:
    """轨道类 - 表示游戏中的一条音符轨道"""
    def __init__(self, index: int):
        """
        初始化轨道
        
        Args:
            index (int): 轨道索引
        """
        self.index = index  # 轨道索引
        self.activated = False  # 当前是否被玩家按住
        self.last_press_time = 0  # 上次按下的时间戳（毫秒）
        self.press_count = 0  # 按下次数统计
        
        # 轨道状态事件回调
        self.on_press: Optional[Callable[[int], None]] = None
        self.on_release: Optional[Callable[[int], None]] = None
    
    def press(self, current_time: int) -> None:
        """
        处理轨道被按下的事件
        
        Args:
            current_time (int): 当前游戏时间（毫秒）
        """
        if not self.activated:
            self.activated = True
            self.last_press_time = current_time
            self.press_count += 1
            
            # 触发按下事件回调
            if self.on_press:
                try:
                    self.on_press(current_time)
                except Exception as e:
                    logger.error(f"Error in track {self.index} press callback: {e}")
    
    def release(self) -> None:
        """
        处理轨道被释放的事件
        """
        if self.activated:
            self.activated = False
            
            # 触发释放事件回调
            if self.on_release:
                try:
                    self.on_release()
                except Exception as e:
                    logger.error(f"Error in track {self.index} release callback: {e}")
    
    def reset(self) -> None:
        """
        重置轨道状态
        """
        self.activated = False
        self.last_press_time = 0
        # 注意：不重置press_count，这是统计数据




class JudgementSystem:
    """判定系统类 - 处理音符判定逻辑"""
    
    # 默认判定窗口配置（毫秒）
    DEFAULT_JUDGEMENT_WINDOWS = {
        JudgementResult.PERFECT: 80,     # 完美判定窗口：±80ms
        JudgementResult.GOOD: 160,       # 良好判定窗口：±160ms
        JudgementResult.BAD: 200,        # 较差判定窗口：±200ms
        # MISS：超出以上所有窗口
    }
    
    # 默认判定分数配置
    DEFAULT_JUDGEMENT_SCORES = {
        JudgementResult.PERFECT: 1.0,    # 完美判定（100%分数）
        JudgementResult.GOOD: 0.65,      # 良好判定（65%分数）
        JudgementResult.BAD: 0.0,        # 较差判定（0%分数）
        JudgementResult.MISS: 0.0,       # 错失判定（0%分数）
    }
    
    # 总分上限
    MAX_SCORE = 1000000
    
    def __init__(self, difficulty: Difficulty = Difficulty.NORMAL):
        """
        初始化判定系统
        
        Args:
            difficulty (Difficulty): 游戏难度，影响判定窗口大小
        """
        self.difficulty = difficulty
        self.judgement_windows = self._adjust_windows_for_difficulty(self.DEFAULT_JUDGEMENT_WINDOWS)
        self.judgement_scores = self.DEFAULT_JUDGEMENT_SCORES.copy()
        
        # 判定统计
        self.judgement_counts: Dict[JudgementResult, int] = {
            result: 0 for result in JudgementResult
        }
        
        # 谱面音符总数（用于计算每个音符的分值）
        self.total_notes = 0
    
    def _adjust_windows_for_difficulty(self, windows: Dict[JudgementResult, int]) -> Dict[JudgementResult, int]:
        """
        根据游戏难度调整判定窗口大小
        
        Args:
            windows (Dict[JudgementResult, int]): 原始判定窗口配置
            
        Returns:
            Dict[JudgementResult, int]: 调整后的判定窗口配置
        """
        # 难度系数：难度越高，判定窗口越小
        difficulty_factors = {
            Difficulty.EASY: 1.3,    # 简单难度：判定窗口放大30%
            Difficulty.NORMAL: 1.0,  # 普通难度：默认窗口
            Difficulty.HARD: 0.8,    # 困难难度：判定窗口缩小20%
            Difficulty.EXPERT: 0.6,  # 专家难度：判定窗口缩小40%
            Difficulty.MASTER: 0.5,  # 大师难度：判定窗口缩小50%
        }
        
        factor = difficulty_factors.get(self.difficulty, 1.0)
        adjusted_windows = {}
        
        for result, window in windows.items():
            if result != JudgementResult.MISS:
                adjusted_windows[result] = max(10, int(window * factor))  # 确保最小窗口为10ms
        
        return adjusted_windows
    
    def get_judgement(self, time_diff: int) -> JudgementResult:
        """
        根据时间差计算判定结果
        
        Args:
            time_diff (int): 实际击中时间与最佳时间的差值绝对值
            
        Returns:
            JudgementResult: 判定结果
        """
        if time_diff <= self.judgement_windows[JudgementResult.PERFECT]:
            return JudgementResult.PERFECT
        elif time_diff <= self.judgement_windows[JudgementResult.GOOD]:
            return JudgementResult.GOOD
        elif time_diff <= self.judgement_windows[JudgementResult.BAD]:
            return JudgementResult.BAD
        else:
            return JudgementResult.MISS
    
    def calculate_score(self, judgement: JudgementResult, combo: int = 0, max_combo_bonus: bool = True) -> int:
        """
        计算得分，按照按键判定自动分配
        
        Args:
            judgement (JudgementResult): 判定结果
            combo (int): 当前连击数（不影响分数计算）
            max_combo_bonus (bool): 是否启用最大连击加成（不使用）
            
        Returns:
            int: 得分
        """
        if self.total_notes == 0:
            return 0
        
        # 计算每个音符的基础分值
        base_score_per_note = self.MAX_SCORE / self.total_notes
        
        # 根据判定结果计算得分，向上取整
        score = base_score_per_note * self.judgement_scores[judgement]
        return math.ceil(score)
    
    def reset_statistics(self) -> None:
        """
        重置判定统计数据
        """
        for result in self.judgement_counts:
            self.judgement_counts[result] = 0
        
        # 重置音符总数
        self.total_notes = 0
        
    def set_total_notes(self, total_notes: int) -> None:
        """
        设置谱面的音符总数
        
        Args:
            total_notes (int): 音符总数
        """
        self.total_notes = total_notes


class GameState:
    """游戏状态类 - 管理游戏的整体状态和逻辑"""
    def __init__(self, difficulty: Difficulty = Difficulty.NORMAL):
        """
        初始化游戏状态
        
        Args:
            difficulty (Difficulty): 游戏难度
        """
        # 游戏基本状态
        self.difficulty = difficulty  # 保存难度设置
        self.score = 0  # 当前分数
        self.combo = 0  # 当前连击数
        self.max_combo = 0  # 最大连击数
        self.judgement: Optional[JudgementResult] = None  # 上一次判定结果
        self.current_time_ms = 0  # 当前游戏时间（毫秒）
        self.is_playing = False  # 游戏是否正在进行
        self.is_paused = False  # 游戏是否暂停
        self.game_speed = 1.0  # 游戏速度倍率
        self.autoplay = False  # 自动判定模式
        self.debug_timer = False  # 调试计时器
        
        # 游戏元素
        self.num_tracks = 10  # 轨道数量
        self.tracks: List[Track] = [Track(i) for i in range(self.num_tracks)]  # 创建轨道
        self.notes: List[Note] = []  # 当前活跃的音符列表
        self.text_events: List[Dict[str, Any]] = []  # 当前活跃的文字事件列表
        self.chart: Dict[str, Any] = {}  # 已加载的谱面数据
        self.chart_end_time_ms = None  # 谱面结束符的时间戳
        
        # 每个轨道的判定结果和判定时间（用于显示）
        self.track_judgements: List[Optional[JudgementResult]] = [None] * self.num_tracks
        self.track_judgement_times: List[int] = [0] * self.num_tracks
        self.track_judgement_display_ms = 500  # 判定结果显示时长（毫秒）
        
        # 判定系统
        self.judgement_system = JudgementSystem(difficulty)
        
        # 性能优化：音符缓存
        self._notes_by_track: List[List[Note]] = [[] for _ in range(self.num_tracks)]
        self._update_notes_cache = True
        
        # 游戏事件回调
        self.on_note_judged: Optional[Callable[[Note, JudgementResult], None]] = None
        self.on_combo_update: Optional[Callable[[int], None]] = None
        self.on_score_update: Optional[Callable[[int], None]] = None
        self.on_game_over: Optional[Callable[[Dict[str, Any]], None]] = None
        
        # 通用回调系统
        self._callbacks: Dict[str, List[Callable]] = {}
        
        # 音频管理器
        self.audio_manager = AudioManager()
    
    def load_chart(self, chart_data: Union[str, Dict[str, Any]]) -> bool:
        """
        加载谱面数据
        
        Args:
            chart_data (Union[str, Dict[str, Any]]): 谱面文件路径或JSON数据
            
        Returns:
            bool: 加载是否成功
        """
        try:
            # 重置游戏状态
            self._reset_game_state()
            
            # 解析谱面数据
            if isinstance(chart_data, str):
                # 根据文件扩展名判断格式
                _, ext = os.path.splitext(chart_data.lower())
                
                if ext == '.chart':
                    # 使用ChartParser解析.chart格式文件
                    parser = ChartParser()
                    self.chart = parser.parse_chart_file(chart_data)
                else:
                    # 尝试JSON格式解析
                    with open(chart_data, 'r', encoding='utf-8') as f:
                        self.chart = json.load(f)
            else:
                # 直接使用提供的数据
                self.chart = chart_data
            
            # 保存谱面速度设置
            if 'speed' in self.chart:
                self.speed = self.chart['speed']
                logger.info(f"Chart speed set to {self.speed} lines per second")
            else:
                # 默认速度
                self.speed = 5.0
                logger.info(f"Using default chart speed: {self.speed} lines per second")
            
            # 获取谱面结束时间
            self.chart_end_time_ms = self.chart.get('end_time_ms')
            if self.chart_end_time_ms is not None:
                logger.info(f"Chart has end marker at {self.chart_end_time_ms}ms")
            
            # 解析谱面中的音符数据
            if 'notes' in self.chart:
                for note_data in self.chart['notes']:
                    try:
                        # 确保note_type是一个有效的NoteType枚举值
                        note_type_value = note_data.get('type', 0)
                        # 尝试直接转换为NoteType，如果失败则使用默认值
                        try:
                            note_type = NoteType(note_type_value)
                        except ValueError:
                            # 如果类型转换失败，尝试根据数值确定类型
                            if isinstance(note_type_value, int):
                                # 确保数值在有效范围内
                                if 0 <= note_type_value < len(NoteType):
                                    note_type = list(NoteType)[note_type_value]
                                else:
                                    note_type = NoteType.NORMAL  # 默认使用普通音符
                            else:
                                note_type = NoteType.NORMAL  # 默认使用普通音符
                        
                        # 使用note_data中的perfect_time作为音符的预计判定时间
                        note = Note(
                            track_index=note_data['track_index'],
                            note_type=note_type,
                            perfect_time=note_data['perfect_time'],
                            duration=note_data.get('duration', 0),
                            tracks=note_data.get('tracks')
                        )
                        self.notes.append(note)
                        logger.debug(f"Created note: type={note_type}, track={note.track_index}, judgment_time={note.perfect_time}ms")
                    except Exception as e:
                        logger.warning(f"Invalid note data: {note_data}, error: {e}")
            
            # 按时间戳排序音符
            self.notes.sort(key=lambda note: note.perfect_time)
            
            # 设置判定系统中的音符总数
            self.judgement_system.set_total_notes(len(self.notes))
            
            # 加载文字事件
            if 'text_events' in self.chart:
                self.text_events = self.chart['text_events']
                logger.info(f"Loaded {len(self.text_events)} text events")
            
            # 更新缓存
            self._update_notes_cache = True
            
            logger.info(f"Successfully loaded chart with {len(self.notes)} notes and {len(self.text_events)} text events")
            return True
        except Exception as e:
            logger.error(f"Failed to load chart: {e}")
            return False
    
    def _reset_game_state(self) -> None:
        """
        重置游戏状态
        """
        self.score = 0
        self.combo = 0
        self.max_combo = 0
        self.judgement = None
        self.current_time_ms = 0
        self.is_playing = False
        self.is_paused = False
        self.notes = []
        self.text_events = []
        self.chart_end_time_ms = None
        
        # 重置轨道
        for track in self.tracks:
            track.reset()
        
        # 重置判定系统
        self.judgement_system.reset_statistics()
        
        # 重置缓存
        self._notes_by_track = [[] for _ in range(self.num_tracks)]
        self._update_notes_cache = True
    
    def _update_notes_cache_impl(self) -> None:
        """
        更新音符按轨道缓存，优化查询性能
        """
        if not self._update_notes_cache:
            return
        
        # 清空缓存
        for i in range(self.num_tracks):
            self._notes_by_track[i].clear()
        
        # 填充缓存
        for note in self.notes:
            if not note.hit:
                # 将音符添加到它所有轨道的缓存中
                for track_idx in note.tracks:
                    if 0 <= track_idx < self.num_tracks:
                        self._notes_by_track[track_idx].append(note)
        
        # 按时间排序每个轨道的音符
        for i in range(self.num_tracks):
            self._notes_by_track[i].sort(key=lambda note: note.perfect_time)
        
        self._update_notes_cache = False
    
    def update(self, delta_time_ms: int) -> None:
        """
        更新游戏状态，检查音符的生命周期
        
        Args:
            delta_time_ms (int): 时间增量（毫秒）
        """
        if not self.is_playing or self.is_paused:
            return
        
        # 如果current_time_ms为0（初始状态），则使用delta_time_ms更新
        # 否则，如果delta_time_ms大于0（表示有有效时间增量），则累加更新
        if self.current_time_ms == 0 or delta_time_ms > 0:
            self.current_time_ms += delta_time_ms
        
        # 更新音符缓存
        self._update_notes_cache_impl()
        
        # 如果启用了自动判定模式，处理自动判定
        if self.autoplay:
            self._process_autoplay()
        else:
            # 处理自动MISS判定
            self._process_auto_miss()
        
        # 处理DRAG音符的特殊判定条件
        # 在非AutoPlay模式下，碰到判定线时，若对应轨道处于按下状态则判定为perfect，否则为miss
        # 在AutoPlay模式下，DRAG音符已经在_process_autoplay方法中处理
        if not self.autoplay:
            for note in self.notes[:]:
                if note.type == NoteType.DRAG and not note.hit:
                    # 检查是否进入判定窗口
                    time_diff = abs(self.current_time_ms - note.perfect_time)
                    if time_diff <= 200:  # 使用MISS判定窗口
                        # 使用check_track_state模块检查轨道状态，优化时序
                        if self.check_track_state(note.track_index):
                            # 轨道被按下，判定为PERFECT
                            self._judge_perfect(note)
                        else:
                            # 轨道未被按下，判定为MISS
                            self._judge_miss(note)
        
        # 更新所有活跃音符的状态 - 优化：只处理时间窗口内的音符
        # 计算时间窗口：当前时间前后各3秒（足够覆盖所有判定窗口和可见范围）
        time_window_start = self.current_time_ms - 3000
        time_window_end = self.current_time_ms + 3000
        
        # 使用列表推导式快速过滤需要处理的音符
        # 修复：对于HOLD音符，需要考虑其持续时间
        notes_to_process = []
        for note in self.notes:
            if note.type == NoteType.HOLD:
                # HOLD音符：检查整个持续时间段是否与处理窗口重叠
                hold_start = note.perfect_time
                hold_end = note.perfect_time + note.duration
                if hold_start <= time_window_end and hold_end >= time_window_start:
                    notes_to_process.append(note)
            else:
                # 普通音符：只检查perfect_time
                if time_window_start <= note.perfect_time <= time_window_end:
                    notes_to_process.append(note)
        
        for note in notes_to_process:
            try:
                # 获取对应轨道的激活状态
                activated = self.check_track_state(note.track_index)
                
                # 更新音符状态
                note.update(self.current_time_ms, activated)
                
                # 检查音符是否已完成生命周期
                if note.is_complete(self.current_time_ms):
                    self.notes.remove(note)
                    self._update_notes_cache = True
            except Exception as e:
                logger.error(f"Error updating note {note.id}: {e}")
        
        # 检查游戏是否结束
        self._check_game_over()
        
    def _process_autoplay(self) -> None:
        """
        处理自动判定逻辑，将所有在判定窗口内的音符判定为PERFECT且时间差为0
        """
        # 直接检查所有活跃音符
        for note in list(self.notes):  # 使用副本避免在迭代中修改列表
            if not note.hit:
                # 检查音符是否进入PERFECT判定窗口
                # 为了平滑体验，我们设置一个更大的窗口来触发自动判定
                perfect_window = self.judgement_system.judgement_windows[JudgementResult.PERFECT] * 2
                time_diff = abs(self.current_time_ms - note.perfect_time)
                
                if time_diff <= perfect_window:
                    # 对于DRAG音符，除了判定为PERFECT外，还需要模拟按住轨道的状态
                    if note.type == NoteType.DRAG:
                        # 模拟按住对应轨道
                        self.tracks[note.track_index].activated = True
                    # 判定为PERFECT且时间差为0
                    self._judge_perfect(note)
            
            # 对于长按音符，确保在自动判定模式下也能正确处理
            elif note.type == NoteType.HOLD and self.current_time_ms < note.perfect_time + note.duration:
                # 模拟按住状态
                self.tracks[note.track_index].activated = True
                note.update(self.current_time_ms, True)
    
    def _judge_perfect(self, note: Note) -> None:
        """
        将音符判定为PERFECT
        
        Args:
            note (Note): 要判定的音符
        """
        # 确保所有判定的时间差都为0，尤其是在自动播放模式下
        self._judge_note(note, 0)
    
    def _process_auto_miss(self) -> None:
        """
        处理自动MISS判定
        """
        # 直接检查所有活跃音符，确保没有遗漏
        for note in list(self.notes):  # 使用副本避免在迭代中修改列表
            # 检查是否应该判定为MISS
            if not note.hit and self.current_time_ms > note.perfect_time + 200:  # 200ms是MISS判定窗口
                self._judge_miss(note)
    
    def _is_worse_judgement(self, new: JudgementResult, old: JudgementResult) -> bool:
        """
        判断新判定是否比旧判定更差
        
        判定等级（从好到差）：PERFECT > GOOD > BAD > MISS
        
        Args:
            new: 新判定
            old: 旧判定
            
        Returns:
            bool: 新判定是否比旧判定更差
        """
        judgement_order = {
            JudgementResult.PERFECT: 0,
            JudgementResult.GOOD: 1,
            JudgementResult.BAD: 2,
            JudgementResult.MISS: 3
        }
        return judgement_order[new] > judgement_order[old]
    
    def _check_game_over(self) -> None:
        """
        检查游戏是否结束
        """
        # 检查游戏是否正在进行
        if not self.is_playing:
            return
            
        # 优先检查是否有谱面结束符
        if self.chart_end_time_ms is not None:
            # 如果当前时间超过了结束符时间，进行结算
            if self.current_time_ms >= self.chart_end_time_ms:
                # 确保所有音符都被判定（在结束符时间之前的音符）
                for note in self.notes[:]:
                    if not note.hit and note.perfect_time <= self.chart_end_time_ms:
                        self._judge_miss(note)
                
                # 触发游戏结束事件
                if self.on_game_over:
                    try:
                        final_stats = {
                            'score': self.score,
                            'max_combo': self.max_combo,
                            'judgements': self.judgement_system.judgement_counts,
                            'accuracy': self.get_accuracy(),
                            'clear_time': self.current_time_ms
                        }
                        self.on_game_over(final_stats)
                    except Exception as e:
                        logger.error(f"Error in game over callback: {e}")
                
                # 触发状态变化回调
                self._trigger_callbacks('on_state_change', 'result')
                
                # 停止游戏
                self.stop_game()
                return
        
        # 如果没有结束符或者还没到结束时间，使用原来的逻辑
        # 检查条件：没有活跃音符且所有音符都已判定
        # 实际游戏中可能需要根据谱面总时长来判断
        # 这里简化处理：如果没有活跃音符且当前时间超过最后一个音符的判定时间+5秒，则认为游戏结束
        if not self.notes:
            # 触发游戏结束事件
            if self.on_game_over:
                try:
                    final_stats = {
                        'score': self.score,
                        'max_combo': self.max_combo,
                        'judgements': self.judgement_system.judgement_counts,
                        'accuracy': self.get_accuracy(),
                        'clear_time': self.current_time_ms
                    }
                    self.on_game_over(final_stats)
                except Exception as e:
                    logger.error(f"Error in game over callback: {e}")
            
            # 触发状态变化回调
            self._trigger_callbacks('on_state_change', 'result')
            
            # 停止游戏
            self.stop_game()
    
    def check_track_state(self, track_index: int) -> bool:
        """
        检测指定轨道的状态
        
        Args:
            track_index (int): 需要检测的轨道索引 (0, 1, 2, 3)
            
        Returns:
            bool: 轨道是否正在被按下（按下为True，松开为False）
        """
        # 使用tracks数组的activated属性来判断轨道状态，保持与其他音符判定逻辑一致
        if 0 <= track_index < self.num_tracks:
            return self.tracks[track_index].activated
        return False
    
    def judge_note(self, track_index: int, action: str = 'press') -> Optional[JudgementResult]:
        """
        根据用户输入和当前时间，判定指定轨道上的音符
        
        Args:
            track_index (int): 轨道索引
            action (str): 用户动作（'press' 或 'release'）
            
        Returns:
            Optional[JudgementResult]: 判定结果，如果没有可判定的音符则返回None
        """
        if not self.is_playing or self.is_paused:
            return None
        
        # 验证轨道索引
        if track_index < 0 or track_index >= self.num_tracks:
            logger.warning(f"Invalid track index: {track_index}")
            return None
        
        # 处理轨道状态
        if action == 'press':
            self.tracks[track_index].press(self.current_time_ms)
        elif action == 'release':
            # 检查是否有HOLD音符在该轨道上并且已经开始判定但未完成
            for note in self.notes:
                if note.type == NoteType.HOLD and note.track_index == track_index and note.hit and not note.is_complete(self.current_time_ms):
                    # 修复：根据按住比例判定，而不是直接BAD
                    hold_progress = note.get_hold_progress()
                    if hold_progress >= 0.8:
                        # 按住80%以上，判定为PERFECT
                        new_judgement = JudgementResult.PERFECT
                    elif hold_progress >= 0.5:
                        # 按住50%-80%，判定为GOOD
                        new_judgement = JudgementResult.GOOD
                    elif hold_progress >= 0.2:
                        # 按住20%-50%，判定为BAD
                        new_judgement = JudgementResult.BAD
                    else:
                        # 按住少于20%，判定为MISS
                        new_judgement = JudgementResult.MISS
                    
                    # 只有当新判定比当前判定差时才更新（保持首击判定）
                    if note.judgement is None or self._is_worse_judgement(new_judgement, note.judgement):
                        # 更新判定计数（先减去旧的）
                        if note.judgement in self.judgement_system.judgement_counts:
                            self.judgement_system.judgement_counts[note.judgement] -= 1
                        # 设置新判定
                        note.judgement = new_judgement
                        self.judgement_system.judgement_counts[new_judgement] += 1
                        self.judgement = new_judgement
                        # 触发判定事件
                        if self.on_note_judged:
                            try:
                                self.on_note_judged(note, new_judgement)
                            except Exception as e:
                                logger.error(f"Error in note judged callback: {e}")
            
            self.tracks[track_index].release()
        else:
            logger.warning(f"Invalid action: {action}")
            return None
        
        # 优化：延迟更新音符缓存，避免每次按键都重建缓存
        # 缓存将在update方法中统一更新，减少重复计算
        if self._update_notes_cache:
            self._update_notes_cache_impl()
        
        # 获取该轨道上的所有未击中音符
        track_notes = self._notes_by_track[track_index]
        
        # 查找所有在判定窗口内的音符，但排除DRAG音符（DRAG音符在update方法中处理）
        target_notes = []
        
        for note in track_notes:
            if not note.hit and note.type != NoteType.DRAG:  # 跳过DRAG音符
                time_diff = abs(self.current_time_ms - note.perfect_time)
                # 只考虑200ms内的音符
                if time_diff <= 200:
                    target_notes.append((note, time_diff))
        
        # 如果没有找到音符，返回None
        if not target_notes:
            return None
        
        # 按时间差排序，找到最接近的音符
        target_notes.sort(key=lambda x: x[1])
        target_note, min_time_diff = target_notes[0]
        
        # 对于HOLD音符，首行判定结果会延申至整个note
        return self._judge_note(target_note, min_time_diff)
    
    def _judge_note(self, note: Note, time_diff: int) -> JudgementResult:
        """
        判定单个音符
        
        Args:
            note (Note): 要判定的音符
            time_diff (int): 时间差
            
        Returns:
            JudgementResult: 判定结果
        """
        # 确定判定结果
        result = self.judgement_system.get_judgement(time_diff)
        
        # 更新音符状态
        note.hit = True
        note.judgement = result
        
        # 根据音符类型播放对应的音效（只在非MISS判定时播放）
        if result != JudgementResult.MISS:
            # 根据音符类型选择对应的音效
            sfx_name = None
            if note.type == NoteType.NORMAL:
                sfx_name = "tab"  # 普通音符使用tab音效
            elif note.type == NoteType.HOLD:
                sfx_name = "hold"  # 长按音符使用hold音效
            elif note.type == NoteType.DRAG:
                sfx_name = "drag"  # 拖动音符使用drag音效
            
            # 播放音效
            if sfx_name:
                self.audio_manager.play_note_sfx(sfx_name)
        
        # 更新游戏状态
        if result != JudgementResult.MISS:
            # 计算得分
            score_gain = self.judgement_system.calculate_score(result, self.combo)
            # 确保总分不超过上限
            self.score = min(self.score + score_gain, self.judgement_system.MAX_SCORE)
            
            # 更新连击
            self.combo += 1
            self.max_combo = max(self.max_combo, self.combo)
            
            # 触发连击更新事件
            if self.on_combo_update:
                try:
                    self.on_combo_update(self.combo)
                except Exception as e:
                    logger.error(f"Error in combo update callback: {e}")
            
            # 触发分数更新事件
            if self.on_score_update:
                try:
                    self.on_score_update(self.score)
                except Exception as e:
                    logger.error(f"Error in score update callback: {e}")
            
            # 触发通用回调
            self._trigger_callbacks('on_score_change', self.score)
            self._trigger_callbacks('on_combo_change', self.combo)
        elif result == JudgementResult.MISS:
            # MISS时重置连击
            self.combo = 0
            # 触发连击更新事件
            self._trigger_callbacks('on_combo_change', self.combo)
        
        # 更新判定计数
        self.judgement_system.judgement_counts[result] += 1
        self.judgement = result
        
        # 更新每个轨道的判定结果和判定时间
        for track_idx in note.tracks:
            if 0 <= track_idx < self.num_tracks:
                self.track_judgements[track_idx] = result
                self.track_judgement_times[track_idx] = self.current_time_ms
        
        # 更新缓存标记
        self._update_notes_cache = True
        
        # 触发音符判定事件
        if self.on_note_judged:
            try:
                self.on_note_judged(note, result)
            except Exception as e:
                logger.error(f"Error in note judged callback: {e}")
        
        # 触发通用回调
        self._trigger_callbacks('on_judgement', result)
        
        return result
    
    def _judge_miss(self, note: Note) -> None:
        """
        将音符判定为MISS
        
        Args:
            note (Note): 要判定为MISS的音符
        """
        # 直接设置音符状态为MISS，不调用_judge_note方法
        note.hit = True
        note.judgement = JudgementResult.MISS
        
        # 更新游戏状态
        self.combo = 0  # MISS时重置连击
        
        # 更新判定计数
        self.judgement_system.judgement_counts[JudgementResult.MISS] += 1
        self.judgement = JudgementResult.MISS
        
        # 更新每个轨道的判定结果和判定时间
        for track_idx in note.tracks:
            if 0 <= track_idx < self.num_tracks:
                self.track_judgements[track_idx] = JudgementResult.MISS
                self.track_judgement_times[track_idx] = self.current_time_ms
        
        # 更新缓存标记
        self._update_notes_cache = True
        
        # 触发音符判定事件
        if self.on_note_judged:
            try:
                self.on_note_judged(note, JudgementResult.MISS)
            except Exception as e:
                logger.error(f"Error in note judged callback: {e}")
        
        # 触发通用回调
        self._trigger_callbacks('on_combo_change', self.combo)
        self._trigger_callbacks('on_judgement', JudgementResult.MISS)
    
    def start_game(self) -> None:
        """
        开始游戏
        """
        if self.notes:
            self.is_playing = True
            self.is_paused = False
            self.current_time_ms = 0
            logger.info("Game started")
            # 触发状态变化回调
            self._trigger_callbacks('on_state_change', 'playing')
        else:
            logger.warning("Cannot start game: no notes loaded")
    
    def pause_game(self) -> None:
        """
        暂停游戏
        """
        if self.is_playing:
            self.is_paused = True
            logger.info("Game paused")
            # 触发状态变化回调
            self._trigger_callbacks('on_state_change', 'paused')
    
    def resume_game(self) -> None:
        """
        恢复游戏
        """
        if self.is_playing and self.is_paused:
            self.is_paused = False
            logger.info("Game resumed")
            # 触发状态变化回调
            self._trigger_callbacks('on_state_change', 'playing')
    
    def stop_game(self) -> None:
        """
        停止游戏
        """
        self.is_playing = False
        self.is_paused = False
        # 保留分数和连击作为最终结果
        logger.info("Game stopped")
        # 触发状态变化回调
        self._trigger_callbacks('on_state_change', 'stopped')
    
    def set_sfx_volume(self, volume: float) -> None:
        """
        设置音效音量
        
        Args:
            volume (float): 音量值（0.0到1.0之间）
        """
        self.audio_manager.set_sfx_volume(volume)
        logger.info(f"SFX volume set to {volume}")
    
    def get_accuracy(self) -> float:
        """
        计算游戏准确率
        
        Returns:
            float: 准确率（0.0-1.0）
        """
        total_notes = sum(self.judgement_system.judgement_counts.values())
        if total_notes == 0:
            return 1.0
        
        # 计算加权准确率
        weighted_score = (
            self.judgement_system.judgement_counts[JudgementResult.PERFECT] * 1.0 +
            self.judgement_system.judgement_counts[JudgementResult.GOOD] * 0.65 +
            self.judgement_system.judgement_counts[JudgementResult.BAD] * 0.0
        )
        
        return weighted_score / total_notes
    
    def set_difficulty(self, difficulty: Difficulty) -> None:
        """
        设置游戏难度
        
        Args:
            difficulty (Difficulty): 游戏难度
        """
        self.judgement_system = JudgementSystem(difficulty)
        logger.info(f"Difficulty set to {difficulty.value}")
    
    def set_game_speed(self, speed: float) -> None:
        """
        设置游戏速度倍率
        
        Args:
            speed (float): 速度倍率（0.5-2.0）
        """
        # 限制速度范围
        self.game_speed = max(0.5, min(2.0, speed))
        logger.info(f"Game speed set to {self.game_speed}x")
        
    def set_autoplay(self, enable: bool) -> None:
        """
        设置是否启用自动判定模式
        
        Args:
            enable (bool): 是否启用
        """
        self.autoplay = enable
        logger.info(f"Autoplay {'enabled' if enable else 'disabled'}")
        
    def set_debug_timer(self, enable: bool) -> None:
        """
        设置是否启用调试计时器
        
        Args:
            enable (bool): 是否启用
        """
        self.debug_timer = enable
        logger.info(f"Debug timer {'enabled' if enable else 'disabled'}")
    
    def hit_note(self, track_index: int) -> Optional[JudgementResult]:
        """
        击中指定轨道上的音符（用于ANSI版本兼容）
        
        Args:
            track_index (int): 轨道索引
            
        Returns:
            Optional[JudgementResult]: 判定结果，如果没有可判定的音符则返回None
        """
        return self.judge_note(track_index, 'press')
    
    def get_game_statistics(self) -> Dict[str, Any]:
        """
        获取游戏统计信息

        Returns:
            Dict[str, Any]: 游戏统计信息
        """
        return {
            'score': self.score,
            'combo': self.combo,
            'max_combo': self.max_combo,
            'judgements': self.judgement_system.judgement_counts,
            'accuracy': self.get_accuracy(),
            'current_time': self.current_time_ms,
            'difficulty': self.judgement_system.difficulty.value,
            'game_speed': self.game_speed,
            'active_notes': len(self.notes)
        }
    
    def should_game_end(self) -> bool:
        """
        判断游戏是否应该结束
        
        Returns:
            bool: 如果游戏应该结束返回True，否则返回False
        """
        # 优先检查是否有谱面结束符
        if self.chart_end_time_ms is not None:
            # 当有结束符时，只检查当前时间是否到达结束符时间
            # 忽略所有其他条件（如音符是否全部判定）
            return self.current_time_ms >= self.chart_end_time_ms
        
        # 如果没有结束符，使用原来的逻辑
        # 检查是否有活跃音符
        if self.notes:
            # 获取最后一个音符的判定时间加上一段延迟作为结束条件
            last_note_time = max(note.perfect_time for note in self.notes) if self.notes else 0
            # 如果当前时间超过最后一个音符时间+3秒，则游戏结束
            if self.current_time_ms > last_note_time + 3000:
                # 确保所有音符都被判定
                for note in self.notes:
                    if not note.hit:
                        self._judge_miss(note)
                return True
        
        # 如果所有音符都已经被判定，则游戏结束
        if all(note.hit for note in self.notes):
            return True
        
        return False
    
    def add_callback(self, event_name: str, callback: Callable) -> None:
        """
        添加事件回调
        
        Args:
            event_name (str): 事件名称
            callback (Callable): 回调函数
        """
        if event_name not in self._callbacks:
            self._callbacks[event_name] = []
        self._callbacks[event_name].append(callback)
    
    def _trigger_callbacks(self, event_name: str, *args, **kwargs) -> None:
        """
        触发指定事件的所有回调
        
        Args:
            event_name (str): 事件名称
            *args: 传递给回调的位置参数
            **kwargs: 传递给回调的关键字参数
        """
        if event_name in self._callbacks:
            for callback in self._callbacks[event_name]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error in callback for event {event_name}: {e}")

    def down(self, number):
        """
        设置轨道为按下状态
        
        Args:
            number (int): 轨道索引 (0-3)
        """
        if 0 <= number < self.num_tracks:
            # 直接调用轨道的press方法，保持与judge_note逻辑一致
            self.tracks[number].press(self.current_time_ms)
    
    def up(self, number):
        """
        设置轨道为松开状态
        
        Args:
            number (int): 轨道索引 (0-3)
        """
        if 0 <= number < self.num_tracks:
            # 直接调用轨道的release方法，保持与judge_note逻辑一致
            self.tracks[number].release()
# 简单的工具函数

def create_test_chart(num_notes: int = 50, duration_ms: int = 30000) -> Dict[str, Any]:
    """
    创建测试用的谱面数据
    
    Args:
        num_notes (int): 音符数量
        duration_ms (int): 谱面时长（毫秒）
        
    Returns:
        Dict[str, Any]: 谱面数据
    """
    import random
    
    chart = {
        'metadata': {
            'title': 'Test Chart',
            'artist': 'TRG Engine',
            'difficulty': 'normal',
            'duration': duration_ms
        },
        'notes': []
    }
    
    # 生成音符
    time_interval = duration_ms // num_notes
    
    for i in range(num_notes):
        # 随机时间（稍微打乱均匀分布）
        time_offset = random.randint(-time_interval // 4, time_interval // 4)
        perfect_time = (i + 1) * time_interval + time_offset
        
        # 随机轨道
        track_index = random.randint(0, 3)
        
        # 随机音符类型
        note_type = random.choice(list(NoteType))
        
        # 根据音符类型设置额外属性
        note_data = {
            'type': note_type.value,
            'track_index': track_index,
            'perfect_time': perfect_time
        }
        
        # 如果是长按音符，设置持续时间
        if note_type == NoteType.HOLD:
            note_data['duration'] = random.randint(500, 2000)
        
        # 如果是拖动音符，设置目标轨道
        elif note_type == NoteType.DRAG:
            # 确保目标轨道与当前轨道不同
            target_tracks = [t for t in range(4) if t != track_index]
            note_data['drag_target'] = random.choice(target_tracks)
        
        chart['notes'].append(note_data)
    
    # 按时间排序音符
    chart['notes'].sort(key=lambda x: x['perfect_time'])
    
    return chart