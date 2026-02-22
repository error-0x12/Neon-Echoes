#!/usr/bin/env python3
"""
Neon Echoes - 制谱器

使用PySide6创建的制谱器，支持：
- 选择并播放音频文件
- 监听按键，自动添加tap音符（10个轨道对应10个按键）
- 实时谱面预览
- 保存谱面为.chart格式
"""

import os
import sys
import time
import threading
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QFileDialog, QLineEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QTextEdit, QSplitter, QFrame, QMessageBox,
    QGroupBox, QMenu, QInputDialog
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QUrl
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QKeyEvent, QMouseEvent
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# 配置日志
logger = logging.getLogger('NeonEchoes.ChartEditor')
logger.setLevel(logging.INFO)
if logger.handlers:
    logger.handlers.clear()
log_file = os.path.join(os.path.dirname(__file__), 'logs', 'chart_editor.log')
os.makedirs(os.path.dirname(log_file), exist_ok=True)
file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# 按键映射 - 10个轨道对应10个按键
TRACK_KEYS = [
    Qt.Key_Q, Qt.Key_W, Qt.Key_E, Qt.Key_R, Qt.Key_T,
    Qt.Key_Y, Qt.Key_U, Qt.Key_I, Qt.Key_O, Qt.Key_P
]

TRACK_KEY_LABELS = ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P']


class Note:
    """音符类"""

    def __init__(self, time_ms: int, track: int, note_type: str = "normal"):
        self.time_ms = time_ms
        self.track = track
        self.type = note_type
        self.duration = 0

    def to_chart_line(self) -> str:
        """转换为.chart格式的一行"""
        if self.type == "normal":
            return f"tab-{self.track + 1}"
        elif self.type == "hold":
            return f"hold-{self.track + 1}-{self.duration}"
        elif self.type == "drag":
            return f"drag-{self.track + 1}"
        return ""

    def __lt__(self, other):
        return self.time_ms < other.time_ms


