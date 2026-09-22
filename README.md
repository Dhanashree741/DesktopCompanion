# 🖥️ Desktop Companion

> A small desktop companion that reminds you to take breaks while you work — without getting in your way.

Desktop Companion is a Windows productivity app built with **Python and PySide6**. It uses a friendly animated character, work/break reminders, sounds, and session tracking to encourage healthier work habits.

The goal is simple:

**Work → Take a break → Get back to work.**

---

## ✨ Features

* **Work & break rhythm** — Set how long you want to work and how long your breaks should be.
* **Break reminders** — Get reminded when you've been working for a while.
* **Break timer** — Accepting a break starts a dedicated break countdown.
* **Scheduled starts** — Schedule a time to start a work session.
* **Daily session tracking** — Track completed sessions and total working time for the day.
* **Persistent daily progress** — Your session count and accumulated work time survive app restarts.
* **Sound effects** — Audio cues for important moments such as starting work, starting/ending breaks, reminders, and stopping.
* **System tray support** — The companion can stay out of the way while you work.
* **Animated companion** — Different character states make reminders feel more personal.
* **Single-instance protection** — Opening another copy while the app is already running exits silently.
* **Customizable reminders** — Choose how often the companion reminds you and how long to wait after choosing "Later."

---

## 🧠 How It Works

### 1. Set your work rhythm

Choose your:

* Work duration
* Break duration
* Reminder behavior

Once configured, the companion handles the rhythm for you.

### 2. Work

Start a work session and the companion gets out of your way.

Your current session time and daily progress are tracked separately.

### 3. Take a break

When your work interval is complete, the companion checks in.

You can:

* **Take the break** → the break timer starts.
* **Later** → continue working and get reminded again according to your settings.

### 4. Get back to work

When the break ends, the companion returns and lets you start another work session or finish for the day.

### 5. Check your progress

At the end of the day, the app shows your accumulated working time and completed sessions.

---

## 🛠️ Tech Stack

* **Python 3**
* **PySide6 / Qt**
* **PyInstaller**
* **Git / GitHub**
* **Windows**

---

## 📁 Project Structure

```text
DesktopCompanion/
│
├── assets/
│   ├── character assets
│   └── sounds/
│       ├── break_over.wav
│       ├── break_start.wav
│       ├── later.wav
│       ├── reminder.wav
│       ├── stop.wav
│       └── work_start.wav
│
├── main.py
├── DesktopCompanion.spec
├── requirements.txt
└── .gitignore
```

---

## 🚀 Run From Source

### 1. Clone the repository

```bash
git clone https://github.com/Dhanashree741/DesktopCompanion.git
cd DesktopCompanion
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Activate it on Windows:

```powershell
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the application

```bash
python main.py
```

---

## 📦 Build the Windows EXE

The project uses PyInstaller.

```powershell
python -m PyInstaller --noconfirm --clean DesktopCompanion.spec
```

The packaged application will be created in:

```text
dist/DesktopCompanion.exe
```

---

## 🎯 Why I Built This

Desktop Companion started from a simple idea:

**What if taking breaks felt less like another productivity task and more like someone reminding you to look away from the screen?**

Instead of building another complicated productivity dashboard, I wanted something small, visual, and easy to keep running in the background.

The character is intentionally a little persistent — because apparently "I'll take a break later" is a very powerful sentence. 

---

## 🔮 Possible Future Improvements

Ideas for future versions may include:

* More character animations
* More sound/theme options
* Additional productivity statistics
* More customization options
* Improved onboarding
* Additional reminder patterns

---

## 📄 License

This project is currently provided for personal and educational use.

---

Made with Python, PySide6, and a slightly annoying desktop companion. 💻👀
