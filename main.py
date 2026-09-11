import sys
import json
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
from PySide6.QtCore import Qt, QTimer, QStandardPaths, QLockFile, QRect
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
    "break_done": "Break's over!\nHope you feel refreshed. 🙂",
    "returning_to_work": "Alright!\nBack to work. 💪",
    "onboarding_intro": "Hey! I'm your Desktop Companion! 👋\nI'll remind you to take regular breaks\nwhile you're working.",
    "onboarding_setup": "Let's set up your schedule! 💪",
    "onboarding_complete": "Perfect! I'll remind you after {minutes} minutes. 🙂",
    "stop": "Okay! I'll stop bothering you. 😌",
}

# Startup introduction sequence shown after the companion walks in.
# Each entry is (message, pause_ms): the message is shown, then after
# pause_ms the next message takes its place. The final entry's pause is
# followed by clearing the bubble and settling into the standing/idle
# state. This is purely additive and never touches the reminder timer.
STARTUP_INTRO = [
    ("I'm your Desktop Companion! 💻✨", 1500),
    ("I'll remind you to take regular breaks\nwhile you work!", 1500),
    ("Let's get started! 🚀", 1000),
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
            "Work interval:"
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
            "Break duration:"
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
            "How often should I be reminded?"
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
# COMPANION
# ============================================================

class Companion(QWidget):

    def __init__(self):

        super().__init__()

        # Load persisted user settings.
        self.settings = load_settings()

        # How many reminders have actually been shown this session.
        self._reminders_shown = 0

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

        for button in (
            self.ok_button,
            self.later_button,
            self.yes_button,
            self.no_button,
            self.stop_button,
            self.onboarding_settings_button,
        ):
            button.setFixedWidth(115)

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

        # Choices are hidden until their dialogue needs them.
        self.ok_button.hide()
        self.later_button.hide()
        self.yes_button.hide()
        self.no_button.hide()
        self.stop_button.hide()
        self.onboarding_settings_button.hide()

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

        button_layout.addStretch()

        # ====================================================
        # DIALOGUE PANEL
        # ====================================================

        self.dialogue_panel = DialoguePanel()

        dialogue_layout = QVBoxLayout()

        dialogue_layout.setContentsMargins(
            7,
            5,
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
        # OPTIONS AREA
        # -----------------------------

        dialogue_layout.addSpacing(0)

        dialogue_layout.addLayout(
            button_layout
        )

        self.dialogue_panel.setLayout(
            dialogue_layout
        )

        dialogue_layout.addStretch(1)
        
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

        # Set when the character returns from a break to show the
        # break-completion dialogue instead of a reminder.
        self._break_done_pending = False

        # True while the companion is performing the startup greeting
        # (walk in -> wave -> settle). Suppresses the normal reminder
        # routing in the shared walk-in settle so no reminder fires early.
        self._startup_greeting = False

        # True while the additive startup self-introduction message chain
        # is running. Guards against ever scheduling a second chain.
        self._startup_intro_active = False

        # Which route the startup sequence takes, decided exactly once at
        # startup and preserved for the whole greeting/animation chain.
        # A brand-new user (False) runs the startup intro as a prelude to
        # the original v1.0 onboarding; a returning user (True) runs the
        # intro as a prelude to the normal idle/parked state. This flag is
        # intentionally NOT re-derived from the mutable settings mid-flow.
        self._startup_onboarding = False

        self._setup_tray()

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
            # Enabled: begin a fresh work interval. The companion greets
            # the user at startup but keeps the first reminder timer
            # scheduled for the full work interval, then settles back
            # into its normal idle/parked state.
            self._begin_reminder_cycle_with_greeting()
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
            #  * Returning user  -> clear the bubble and settle into the
            #    normal standing/idle state.
            #
            # _after_walk_in() is deliberately NOT called here: for an
            # already-onboarded user that would fire show_main_reminder()
            # immediately. The reminder timer is left untouched and keeps
            # running, so no reminder fires early.
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
        # touches the reminder timer, which keeps running as configured.
        # Once every message has been shown, the on_done callback takes
        # over so the intro is a prelude to (not a replacement for) the
        # existing onboarding / idle behavior.
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

        # Returning-user post-introduction state: clear the dialogue
        # bubble and settle the character into its normal standing/idle
        # pose. The reminder timer keeps running as already scheduled.
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

        self.show()

        self.raise_()

        # Manually showing the companion cancels any pending scheduled
        # reminder or break so no stale timer can fire right after and
        # create a duplicate. The manual show becomes the active one and
        # starts no work/reminder/break timer of its own.
        self._stop_reminder_timer()

        self._stop_break_timer()

        self._reset_offscreen()

        self._returning = False

        self._break_done_pending = False

        self._busy = False

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
            ) and not self._has_active_cycle():
                # Re-enabled reminders from a quiet state -> start a cycle.
                self._begin_reminder_cycle()

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

    def _has_active_cycle(self):

        # A cycle is active whenever the companion is on screen, busy,
        # or has a work/reminder/break timer scheduled.
        return (
            self.isVisible()
            or self._busy
            or self.reminder_timer.isActive()
            or self.break_timer.isActive()
        )

    def _begin_reminder_cycle(self):

        # Begin a fresh work -> break -> work cycle from a quiet state:
        # reset counters and start the work interval timer.
        self._reminders_shown = 0

        self._start_work_interval()

    def _begin_reminder_cycle_with_greeting(self):

        # Same as _begin_reminder_cycle: it schedules the single first
        # reminder timer for the full work interval and resets counters.
        # The companion is hidden/off-screen by that logic, so afterwards
        # we walk it back in for a brief startup greeting without
        # touching the already-scheduled reminder timer.
        self._begin_reminder_cycle()

        # Greeting: reveal the companion off-screen and walk it in with
        # an excited wave plus the standard "Hey!" message.
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
            self._idle_greeting()
            return

        if self._break_done_pending:
            self._show_break_done()
            return

        if self._returning:
            self.show_second_reminder()
        else:
            self.show_main_reminder()

    def _should_prompt(self):

        return bool(
            self.settings.get(
                "enabled",
                True
            )
        )

    def _idle_greeting(self):

        self.message.setText(
            CHARACTER_DIALOGUE["greeting"]
        )

        # Greeting pose: an excited wave while staying visible.
        self._set_character(
            "excited_waving"
        )

        self._hide_all_choices()

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
        # confirmation, then hand off to the normal work cycle (or idle,
        # if reminders were explicitly disabled).
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

        # The confirmation is done; either start the configured work
        # interval or go idle (reminders disabled). No immediate break
        # reminder is shown here.
        if self._should_prompt():
            self._begin_reminder_cycle()
        else:
            self._stop_after_walkout()

    def show_main_reminder(self):

        # A new work-based reminder transaction begins here; count it as
        # one reminder cycle. Later postponements do NOT increment this.
        self._reminders_shown += 1

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

        # The reaction transaction has fully finished; clear the busy
        # guard so the Companion can be manually shown again later.
        self._busy = False

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

        self.hide()

        self._start_break_timer()

    def _on_break_fire(self):

        # The break has finished; the character returns and announces
        # the break is over before the next work interval begins.
        self._stop_break_timer()

        if not self._should_prompt():
            self.hide()
            return

        self._reset_offscreen()

        self._returning = True

        self._break_done_pending = True

        self._busy = True

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

        self.hide()

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

        self.reminder_timer.start(
            ms
        )

    def _stop_reminder_timer(self):

        self.reminder_timer.stop()

    def _start_break_timer(self):

        # Stop-then-start so a break is never scheduled more than once.
        self.break_timer.stop()

        self.break_timer.start(
            self._break_ms()
        )

    def _stop_break_timer(self):

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

        if not self._should_prompt():
            self.hide()
            return

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

        self._busy = False

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