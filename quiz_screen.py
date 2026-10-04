"""Screen helper for the quiz-solver skill.

Usage:
    python quiz_screen.py calibrate          # click 10 spots on a see-through overlay
    python quiz_screen.py calibrate next     # re-pick only the named spot(s), keep the rest
    python quiz_screen.py shot               # screenshot the quiz area (no clicks), print the PNG path
    python quiz_screen.py answer B high      # re-check screen, click answer + confidence, press Next
    python quiz_screen.py presets            # list saved presets
    python quiz_screen.py --preset NAME create   # make a NEW preset (refuses if it exists)
    python quiz_screen.py stop               # stop flag: shot/answer refuse to act (exit 5)
    python quiz_screen.py start              # clear the stop flag (start of every run)
    Put `--preset NAME` first to use presets/NAME.json instead of config.json,
    e.g. `python quiz_screen.py --preset mgh calibrate`.

Exit codes: 0 ok, 1 bad usage / no calibration, 2 selections didn't register,
3 page didn't change after Next, 4 screen changed since the last shot (nothing clicked),
5 stopped by the user (nothing done).
"""
import ctypes
import json
import sys
import time
from pathlib import Path

# Use real screen pixels everywhere (overlay, clicks, screenshots) so the
# numbers saved at calibration match the numbers used later, at any Windows
# display scaling.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (AttributeError, OSError):
    ctypes.windll.user32.SetProcessDPIAware()

import pyautogui
from PIL import Image, ImageChops, ImageGrab

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "config.json"     # the default (no preset named)
PRESETS = HERE / "presets"
SHOTS = HERE / "shots"
RESERVED = {"reset", "next", "presets", "default", "stop", "start", "create"}
STOP_FLAG = HERE / "STOP"   # global: stops every run, whatever preset

# Order the user clicks during calibration.
STEPS = [
    ("region_tl", "TOP-LEFT corner of the quiz area"),
    ("region_br", "BOTTOM-RIGHT corner of the quiz area"),
    ("A", "answer button A"),
    ("B", "answer button B"),
    ("C", "answer button C"),
    ("D", "answer button D"),
    ("high", "confidence HIGH"),
    ("medium", "confidence MEDIUM"),
    ("low", "confidence LOW"),
    ("next", "the NEXT button"),
]

pyautogui.PAUSE = 0.15  # small gap after each click so the page keeps up


def load_config():
    if not CONFIG.exists():
        print(f"NOT CALIBRATED: no saved spots at {CONFIG}. Saved presets: {preset_names()}")
        sys.exit(1)
    cfg = json.loads(CONFIG.read_text())
    size = list(pyautogui.size())
    if cfg.get("screen_size") != size:
        print(f"WARNING: screen size is {size} but calibration was done at "
              f"{cfg.get('screen_size')}. Re-calibrate if clicks miss.")
    return cfg


def region_box(cfg):
    # The picked zone, stretched to include every spot we click (plus a
    # margin), so the "screen changed?" check covers every click target.
    pts = [cfg["region_tl"], cfg["region_br"]] + [cfg[k] for k, _ in STEPS[2:]]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    pad = 30
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def grab(cfg):
    return ImageGrab.grab(bbox=region_box(cfg), all_screens=True)


def grab_patch(point, half=40):
    x, y = point
    return ImageGrab.grab(bbox=(x - half, y - 12, x + half, y + 12), all_screens=True)


def press(point):
    # Move first, let the cursor settle, then click. A combined fast
    # move+click was seen registering at the PREVIOUS cursor spot.
    pyautogui.moveTo(*point)
    time.sleep(0.08)
    pyautogui.click()


def park(cfg):
    # Rest the mouse on a harmless spot just inside the quiz area so hover
    # colors don't show up in screenshots.
    x, y = cfg["region_tl"]
    pyautogui.moveTo(x + 6, y + 6)


