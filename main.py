import os
import sys
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QDialog,
    QComboBox,
    QCheckBox,
    QMenu,
    QSystemTrayIcon,
    QSpinBox,
)
from PySide6.QtCore import Qt, QTime, QTimer, QStandardPaths, QLockFile, QRect

# Controlled debug logging. Set the COMPANION_DEBUG environment variable
# to a non-empty value to trace timer scheduling/firing; otherwise the
# app runs silently just like before.
DEBUG = bool(os.environ.get("COMPANION_DEBUG", ""))


def _debug(msg):
    if DEBUG:
        print(f"[companion] {msg}", flush=True)


def _today_str():
    return datetime.now().strftime("%Y-%m-%d")
from PySide6.QtGui import (
    QPixmap,
    QFont,
    QPainter,
    QColor,
    QPen,
    QIcon,
)

DEFAULT_SETTINGS = {
    "enabled": True,
    "reminder_mode": "three_times",
    "delay_minutes": 5,
    "work_interval_minutes": 30,
    "break_duration_minutes": 5,
    "onboarding_completed": False,
    # Optional scheduled start (ISO local datetime) chosen by the user;
    # empty means no schedule is pending.
    "scheduled_start": "",
    # Date (YYYY-MM-DD) on which the user said "Not today" to the
    # start-work prompt; empty means the prompt is fully active.
    "prompt_dismissed_on": "",
    # Rolling per-day session counter, reset whenever sessions_date
    # differs from the current date.
    "sessions_today": 0,
    "sessions_date": "",
}

CHARACTER_IMAGES = {
    "standing": "character_standing.png",
    "walking_in": "character_walking_in.png",
    "thinking": "character_thinking.png",
    "happy_thumbs_up": "character_happy_thumbs_up.png",
    "happy_walk_away": "character_happy_walk_away.png",
    "sad_tears": "character_sad_tears.png",
    "angry_walk_away": "character_angry_walk_away.png",
    "peek": "character_peek.png",
    "angry_walk_away_2": "character_angry_walk_away_2.png",
    "happy_return": "character_happy_return.png",
    "frustrated": "character_frustrated.png",
    "satisfied": "character_satisfied.png",
    "excited_waving": "character_excited_waving.png",
    "concerned": "character_concerned.png",
    "energetic_encouraging": "character_energetic_encouraging.png",
    "happy_proud": "character_happy_proud.png",
    "pleading": "character_pleading.png",
    "dramatic_goodbye": "character_dramatic_goodbye.png",
    "refreshed_happy": "character_refreshed_happy.png",
}

# Expected future sound effects. Existing files simply play; missing
# files are skipped silently so the app never crashes without sounds.
SOUND_NAMES = [
    "reminder.wav",
    "break_start.wav",
    "break_over.wav",
    "later.wav",
    "stop.wav",
]

# Subtle idle bounces for the expressive poses. Each entry describes a
# gentle repeating up/down movement (in pixels) and the frame cadence
# (in ms). Poses without an entry simply stay perfectly still, keeping
# the existing pixel-art look intact.
IDLE_ANIMATIONS = {
    "excited_waving": {"px": 2, "every": 120},
    "concerned": {"px": 1, "every": 200},
    "energetic_encouraging": {"px": 2, "every": 110},
    "happy_proud": {"px": 2, "every": 130},
    "pleading": {"px": 1, "every": 190},
    "dramatic_goodbye": {"px": 1, "every": 180},
    "refreshed_happy": {"px": 2, "every": 120},
}

REMINDER_MESSAGES = {
    "first": {
        "message": "You've been at it for a while! 👀\nHow about a little break?",
        "okay_text": "Okay 👍",
        "later_text": "Later 😭",
    },
    "second": {
        "message": "Bro... your eyes need a break. 😭\nSeriously. Go rest!",
        "yes_text": "Yes 😭",
        "no_text": "Noo 😏",
    },
}

CHARACTER_DIALOGUE = {
    "greeting": "Hey! 👋",
    "second_greeting": "Bro... 👁️👁️",
    "accept": "That's the spirit! 😌\nYour eyes will thank you.",
    "first_refusal": "Alright, I'll give you a little more time... 👀",
    "second_accept": "That's what I thought. 😌",
    "second_refusal": "Okay, suit yourself. 😏\nBut I'll be back. 👀",
    "break_done": "Break complete! Ready for another round? 🚀",
    "break_almost": "Almost ready to get back at it 💪",
    "returning_to_work": "Alright!\nBack to work. 💪",
    "onboarding_intro": "Hey! I'm your Desktop Companion! 👋\nI'll remind you to take regular breaks\nwhile you're working.",
    "onboarding_setup": "Let's set up your schedule! 💪",
    "onboarding_complete": "Perfect! I'll remind you after {minutes} minutes. 🙂",
    "stop": "Okay! I'll stop bothering you. 😌",
    "start_work_prompt": "Ready to work? 👋",
    "start_work_yes": "That's the spirit!\nLet's do this. 💪",
    "work_duration_question": "How long do you want to work? 💪",
    "schedule_confirm": "Got it! I'll come back at {time} 🕒",
    "schedule_past": "That time already passed!\nPick a future time. 🙂",
    "scheduled_prompt": "It's time to work! 💪",
    "scheduled_delayed": "Okay, take your time!\nI'll be right here. 🙂",
    "resting_prompt": "I'll be here when you're ready 🙂",
    "schedule_waiting": "I'll remind you when it's time to work 🙂",
}

# Short friendly flavour messages shown while a work session runs. One
# message is picked per session and kept stable (never re-rendered every
# second) so the dialogue reads like a token of encouragement, not a
# counter. The same quote stays until the next work interval begins.
WORKING_MESSAGES = [
    "You've got this, dude 💻",
    "Focus mode activated 😎",
    "Keep going — you're doing great.",
    "I'm counting your work time ⏱️",
]

# Chilled messages shown while the companion is on a break. Picked once
# per break and kept stable for the whole countdown.
BREAK_MESSAGES = [
    "Relax a bit, dude 😌",
    "Stretch your shoulders a little.",
    "Look away from the screen 👀",
    "You earned this break.",
    "Deep breaths. In, out. 🌬️",
]

# How long the companion lingers after showing the live working/break
# status (a manual "Show Companion" while a session is already running,
# or the start of a break) before it walks away and hides. The session
# timers keep running untouched in the background the whole time.
PEEK_AUTO_HIDE_MS = 5000

# Startup introduction sequence shown after the companion walks in.
# Each entry is (message, pause_ms): the message is shown, then after
# pause_ms the next message takes its place. The final entry's pause is
# followed by clearing the bubble and settling into the standing/idle
# state. This is purely additive and never touches the reminder timer.
#
# Kept to one short line so the character introduces itself quickly and
# then hands straight over to the start-work prompt ("Ready to work? 👋"),
# which offers the "Start now" / "Choose a time" choices.
STARTUP_INTRO = [
    (
        "Hey! I'm your Desktop Companion 👋\nI'll remind you to take regular breaks.",
        2200,
    ),
]


# ============================================================
# SOUND
# ============================================================

# Looked up lazily so a missing Qt multimedia backend can never crash
# the app. Kept at module scope so it is only initialized once.
_sound_player = None


def _assets_dir():
    return (
        Path(sys._MEIPASS)
        if getattr(sys, "frozen", False)
        else Path(__file__).parent
    )


def play_sound(sound_name):
    """Play a short sound effect located in assets/sounds/.

    Safely does nothing if the sound file (or Qt's multimedia backend)
    is unavailable, so the app never crashes because of audio.
    """
    global _sound_player

    if not sound_name:
        return

    try:
        from PySide6.QtMultimedia import (
            QSoundEffect,
        )
        from PySide6.QtCore import (
            QUrl,
        )
    except Exception:
        return

    if _sound_player is None:
        _sound_player = QSoundEffect()

    path = (
        _assets_dir()
        / "assets"
        / "sounds"
        / sound_name
    )

    if not path.exists():
        return

    try:
        _sound_player.setSource(
            QUrl.fromLocalFile(
                str(path)
            )
        )
        _sound_player.play()
    except Exception:
        pass


# ============================================================
# PIXEL CHOICE
# ============================================================