class ChartPreviewWidget(QWidget):
    """谱面预览控件"""

    # 信号定义
    note_right_clicked = Signal(Note, int)  # 音符右击信号 (note, note_index)
    track_right_clicked = Signal(int, int)  # 轨道右击信号 (track_index, time_ms)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.notes: List[Note] = []
        self.current_time_ms = 0
        self.num_tracks = 10
        self.setMinimumHeight(300)
        self.setMouseTracking(True)

        # 用于拖拽放置
        self._dragging = False
        self._drag_start_y = 0
        self._drag_track = -1
        self._drag_note_type = "normal"

    def set_notes(self, notes: List[Note]):
        self.notes = notes
        self.update()

    def set_current_time(self, time_ms: int):
        self.current_time_ms = time_ms
        self.update()

    def _get_track_at_x(self, x: int) -> int:
        """根据X坐标获取轨道索引"""
        track_width = self.width() / self.num_tracks
        track = int(x / track_width)
        return max(0, min(track, self.num_tracks - 1))

    def _get_time_at_y(self, y: int) -> int:
        """根据Y坐标获取时间（毫秒）"""
        height = self.height()
        center_y = height // 2
        preview_duration = 5000

        # 计算相对于判定线的位置
        progress = (center_y - y) / (center_y - 30)
        time_diff = int(progress * preview_duration)
        return self.current_time_ms + time_diff

    def _get_note_at_pos(self, x: int, y: int) -> tuple:
        """获取指定位置的音符和索引"""
        width = self.width()
        height = self.height()
        track_width = width / self.num_tracks
        center_y = height // 2
        preview_duration = 5000

        track = self._get_track_at_x(x)
        track_x = int(track * track_width)
        note_width = int(track_width * 0.8)
        note_x_start = track_x + int(track_width * 0.1)
        note_x_end = note_x_start + note_width

        if not (note_x_start <= x <= note_x_end):
            return None, -1

        for i, note in enumerate(self.notes):
            if note.track != track:
                continue

            time_diff = note.time_ms - self.current_time_ms
            if abs(time_diff) > preview_duration:
                continue

            progress = time_diff / preview_duration
            note_y = center_y - int(progress * (center_y - 30))

            if note_y <= y <= note_y + 15:
                return note, i

        return None, -1

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.RightButton:
            x = int(event.position().x())
            y = int(event.position().y())

            # 先检查是否点击了音符
            note, note_index = self._get_note_at_pos(x, y)
            if note:
                self.note_right_clicked.emit(note, note_index)
            else:
                # 点击轨道，准备放置音符
                track = self._get_track_at_x(x)
                time_ms = self._get_time_at_y(y)
                self.track_right_clicked.emit(track, time_ms)

        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(20, 20, 30))

        width = self.width()
        height = self.height()
        track_width = width / self.num_tracks
        center_y = height // 2
        preview_duration = 5000

        # 绘制轨道
        for i in range(self.num_tracks):
            x = int(i * track_width)
            color = QColor(60, 60, 80)
            painter.fillRect(x, 0, int(track_width), height, color)

            # 轨道边界
            pen = QPen(QColor(80, 80, 100), 1)
            painter.setPen(pen)
            painter.drawLine(x, 0, x, height)

        # 绘制判定线
        pen = QPen(QColor(255, 50, 50), 2)
        painter.setPen(pen)
        painter.drawLine(0, center_y, width, center_y)

        # 绘制音符
        for note in self.notes:
            time_diff = note.time_ms - self.current_time_ms
            if abs(time_diff) > preview_duration:
                continue

            track_x = int(note.track * track_width)
            note_width = int(track_width * 0.8)
            note_x = track_x + int(track_width * 0.1)

            # 计算Y位置
            progress = time_diff / preview_duration
            note_y = center_y - int(progress * (center_y - 30))

            if 0 <= note_y < height - 10:
                if note.type == "normal":
                    color = QColor(50, 200, 50)
                elif note.type == "hold":
                    color = QColor(50, 50, 200)
                elif note.type == "drag":
                    color = QColor(200, 200, 50)
                else:
                    color = QColor(200, 200, 200)

                painter.fillRect(note_x, note_y, note_width, 15, color)
                pen = QPen(QColor(255, 255, 255), 1)
                painter.setPen(pen)
                painter.drawRect(note_x, note_y, note_width, 15)

                # 绘制hold音符的持续时间
                if note.type == "hold" and note.duration > 0:
                    hold_height = int((note.duration / preview_duration) * (center_y - 30))
                    hold_color = QColor(50, 50, 200, 128)
                    painter.fillRect(note_x, note_y, note_width, hold_height, hold_color)

        # 绘制轨道标签
        painter.setPen(QColor(200, 200, 200))
        font = QFont("Arial", 10)
        painter.setFont(font)
        for i in range(self.num_tracks):
            x = int(i * track_width + track_width // 2 - 5)
            painter.drawText(x, 20, TRACK_KEY_LABELS[i])


class ChartEditorWindow(QMainWindow):
    """制谱器主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Neon Echoes - 制谱器")
        self.setGeometry(100, 100, 1200, 800)

        self.notes: List[Note] = []
        self.is_playing = False
        self.is_recording = False
        self.record_start_time = 0.0
        self.media_player: Optional[QMediaPlayer] = None
        self.audio_output: Optional[QAudioOutput] = None
        self.audio_file: Optional[str] = None

        self._setup_ui()
        self._setup_media_player()

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_preview)
        self.update_timer.start(33)

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 标题
        title_label = QLabel("🎵 Neon Echoes 制谱器 🎵")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #00ffaa; padding: 10px;")
        main_layout.addWidget(title_label)

        # 提示标签
        hint_label = QLabel("💡 提示: 右击轨道放置音符 | 右击音符编辑 | 录制模式使用 QWERTYUIOP 按键")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet("font-size: 12px; color: #aaaaaa; padding: 5px;")
        main_layout.addWidget(hint_label)

        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter)

        # 顶部控制区
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)

        # 文件控制区
        file_group = QGroupBox("文件设置")
        file_layout = QHBoxLayout(file_group)

        self.audio_file_btn = QPushButton("选择音频文件")
        self.audio_file_btn.clicked.connect(self._select_audio_file)
        file_layout.addWidget(self.audio_file_btn)

        self.audio_file_label = QLabel("未选择音频文件")
        self.audio_file_label.setStyleSheet("color: #aaaaaa;")
        file_layout.addWidget(self.audio_file_label, 1)
        top_layout.addWidget(file_group)

        # 谱面信息区
        info_group = QGroupBox("谱面信息")
        info_layout = QHBoxLayout(info_group)

        info_layout.addWidget(QLabel("曲名:"))
        self.name_edit = QLineEdit("新谱面")
        info_layout.addWidget(self.name_edit)

        info_layout.addWidget(QLabel("作者:"))
        self.maker_edit = QLineEdit("Unknown")
        info_layout.addWidget(self.maker_edit)

        info_layout.addWidget(QLabel("难度等级:"))
        self.level_spin = QSpinBox()
        self.level_spin.setRange(1, 20)
        self.level_spin.setValue(5)
        info_layout.addWidget(self.level_spin)

        info_layout.addWidget(QLabel("难度:"))
        self.difficulty_combo = QComboBox()
        self.difficulty_combo.addItems(["EZ", "HD", "IN", "AT", "SP"])
        self.difficulty_combo.setCurrentIndex(1)
        info_layout.addWidget(self.difficulty_combo)

        info_layout.addWidget(QLabel("速度:"))
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.5, 30.0)
        self.speed_spin.setValue(5.0)
        self.speed_spin.setSingleStep(0.5)
        info_layout.addWidget(self.speed_spin)

        top_layout.addWidget(info_group)

        # 播放控制区
        play_group = QGroupBox("播放控制")
        play_layout = QHBoxLayout(play_group)

        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.clicked.connect(self._toggle_play)
        self.play_btn.setMinimumHeight(40)
        self.play_btn.setStyleSheet("background-color: #336633; font-size: 14px;")
        play_layout.addWidget(self.play_btn)

        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setMinimumHeight(40)
        play_layout.addWidget(self.stop_btn)

        play_layout.addWidget(QLabel("|"))

        self.record_btn = QPushButton("🎤 录制")
        self.record_btn.clicked.connect(self._toggle_record)
        self.record_btn.setMinimumHeight(40)
        self.record_btn.setStyleSheet("background-color: #663333; font-size: 14px;")
        play_layout.addWidget(self.record_btn)

        self.clear_btn = QPushButton("🗑️ 清空音符")
        self.clear_btn.clicked.connect(self._clear_notes)
        self.clear_btn.setMinimumHeight(40)
        play_layout.addWidget(self.clear_btn)

        play_layout.addWidget(QLabel("|"))

        self.load_btn = QPushButton("📂 导入谱面")
        self.load_btn.clicked.connect(self._load_chart)
        self.load_btn.setMinimumHeight(40)
        self.load_btn.setStyleSheet("background-color: #663366; font-size: 14px;")
        play_layout.addWidget(self.load_btn)

        self.save_btn = QPushButton("💾 保存谱面")
        self.save_btn.clicked.connect(self._save_chart)
        self.save_btn.setMinimumHeight(40)
        self.save_btn.setStyleSheet("background-color: #333366; font-size: 14px;")
        play_layout.addWidget(self.save_btn)

        top_layout.addWidget(play_group)

        # 进度条
        progress_layout = QHBoxLayout()
        progress_layout.addWidget(QLabel("进度:"))
        self.time_label = QLabel("0:00.000 / 0:00.000")
        progress_layout.addWidget(self.time_label)
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setMinimum(0)
        self.progress_slider.setMaximum(1000)
        self.progress_slider.setValue(0)
        self.progress_slider.sliderPressed.connect(self._slider_pressed)
        self.progress_slider.sliderReleased.connect(self._slider_released)
        self.progress_slider.sliderMoved.connect(self._slider_moved)
        progress_layout.addWidget(self.progress_slider, 1)
        top_layout.addLayout(progress_layout)

        splitter.addWidget(top_widget)

        # 预览区
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)

        preview_label = QLabel("谱面预览 (使用 Q W E R T Y U I O P 添加音符)")
        preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_label.setStyleSheet("font-size: 14px; color: #aaaaaa; padding: 5px;")
        preview_layout.addWidget(preview_label)

        self.preview_widget = ChartPreviewWidget()
        self.preview_widget.note_right_clicked.connect(self._on_note_right_clicked)
        self.preview_widget.track_right_clicked.connect(self._on_track_right_clicked)
        preview_layout.addWidget(self.preview_widget, 1)

        # 音符列表
        notes_label = QLabel("音符列表:")
        notes_label.setStyleSheet("font-size: 14px; color: #aaaaaa; padding: 5px;")
        preview_layout.addWidget(notes_label)

        self.notes_text = QTextEdit()
        self.notes_text.setReadOnly(True)
        self.notes_text.setMaximumHeight(150)
        self.notes_text.setStyleSheet("background-color: #111111; color: #00ffaa; font-family: monospace;")
        preview_layout.addWidget(self.notes_text)

        splitter.addWidget(preview_widget)
        splitter.setSizes([300, 500])

    def _setup_media_player(self):
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)

    def _select_audio_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", "", "音频文件 (*.mp3 *.wav *.ogg *.flac)"
        )
        if file_path:
            self.audio_file = file_path
            self.audio_file_label.setText(Path(file_path).name)
            self.media_player.setSource(QUrl.fromLocalFile(file_path))
            logger.info(f"选择了音频文件: {file_path}")

    def _toggle_play(self):
        if not self.audio_file:
            QMessageBox.warning(self, "警告", "请先选择音频文件！")
            return

        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def _stop(self):
        self.media_player.stop()
        self.is_recording = False
        self.record_btn.setText("🎤 录制")
        self.record_btn.setStyleSheet("background-color: #663333; font-size: 14px;")

    def _toggle_record(self):
        if not self.audio_file:
            QMessageBox.warning(self, "警告", "请先选择音频文件！")
            return

        self.is_recording = not self.is_recording
        if self.is_recording:
            self.record_start_time = time.time()
            self.record_btn.setText("⏹ 停止录制")
            self.record_btn.setStyleSheet("background-color: #ff3333; font-size: 14px;")
            if self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.media_player.play()
        else:
            self.record_btn.setText("🎤 录制")
            self.record_btn.setStyleSheet("background-color: #663333; font-size: 14px;")

    def _clear_notes(self):
        reply = QMessageBox.question(
            self, "确认", "确定要清空所有音符吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.notes.clear()
            self._update_notes_text()
            self.preview_widget.set_notes(self.notes)

    def _save_chart(self):
        if not self.notes:
            QMessageBox.warning(self, "警告", "谱面没有音符！")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存谱面", "", "谱面文件 (*.chart)"
        )
        if file_path:
            self._write_chart(file_path)

    def _load_chart(self):
        """导入谱面文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入谱面", "", "谱面文件 (*.chart)"
        )
        if not file_path:
            return

        try:
            self._parse_chart_file(file_path)
            QMessageBox.information(self, "成功", f"谱面已导入:\n{file_path}")
            logger.info(f"谱面已导入: {file_path}")
        except Exception as e:
            logger.error(f"导入谱面失败: {e}")
            QMessageBox.critical(self, "错误", f"导入失败:\n{str(e)}")

    def _parse_chart_file(self, file_path: str):
        """解析谱面文件"""
        import re

        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 清空现有音符
        self.notes.clear()

        current_time_ms = 0
        audio_file_name = None

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # 结束标记
            if line == '&':
                break

            # 解析时间
            time_match = re.match(r'^(\d+:\d+(?::\d+)?)$', line)
            if time_match:
                time_str = time_match.group(1)
                parts = time_str.split(':')
                if len(parts) == 2:
                    minutes, seconds = map(int, parts)
                    milliseconds = 0
                elif len(parts) == 3:
                    minutes, seconds, milliseconds = map(int, parts)
                else:
                    continue
                current_time_ms = minutes * 60 * 1000 + seconds * 1000 + milliseconds
                continue

            # 解析元数据
            if line.startswith('name-'):
                self.name_edit.setText(line[5:].strip())
                continue

            if line.startswith('maker-'):
                maker_text = line[6:].strip()
                # 处理可能包含 '-' 的作者名
                if '-' in maker_text:
                    maker = maker_text.split('-', 1)[0].strip()
                else:
                    maker = maker_text
                self.maker_edit.setText(maker)
                continue

            if line.startswith('level-'):
                parts = line[6:].split('-', 1)
                try:
                    self.level_spin.setValue(int(parts[0]))
                    if len(parts) > 1:
                        difficulty = parts[1].strip().upper()
                        index = self.difficulty_combo.findText(difficulty)
                        if index >= 0:
                            self.difficulty_combo.setCurrentIndex(index)
                except ValueError:
                    pass
                continue

            if line.startswith('audio-'):
                audio_file_name = line[6:].strip()
                continue

            if line.startswith('speed-') or line.startswith('line-'):
                try:
                    if line.startswith('speed-'):
                        speed = float(line[6:])
                    else:
                        speed = float(line[5:])
                    self.speed_spin.setValue(speed)
                except ValueError:
                    pass
                continue

            # 解析音符
            note = self._parse_note_line(line, current_time_ms)
            if note:
                self.notes.append(note)

        # 尝试自动匹配音频文件
        if audio_file_name and audio_file_name.upper() != 'N':
            self._try_load_audio(audio_file_name, file_path)

        # 更新UI
        self._update_notes_text()
        self.preview_widget.set_notes(self.notes)

    def _parse_note_line(self, line: str, time_ms: int) -> Optional[Note]:
        """解析音符行"""
        # tab音符: tab-1
        if line.startswith('tab-'):
            parts = line[4:].split('-')
            try:
                track = int(parts[0]) - 1  # 转换为0-based
                if 0 <= track < 10:
                    return Note(time_ms, track, "normal")
            except ValueError:
                pass

        # hold音符: hold-1-500
        elif line.startswith('hold-'):
            parts = line[5:].split('-')
            try:
                track = int(parts[0]) - 1
                duration = int(parts[1]) if len(parts) > 1 else 0
                if 0 <= track < 10:
                    note = Note(time_ms, track, "hold")
                    note.duration = duration
                    return note
            except (ValueError, IndexError):
                pass

        # drag音符: drag-1
        elif line.startswith('drag-'):
            parts = line[5:].split('-')
            try:
                track = int(parts[0]) - 1
                if 0 <= track < 10:
                    return Note(time_ms, track, "drag")
            except ValueError:
                pass

        return None

    def _try_load_audio(self, audio_file_name: str, chart_file_path: str):
        """尝试加载音频文件"""
        chart_dir = Path(chart_file_path).parent
        audio_dir = chart_dir.parent / 'audio'

        # 可能的音频文件路径
        possible_paths = [
            audio_dir / audio_file_name,
            chart_dir / audio_file_name,
            Path(audio_file_name),
        ]

        # 尝试不同的扩展名
        extensions = ['', '.mp3', '.wav', '.ogg', '.flac']

        for path in possible_paths:
            for ext in extensions:
                full_path = path.with_suffix(ext) if ext else path
                if full_path.exists():
                    self.audio_file = str(full_path)
                    self.audio_file_label.setText(full_path.name)
                    self.media_player.setSource(QUrl.fromLocalFile(self.audio_file))
                    logger.info(f"自动加载音频文件: {self.audio_file}")
                    return

        # 如果没找到，只显示文件名
        self.audio_file_label.setText(f"未找到: {audio_file_name}")
        self.audio_file_label.setStyleSheet("color: #ff6666;")
        logger.warning(f"未找到音频文件: {audio_file_name}")

    def _write_chart(self, file_path: str):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"name-{self.name_edit.text()}\n")
                f.write(f"maker-{self.maker_edit.text()}\n")
                f.write(f"level-{self.level_spin.value()}-{self.difficulty_combo.currentText()}\n")
                if self.audio_file:
                    f.write(f"audio-{Path(self.audio_file).name}\n")
                else:
                    f.write("audio-N\n")
                f.write(f"speed-{self.speed_spin.value()}\n\n")

                sorted_notes = sorted(self.notes)
                current_time_str = ""

                for note in sorted_notes:
                    time_str = self._format_time(note.time_ms)
                    if time_str != current_time_str:
                        current_time_str = time_str
                        f.write(f"{time_str}\n")
                    f.write(f"{note.to_chart_line()}\n")

                f.write("\n&\n")

            QMessageBox.information(self, "成功", f"谱面已保存到:\n{file_path}")
            logger.info(f"谱面已保存到: {file_path}")
        except Exception as e:
            logger.error(f"保存谱面失败: {e}")
            QMessageBox.critical(self, "错误", f"保存失败:\n{str(e)}")

    def _format_time(self, ms: int) -> str:
        minutes = ms // 60000
        seconds = (ms % 60000) // 1000
        millis = ms % 1000
        return f"{minutes}:{seconds}:{millis:03d}"

    def _update_preview(self):
        if self.media_player:
            position = self.media_player.position()
            self.preview_widget.set_current_time(position)
            self.preview_widget.set_notes(self.notes)

    def _on_position_changed(self, position: int):
        duration = self.media_player.duration()
        if duration > 0:
            self.progress_slider.setValue(int(position * 1000 / duration))

        pos_str = self._format_time(position)
        dur_str = self._format_time(duration)
        self.time_label.setText(f"{pos_str} / {dur_str}")

    def _on_duration_changed(self, duration: int):
        pass

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("⏸ 暂停")
            self.play_btn.setStyleSheet("background-color: #666633; font-size: 14px;")
        else:
            self.play_btn.setText("▶ 播放")
            self.play_btn.setStyleSheet("background-color: #336633; font-size: 14px;")

    def _slider_pressed(self):
        self.media_player.pause()

    def _slider_released(self):
        value = self.progress_slider.value()
        duration = self.media_player.duration()
        if duration > 0:
            position = int(value * duration / 1000)
            self.media_player.setPosition(position)
        self.media_player.play()

    def _slider_moved(self, value):
        duration = self.media_player.duration()
        if duration > 0:
            position = int(value * duration / 1000)
            pos_str = self._format_time(position)
            dur_str = self._format_time(duration)
            self.time_label.setText(f"{pos_str} / {dur_str}")

    def _update_notes_text(self):
        sorted_notes = sorted(self.notes)
        text = ""
        for i, note in enumerate(sorted_notes[-50:], max(0, len(sorted_notes) - 50) + 1):
            time_str = self._format_time(note.time_ms)
            text += f"{i:3d}. [{time_str}] 轨道 {note.track + 1} ({TRACK_KEY_LABELS[note.track]})\n"
        self.notes_text.setText(text)
        self.notes_text.verticalScrollBar().setValue(self.notes_text.verticalScrollBar().maximum())

    def keyPressEvent(self, event: QKeyEvent):
        if not self.is_recording:
            super().keyPressEvent(event)
            return

        key = event.key()
        if key in TRACK_KEYS:
            track_index = TRACK_KEYS.index(key)
            position = self.media_player.position()
            note = Note(position, track_index, "normal")
            self.notes.append(note)
            self._update_notes_text()
            logger.debug(f"添加音符: 轨道 {track_index + 1}, 时间 {position}ms")

        super().keyPressEvent(event)

    def _on_track_right_clicked(self, track: int, time_ms: int):
        """处理轨道右击事件 - 放置新音符"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d3d;
                color: #ffffff;
                border: 1px solid #555566;
            }
            QMenu::item:selected {
                background-color: #444455;
            }
        """)

        # 添加音符类型选项
        action_tab = menu.addAction(f"🎵 放置 Tab 音符 (轨道 {track + 1})")
        action_hold = menu.addAction(f"🎹 放置 Hold 音符 (轨道 {track + 1})")
        action_drag = menu.addAction(f"✋ 放置 Drag 音符 (轨道 {track + 1})")

        action = menu.exec(self.cursor().pos())

        if action == action_tab:
            self._place_note(track, time_ms, "normal")
        elif action == action_hold:
            self._place_hold_note(track, time_ms)
        elif action == action_drag:
            self._place_note(track, time_ms, "drag")

    def _place_note(self, track: int, time_ms: int, note_type: str, duration: int = 0):
        """放置音符"""
        note = Note(time_ms, track, note_type)
        note.duration = duration
        self.notes.append(note)
        self._update_notes_text()
        self.preview_widget.set_notes(self.notes)
        logger.info(f"放置音符: 类型={note_type}, 轨道={track + 1}, 时间={time_ms}ms, 长度={duration}ms")

    def _place_hold_note(self, track: int, time_ms: int):
        """放置hold音符，弹出对话框设置长度"""
        duration, ok = QInputDialog.getInt(
            self, "设置Hold长度", "请输入Hold音符的持续时间(毫秒):",
            500, 50, 10000, 50
        )
        if ok:
            self._place_note(track, time_ms, "hold", duration)

    def _on_note_right_clicked(self, note: Note, note_index: int):
        """处理音符右击事件 - 编辑音符"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d3d;
                color: #ffffff;
                border: 1px solid #555566;
            }
            QMenu::item:selected {
                background-color: #444455;
            }
        """)

        # 显示当前音符信息
        info_action = menu.addAction(f"当前: {note.type.upper()} | 轨道 {note.track + 1} | {note.time_ms}ms")
        info_action.setEnabled(False)
        menu.addSeparator()

        # 更改类型
        change_menu = menu.addMenu("🔄 更改类型")
        action_to_tab = change_menu.addAction("更改为 Tab")
        action_to_hold = change_menu.addAction("更改为 Hold")
        action_to_drag = change_menu.addAction("更改为 Drag")

        # 编辑选项
        menu.addSeparator()
        action_edit_time = menu.addAction("⏱️ 修改时间")
        if note.type == "hold":
            action_edit_duration = menu.addAction("📏 修改Hold长度")
        action_delete = menu.addAction("🗑️ 删除音符")

        action = menu.exec(self.cursor().pos())

        if action == action_to_tab:
            self._change_note_type(note_index, "normal")
        elif action == action_to_hold:
            self._change_note_type_to_hold(note_index)
        elif action == action_to_drag:
            self._change_note_type(note_index, "drag")
        elif action == action_edit_time:
            self._edit_note_time(note_index)
        elif note.type == "hold" and action == action_edit_duration:
            self._edit_note_duration(note_index)
        elif action == action_delete:
            self._delete_note(note_index)

    def _change_note_type(self, note_index: int, new_type: str):
        """更改音符类型"""
        if 0 <= note_index < len(self.notes):
            old_type = self.notes[note_index].type
            self.notes[note_index].type = new_type
            if new_type != "hold":
                self.notes[note_index].duration = 0
            self._update_notes_text()
            self.preview_widget.set_notes(self.notes)
            logger.info(f"音符类型更改: {old_type} -> {new_type}")

    def _change_note_type_to_hold(self, note_index: int):
        """更改音符类型为hold，并设置长度"""
        duration, ok = QInputDialog.getInt(
            self, "设置Hold长度", "请输入Hold音符的持续时间(毫秒):",
            500, 50, 10000, 50
        )
        if ok:
            if 0 <= note_index < len(self.notes):
                old_type = self.notes[note_index].type
                self.notes[note_index].type = "hold"
                self.notes[note_index].duration = duration
                self._update_notes_text()
                self.preview_widget.set_notes(self.notes)
                logger.info(f"音符类型更改: {old_type} -> hold, 长度={duration}ms")

    def _edit_note_time(self, note_index: int):
        """修改音符时间"""
        if 0 <= note_index < len(self.notes):
            note = self.notes[note_index]
            new_time, ok = QInputDialog.getInt(
                self, "修改时间", "请输入新的时间(毫秒):",
                note.time_ms, 0, 9999999, 10
            )
            if ok:
                note.time_ms = new_time
                self._update_notes_text()
                self.preview_widget.set_notes(self.notes)
                logger.info(f"音符时间修改: {note.time_ms}ms")

    def _edit_note_duration(self, note_index: int):
        """修改hold音符长度"""
        if 0 <= note_index < len(self.notes):
            note = self.notes[note_index]
            new_duration, ok = QInputDialog.getInt(
                self, "修改Hold长度", "请输入新的持续时间(毫秒):",
                note.duration, 50, 10000, 50
            )
            if ok:
                note.duration = new_duration
                self._update_notes_text()
                self.preview_widget.set_notes(self.notes)
                logger.info(f"Hold音符长度修改: {new_duration}ms")

    def _delete_note(self, note_index: int):
        """删除音符"""
        if 0 <= note_index < len(self.notes):
            note = self.notes.pop(note_index)
            self._update_notes_text()
            self.preview_widget.set_notes(self.notes)
            logger.info(f"删除音符: 类型={note.type}, 轨道={note.track + 1}, 时间={note.time_ms}ms")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = ChartEditorWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