def calibrate(only=None):
    # only = list of spot names to re-pick (e.g. ["next"]); the rest are kept.
    import tkinter as tk

    steps = STEPS
    keep = {}
    if only:
        bad = [k for k in only if k not in dict(STEPS)]
        if bad:
            print(f"BAD USAGE: unknown spot(s) {bad}. Known: {[k for k, _ in STEPS]}")
            sys.exit(1)
        keep = load_config()
        steps = [s for s in STEPS if s[0] in only]

    root = tk.Tk()
    root.title("quiz-solver setup")
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.35)
    root.configure(bg="black", cursor="crosshair")
    canvas = tk.Canvas(root, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    label = tk.Label(root, font=("Segoe UI", 20, "bold"), fg="yellow", bg="black")
    label.place(relx=0.5, y=30, anchor="n")

    points = {}
    step = [0]

    def show():
        key, desc = steps[step[0]]
        label.config(text=f"Step {step[0] + 1}/{len(steps)}: click {desc}   (Esc = cancel)")

    def on_click(event):
        key, _ = steps[step[0]]
        points[key] = [event.x_root, event.y_root]
        canvas.create_oval(event.x_root - 6, event.y_root - 6, event.x_root + 6,
                           event.y_root + 6, fill="red", outline="white")
        step[0] += 1
        if step[0] == len(steps):
            root.after(300, root.destroy)
        else:
            show()

    root.bind_all("<Button-1>", on_click)
    root.bind_all("<Escape>", lambda e: root.destroy())
    show()
    root.mainloop()

    if len(points) != len(steps):
        print("CANCELLED: calibration not saved.")
        sys.exit(1)
    points = {**keep, **points, "screen_size": list(pyautogui.size())}
    CONFIG.write_text(json.dumps(points, indent=2))
    print(f"SAVED: {CONFIG} ({', '.join(k for k, _ in steps)})")


def same_screen(a, b):
    # Allow a sliver of noise (e.g. font smoothing); anything bigger means
    # the zone shows something else now.
    if a.size != b.size:
        return False
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L")
    changed = sum(diff.point(lambda v: 255 if v > 30 else 0).histogram()[255:])
    return changed <= a.size[0] * a.size[1] * 0.005


def check_stop():
    if STOP_FLAG.exists():
        print("STOPPED: the run was stopped by the user. Nothing was done.")
        sys.exit(5)


def shot():
    # No clicks here: a screenshot copies whatever is visible, and a click
    # would land on whatever window happens to sit in the zone.
    check_stop()
    cfg = load_config()
    park(cfg)
    time.sleep(0.2)
    SHOTS.mkdir(exist_ok=True)
    path = SHOTS / f"q_{time.strftime('%Y%m%d_%H%M%S')}.png"
    grab(cfg).save(path)
    (SHOTS / "last.txt").write_text(str(path))
    print(path)


def answer(letter, level):
    letter, level = letter.upper(), level.lower()
    if letter not in "ABCD" or len(letter) != 1 or level not in ("high", "medium", "low"):
        print("BAD USAGE: answer <A|B|C|D> <high|medium|low>")
        sys.exit(1)
    check_stop()
    cfg = load_config()

    # Only click if the zone still shows exactly what the helper read.
    last = SHOTS / "last.txt"
    if not last.exists():
        print("NO SHOT: run `shot` first.")
        sys.exit(1)
    park(cfg)
    time.sleep(0.2)
    if not same_screen(Image.open(last.read_text().strip()), grab(cfg)):
        print("SCREEN CHANGED: the quiz area no longer matches the screenshot the "
              "helper read. Nothing was clicked.")
        sys.exit(4)

    next_before = grab_patch(cfg["next"])

    press(cfg[letter])
    press(cfg[level])
    park(cfg)
    time.sleep(0.3)

    # The Next button should look different once it unlocks.
    if ImageChops.difference(next_before, grab_patch(cfg["next"])).getbbox() is None:
        print("STUCK: Next button didn't change after picking answer + confidence. "
              "Clicks probably missed -- re-calibrate.")
        sys.exit(2)

    # Snapshot with the selections showing, so "nothing changed" really
    # means Next did nothing.
    before_page = grab(cfg)
    press(cfg["next"])
    park(cfg)
    time.sleep(0.6)

    if ImageChops.difference(before_page, grab(cfg)).getbbox() is None:
        print("STUCK: page looks the same after pressing Next.")
        sys.exit(3)
    print(f"CLICKED: {letter} + {level} + Next")


def preset_names():
    return sorted(f.stem for f in PRESETS.glob("*.json")) if PRESETS.exists() else []


if __name__ == "__main__":
    import re
    args = sys.argv[1:]
    if args[:1] == ["--preset"]:
        if len(args) < 2 or not re.fullmatch(r"[a-z0-9_-]{1,40}", args[1]) or args[1] in RESERVED:
            print(f"BAD PRESET NAME: use lowercase letters, numbers, - or _ "
                  f"(not {sorted(RESERVED)}).")
            sys.exit(1)
        PRESETS.mkdir(exist_ok=True)
        CONFIG = PRESETS / f"{args[1]}.json"
        args = args[2:]
    if args == ["stop"]:
        STOP_FLAG.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
        print("STOP SET: no more screenshots or clicks until the next run starts.")
    elif args == ["start"]:
        STOP_FLAG.unlink(missing_ok=True)
        print("READY: stop flag cleared.")
    elif args == ["presets"]:
        print("default" + ("" if (HERE / "config.json").exists() else " (not set)"))
        for n in preset_names():
            print(n)
    elif args == ["create"]:
        # The ONLY way a new preset file comes into existence.
        if CONFIG.parent != PRESETS:
            print("BAD USAGE: create needs --preset NAME.")
            sys.exit(1)
        if CONFIG.exists():
            print(f"EXISTS: preset '{CONFIG.stem}' already exists -- use calibrate to redo it.")
            sys.exit(1)
        calibrate()
    elif args[:1] == ["calibrate"]:
        if CONFIG.parent == PRESETS and not CONFIG.exists():
            print(f"NO SUCH PRESET: '{CONFIG.stem}'. Saved presets: {preset_names()}. "
                  f"Make it on purpose with `create`.")
            sys.exit(1)
        calibrate(args[1:] or None)
    elif args == ["shot"]:
        shot()
    elif len(args) == 3 and args[0] == "answer":
        answer(args[1], args[2])
    else:
        print(__doc__)
        sys.exit(1)