class PixelChoice(QPushButton):

    def __init__(self, text, parent=None):
        super().__init__(text, parent)

        self.normal_text = text

        self.setFixedSize(95, 24)

        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #4A3728;
                border: none;
                padding: 0px;
                margin: 0px;
                font-size: 12px;
                font-weight: bold;
            }

            QPushButton:hover {
                background: transparent;
                color: #70472E;
            }

            QPushButton:pressed {
                background: transparent;
                color: #8B5E3C;
            }
        """)

        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, event):
        self.setText("▶ " + self.normal_text)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setText(self.normal_text)
        super().leaveEvent(event)

# ============================================================
# PIXEL MESSAGE LABEL
# ============================================================

class MessageLabel(QLabel):

    def __init__(self, text, parent=None):
        super().__init__(text, parent)

        self.setAlignment(
            Qt.AlignCenter | Qt.AlignVCenter
        )

        # Monospace font gives a more retro feel.
        font = QFont(
            "Courier New"
        )

        font.setPointSize(10)
        font.setBold(True)

        self.setFont(
            font
        )

        self.setStyleSheet("""
            QLabel {
                background: transparent;
                color: #4A3728;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)

        # Wrap long text instead of clipping it; the vertically-centered
        # text area keeps the same visual style, only taller when needed.
        self.setWordWrap(True)

        # Fixed width matched to the dialogue panel; the height grows
        # dynamically to fit wrapped lines (see _needed_height).
        self.setFixedWidth(300)

        self.setMinimumHeight(62)

        self._resize_callback = None

    def setText(self, text):
        super().setText(text)

        if self._resize_callback is not None:
            self._resize_callback(
                self._needed_height()
            )

    def _needed_height(self):

        # Height required to show the current text wrapped at the label
        # width, never smaller than the original single-height area so
        # short messages keep their existing look.
        width = self.width()

        if width <= 0:
            width = 300

        metrics = self.fontMetrics()

        rect = metrics.boundingRect(
            QRect(
                0,
                0,
                width,
                10000
            ),
            int(
                Qt.TextWordWrap
            ),
            self.text()
        )

        return max(
            62,
            rect.height() + 8
        )

# ============================================================
# PIXEL DIALOGUE PANEL
# ============================================================

class DialoguePanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAttribute(
            Qt.WA_TranslucentBackground
        )

        # Compact dialogue box
        self.setFixedSize(322, 132)

        # Small dismiss ("✕") button. Shown only on the resting prompt so
        # dismissing cleanly hides the whole companion; the frameless
        # window's other prompts (start-now, reminder, schedule) never
        # expose it.
        self.close_button = QPushButton(
            "✕",
            self
        )

        self.close_button.setFixedSize(
            24,
            22
        )

        self.close_button.setCursor(
            Qt.PointingHandCursor
        )

        self.close_button.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #6B4F38;
                border: none;
                padding: 0px;
                margin: 0px;
                font-family: 'Courier New';
                font-size: 12px;
                font-weight: bold;
            }

            QPushButton:hover {
                color: #4A3728;
            }

            QPushButton:pressed {
                color: #3A2A1E;
            }
        """)

        self.close_button.hide()

    def paintEvent(self, event):

        painter = QPainter(self)

        try:

            # IMPORTANT:
            # Pixel art should NOT be anti-aliased.
            painter.setRenderHint(
                QPainter.Antialiasing,
                False
            )

            w = self.width()
            h = self.height()

            # ------------------------------------------------
            # COLORS
            # ------------------------------------------------

            outer_color = QColor("#5A402F")
            border_color = QColor("#8A6245")
            inner_border = QColor("#C49A6C")
            background_color = QColor("#E8D3B5")
            shadow_color = QColor(60, 42, 30, 90)

            # ------------------------------------------------
            # GEOMETRY
            # ------------------------------------------------

            corner = 6
            border = 3

            divider_y = 76

            # ------------------------------------------------
            # SHADOW
            # ------------------------------------------------

            painter.setPen(Qt.NoPen)
            painter.setBrush(shadow_color)

            painter.drawRect(
                5,
                5,
                w - 1,
                h - 8
            )

            # ------------------------------------------------
            # OUTER PIXEL FRAME
            # ------------------------------------------------

            painter.setBrush(outer_color)

            painter.drawRect(
                0,
                0,
                w - 7,
                h - 12
            )

            # ------------------------------------------------
            # PIXEL CORNER CUTOUTS
            # ------------------------------------------------

            painter.setBrush(Qt.transparent)

            painter.setPen(
                QPen(
                    outer_color,
                    1
                )
            )

            # Top-left
            painter.drawPoint(0, 0)

            # ------------------------------------------------
            # MAIN INNER BORDER
            # ------------------------------------------------

            painter.setPen(Qt.NoPen)
            painter.setBrush(border_color)

            painter.drawRect(
                border,
                border,
                w - 13,
                h - 18
            )

            # ------------------------------------------------
            # INNER HIGHLIGHT
            # ------------------------------------------------

            painter.setBrush(inner_border)

            painter.drawRect(
                border + 2,
                border + 2,
                w - 17,
                h - 22
            )

            # ------------------------------------------------
            # DIALOGUE BACKGROUND
            # ------------------------------------------------

            painter.setBrush(background_color)

            painter.drawRect(
                border + 4,
                border + 4,
                w - 21,
                h - 26
            )

            # ------------------------------------------------
            # PIXEL CORNER DETAILS
            # ------------------------------------------------

            painter.setBrush(border_color)

            # top-left pixel accent
            painter.drawRect(
                8,
                5,
                5,
                3
            )

            # top-right pixel accent
            painter.drawRect(
                w - 22,
                5,
                5,
                3
            )

            # bottom-left accent
            painter.drawRect(
                8,
                h - 18,
                5,
                3
            )

            # bottom-right accent
            painter.drawRect(
                w - 22,
                h - 18,
                5,
                3
            )

        finally:
            painter.end()


# ============================================================
# STATUS PANEL
# ============================================================

class StatusPanel(QWidget):

    # Pixel-styled highlight box under the dialogue panel that shows the
    # current work/break status, an elapsed/countdown timer and the
    # per-day session count. A filled, bordered box with a bold, dark
    # label keeps the text readable on any background/theme and matches
    # the pixel-art look without ever drawing attention away from the
    # character.
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAttribute(
            Qt.WA_TranslucentBackground
        )

        layout = QVBoxLayout(
            self
        )

        layout.setContentsMargins(
            10,
            2,
            10,
            4
        )

        layout.setSpacing(
            0
        )

        self.label = QLabel(
            ""
        )

        self.label.setAlignment(
            Qt.AlignCenter
        )

        font = QFont(
            "Courier New"
        )

        font.setPointSize(10)
        font.setBold(True)

        self.label.setFont(
            font
        )

        # Dark brown text on the light cream box: high contrast in both
        # light and dark system themes.
        self.label.setStyleSheet("""
            QLabel {
                background: transparent;
                color: #3A2A1E;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)

        layout.addWidget(
            self.label
        )

        self.setFixedHeight(
            28
        )

    def set_text(self, text):
        self.label.setText(
            text
        )

    def paintEvent(self, event):

        painter = QPainter(self)

        try:

            # Pixel art should NOT be anti-aliased.
            painter.setRenderHint(
                QPainter.Antialiasing,
                False
            )

            w = self.width()
            h = self.height()

            shadow_color = QColor(60, 42, 30, 70)

            painter.setPen(Qt.NoPen)
            painter.setBrush(shadow_color)

            painter.drawRect(
                3,
                3,
                w - 1,
                h - 5
            )

            painter.setBrush(QColor("#8A6245"))

            painter.drawRect(
                0,
                0,
                w - 3,
                h - 4
            )

            painter.setBrush(QColor("#F0DDBE"))

            painter.drawRect(
                2,
                2,
                w - 7,
                h - 8
            )

        finally:
            painter.end()


# ============================================================
# SETTINGS PERSISTENCE
# ============================================================

def settings_path():

    # Store user settings in an OS-appropriate, user-writable config
    # directory (e.g. %APPDATA%\\DesktopCompanion on Windows) rather than
    # beside the executable or inside assets. This stays writable even
    # when the app is packaged as an .exe installed in a read-only place.
    config_dir = (
        QStandardPaths
        .writableLocation(
            QStandardPaths.AppConfigLocation
        )
    )

    if not config_dir:
        config_dir = (
            str(Path.home())
        )

    base_dir = Path(
        config_dir
    )

    try:
        base_dir.mkdir(
            parents=True,
            exist_ok=True
        )
    except Exception:
        pass

    return (
        base_dir
        / "settings.json"
    )


def load_settings():

    result = dict(
        DEFAULT_SETTINGS
    )

    path = settings_path()

    try:

        if path.exists():

            with open(
                path,
                "r",
                encoding="utf-8"
            ) as f:
                data = json.load(f)

            if isinstance(
                data,
                dict
            ):
                for key in (
                    "enabled",
                    "reminder_mode",
                    "delay_minutes",
                    "work_interval_minutes",
                    "break_duration_minutes",
                    "onboarding_completed",
                    "scheduled_start",
                    "prompt_dismissed_on",
                    "sessions_today",
                    "sessions_date",
                ):
                    if key in data:
                        result[key] = data[key]

    except Exception:
        pass

    return result


def save_settings(settings):

    try:

        path = settings_path()

        with open(
            path,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                settings,
                f,
                indent=4
            )

    except Exception:
        pass


# ============================================================
# SETTINGS WINDOW
# ============================================================

class SettingsWindow(QDialog):

    MODE_OPTIONS = [
        ("three_times", "Remind me three times"),
        ("keep_reminding", "Keep reminding me"),
        ("stop_after_one", "Stop after one reminder"),
    ]

    def __init__(
        self,
        settings,
        parent=None
    ):
        super().__init__(parent)

        self.setWindowTitle(
            "Desktop Companion Settings"
        )

        self.setModal(
            True
        )

        self.setFixedWidth(
            330
        )

        self.setStyleSheet("""
            QDialog {
                background: #E8D3B5;
            }
            QLabel {
                color: #4A3728;
                font-family: 'Courier New';
                font-weight: bold;
            }
            QCheckBox {
                color: #4A3728;
                font-family: 'Courier New';
                font-weight: bold;
            }
            QComboBox {
                background: #F4E3C8;
                color: #4A3728;
                border: 2px solid #8A6245;
                font-family: 'Courier New';
                font-weight: bold;
                padding: 2px;
            }
            QComboBox QAbstractItemView {
                background: #F4E3C8;
                color: #4A3728;
                selection-background-color: #C49A6C;
                selection-color: #3A2A1E;
            }
            QSpinBox {
                background: #F4E3C8;
                color: #4A3728;
                border: 2px solid #8A6245;
                font-family: 'Courier New';
                font-weight: bold;
                padding: 2px;
            }
            QPushButton {
                background: #C49A6C;
                color: #3A2A1E;
                border: 2px solid #5A402F;
                font-family: 'Courier New';
                font-weight: bold;
                padding: 5px 16px;
            }
            QPushButton:hover {
                background: #D3AC7E;
            }
            QPushButton:pressed {
                background: #B0875E;
            }
        """)

        layout = QVBoxLayout()

        title = QLabel(
            "DESKTOP COMPANION"
        )

        title.setAlignment(
            Qt.AlignCenter
        )

        title.setStyleSheet(
            "font-size: 16px;"
        )

        subtitle = QLabel(
            "SETTINGS"
        )

        subtitle.setAlignment(
            Qt.AlignCenter
        )

        subtitle.setStyleSheet(
            "font-size: 12px;"
        )

        layout.addWidget(
            title
        )

        layout.addWidget(
            subtitle
        )

        layout.addSpacing(
            10
        )

        # -----------------------------
        # ENABLE REMINDERS
        # -----------------------------

        self.enable_check = QCheckBox(
            "Enable reminders"
        )

        self.enable_check.setChecked(
            bool(
                settings.get(
                    "enabled",
                    True
                )
            )
        )

        layout.addWidget(
            self.enable_check
        )

        layout.addSpacing(
            8
        )

        # -----------------------------
        # WORK INTERVAL
        # -----------------------------

        work_label = QLabel(
            "How long should you work\nbefore I remind you?"
        )

        self.work_spin = QSpinBox()

        # Positive minutes only; zero/negative are invalid.
        self.work_spin.setRange(
            1,
            1440
        )

        self.work_spin.setSuffix(
            " min"
        )

        self.work_spin.setValue(
            int(
                settings.get(
                    "work_interval_minutes",
                    30
                )
            )
        )

        layout.addWidget(
            work_label
        )

        layout.addWidget(
            self.work_spin
        )

        layout.addSpacing(
            8
        )

        # -----------------------------
        # BREAK DURATION
        # -----------------------------

        break_label = QLabel(
            "How long should your break be?"
        )

        self.break_spin = QSpinBox()

        # Positive minutes only; zero/negative are invalid.
        self.break_spin.setRange(
            1,
            1440
        )

        self.break_spin.setSuffix(
            " min"
        )

        self.break_spin.setValue(
            int(
                settings.get(
                    "break_duration_minutes",
                    5
                )
            )
        )

        layout.addWidget(
            break_label
        )

        layout.addWidget(
            self.break_spin
        )

        layout.addSpacing(
            8
        )

        # -----------------------------
        # REMINDER BEHAVIOR
        # -----------------------------

        behavior_label = QLabel(
            "How often should I remind you\nabout a break?"
        )

        self.mode_combo = QComboBox()

        for value, label in self.MODE_OPTIONS:
            self.mode_combo.addItem(
                label,
                value
            )

        current_mode = (
            settings.get(
                "reminder_mode",
                "three_times"
            )
        )

        idx = self.mode_combo.findData(
            current_mode
        )

        if idx >= 0:
            self.mode_combo.setCurrentIndex(
                idx
            )

        layout.addWidget(
            behavior_label
        )

        layout.addWidget(
            self.mode_combo
        )

        layout.addSpacing(
            8
        )

        # -----------------------------
        # LATER DELAY
        # -----------------------------

        delay_label = QLabel(
            'If I click "Later", remind me again after'
        )

        self.delay_spin = QSpinBox()

        # Positive minutes only; zero/negative are invalid.
        self.delay_spin.setRange(
            1,
            1440
        )

        self.delay_spin.setSuffix(
            " min"
        )

        self.delay_spin.setValue(
            int(
                settings.get(
                    "delay_minutes",
                    5
                )
            )
        )

        layout.addWidget(
            delay_label
        )

        layout.addWidget(
            self.delay_spin
        )

        layout.addSpacing(
            16
        )

        # -----------------------------
        # BUTTONS
        # -----------------------------

        button_row = QHBoxLayout()

        button_row.addStretch()

        save_button = QPushButton(
            "Save"
        )

        save_button.clicked.connect(
            self.accept
        )

        cancel_button = QPushButton(
            "Cancel"
        )

        cancel_button.clicked.connect(
            self.reject
        )

        button_row.addWidget(
            save_button
        )

        button_row.addWidget(
            cancel_button
        )

        button_row.addStretch()

        layout.addLayout(
            button_row
        )

        self.setLayout(
            layout
        )

    def values(self):

        return {
            "enabled": (
                self.enable_check.isChecked()
            ),
            "reminder_mode": (
                self.mode_combo.currentData()
            ),
            "delay_minutes": int(
                self.delay_spin.value()
            ),
            "work_interval_minutes": int(
                self.work_spin.value()
            ),
            "break_duration_minutes": int(
                self.break_spin.value()
            ),
        }


# ============================================================
# SCHEDULE TIME DIALOG
# ============================================================

class ClockTimePicker(QWidget):
    """One-click analog clock used to choose a start time.

    There is no typed or spun number input: clicking the OUTER ring snaps
    to the nearest hour (labels 1-12), and clicking the INNER disc snaps
    to the nearest five-minute mark (0,5,...55). Both hands update live so
    the chosen time is always visible. Pure clock-time choice; the caller
    maps it onto the current day (and rejects past times).
    """

    def __init__(self, time=None, parent=None):
        super().__init__(parent)

        self.setFixedSize(200, 200)

        self.setCursor(Qt.PointingHandCursor)

        if time is not None:
            self._time = QTime(time.hour(), time.minute(), 0)
        else:
            now = QTime.currentTime()
            self._time = QTime(now.hour(), now.minute(), 0)

        # (zone, index) under the mouse: ("hour", 0..11) or ("minute", 0..11).
        self._hover = None

        # Optional callback fired whenever the chosen time changes.
        self.on_change = None

    def time(self):
        return self._time

    def set_time(self, t):
        self._time = QTime(t.hour(), t.minute(), 0)

        self.update()

        if self.on_change is not None:
            self.on_change(self._time)

    def _pick(self, pos):
        """Map a widget position to (zone, index) or None when over the hub."""
        cx, cy = self.width() / 2.0, self.height() / 2.0
        R = min(self.width(), self.height()) / 2.0 - 4

        dx = pos.x() - cx
        dy = pos.y() - cy

        r = math.hypot(dx, dy)

        if r < R * 0.15:
            return None

        deg = (math.degrees(math.atan2(dx, -dy))) % 360

        if r >= R * 0.62:
            # Outer ring: nearest hour.
            index = int(round(deg / 30.0)) % 12
            return ("hour", index)

        # Inner disc: nearest five-minute mark.
        minutes = int(round(deg / 6.0)) % 60
        index = int(round(minutes / 5.0)) % 12
        return ("minute", index)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        choice = self._pick(event.position())

        if choice is None or choice[0] is None:
            return

        zone, index = choice

        hour = self._time.hour()
        minute = self._time.minute()

        if zone == "hour":
            hour = index if index else 12
        else:
            minute = index * 5

        self.set_time(QTime(hour, minute))

    def mouseMoveEvent(self, event):
        choice = self._pick(event.position())

        if choice is None or choice[0] is None:
            if self._hover is not None:
                self._hover = None
                self.update()
            return

        if choice != self._hover:
            self._hover = choice
            self.update()

    def leaveEvent(self, event):
        if self._hover is not None:
            self._hover = None
            self.update()

    def _endpoint(self, length, angle_deg):
        rad = math.radians(angle_deg)
        return (
            self._cx + length * math.sin(rad),
            self._cy - length * math.cos(rad),
        )

    def paintEvent(self, event):
        painter = QPainter(self)

        painter.setRenderHint(QPainter.Antialiasing, False)

        self._cx = self.width() / 2.0
        self._cy = self.height() / 2.0
        R = min(self.width(), self.height()) / 2.0 - 4

        # Outer rim.
        painter.setPen(QPen(QColor("#5A402F"), 2))
        painter.setBrush(QColor("#F4E3C8"))
        painter.drawEllipse(QRect(int(self._cx - R), int(self._cy - R), int(R * 2), int(R * 2)))

        # Inner face.
        painter.setPen(QPen(QColor("#8A6245"), 1))
        painter.setBrush(QColor("#F0DDBE"))
        painter.drawEllipse(QRect(int(self._cx - R + 4), int(self._cy - R + 4), int((R - 4) * 2), int((R - 4) * 2)))

        painter.setPen(QPen(QColor("#C4A57E"), 1, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRect(int(self._cx - R * 0.62), int(self._cy - R * 0.62), int(R * 1.24), int(R * 1.24)))

        def draw_hand(angle_deg, length, color, width):
            x1, y1 = self._endpoint(0, angle_deg)
            x2, y2 = self._endpoint(length, angle_deg)
            painter.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Minute ticks (five-minute steps) inside the inner disc.
        for i in range(12):
            angle = i * 30
            hovered = self._hover == ("minute", i)
            painter.setPen(QPen(QColor("#9A7B5C"), 3 if hovered else 2))
            x1, y1 = self._endpoint(R * 0.54, angle)
            x2, y2 = self._endpoint(R * 0.62, angle)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Hour ticks on the outer ring.
        for i in range(12):
            angle = i * 30
            hovered = self._hover == ("hour", i)
            painter.setPen(QPen(QColor("#3A2A1E") if hovered else QColor("#8A6245"), 3))
            x1, y1 = self._endpoint(R * 0.72, angle)
            x2, y2 = self._endpoint(R - 2, angle)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Hour labels 1-12.
        painter.setFont(QFont("Courier New", 9, QFont.Bold))
        painter.setPen(QColor("#3A2A1E"))
        for i in range(12):
            angle = i * 30
            label_x, label_y = self._endpoint(R * 0.84, angle)
            painter.drawText(int(label_x) - 7, int(label_y) + 4, str(i if i else 12))

        # Clock hands.
        hour_angle = (self._time.hour() % 12) * 30 + self._time.minute() * 0.5
        minute_angle = self._time.minute() * 6
        draw_hand(hour_angle, R * 0.42, "#8A6245", 3)
        draw_hand(minute_angle, R * 0.66, "#5A402F", 2)

        # Center hub.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#5A402F"))
        painter.drawEllipse(QRect(int(self._cx - 4), int(self._cy - 4), 8, 8))


class ScheduleTimeDialog(QDialog):

    # Small time picker used to schedule when the companion should walk
    # in and ask the user to start working. Pure clock-time choice; the
    # caller maps it onto the current day (and rejects past times).
    def __init__(
        self,
        parent=None
    ):
        super().__init__(parent)

        self.setWindowTitle(
            "Schedule a start time"
        )

        self.setModal(
            True
        )

        # Closed properly after accept/reject so the picker never lingers
        # behind the next dialogue.
        self.setAttribute(
            Qt.WA_DeleteOnClose
        )

        self.setFixedWidth(
            300
        )

        self.setStyleSheet("""
            QDialog {
                background: #E8D3B5;
            }
            QLabel {
                color: #4A3728;
                font-family: 'Courier New';
                font-weight: bold;
            }
            QPushButton {
                background: #C49A6C;
                color: #3A2A1E;
                border: 2px solid #5A402F;
                font-family: 'Courier New';
                font-weight: bold;
                padding: 5px 16px;
            }
            QPushButton:hover {
                background: #D3AC7E;
            }
            QPushButton:pressed {
                background: #B0875E;
            }
        """)

        layout = QVBoxLayout()

        title = QLabel(
            "WHEN SHOULD I COME BACK?"
        )

        title.setAlignment(
            Qt.AlignCenter
        )

        title.setStyleSheet(
            "font-size: 13px;"
        )

        layout.addWidget(
            title
        )

        layout.addSpacing(
            8
        )

        # Default to the current time so the picker is immediately clear;
        # the user clicks the clock to move to the time they want to start.
        default_time = (
            QTime.currentTime()
        )

        self.clock = ClockTimePicker(
            default_time
        )

        self.current_label = QLabel(
            "Selected: " + default_time.toString("h:mm AP")
        )

        self.current_label.setAlignment(
            Qt.AlignCenter
        )

        self.clock.on_change = self._on_clock_change

        hint = QLabel(
            "Tip: outer ring = hour · inner disc = minutes (5-min steps)"
        )

        hint.setAlignment(
            Qt.AlignCenter
        )

        hint.setStyleSheet(
            "font-size: 10px; color: #8A6245; font-weight: normal;"
        )

        layout.addWidget(
            self.clock,
            0,
            Qt.AlignCenter
        )

        layout.addSpacing(
            6
        )

        layout.addWidget(
            self.current_label
        )

        layout.addWidget(
            hint
        )

        layout.addSpacing(
            12
        )

        button_row = QHBoxLayout()

        button_row.addStretch()

        now_button = QPushButton(
            "Now"
        )

        now_button.setToolTip(
            "Reset to the current time"
        )

        now_button.clicked.connect(
            self._reset_to_now
        )

        save_button = QPushButton(
            "Schedule"
        )

        save_button.clicked.connect(
            self.accept
        )

        cancel_button = QPushButton(
            "Cancel"
        )

        cancel_button.clicked.connect(
            self.reject
        )

        button_row.addWidget(
            now_button
        )

        button_row.addSpacing(
            6
        )

        button_row.addWidget(
            save_button
        )

        button_row.addWidget(
            cancel_button
        )

        button_row.addStretch()

        layout.addLayout(
            button_row
        )

        self.setLayout(
            layout
        )

    def _on_clock_change(self, t):
        self.current_label.setText(
            "Selected: " + t.toString("h:mm AP")
        )

    def _reset_to_now(self):
        self.clock.set_time(
            QTime.currentTime()
        )

    def selected_time(self):
        return self.clock.time()


# ============================================================
# WORK DURATION DIALOG
# ============================================================

class WorkDurationDialog(QDialog):

    # Beginner-friendly "How long do you want to work?" selector. Simple
    # preset buttons fill the spin box; the big confirm button starts the
    # work session. Same pixel-art styling as the rest of the app.
    PRESETS = [
        15,
        25,
        30,
        45,
        60,
    ]

    def __init__(
        self,
        settings,
        parent=None
    ):
        super().__init__(parent)

        self.setWindowTitle(
            "How long do you want to work?"
        )

        self.setModal(
            True
        )

        self.setFixedWidth(
            330
        )

        self.setStyleSheet("""
            QDialog {
                background: #E8D3B5;
            }
            QLabel {
                color: #4A3728;
                font-family: 'Courier New';
                font-weight: bold;
            }
            QSpinBox {
                background: #F4E3C8;
                color: #4A3728;
                border: 2px solid #8A6245;
                font-family: 'Courier New';
                font-weight: bold;
                padding: 4px;
                font-size: 14px;
            }
            QPushButton {
                background: #C49A6C;
                color: #3A2A1E;
                border: 2px solid #5A402F;
                font-family: 'Courier New';
                font-weight: bold;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background: #D3AC7E;
            }
            QPushButton:pressed {
                background: #B0875E;
            }
        """)

        layout = QVBoxLayout()

        title = QLabel(
            "HOW LONG DO YOU WANT\nTO WORK? 💪"
        )

        title.setAlignment(
            Qt.AlignCenter
        )

        title.setStyleSheet(
            "font-size: 14px;"
        )

        layout.addWidget(
            title
        )

        layout.addSpacing(
            10
        )

        # ------------------------------------------------
        # PRESET CHIPS
        # ------------------------------------------------

        preset_row = QHBoxLayout()

        preset_row.setSpacing(
            6
        )

        default_minutes = int(
            settings.get(
                "work_interval_minutes",
                30
            )
        )

        for minutes in self.PRESETS:

            preset_button = QPushButton(
                f"{minutes}m"
            )

            preset_button.setFixedSize(
                54,
                30
            )

            preset_button.clicked.connect(
                lambda checked,
                value=minutes: self.spin.setValue(
                    value
                )
            )

            preset_row.addWidget(
                preset_button
            )

        layout.addLayout(
            preset_row
        )

        layout.addSpacing(
            12
        )

        # ------------------------------------------------
        # CUSTOM MINUTES SPIN
        # ------------------------------------------------

        spin_row = QHBoxLayout()

        spin_row.addStretch()

        spin_label = QLabel(
            "Minutes:"
        )

        spin_row.addWidget(
            spin_label
        )

        self.spin = QSpinBox()

        self.spin.setRange(
            1,
            1440
        )

        self.spin.setSuffix(
            " min"
        )

        self.spin.setValue(
            default_minutes
        )

        spin_row.addWidget(
            self.spin
        )

        spin_row.addStretch()

        layout.addLayout(
            spin_row
        )

        layout.addSpacing(
            16
        )

        # ------------------------------------------------
        # BUTTONS
        # ------------------------------------------------

        button_row = QHBoxLayout()

        button_row.addStretch()

        start_button = QPushButton(
            "Start 💪"
        )

        start_button.setFixedSize(
            110,
            34
        )

        start_button.clicked.connect(
            self.accept
        )

        cancel_button = QPushButton(
            "Cancel"
        )

        cancel_button.clicked.connect(
            self.reject
        )

        button_row.addWidget(
            start_button
        )

        button_row.addWidget(
            cancel_button
        )

        button_row.addStretch()

        layout.addLayout(
            button_row
        )

        self.setLayout(
            layout
        )

    def selected_minutes(self):
        return int(
            self.spin.value()
        )


# ============================================================
# COMPANION
# ============================================================

class Companion(QWidget):

    def __init__(self):

        super().__init__()

        # Load persisted user settings.
        self.settings = load_settings()

        # How many reminders have actually been shown this session.
        self._reminders_shown = 0

        # Internal session state. Launching/showing the Companion does NOT
        # mean the user is working:
        #   "idle"               -> no session; reminders disabled or stopped
        #   "waiting_to_start"   -> enabled, but the user has not started yet
        #   "working"            -> a work interval / reminder cycle is live
        #   "break"              -> a break is in progress
        # Transitions happen in _show_start_work_prompt, accept_start_work,
        # _start_work_interval, _begin_break and _stop_after_walkout.
        self._session_state = "idle"

        # ====================================================
        # WINDOW
        # ====================================================

        self.setAttribute(
            Qt.WA_TranslucentBackground
        )

        self.setAttribute(
            Qt.WA_ShowWithoutActivating
        )

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )

        # ====================================================
        # CHARACTER
        # ====================================================

        if getattr(
            sys,
            "frozen",
            False
        ):
            base_dir = Path(
                sys._MEIPASS
            )
        else:
            base_dir = (
                Path(__file__).parent
            )

        image_path = (
            base_dir
            / "assets"
            / "character.png"
        )

        self.character = QLabel()

        pixmap = QPixmap(
            str(image_path)
        )

        pixmap = pixmap.scaled(
            150,
            150,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.character.setPixmap(
            pixmap
        )

        self.character.setFixedSize(
            pixmap.width(),
            pixmap.height()
        )

        self.character.setAttribute(
            Qt.WA_TranslucentBackground
        )

        # ====================================================
        # MESSAGE
        # ====================================================

        self.message = MessageLabel(
            CHARACTER_DIALOGUE["greeting"]
        )

        # ====================================================
        # OPTIONS
        # ====================================================

        # State guard so we never process a choice twice
        # or while the dialogue is in transition.
        self._busy = False
        self._returning = False

        # "Okay" / "Later" for the first reminder
        self.ok_button = PixelChoice(
            REMINDER_MESSAGES["first"]["okay_text"]
        )

        self.later_button = PixelChoice(
            REMINDER_MESSAGES["first"]["later_text"]
        )

        # Tricky second-reminder choices:
        # "Yes" clearly accepts; "!No" looks like a refusal
        # but the wording itself still nudges toward the break.
        self.yes_button = PixelChoice(
            REMINDER_MESSAGES["second"]["yes_text"]
        )

        self.no_button = PixelChoice(
            REMINDER_MESSAGES["second"]["no_text"]
        )

        # Immediate escape action: stops the automatic reminder cycle
        # (work/reminder/break) without quitting the app.
        self.stop_button = PixelChoice(
            "Stop ✋"
        )

        # First-launch onboarding: opens the SettingsWindow.
        self.onboarding_settings_button = PixelChoice(
            "Set up schedule ⚙"
        )

        # Explicit session-start choices. Launching or showing the
        # Companion never auto-starts a work session; the user must
        # confirm they are starting now, schedule a start time, or
        # dismiss the prompt (via the panel's ✕) for the day.
        self.start_now_button = PixelChoice(
            "Start now ▶"
        )

        # Opens the schedule picker so the companion returns at a
        # specific time and asks to start work then.
        self.choose_time_button = PixelChoice(
            "Choose a time 🕒"
        )

        # "Not yet" shown after a scheduled start fires: the user can
        # delay instead of being forced to start immediately. No schedule
        # is re-created, so it never loops back into the picker.
        self.not_yet_button = PixelChoice(
            "Not yet ⏸"
        )

        # Visible while a schedule is pending (and from the tray) so a
        # work session can be started later without relaunching the app.
        self.start_work_button = PixelChoice(
            "Start working ▶"
        )

        for button in (
            self.ok_button,
            self.later_button,
            self.yes_button,
            self.no_button,
            self.stop_button,
            self.onboarding_settings_button,
        ):
            button.setFixedWidth(115)

        # The two startup choices (and the scheduled-start pair) share
        # one consistent width so they stay evenly balanced in the row.
        self.start_now_button.setFixedWidth(140)
        self.choose_time_button.setFixedWidth(140)
        self.not_yet_button.setFixedWidth(140)
        self.start_work_button.setFixedWidth(140)

        # Connections
        self.ok_button.clicked.connect(
            self.accept_reminder
        )

        self.later_button.clicked.connect(
            self.delay_reminder
        )

        self.yes_button.clicked.connect(
            self.accept_second
        )

        self.no_button.clicked.connect(
            self.refuse_second
        )

        self.stop_button.clicked.connect(
            self.stop_reminders
        )

        self.onboarding_settings_button.clicked.connect(
            self._open_settings
        )

        self.start_now_button.clicked.connect(
            self.accept_start_work
        )

        self.not_yet_button.clicked.connect(
            self.delay_scheduled_start
        )

        self.choose_time_button.clicked.connect(
            self._choose_schedule_time
        )

        self.start_work_button.clicked.connect(
            self.accept_start_work
        )

        # Current interactive prompt context, used to restore the right
        # state if the user cancels the work-duration question:
        #   None               -> quiet/idle (e.g. tray Start Work)
        #   "start"            -> the two-choice startup prompt
        #   "scheduled"        -> the scheduled-start prompt
        #   "schedule_waiting" -> parked while a start time is pending
        self._active_prompt = None

        # Choices are hidden until their dialogue needs them.
        self.ok_button.hide()
        self.later_button.hide()
        self.yes_button.hide()
        self.no_button.hide()
        self.stop_button.hide()
        self.onboarding_settings_button.hide()
        self.start_now_button.hide()
        self.choose_time_button.hide()
        self.not_yet_button.hide()
        self.start_work_button.hide()

        # ====================================================
        # OPTIONS LAYOUT
        # ====================================================

        button_layout = QHBoxLayout()

        button_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        button_layout.setSpacing(
            14
        )

        button_layout.addStretch()

        button_layout.addWidget(
            self.ok_button
        )

        button_layout.addWidget(
            self.later_button
        )

        button_layout.addWidget(
            self.yes_button
        )

        button_layout.addWidget(
            self.no_button
        )

        button_layout.addWidget(
            self.stop_button
        )

        button_layout.addWidget(
            self.onboarding_settings_button
        )

        button_layout.addWidget(
            self.start_work_button
        )

        button_layout.addStretch()

        # Second options row: the two startup choices (Start now / Choose
        # a time) and the scheduled-start pair (Start now / Not yet) live
        # here. Only the pair relevant to the current prompt is shown, so
        # exactly two evenly-spaced, equal-width buttons are visible at a
        # time and the empty row collapses away.
        schedule_button_row = QHBoxLayout()

        schedule_button_row.setContentsMargins(
            0,
            0,
            0,
            0
        )

        schedule_button_row.setSpacing(
            14
        )

        schedule_button_row.addStretch()

        schedule_button_row.addWidget(
            self.start_now_button
        )

        schedule_button_row.addWidget(
            self.not_yet_button
        )

        schedule_button_row.addWidget(
            self.choose_time_button
        )

        schedule_button_row.addStretch()

        # ====================================================
        # DIALOGUE PANEL
        # ====================================================

        self.dialogue_panel = DialoguePanel()

        dialogue_layout = QVBoxLayout()

        dialogue_layout.setContentsMargins(
            7,
            6,
            7,
            7
        )

        dialogue_layout.setSpacing(0)

        # -----------------------------
        # MESSAGE AREA
        # -----------------------------

        dialogue_layout.addWidget(
            self.message,
            alignment=Qt.AlignCenter
        )

        # -----------------------------
        # DISMISS (✕) AREA
        # -----------------------------

        dialogue_layout.addSpacing(2)

        close_row = QHBoxLayout()

        close_row.setContentsMargins(
            0,
            0,
            0,
            0
        )

        close_row.addStretch()

        close_row.addWidget(
            self.dialogue_panel.close_button
        )

        dialogue_layout.addLayout(
            close_row
        )

        # -----------------------------
        # OPTIONS AREA
        # -----------------------------

        dialogue_layout.addSpacing(6)

        dialogue_layout.addLayout(
            button_layout
        )

        dialogue_layout.addLayout(
            schedule_button_row
        )

        self.dialogue_panel.setLayout(
            dialogue_layout
        )

        dialogue_layout.addStretch(1)

        self.dialogue_panel.close_button.clicked.connect(
            self.dismiss_start_prompt
        )
        
        # ====================================================
        # MAIN LAYOUT
        # ====================================================

        main_layout = QVBoxLayout()

        main_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        main_layout.setSpacing(
            2
        )

        main_layout.addWidget(
            self.dialogue_panel,
            alignment=Qt.AlignCenter
        )

        # Slim work-status line (elapsed / countdown / session count).
        # Translucent and cheap; it simply mirrors the current cycle.
        self.status_panel = StatusPanel()

        main_layout.addWidget(
            self.status_panel,
            alignment=Qt.AlignCenter
        )

        # The character sits inside a fixed-size container so the subtle
        # idle bounce can move it a few pixels without ever reflowing the
        # dialogue panel, buttons, or the window docking.
        self.character_container = QWidget()

        character_cell = QVBoxLayout(
            self.character_container
        )

        character_cell.setContentsMargins(
            8,
            8,
            8,
            8
        )

        character_cell.setSpacing(0)

        character_cell.addWidget(
            self.character,
            alignment=Qt.AlignCenter
        )

        main_layout.addWidget(
            self.character_container,
            alignment=Qt.AlignCenter
        )

        self.setLayout(
            main_layout
        )

        # Track the current dialogue growth so we only re-fit (and
        # reposition) the window when the message area height changes.
        self._last_dialogue_delta = 0

        self.message._resize_callback = (
            self._fit_dialogue
        )

        self.adjustSize()

        # ====================================================
        # SCREEN POSITION
        # ====================================================

        screen = (
            QApplication
            .primaryScreen()
            .availableGeometry()
        )

        self.screen_right = (
            screen.right()
        )

        self.screen_bottom = (
            screen.bottom()
        )

        self.final_x = (
            self.screen_right
            - self.width()
            - 30
        )

        self.final_y = (
            self.screen_bottom
            - self.height()
            - 30
        )

        # Start outside screen
        self.current_x = (
            self.screen_right + 20
        )

        self.move(
            self.current_x,
            self.final_y
        )

        # ====================================================
        # TIMERS
        # ====================================================

        # Walking animation timer (walk in / walk out only).
        # Kept separate from the reminder timer below.
        self.walk_timer = QTimer(
            self
        )

        self.walk_timer.timeout.connect(
            self._walk_step
        )

        self._walk_action = None

        # Callback invoked once the character finishes walking out.
        self._walk_out_done = None

        # Idle animation timer for the subtle expressive bounces. It only
        # nudges the character inside its container and never runs while
        # the character is walking.
        self.idle_timer = QTimer(
            self
        )

        self.idle_timer.timeout.connect(
            self._idle_tick
        )

        self._idle_key = None
        self._idle_frame = 0
        self._character_base_top = 0

        # Reminder timer (work interval / Later delay).
        # A single recurring timer only: work-interval firing and
        # Later-delay firing both route through here, stop-then-start
        # so no duplicate reminder timers can ever be scheduled.
        self.reminder_timer = QTimer(
            self
        )

        self.reminder_timer.timeout.connect(
            self._on_reminder_fire
        )

        # Break timer (break duration after a break is accepted).
        # Deliberately a distinct, clearly named timer from the
        # reminder timer; stop-then-start to avoid duplicates.
        self.break_timer = QTimer(
            self
        )

        self.break_timer.timeout.connect(
            self._on_break_fire
        )

        # Scheduled-start timer. Single-shot: when it fires the companion
        # walks in and asks the user to start work. Always stop-then-start
        # so at most one schedule is ever armed.
        self.schedule_timer = QTimer(
            self
        )

        self.schedule_timer.setSingleShot(
            True
        )

        self.schedule_timer.timeout.connect(
            self._on_schedule_fire
        )

        # Local datetime when a scheduled start should fire, or None.
        self._scheduled_start_at = None

        # One-second status-line refresher. Only ticks while a work/break
        # session (or a pending schedule) is live; otherwise it is stopped
        # and the panel is blank.
        self.status_timer = QTimer(
            self
        )

        self.status_timer.timeout.connect(
            self._status_tick
        )

        # Single-shot "peek" timer: after the companion has shown the live
        # working/break status (manual Show Companion or break start), it
        # walks away and hides so it never lingers indefinitely. Separate
        # from the work/break/reminder timers and only ever touches window
        # visibility, never a session timer.
        self.auto_hide_timer = QTimer(
            self
        )

        self.auto_hide_timer.setSingleShot(
            True
        )

        self.auto_hide_timer.timeout.connect(
            self._auto_hide_after_view
        )

        # Wall-clock timestamps used to render the status line.
        self._status_started_at = None
        self._break_ends_at = None

        # Set when the character returns from a break to show the
        # break-completion dialogue instead of a reminder.
        self._break_done_pending = False

        # Stable dialogue lines for the currently running session. Set by
        # _start_work_interval / _begin_break and reused while the window
        # is visible, so the bubble is never blank during a session.
        self._working_message = ""
        self._break_message = ""
        self._break_warned = False

        # True while the companion is performing the startup greeting
        # (walk in -> wave -> settle). Suppresses the normal reminder
        # routing in the shared walk-in settle so no reminder fires early.
        self._startup_greeting = False

        # True while the additive startup self-introduction message chain
        # is running. Guards against ever scheduling a second chain.
        self._startup_intro_active = False

        # One-shot arrival routes for manual "Show Companion" walk-ins:
        # with no live session the companion asks whether work should
        # start; during a live session it just settles quietly. Cleared
        # by the arrival router so a stale flag can never misroute a
        # later reminder/break return.
        self._prompt_on_arrival = False
        self._quiet_return = False

        # True when the walk-in that is currently running was triggered by
        # a scheduled start. On arrival the companion shows the dedicated
        # scheduled-start prompt (work-start message + duration / Not yet)
        # instead of the generic two-choice startup prompt.
        self._scheduled_prompt_on_arrival = False

        # Which route the startup sequence takes, decided exactly once at
        # startup and preserved for the whole greeting/animation chain.
        # A brand-new user (False) runs the startup intro as a prelude to
        # the original v1.0 onboarding; a returning user (True) runs the
        # intro as a prelude to the normal idle/parked state. This flag is
        # intentionally NOT re-derived from the mutable settings mid-flow.
        self._startup_onboarding = False

        self._setup_tray()

        # Re-arm any schedule that was pending when the app last closed.
        # Past schedules are stale and are cleared silently so the normal
        # start prompt takes over instead.
        self._rearm_pending_schedule()

        # ====================================================
        # WALK IN (START)
        # ====================================================

        self.message.setText(
            CHARACTER_DIALOGUE["greeting"]
        )

        if not self.settings.get(
            "onboarding_completed",
            False
        ):
            # First launch: the startup intro is a prelude to the v1.0
            # onboarding flow. Capture the route here, once, so the whole
            # startup chain uses it without re-inferring from settings.
            self._startup_onboarding = True

            self._begin_onboarding()
            return

        if self._should_prompt():
            # Enabled: greet, then explicitly ask whether the user is
            # starting work now. No work/reminder/break timer runs until
            # the user confirms, so launching never implies working.
            self._begin_startup_greeting()
            return

        # Disabled: the companion greets the user and stays visible.
        self._set_character(
            "walking_in"
        )

        self._walk_action = "in"

        self.walk_timer.start(
            30
        )

    # ========================================================
    # WALK ANIMATION
    # ========================================================

    def _walk_step(self):

        if self._walk_action == "in":
            self._step_in()
        else:
            self._step_out()

    def _step_in(self):

        self.current_x -= 8

        self.move(
            self.current_x,
            self.final_y
        )

        if self.current_x <= self.final_x:

            self.current_x = (
                self.final_x
            )

            self.move(
                self.current_x,
                self.final_y
            )

            self.walk_timer.stop()

            self._walk_action = None

            # The character is now at its resting spot. Briefly show
            # a personality pose before settling into standing. The
            # return also routes through this same walk-in, so pick the
            # pose according to which entrance is in progress.
            if self._startup_greeting:
                pose = "excited_waving"
            else:
                pose = (
                    "peek" if self._returning else "thinking"
                )

            self._set_character(
                pose
            )

            QTimer.singleShot(
                600,
                self._after_arrive_stand
            )

    def _after_arrive_stand(self):

        # Settle the character into the standing pose, then continue
        # with the existing delayed post-walk-in behavior.
        self._set_character(
            "standing"
        )

        if self._startup_greeting:
            # Startup greeting complete: run the short self-introduction
            # sequence (Hey! -> a few intro lines), then hand control to
            # the appropriate next step based on the onboarding route
            # decided once at startup (self._startup_onboarding).
            #
            #  * Brand-new user  -> the intro flows DIRECTLY into the
            #    schedule-setup step (message + button). The stale v1.0
            #    _show_onboarding_intro() is deliberately skipped: it
            #    repeats the "Hey! / Desktop Companion" greeting text that
            #    the startup intro already showed.
            #  * Returning user  -> _settle_after_greeting() asks whether
            #    the user is starting work now; nothing is scheduled.
            #
            # _after_walk_in() is deliberately NOT called here: for an
            # already-onboarded user that would fire show_main_reminder()
            # immediately. No work/reminder/break timer is running yet, so
            # nothing fires early and the user is explicitly asked.
            self._startup_greeting = False

            if self._startup_onboarding:
                self._run_startup_intro(
                    self._show_onboarding_setup,
                    STARTUP_INTRO[:-1]
                )
            else:
                self._run_startup_intro(
                    self._settle_after_greeting
                )

            return

        QTimer.singleShot(
            1500,
            self._after_walk_in
        )

    def _run_startup_intro(self, on_done, entries=STARTUP_INTRO):

        # A purely additive chain of single-shot timers that steps the
        # companion through its startup self-introduction. It never
        # duplicates timers (a guard flag prevents a second run) and never
        # starts the reminder timer itself. Once every message has been
        # shown, the on_done callback takes over so the intro is a
        # prelude to (not a replacement for) the existing onboarding /
        # idle behavior.
        #
        # entries lets each route show its own message chain. Returning
        # users keep the default STARTUP_INTRO; brand-new users pass a
        # shorter intro so the greeting flows straight into the schedule
        # setup step without any extra trailer line.
        if self._startup_intro_active:
            return

        self._startup_intro_active = True

        def step(index):

            if index < len(entries):

                message, pause = entries[index]

                self.message.setText(
                    message
                )

                QTimer.singleShot(
                    int(pause),
                    lambda: step(index + 1)
                )

                return

            # All messages shown: hand control to the caller.
            self._startup_intro_active = False

            if on_done is not None:
                on_done()

        step(0)

    def _settle_after_greeting(self):

        # Returning-user post-introduction: if a start time was scheduled
        # (re-armed from a previous run) show the waiting confirmation;
        # otherwise, if reminders are enabled, settle into the quiet
        # resting state with the simple "Start working" action (no timers
        # have been started, and the full two-choice startup prompt is
        # reserved for first-run onboarding). If reminders are disabled
        # just clear the bubble and settle into the normal standing/idle
        # pose.
        if self._scheduled_start_at is not None:
            self._show_schedule_waiting()
            return

        if self._should_prompt():
            self._show_resting_start()
        else:
            self.message.setText(
                ""
            )

            self._set_character(
                "standing"
            )

    def _step_out(self):

        self.current_x += 8

        self.move(
            self.current_x,
            self.final_y
        )

        if self.current_x > self.screen_right:

            self.walk_timer.stop()

            self._walk_action = None

            callback = self._walk_out_done

            self._walk_out_done = None

            if callback is not None:
                callback()

    def _start_walk_out(self, on_done):

        # Any idle bounce must stop before the character moves off
        # screen so the walk-out animation stays clean.
        self._stop_idle_animation()

        self._walk_out_done = on_done

        self._walk_action = "out"

        self.walk_timer.start(
            30
        )

    def _reset_offscreen(self):

        self.current_x = (
            self.screen_right + 20
        )

        self.move(
            self.current_x,
            self.final_y
        )

    def _set_character(self, key):

        filename = (
            CHARACTER_IMAGES.get(
                key
            )
        )

        if filename is None:
            return

        if getattr(
            sys,
            "frozen",
            False
        ):
            base_dir = Path(
                sys._MEIPASS
            )
        else:
            base_dir = (
                Path(__file__).parent
            )

        image_path = (
            base_dir
            / "assets"
            / filename
        )

        pixmap = QPixmap(
            str(image_path)
        )

        if pixmap.isNull():
            return

        pixmap = pixmap.scaled(
            150,
            150,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.character.setPixmap(
            pixmap
        )

        self.character.setFixedSize(
            pixmap.width(),
            pixmap.height()
        )

        self._start_idle_animation(
            key
        )

    def _start_idle_animation(self, key):

        # Begin a subtle bouncing idle animation for expressive poses,
        # or stop any existing one for poses without an idle definition.
        spec = IDLE_ANIMATIONS.get(
            key
        )

        if spec is None:
            self._stop_idle_animation()
            return

        self._idle_key = key
        self._idle_frame = 0

        self._character_base_top = (
            self.character.y()
        )

        self.idle_timer.start(
            int(spec["every"])
        )

    def _stop_idle_animation(self):

        self.idle_timer.stop()

        self._idle_key = None
        self._idle_frame = 0

        if (
            getattr(
                self,
                "character_container",
                None
            )
            is not None
        ):
            # Snap the character back so the idle offset never leaks
            # into the next pose or into the walk animation.
            self.character.move(
                self.character.x(),
                self._character_base_top
            )

    def _idle_tick(self):

        # Gently move the character up/down inside its container by a
        # pixel or two, producing a short repeating bounce.
        spec = IDLE_ANIMATIONS.get(
            self._idle_key
        )

        if spec is None:
            self._stop_idle_animation()
            return

        self._idle_frame += 1

        px = int(spec["px"])

        if self._idle_frame % 2:
            offset = px
        else:
            offset = 0

        self.character.move(
            self.character.x(),
            self._character_base_top - offset
        )

    # ========================================================
    # SETTINGS / TRAY
    # ========================================================

    def _setup_tray(self):

        try:
            icon_path = (
                Path(__file__).parent
                / "assets"
                / "character.png"
            )

            if getattr(
                sys,
                "frozen",
                False
            ):
                icon_path = (
                    Path(sys._MEIPASS)
                    / "assets"
                    / "character.png"
                )
        except Exception:
            icon_path = None

        menu = QMenu()

        show_action = menu.addAction(
            "Show Companion"
        )

        show_action.triggered.connect(
            self._show_companion
        )

        start_work_action = menu.addAction(
            "Start Work"
        )

        start_work_action.triggered.connect(
            self._start_work_from_tray
        )

        settings_action = menu.addAction(
            "Settings..."
        )

        settings_action.triggered.connect(
            self._open_settings
        )

        menu.addSeparator()

        quit_action = menu.addAction(
            "Quit"
        )

        quit_action.triggered.connect(
            QApplication.instance().quit
        )

        if icon_path is not None and icon_path.exists():
            self.tray_icon = QSystemTrayIcon(
                QIcon(str(icon_path))
            )
        else:
            self.tray_icon = QSystemTrayIcon()

        self.tray_icon.setToolTip(
            "Desktop Companion"
        )

        self.tray_icon.setContextMenu(
            menu
        )

        self.tray_icon.activated.connect(
            self._on_tray_activated
        )

        self.tray_icon.show()

    def _on_tray_activated(self, reason):

        if (
            reason
            == QSystemTrayIcon.Trigger
        ):
            self._show_companion()

    def _show_companion(self):

        # If an interaction/animation is already in progress, a tray
        # Show request must not interrupt it or clear its busy state.
        if self._busy:
            return

        # A user-visible show request always cancels any pending peek
        # walk-away; the show below (re)arms it after settling.
        self.auto_hide_timer.stop()

        self.show()

        self.raise_()

        # An active work/break session must never be reset or duplicated
        # by a manual show: its timers keep running untouched and the
        # companion simply returns for a quiet greeting.
        if self._is_work_session_active():
            # Drop a stale peek walk-out callback before starting the
            # next walk-in so no orphaned hide fires later.
            self._walk_out_done = None

            self._reset_offscreen()

            self._returning = False

            self._quiet_return = True

            self._prompt_on_arrival = False

            self.message.setText(
                CHARACTER_DIALOGUE["greeting"]
            )

            self._set_character(
                "peek"
            )

            self._walk_action = "in"

            self.walk_timer.start(
                30
            )

            return

        # No live session: a manual show returns the companion to the
        # waiting state (start-work prompt) instead of firing an
        # immediate reminder. Restarting is impossible because no session
        # exists, and resetting is exactly what a fresh manual show wants.
        self._stop_reminder_timer()

        self._stop_break_timer()

        self._reset_offscreen()

        self._returning = False

        self._break_done_pending = False

        self._busy = False

        self._prompt_on_arrival = True

        self._quiet_return = False

        self._walk_action = "in"

        self.message.setText(
            CHARACTER_DIALOGUE["greeting"]
        )

        # Fresh show: the character walks in.
        self._set_character(
            "walking_in"
        )

        self.walk_timer.start(
            30
        )

    def _open_settings(self):

        # Track whether this save completes the first-launch onboarding.
        was_onboarding = not self.settings.get(
            "onboarding_completed",
            False
        )

        dialog = SettingsWindow(
            self.settings,
            self
        )

        if dialog.exec() == QDialog.Accepted:

            new_settings = dialog.values()

            self.settings.update(
                new_settings
            )

            # Saving during onboarding marks it complete (even if the
            # user disabled reminders — they explicitly chose that).
            self.settings["onboarding_completed"] = True

            self._save_settings()

            if was_onboarding:
                # Show the confirmation, then start the configured work
                # interval (or go idle if reminders are disabled). No
                # immediate break reminder is shown.
                self._complete_onboarding()
            elif new_settings.get(
                "enabled",
                False
            ) and not self._session_timers_running():
                # Re-enabled reminders from a quiet state -> ask whether
                # the user is starting work now (no timer auto-starts).
                self._show_start_work_prompt()

    def _save_settings(self):

        # Persist the current settings. Called only when settings are
        # intentionally changed, never on transient interactions.
        save_settings(
            self.settings
        )

    def _fit_dialogue(self, label_height):

        # Called whenever the message text changes. Long messages wrap
        # and need a taller label, so grow the dialogue panel to match
        # while keeping the baseline size for short messages. The window
        # keeps its bottom-right docking by recomputing its y position.
        delta = label_height - 62

        if delta < 0:
            delta = 0

        self.message.setFixedHeight(
            62 + delta
        )

        self.dialogue_panel.setFixedHeight(
            132 + delta
        )

        if delta == self._last_dialogue_delta:
            return

        self._last_dialogue_delta = delta

        self.adjustSize()

        screen = (
            QApplication
            .primaryScreen()
            .availableGeometry()
        )

        self.final_y = (
            screen.bottom()
            - self.height()
            - 30
        )

        self.move(
            self.current_x,
            self.final_y
        )

    def _begin_reminder_cycle(self):

        # Begin a fresh work -> break -> work cycle from a quiet state:
        # reset counters, roll the per-day session counter, clear any
        # leftover schedule/dismissal and start the work interval timer.
        self._reminders_shown = 0

        self._clear_schedule(
            persist=False
        )

        self.settings["prompt_dismissed_on"] = ""

        today = _today_str()

        if self.settings.get(
            "sessions_date",
            ""
        ) != today:
            self.settings["sessions_date"] = today
            self.settings["sessions_today"] = 0

        self.settings["sessions_today"] = int(
            self.settings.get(
                "sessions_today",
                0
            )
        ) + 1

        self._save_settings()

        self._start_work_interval()

    def _begin_startup_greeting(self):

        # Walk the companion in with a cheerful startup greeting. Unlike
        # the old behavior, NO work/reminder/break timer is scheduled
        # here: the character simply greets the user, then asks whether
        # they are starting work now (see _settle_after_greeting).
        self._startup_greeting = True

        self.show()

        self._returning = False

        self._break_done_pending = False

        self._busy = False

        self.message.setText(
            CHARACTER_DIALOGUE["greeting"]
        )

        self._hide_all_choices()

        self._set_character(
            "excited_waving"
        )

        self._reset_offscreen()

        self._walk_action = "in"

        self.walk_timer.start(
            30
        )

    # ========================================================
    # INTRO SEQUENCE
    # ========================================================

    def _after_walk_in(self):

        # First launch: onboarding takes priority over everything else.
        if not self.settings.get(
            "onboarding_completed",
            False
        ):
            self._show_onboarding_intro()
            return

        if not self._should_prompt():
            self._prompt_on_arrival = False
            self._quiet_return = False
            self._idle_greeting()
            return

        if self._break_done_pending:
            self._prompt_on_arrival = False
            self._quiet_return = False
            self._show_break_done()
            return

        if self._returning:
            self._prompt_on_arrival = False
            self._quiet_return = False
            self.show_second_reminder()
            return

        # A manual "Show Companion" with no live session asks whether the
        # user wants to start work; one performed mid-session just settles
        # quietly so the active cycle is left untouched. A walk-in that
        # was triggered by a schedule firing shows the dedicated
        # scheduled-start prompt instead of the generic two-choice one.
        if self._prompt_on_arrival:
            self._prompt_on_arrival = False

            if self._scheduled_prompt_on_arrival:
                self._scheduled_prompt_on_arrival = False
                self._show_scheduled_start_prompt()
            else:
                self._show_start_work_prompt()
            return

        if self._quiet_return:
            self._quiet_return = False
            self._quiet_stand()
            return

        self.show_main_reminder()

    def _should_prompt(self):

        return bool(
            self.settings.get(
                "enabled",
                True
            )
        )

    def _idle_greeting(self):

        self._session_state = "idle"

        self.message.setText(
            CHARACTER_DIALOGUE["greeting"]
        )

        # Greeting pose: an excited wave while staying visible.
        self._set_character(
            "excited_waving"
        )

        self._hide_all_choices()

        self._sync_status_timer()

    # ========================================================
    # START WORK (explicit session start)
    # ========================================================

    def _session_timers_running(self):

        return (
            self.reminder_timer.isActive()
            or self.break_timer.isActive()
        )

    def _is_work_session_active(self):

        # A work/break session is live whenever its timers are scheduled
        # or the internal state says we are working/on break. Idle and
        # waiting_to_start are deliberately NOT active sessions.
        return (
            self._session_state in ("working", "break")
            or self._session_timers_running()
        )

    def _show_start_work_prompt(self):

        # Enabled but no session running: the companion asks whether the
        # user is starting work now. "Start now" and "Choose a time" are
        # the only startup choices (no ✕: dismissing a starting point
        # should never leave the character stood silently with an empty
        # bubble). No timer runs until the user explicitly starts (or the
        # schedule fires), and starting always asks how long to work.
        self._busy = False

        self._session_state = "waiting_to_start"

        self.show()

        self._hide_all_choices()

        self._active_prompt = "start"

        self.message.setText(
            CHARACTER_DIALOGUE["start_work_prompt"]
        )

        self._set_character(
            "energetic_encouraging"
        )

        self.start_now_button.show()

        self.choose_time_button.show()

        self._set_choices_enabled(
            True
        )

        self._sync_status_timer()

    def _show_resting_start(self):

        # Quiet, non-blocking steady state for returning users with no
        # active session and no schedule. Unlike the first-run start
        # prompt -- which asks "Ready to work?" with "Start now" /
        # "Choose a time" -- this only offers the obvious "Start working"
        # action, so launching the app never replays the full startup
        # prompt automatically. The ✕ simply closes this bubble; nothing
        # starts or schedules until the user acts explicitly.
        self._busy = False

        self._session_state = "waiting_to_start"

        self.show()

        self._hide_all_choices()

        self._active_prompt = "resting"

        self.message.setText(
            CHARACTER_DIALOGUE["resting_prompt"]
        )

        self._set_character(
            "standing"
        )

        self.start_work_button.show()

        self.dialogue_panel.close_button.show()

        self._set_choices_enabled(
            True
        )

        self._sync_status_timer()

    def dismiss_start_prompt(self):

        # The panel's ✕ close/cross action. It cleanly hides the whole
        # companion: no timer is started, nothing is scheduled, and the
        # prompt is NOT suppressed afterwards (the next launch, walk-in,
        # or scheduled start asks again). Hiding instead of blanking the
        # bubble means the character is never left stood silently with an
        # empty dialogue. Use the tray's "Show Companion" to bring it
        # back.
        if self._busy:
            return

        if self._session_state not in (
            "waiting_to_start",
            "idle",
        ):
            return

        self._busy = False

        self._session_state = "idle"

        self._active_prompt = None

        self._hide_all_choices()

        self.auto_hide_timer.stop()

        self._walk_out_done = None

        self._sync_status_timer()

        self.hide()

    def _ask_duration(self, on_confirm):

        # Always ask "How long do you want to work?" before starting a
        # manual (or scheduled-start) work session, so the configured
        # interval is never silently applied. Cancelling returns to the
        # prompt that was active and never starts a session.
        if self._busy:
            return

        self.show()

        self._busy = True

        self._hide_all_choices()

        self._set_choices_enabled(
            False
        )

        self.message.setText(
            CHARACTER_DIALOGUE[
                "work_duration_question"
            ]
        )

        self._set_character(
            "energetic_encouraging"
        )

        dialog = WorkDurationDialog(
            self.settings,
            self
        )

        accepted = (
            dialog.exec() == QDialog.Accepted
        )

        if accepted:

            minutes = (
                dialog.selected_minutes()
            )

            self._begin_manual_work(
                minutes
            )
        else:
            self._restore_after_duration_cancel()

    def _restore_after_duration_cancel(self):

        # The user cancelled the duration question: put back whichever
        # prompt (or quiet state) was showing before it was asked. No
        # timer was started.
        self._busy = False

        self._set_choices_enabled(
            True
        )

        prompt = self._active_prompt

        if prompt == "scheduled":
            self._show_scheduled_start_prompt()
        elif prompt == "schedule_waiting":
            self._show_schedule_waiting()
        elif prompt == "resting":
            self._show_resting_start()
        elif prompt == "start":
            self._show_start_work_prompt()
        else:
            self._show_idle_after_cancel()

    def _show_idle_after_cancel(self):

        self._session_state = "idle"

        self._hide_all_choices()

        self.message.setText(
            ""
        )

        self._set_character(
            "standing"
        )

        self._sync_status_timer()

    def _begin_manual_work(self, minutes):

        # The user chose an explicit work duration: apply it as the work
        # interval (persisted so the next reminder/session uses the same
        # length), cancel any pending schedule and today's dismissal, then
        # reuse the existing cycle-start logic so the reminder timer,
        # reminder routing, break flow, session counter and status panel
        # are all untouched.
        self.settings[
            "work_interval_minutes"
        ] = int(
            minutes
        )

        self._clear_schedule(
            persist=False
        )

        self.settings["prompt_dismissed_on"] = ""

        self._save_settings()

        self._session_state = "working"

        self._set_choices_enabled(
            False
        )

        self.message.setText(
            CHARACTER_DIALOGUE["start_work_yes"]
        )

        self._hide_all_choices()

        self._set_character(
            "happy_thumbs_up"
        )

        QTimer.singleShot(
            1800,
            self._begin_reminder_cycle
        )

    def accept_start_work(self):

        # "Start now" (startup + scheduled prompts) and "Start working"
        # (pending-schedule + tray): every entry asks the duration
        # question before anything starts.
        if self._busy:
            return

        if not self._should_prompt():
            return

        if self._is_work_session_active():
            return

        self._ask_duration(
            self._begin_manual_work
        )

    def _start_work_from_tray(self):

        # Tray shortcut to begin a work session from the idle/waiting
        # state. No-op while an interaction is busy or a session is
        # already running, so it can never restart or duplicate a cycle.
        if self._busy:
            return

        if self._is_work_session_active():
            return

        self._active_prompt = None

        self._show_idle_after_cancel()

        self._ask_duration(
            self._begin_manual_work
        )

    def _quiet_stand(self):

        # Post-show arrival when a work/break session is already active:
        # do not show a reminder or reset anything, just settle quietly
        # so the running cycle stays completely untouched. Keep a real
        # dialogue line on the bubble instead of blanking it, so a manual
        # "Show Companion" never leaves an unexplained empty bubble.
        self._hide_all_choices()

        if self._session_state == "break":
            self.message.setText(
                self._current_break_message()
            )
        elif self._session_state == "working":
            self.message.setText(
                self._working_message
            )
        else:
            self.message.setText(
                ""
            )

        self._set_character(
            "standing"
        )

        # Brief peek: let the user read the live status / dialogue, then
        # walk away and hide so the companion never lingers indefinitely
        # on a running session. The session timers are left untouched.
        self.auto_hide_timer.start(
            PEEK_AUTO_HIDE_MS
        )

    def _auto_hide_after_view(self):

        # "Peek" timeout: the companion has shown the current working /
        # break status for a few seconds. If nothing interactive is
        # waiting (no reminder/choice and no running walk), walk away and
        # hide while the work/break/reminder timers keep running in the
        # background.
        if self._busy:
            return

        if self._session_state not in (
            "working",
            "break",
        ):
            return

        if self._walk_action is not None:
            return

        for button in (
            self.ok_button,
            self.later_button,
            self.yes_button,
            self.no_button,
            self.stop_button,
            self.start_now_button,
            self.choose_time_button,
            self.not_yet_button,
            self.start_work_button,
            self.onboarding_settings_button,
        ):
            if button.isVisible():
                return

        self._start_walk_out(
            self._hide_after_peek
        )

    def _hide_after_peek(self):

        # Walk-out finished for the peek: simply remove the window. No
        # session state or timer is touched here.
        self.hide()

    def _current_break_message(self):

        # Dialogue line to show while a break is running: the stable
        # chilled message for most of the break, switching once to a
        # motivating line in the final few seconds.
        if self._session_state != "break":
            return self._break_message

        if self._break_ends_at is None:
            return self._break_message

        remaining = int(
            (
                self._break_ends_at
                - datetime.now()
            ).total_seconds()
        )

        if 0 < remaining <= 10:
            return CHARACTER_DIALOGUE["break_almost"]

        return self._break_message

    # ========================================================
    # SCHEDULED START
    # ========================================================

    def _rearm_pending_schedule(self):

        # Restored on launch from persisted settings. A future time keeps
        # the schedule armed; a past time is stale and cleared silently.
        raw = self.settings.get(
            "scheduled_start",
            ""
        )

        if not raw:
            return

        try:
            dt = datetime.fromisoformat(
                raw
            )
        except (
            ValueError,
            TypeError,
        ):
            dt = None

        if dt is None:
            self.settings["scheduled_start"] = ""
            self._save_settings()
            return

        if dt > datetime.now():
            self._scheduled_start_at = dt

            ms = max(
                1,
                int(
                    (
                        dt - datetime.now()
                    ).total_seconds()
                    * 1000
                )
            )

            self.schedule_timer.start(
                ms
            )

            _debug(
                f"schedule re-armed at {dt.isoformat()} ({ms} ms)"
            )
        else:
            self._scheduled_start_at = None

            self.settings["scheduled_start"] = ""

            self._save_settings()

            _debug(
                "stale schedule cleared on launch"
            )

    def _schedule_label(self):

        # Human-readable schedule time, e.g. "3:00 PM".
        if self._scheduled_start_at is None:
            return ""

        return (
            self._scheduled_start_at
            .strftime("%I:%M %p")
            .lstrip("0")
        )

    def _choose_schedule_time(self):

        if self._busy:
            return

        if self._is_work_session_active():
            return

        dialog = ScheduleTimeDialog(
            self
        )

        if dialog.exec() != QDialog.Accepted:
            # User cancelled (or the dialog is already closed); the
            # startup prompt stays exactly as it was.
            return

        chosen = dialog.selected_time()

        # The schedule picker confirmed: close it fully so no duplicate
        # panel is left visible behind the next dialogue.
        dialog.close()

        now = datetime.now()

        target = now.replace(
            hour=chosen.hour(),
            minute=chosen.minute(),
            second=0,
            microsecond=0
        )

        if target <= now:
            self.message.setText(
                CHARACTER_DIALOGUE["schedule_past"]
            )

            self._set_character(
                "concerned"
            )

            return

        self._set_schedule(
            target
        )

        self.message.setText(
            CHARACTER_DIALOGUE["schedule_confirm"].format(
                time=self._schedule_label()
            )
        )

        self._set_character(
            "happy_proud"
        )

    def _set_schedule(self, target_dt):

        # Arm the single-shot schedule, persist it (so it survives a
        # relaunch), and clear today's dismissal since the user just
        # committed to a start time.
        self._busy = True

        self._hide_all_choices()

        self._set_choices_enabled(
            False
        )

        self._scheduled_start_at = target_dt

        self.settings["scheduled_start"] = (
            target_dt.isoformat()
        )

        self.settings["prompt_dismissed_on"] = ""

        self._save_settings()

        ms = max(
            1,
            int(
                (
                    target_dt - datetime.now()
                ).total_seconds()
                * 1000
            )
        )

        self.schedule_timer.start(
            ms
        )

        _debug(
            f"schedule armed at {target_dt.isoformat()} ({ms} ms)"
        )

        self._sync_status_timer()

        QTimer.singleShot(
            1800,
            self._show_schedule_waiting
        )

    def _show_schedule_waiting(self):

        # Parked while a schedule is pending: show the confirmation and
        # keep the Start working button available. The schedule timer
        # (plus the status line) keeps counting down in the background.
        # This is the only remaining panel: the picker itself is already
        # closed, and no duplicate dialogue is left behind.
        self._busy = False

        self._active_prompt = "schedule_waiting"

        self._session_state = "waiting_to_start"

        # Only the intended scheduled-waiting state remains visible: any
        # previously visible choices are hidden so no duplicate/stale
        # buttons leak into this panel.
        self._hide_all_choices()

        self.message.setText(
            CHARACTER_DIALOGUE["schedule_waiting"]
        )

        self._set_character(
            "standing"
        )

        self.start_work_button.show()

        self._set_choices_enabled(
            True
        )

    def _clear_schedule(self, persist):

        self.schedule_timer.stop()

        self._scheduled_start_at = None

        self.settings["scheduled_start"] = ""

        if persist:
            self._save_settings()

        self._sync_status_timer()

    def _on_schedule_fire(self):

        # The scheduled moment arrived: clear the stored schedule and walk
        # in with the dedicated scheduled-start prompt ("It's time to
        # work!" + work duration / Not yet) rather than a break reminder
        # or the generic startup prompt.
        self._clear_schedule(
            persist=True
        )

        _debug(
            "schedule fired -> scheduled-start prompt"
        )

        if not self._should_prompt():
            self._busy = False
            self.hide()
            return

        self._busy = True

        self._prompt_on_arrival = True

        self._scheduled_prompt_on_arrival = True

        self._quiet_return = False

        self._returning = False

        self._break_done_pending = False

        self._reset_offscreen()

        self.show()

        self._hide_all_choices()

        self.message.setText(
            CHARACTER_DIALOGUE["greeting"]
        )

        self._set_character(
            "walking_in"
        )

        self._walk_action = "in"

        self.walk_timer.start(
            30
        )

    def _show_scheduled_start_prompt(self):

        # Shown right after a scheduled start fires. The user is told it
        # is time to work, then offered Start now (which asks the work
        # duration) or Not yet (delay). Choosing a time never re-opens
        # the scheduling screen here.
        self._busy = False

        self._active_prompt = "scheduled"

        self._session_state = "waiting_to_start"

        self.show()

        self._hide_all_choices()

        self.message.setText(
            CHARACTER_DIALOGUE["scheduled_prompt"]
        )

        self._set_character(
            "energetic_encouraging"
        )

        self.start_now_button.show()

        self.not_yet_button.show()

        self.dialogue_panel.close_button.show()

        self._set_choices_enabled(
            True
        )

        self._sync_status_timer()

    def delay_scheduled_start(self):

        # "Not yet": don't force the user to start now. Park quietly in
        # the standing state; no schedule is re-armed and the scheduling
        # screen is never reopened, so this can never loop.
        if self._busy:
            return

        self._busy = True

        self._set_choices_enabled(
            False
        )

        self.message.setText(
            CHARACTER_DIALOGUE["scheduled_delayed"]
        )

        self._hide_all_choices()

        self._set_character(
            "pleading"
        )

        QTimer.singleShot(
            1800,
            self._finish_delay_scheduled_start
        )

    def _finish_delay_scheduled_start(self):

        self._busy = False

        self._active_prompt = None

        self._session_state = "idle"

        self._hide_all_choices()

        self.message.setText(
            ""
        )

        self._set_character(
            "standing"
        )

        self._sync_status_timer()

    # ========================================================
    # STATUS PANEL
    # ========================================================

    def _sync_status_timer(self):

        # Keep the lightweight one-second status refresher running only
        # while something is actually live (working / break / schedule
        # pending); otherwise stop it and blank the line so a stale status
        # never shows on an idle companion.
        if (
            self._session_state in ("working", "break")
            or self._scheduled_start_at is not None
        ):
            if not self.status_timer.isActive():
                self.status_timer.start(
                    1000
                )

            self._status_tick()
        else:
            self.status_timer.stop()

            self.status_panel.set_text(
                ""
            )

    def _status_tick(self):

        # Render the status line based on the current session. Pure
        # wall-clock reads; no settings writes happen here.
        if self._session_state == "working":
            elapsed = ""

            if self._status_started_at is not None:
                secs = int(
                    (
                        datetime.now()
                        - self._status_started_at
                    ).total_seconds()
                )

                elapsed = "{:02d}:{:02d}".format(
                    secs // 60,
                    secs % 60
                )

            sessions = int(
                self.settings.get(
                    "sessions_today",
                    0
                )
            )

            self.status_panel.set_text(
                f"💪 Working · {elapsed} · Session {sessions}"
            )
        elif self._session_state == "break":
            remaining = ""

            if self._break_ends_at is not None:
                secs = max(
                    0,
                    int(
                        (
                            self._break_ends_at
                            - datetime.now()
                        ).total_seconds()
                    )
                )

                remaining = "{:02d}:{:02d}".format(
                    secs // 60,
                    secs % 60
                )

            self.status_panel.set_text(
                f"☕ Break · {remaining} left"
            )

            # Show the motivating line once as the break winds down while
            # keeping the message stable (changing it every tick would
            # make the bubble flicker).
            if self._break_ends_at is not None and secs <= 10:
                head = self._current_break_message()

                if self.message.text() != head:
                    self.message.setText(
                        head
                    )
        elif self._scheduled_start_at is not None:
            self.status_panel.set_text(
                f"🕒 Starting at {self._schedule_label()}"
            )
        else:
            self.status_panel.set_text(
                ""
            )

    # ========================================================
    # ONBOARDING (first launch)
    # ========================================================

    def _begin_onboarding(self):

        # Walk the character in for the first-launch introduction. The
        # walk-in uses the shared startup-greeting path (excited_waving +
        # "Hey!") so a brand-new user first sees the short self-intro,
        # which then hands control to the existing v1.0 onboarding flow.
        self._reset_offscreen()

        self._returning = False

        self._break_done_pending = False

        self._busy = False

        self._startup_greeting = True

        self.message.setText(
            CHARACTER_DIALOGUE["greeting"]
        )

        self._set_character(
            "walking_in"
        )

        self._walk_action = "in"

        self.walk_timer.start(
            30
        )

    def _show_onboarding_intro(self):

        self._hide_all_choices()

        self.message.setText(
            CHARACTER_DIALOGUE["onboarding_intro"]
        )

        # The character just walked in; greet with an excited wave.
        self._set_character(
            "excited_waving"
        )

        # After a brief pause, prompt the user to set up their schedule.
        QTimer.singleShot(
            2500,
            self._show_onboarding_setup
        )

    def _show_onboarding_setup(self):

        # This is only ever reached through the onboarding route preserved
        # at startup (self._startup_onboarding), so there is no need to
        # re-check the mutable onboarding_completed setting here. Returning
        # silently because of unrelated settings state would interrupt the
        # new-user startup sequence, so this method always proceeds.
        self.message.setText(
            CHARACTER_DIALOGUE["onboarding_setup"]
        )

        self._set_character(
            "energetic_encouraging"
        )

        self.onboarding_settings_button.show()

        self._set_choices_enabled(
            True
        )

    def _complete_onboarding(self):

        # Called after the initial settings are saved. Show a short
        # confirmation, then ask whether the user is starting work now
        # (or settle into idle if reminders were explicitly disabled).
        minutes = int(
            self.settings.get(
                "work_interval_minutes",
                30
            )
        )

        self._hide_all_choices()

        self.message.setText(
            CHARACTER_DIALOGUE["onboarding_complete"].format(
                minutes=minutes
            )
        )

        self._set_character(
            "happy_proud"
        )

        QTimer.singleShot(
            2200,
            self._onboarding_finish
        )

    def _onboarding_finish(self):

        # The confirmation is done. Reminders enabled -> ask whether the
        # user is starting work now (no timer runs yet). Disabled -> the
        # companion stops and hides.
        if self._should_prompt():
            self._show_start_work_prompt()
        else:
            self._stop_after_walkout()

    def show_main_reminder(self):

        _debug(
            "main reminder shown"
        )

        # The reminder walk-in finished; the choices are now live, so the
        # busy guard set by _on_reminder_fire is released.
        self._busy = False

        # A new work-based reminder transaction begins here; count it as
        # one reminder cycle. Later postponements do NOT increment this.
        self._reminders_shown += 1

        # Only the intended reminder choices are visible; any stale
        # startup/schedule buttons are cleared first.
        self._hide_all_choices()

        self.message.setText(
            REMINDER_MESSAGES["first"]["message"]
        )

        # The actual reminder appears: switch from the entrance pose to a
        # concerned look and play the reminder sound.
        self._set_character(
            "concerned"
        )

        play_sound(
            "reminder.wav"
        )

        self.ok_button.show()
        self.later_button.show()
        self.yes_button.hide()
        self.no_button.hide()
        self.stop_button.show()

        self._set_choices_enabled(
            True
        )

    def _hide_all_choices(self):

        self.ok_button.hide()
        self.later_button.hide()
        self.yes_button.hide()
        self.no_button.hide()
        self.stop_button.hide()
        self.onboarding_settings_button.hide()
        self.start_now_button.hide()
        self.choose_time_button.hide()
        self.not_yet_button.hide()
        self.start_work_button.hide()
        self.dialogue_panel.close_button.hide()

    # ========================================================
    # OKAY
    # ========================================================

    def accept_reminder(self):

        if self._busy:
            return

        self._busy = True

        self._set_choices_enabled(
            False
        )

        self.message.setText(
            CHARACTER_DIALOGUE["accept"]
        )

        self._hide_all_choices()

        # User accepts the break: start sound plays, then the happy
        # reaction and happy walk-away pose while it leaves.
        play_sound(
            "break_start.wav"
        )

        self._set_character(
            "happy_thumbs_up"
        )

        QTimer.singleShot(
            1500,
            self._complete_accept_happy
        )

    def _complete_accept_happy(self):

        # The happy walk-away pose is the visual state shown
        # while the character animates off the screen.
        self._set_character(
            "happy_walk_away"
        )

        self._start_walk_out(
            self._begin_break
        )

    def _complete_accept(self):

        # Reminders stop: walk out and hide, keep the app running.
        self._start_walk_out(
            self._stop_after_walkout
        )

    def _stop_after_walkout(self):

        self._stop_reminder_timer()

        self._stop_break_timer()

        # No session is running anymore: the companion settles into the
        # idle state. It can be started again later via "Start Work".
        self._session_state = "idle"

        # The reaction transaction has fully finished; clear the busy
        # guard so the Companion can be manually shown again later.
        self._busy = False

        # Clear status markers so the status line blanks out cleanly.
        self._status_started_at = None

        self._break_ends_at = None

        self._sync_status_timer()

        self.hide()

    # ========================================================
    # BREAK (after a break is accepted)
    # ========================================================

    def _begin_break(self):

        # Called once the walk-out animation has finished following an
        # accepted break. No other timers should be running: the break
        # timer is the single next step.
        self._stop_reminder_timer()

        self._reset_offscreen()

        self._busy = False

        self._session_state = "break"

        self._break_ends_at = (
            datetime.now()
            + timedelta(
                milliseconds=self._break_ms()
            )
        )

        self._break_message = random.choice(
            BREAK_MESSAGES
        )

        self._break_warned = False

        # Show the break status + stable chilled dialogue, then auto-hide
        # after a short peek so the character does not stand on screen for
        # the whole break. The break timer keeps counting in the
        # background; the companion returns when the break is over.
        self._hide_all_choices()

        self.message.setText(
            self._break_message
        )

        self._set_character(
            "standing"
        )

        self.current_x = self.final_x

        self.move(
            self.current_x,
            self.final_y
        )

        self.show()

        self.auto_hide_timer.start(
            PEEK_AUTO_HIDE_MS
        )

        self._sync_status_timer()

        self._start_break_timer()

    def _on_break_fire(self):

        # The break has finished; the character returns and announces
        # the break is over before the next work interval begins.
        self._stop_break_timer()

        # A pending peek walk-away must not fight the break-completion
        # return.
        self.auto_hide_timer.stop()

        _debug(
            "break over -> return walk-in"
        )

        # Clear any stale arrival route from a manual "Show Companion"
        # that was in progress when the break ended: the break-return
        # walk-in replaces whatever was queued.
        self._prompt_on_arrival = False

        self._quiet_return = False

        if not self._should_prompt():
            self.hide()
            return

        self._returning = True

        self._break_done_pending = True

        self._busy = True

        # If the companion is already settled on screen (still showing the
        # break countdown), announce completion where it stands: no
        # teleport off-screen and no redundant walk-in. Only a hidden
        # companion walks in for the completion announcement.
        if self.isVisible() and self._walk_action is None:
            self._walk_out_done = None
            self._show_break_done()
            return

        self._walk_out_done = None

        self._reset_offscreen()

        # Reveal the companion before walking back in to announce the
        # break is over (WA_ShowWithoutActivating keeps it from stealing
        # focus).
        self.show()

        # Reset the dialogue so the previous reaction text does not leak
        # into this return walk-in; the break-completion message is shown
        # fresh on arrival.
        self._hide_all_choices()

        self.message.setText(
            CHARACTER_DIALOGUE["returning_to_work"]
        )

        # Reuse the happy_return -> peek -> standing entrance used for
        # other returns so the break-completion return feels consistent.
        self._set_character(
            "happy_return"
        )

        self._walk_action = "in"

        self.walk_timer.start(
            30
        )

    def _show_break_done(self):

        self._break_done_pending = False

        self.message.setText(
            CHARACTER_DIALOGUE["break_done"]
        )

        self._hide_all_choices()

        # Break is over: show the refreshed, happy pose and play the
        # break-over sound.
        self._set_character(
            "refreshed_happy"
        )

        play_sound(
            "break_over.wav"
        )

        # Briefly hold the break-completed announcement, then move on to
        # the next work interval (or stop the cycle).
        QTimer.singleShot(
            2500,
            self._go_to_work_state
        )

    def _go_to_work_state(self):

        # Walk the character away / back into its resting position, then
        # start the next work interval or stop the cycle entirely.
        self._start_walk_out(
            self._finish_break_and_work
        )

    def _finish_break_and_work(self):

        self._busy = False

        if self._continue_after_break():
            self._start_work_interval()
        else:
            self._stop_after_walkout()

    def _continue_after_break(self):

        if not self._should_prompt():
            return False

        mode = self.settings.get(
            "reminder_mode",
            "three_times"
        )

        if mode == "stop_after_one":
            return False

        if mode == "three_times":
            return (
                self._reminders_shown < 3
            )

        # keep_reminding -> unlimited
        return True

    def _start_work_interval(self):

        # Clear any in-flight timers, hide the companion, and schedule
        # the next reminder after the work interval elapses.
        self._stop_reminder_timer()

        self._stop_break_timer()

        self._reset_offscreen()

        self._returning = False

        self._break_done_pending = False

        self._busy = False

        self._session_state = "working"

        self._status_started_at = datetime.now()

        self._working_message = random.choice(
            WORKING_MESSAGES
        )

        self._break_ends_at = None

        self._sync_status_timer()

        self.hide()

        _debug(
            f"work interval started ({self._work_interval_ms()} ms)"
        )

        self._start_reminder_timer(
            self._work_interval_ms()
        )

    # ========================================================
    # LATER (refusal on the first reminder)
    # ========================================================

    def delay_reminder(self):

        if self._busy:
            return

        self._busy = True

        self._set_choices_enabled(
            False
        )

        self.message.setText(
            CHARACTER_DIALOGUE["first_refusal"]
        )

        self._hide_all_choices()

        # Later: play the later sound, then show the sad reaction while
        # deciding what to do next.
        play_sound(
            "later.wav"
        )

        self._set_character(
            "sad_tears"
        )

        QTimer.singleShot(
            1500,
            self._begin_refusal_first
        )

    def _begin_refusal_first(self):

        # First-reminder refusal: use the angry walk-away pose
        # while the character leaves the screen.
        self._set_character(
            "angry_walk_away"
        )

        self._begin_refusal()

    def _begin_refusal(self):

        if self._allow_another_reminder():
            self._start_walk_out(
                self._schedule_next_reminder
            )
        else:
            self._start_walk_out(
                self._stop_after_walkout
            )

    def _schedule_next_reminder(self):

        # Reset character to its off-screen start position.
        self._reset_offscreen()

        # This is a Later-delayed return, so the character comes back
        # for a second-style reminder after the delay elapses.
        self._returning = True

        # Stop-then-start guarantees only one delayed reminder is
        # ever scheduled, even across repeated interactions.
        self._start_reminder_timer(
            self._delay_ms()
        )

        # The refusal transaction has finished; clear the busy guard so
        # the Companion can be manually shown again while the reminder
        # is pending.
        self._busy = False

    def _delay_ms(self):

        minutes = int(
            self.settings.get(
                "delay_minutes",
                5
            )
        )

        return (
            minutes
            * 60
            * 1000
        )

    def _work_interval_ms(self):

        minutes = int(
            self.settings.get(
                "work_interval_minutes",
                30
            )
        )

        return (
            minutes
            * 60
            * 1000
        )

    def _break_ms(self):

        minutes = int(
            self.settings.get(
                "break_duration_minutes",
                5
            )
        )

        return (
            minutes
            * 60
            * 1000
        )

    def _start_reminder_timer(self, ms):

        # Stop-then-start so repeated scheduling can never leave
        # more than one active reminder timer behind.
        self.reminder_timer.stop()

        _debug(
            f"reminder timer armed for {ms} ms"
        )

        self.reminder_timer.start(
            ms
        )

    def _stop_reminder_timer(self):

        if self.reminder_timer.isActive():
            _debug(
                "reminder timer stopped"
            )

        self.reminder_timer.stop()

    def _start_break_timer(self):

        # Stop-then-start so a break is never scheduled more than once.
        self.break_timer.stop()

        _debug(
            f"break timer armed for {self._break_ms()} ms"
        )

        self.break_timer.start(
            self._break_ms()
        )

    def _stop_break_timer(self):

        if self.break_timer.isActive():
            _debug(
                "break timer stopped"
            )

        self.break_timer.stop()

    def _allow_another_reminder(self):

        # "Later" is only a postponement of the CURRENT reminder
        # transaction. It is allowed as long as reminders are enabled and
        # never consumes an additional reminder-cycle slot; the number of
        # actual cycles is bounded by _continue_after_break instead.
        return self._should_prompt()

    # ========================================================
    # REMINDER FIRE -> RETURN
    # ========================================================

    def _on_reminder_fire(self):

        self._stop_reminder_timer()

        # A pending peek walk-away must never swallow the reminder that is
        # arriving; the reminder return replaces it.
        self.auto_hide_timer.stop()

        self._walk_out_done = None

        _debug(
            "reminder fired -> walk-in"
        )

        # Clear any stale arrival route from a manual "Show Companion"
        # that was in progress when the reminder fired: the reminder
        # walk-in replaces whatever was queued.
        self._prompt_on_arrival = False

        self._quiet_return = False

        if not self._should_prompt():
            self._busy = False
            self.hide()
            return

        # Mark the reminder walk-in as busy so a tray "Show Companion"
        # cannot steal the in-progress arrival and swallow the reminder.
        # The guard is released once the reminder choices go live.
        self._busy = True

        # Character starts off-screen again, then walks back in. Whether
        # this is a work-interval return (fresh main reminder) or a
        # Later-delayed return (second reminder) is decided by the
        # pre-set _returning flag; _after_walk_in routes accordingly.
        self._reset_offscreen()

        # The companion may have been hidden during the work interval;
        # reveal it before walking in (WA_ShowWithoutActivating keeps it
        # from stealing focus).
        self.show()

        # Reset the dialogue so no previous reaction text leaks into this
        # walk-in. A work-interval return shows a fresh greeting; a
        # Later-delayed return shows the second greeting. The actual
        # reminder message is set fresh on arrival.
        self._hide_all_choices()

        if self._returning:
            self.message.setText(
                CHARACTER_DIALOGUE["second_greeting"]
            )
        else:
            self.message.setText(
                CHARACTER_DIALOGUE["greeting"]
            )

        # The character happily returns, shown while walking back in.
        self._set_character(
            "happy_return"
        )

        self._walk_action = "in"

        self.walk_timer.start(
            30
        )

    # ========================================================
    # SECOND REMINDER
    # ========================================================

    def show_second_reminder(self):

        # A Later postponement re-shows the current reminder transaction.
        # It does NOT consume an additional reminder-cycle slot.
        self.message.setText(
            CHARACTER_DIALOGUE["second_greeting"]
        )

        self._hide_all_choices()

        QTimer.singleShot(
            1500,
            self._show_second_choices
        )

    def _show_second_choices(self):

        _debug(
            "second reminder choices shown"
        )

        self._busy = False

        # Only the intended second-reminder choices are visible; any
        # stale reminder/startup buttons are cleared first.
        self._hide_all_choices()

        self.message.setText(
            REMINDER_MESSAGES["second"]["message"]
        )

        # Final reminder after choosing Later: show a pleading look and
        # play the reminder sound.
        self._set_character(
            "pleading"
        )

        play_sound(
            "reminder.wav"
        )

        self.yes_button.show()
        self.no_button.show()
        self.ok_button.hide()
        self.later_button.hide()
        self.stop_button.show()

        self._set_choices_enabled(
            True
        )

    # ========================================================
    # SECOND REMINDER CHOICES
    # ========================================================

    def accept_second(self):

        if self._busy:
            return

        self._busy = True

        self._set_choices_enabled(
            False
        )

        self.message.setText(
            CHARACTER_DIALOGUE["second_accept"]
        )

        self._hide_all_choices()

        # Second-reminder accept: break starts, so play the start sound,
        # then the satisfied reaction and happy walk-away pose.
        play_sound(
            "break_start.wav"
        )

        self._set_character(
            "satisfied"
        )

        QTimer.singleShot(
            1500,
            self._complete_accept_happy
        )

    def refuse_second(self):

        if self._busy:
            return

        self._busy = True

        self._set_choices_enabled(
            False
        )

        self.message.setText(
            CHARACTER_DIALOGUE["second_refusal"]
        )

        self._hide_all_choices()

        # Second-reminder refusal: show frustration, then the
        # second angry walk-away pose while leaving.
        self._set_character(
            "frustrated"
        )

        QTimer.singleShot(
            1500,
            self._begin_refusal_second
        )

    def _begin_refusal_second(self):

        self._set_character(
            "angry_walk_away_2"
        )

        self._begin_refusal()

    # ========================================================
    # STOP (immediate automatic-cycle escape)
    # ========================================================

    def stop_reminders(self):

        if self._busy:
            return

        self._busy = True

        self._set_choices_enabled(
            False
        )

        self.message.setText(
            CHARACTER_DIALOGUE["stop"]
        )

        self._hide_all_choices()

        # Look dramatically/sadly expressive before walking away, and
        # play the stop sound.
        self._set_character(
            "dramatic_goodbye"
        )

        play_sound(
            "stop.wav"
        )

        QTimer.singleShot(
            1500,
            self._complete_stop
        )

    def _complete_stop(self):

        # No work interval, reminder, or break timer should remain.
        # stop_after_walkout also hides the companion and clears _busy.
        self._stop_reminder_timer()

        self._stop_break_timer()

        self._break_done_pending = False

        self._start_walk_out(
            self._stop_after_walkout
        )

    # ========================================================
    # CHOICE HELPERS
    # ========================================================

    def _set_choices_enabled(self, enabled):

        for button in (
            self.ok_button,
            self.later_button,
            self.yes_button,
            self.no_button,
            self.stop_button,
            self.onboarding_settings_button,
            self.start_now_button,
            self.choose_time_button,
            self.not_yet_button,
            self.start_work_button,
        ):
            button.setEnabled(
                enabled
            )


# ============================================================
# APPLICATION
# ============================================================

if __name__ == "__main__":

    app = QApplication(
        sys.argv
    )

    # App name drives the config-folder path (%APPDATA%\\DesktopCompanion).
    app.setApplicationName(
        "DesktopCompanion"
    )

    # -----------------------------
    # SINGLE-INSTANCE LOCK
    # -----------------------------
    # Acquire a per-user lock before creating any Companion, tray icon,
    # or timers. If another instance already owns the lock, exit cleanly
    # instead of starting a second tray/timers.
    lock_dir = Path(
        QStandardPaths.writableLocation(
            QStandardPaths.AppConfigLocation
        )
    )

    try:
        lock_dir.mkdir(
            parents=True,
            exist_ok=True
        )
    except Exception:
        pass

    lock = QLockFile(
        str(lock_dir / "companion.lock")
    )

    lock.tryLock(0)

    if not lock.isLocked():
        # Another DesktopCompanion instance is already running.
        sys.exit(0)

    print("1. QApplication created")

    companion = Companion()

    print("2. Companion created")

    companion.show()

    print("3. Companion shown")

    sys.exit(
        app.exec()
    )