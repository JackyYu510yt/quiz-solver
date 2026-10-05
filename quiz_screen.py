"""Screen helper for the quiz-solver skill.

Usage:
    python quiz_screen.py calibrate          # click 10 spots on a see-through overlay
    python quiz_screen.py calibrate next     # re-pick only the named spot(s), keep the rest
    python quiz_screen.py shot               # screenshot the quiz area (no clicks), print the PNG path
    python quiz_screen.py answer B high      # re-check screen, click answer + confidence, press Next
    python quiz_screen.py answer A,C high 4  # marker mode: several answers; 4 = choices the helper saw
    python quiz_screen.py answer A high 4 URL  # same, plus the helper's source for shots/log.csv
    python quiz_screen.py pick B             # test mode: re-check screen, click ONLY the answer(s), check them
    python quiz_screen.py markers on|off     # find the answers on screen each round (on) or use saved spots (off)
    python quiz_screen.py memory             # print the answer-memory file path + how many questions it holds
    python quiz_screen.py remember F.json correct|wrong  # save a feedback reading to memory (if consistent)
    python quiz_screen.py presets            # list saved presets
    python quiz_screen.py --preset NAME create   # make a NEW preset (refuses if it exists)
    python quiz_screen.py stop               # stop flag: shot/answer refuse to act (exit 5)
    python quiz_screen.py start              # clear the stop flag (start of every run)
    Put `--preset NAME` first to use presets/NAME.json instead of config.json,
    e.g. `python quiz_screen.py --preset mgh calibrate`.

Marker mode (`markers on`): instead of the saved A-D spots, every round the
script finds the radio circles / checkboxes in the screenshot (teal shapes in
the column of the saved A spot), labels them A, B, C... top to bottom, clicks
those, and checks exactly the right ones show as selected BEFORE pressing a
confidence button (which submits on some sites).

Exit codes: 0 ok, 1 bad usage / no calibration, 2 selections didn't register,
3 page didn't change after a click that should change it, 4 screen changed since
the last shot (nothing clicked), 5 stopped by the user (nothing done),
6 wrong selection after clicking the answers (nothing submitted),
7 couldn't find the answer choices / count didn't match (nothing clicked).
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
RESERVED = {"reset", "next", "presets", "default", "stop", "start", "create", "test", "markers"}
STOP_FLAG = HERE / "STOP"   # global: stops every run, whatever preset
LETTERS = "ABCDEFGH"
NEXT_HALF_W, NEXT_HALF_H = 50, 12   # Next-button picture is 100 x 24 px
# How exact a match must be to click it. Measured on the McGraw Hill page:
# the real button scored 0.87 after the page shifted a few px (scrollbar),
# the best look-alike 0.52 -- so: >= 0.75 AND >= 0.2 ahead of the runner-up.
NEXT_MATCH = 0.75
NEXT_GAP = 0.2

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


def _teal(c):
    r, g, b = c[:3]
    return r < 90 and g > 80 and b > 100 and g - r > 40


def find_choices(img, cfg):
    """Radio circles / checkboxes in the column of the saved A spot, top to
    bottom, as [{"x", "y" (screen px), "fill" (share of teal pixels)}].
    Measured on the McGraw Hill page: markers are ~16 px teal shapes; an empty
    radio is ~0.31 teal, a selected one ~0.68, an empty checkbox ~0.44."""
    img = img.convert("RGB")
    px = img.load()
    W, H = img.size
    ox, oy = region_box(cfg)[:2]
    col = cfg["A"][0] - ox
    x_lo, x_hi = max(0, col - 20), min(W, col + 21)
    seen, found = set(), []
    for y in range(H):
        for x in range(x_lo, x_hi):
            if (x, y) in seen or not _teal(px[x, y]):
                continue
            stack, pts = [(x, y)], []
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                pts.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if (x_lo <= nx < x_hi and 0 <= ny < H and (nx, ny) not in seen
                            and _teal(px[nx, ny])):
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            w, h = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
            mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            if 12 <= w <= 20 and 12 <= h <= 20 and abs(mx - col) <= 6:
                found.append({"x": round(mx + ox), "y": round(my + oy),
                              "fill": round(len(pts) / (w * h), 2)})
    return sorted(found, key=lambda m: m["y"])


def judge_feedback(img):
    """correct / wrong / unknown from the feedback screen's colors. Measured
    on the McGraw Hill page (inside the quiz zone): 'correct' screens have
    thousands of green badge/check pixels and no red; 'incorrect' ones have
    hundreds of red badge/X pixels and no green; a question has neither."""
    img = img.convert("RGB")
    red = green = 0
    for r, g, b in img.getdata():
        if r > 180 and g < 80 and b < 90:
            red += 1
        elif g > 100 and r < 80 and b < 110 and g - r > 60 and g - b > 30:
            green += 1
    if red >= 50:
        return "wrong"
    if green >= 50:
        return "correct"
    return "unknown"


def log_round(letters, level, result, shot_path, source):
    # One row per submitted question, kept across runs.
    import csv
    path = SHOTS / "log.csv"
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "preset", "answer", "confidence", "result", "source", "feedback_shot"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), CONFIG.stem, ",".join(letters),
                    level, result, source, shot_path])


def memory_path():
    return CONFIG.with_name(CONFIG.stem + ".memory.json")


def _norm(text):
    return " ".join(text.lower().split()).strip(" .?!:;,'\"")


def remember(json_file, result):
    """Save one question + its answer key (read off a feedback screen by the
    reader helper) to the memory file -- only if it is self-consistent."""
    try:
        item = json.loads(Path(json_file).read_text(encoding="utf-8"))
        q, choices = item["question"], item["choices"]
        selected, correct = item["selected"], item["correct"]
        ok_types = (isinstance(q, str) and q.strip() and len(choices) >= 2
                    and all(isinstance(c, str) and c.strip() for c in choices + selected + correct))
    except (OSError, ValueError, KeyError, TypeError):
        ok_types = False
    if not ok_types:
        print("NOT SAVED: the reader's reply isn't a complete question/choices/selected/correct record.")
        return
    norm_choices = [_norm(c) for c in choices]
    if not correct or any(_norm(c) not in norm_choices for c in correct + selected):
        print("NOT SAVED: the correct/selected answers aren't among the choices.")
        return
    same = sorted(map(_norm, selected)) == sorted(map(_norm, correct))
    if result not in ("correct", "wrong") or same != (result == "correct"):
        print(f"NOT SAVED: the badge says '{result}' but the answer key "
              f"{'matches' if same else 'differs from'} what was selected -- not trusted.")
        return

    path = memory_path()
    mem = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    key = (_norm(q), sorted(norm_choices))
    mem = [m for m in mem if (_norm(m["question"]), sorted(map(_norm, m["choices"]))) != key]
    mem.append({"question": q, "choices": choices, "correct": correct,
                "saved": time.strftime("%Y-%m-%d %H:%M:%S")})
    path.write_text(json.dumps(mem, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"SAVED TO MEMORY ({len(mem)} questions): {q[:70]} -> {correct}")


def parse_letters(text, marker_mode):
    letters = [s.strip().upper() for s in text.split(",") if s.strip()]
    allowed = LETTERS if marker_mode else "ABCD"
    if (not letters or len(set(letters)) != len(letters)
            or any(len(l) != 1 or l not in allowed for l in letters)
            or (not marker_mode and len(letters) != 1)):
        print(f"BAD USAGE: answer letters must be from {allowed}, comma-separated, no repeats"
              + ("" if marker_mode else " (one letter: marker mode is off)") + ".")
        sys.exit(1)
    return letters


def calibrate(only=None):
    # only = list of spot names to re-pick (e.g. ["next"]); the rest are kept.
    import tkinter as tk

    steps = STEPS
    if only:
        bad = [k for k in only if k not in dict(STEPS)]
        if bad:
            print(f"BAD USAGE: unknown spot(s) {bad}. Known: {[k for k, _ in STEPS]}")
            sys.exit(1)
        steps = [s for s in STEPS if s[0] in only]
    # Keep everything already saved (other spots, the markers setting).
    keep = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}

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
    if "next" in dict(steps):
        save_next_picture(points["next"])


def next_picture_path():
    return CONFIG.with_name(CONFIG.stem + ".next.png")


def save_next_picture(point):
    # A small picture of the Next button (taken with the overlay gone and the
    # mouse away, so no hover color). Marker mode finds the button by this
    # picture after each submit, because the page moves the button around.
    pyautogui.moveTo(5, 5)
    time.sleep(0.5)
    x, y = point
    ImageGrab.grab(bbox=(x - NEXT_HALF_W, y - NEXT_HALF_H, x + NEXT_HALF_W,
                         y + NEXT_HALF_H)).save(next_picture_path())
    print(f"SAVED NEXT PICTURE: {next_picture_path()}")


def find_next_button(timeout):
    """Search the screen for the saved Next-button picture; return its
    center or None. Only a near-exact match counts."""
    import cv2
    import numpy as np
    tpl = np.array(Image.open(next_picture_path()).convert("RGB"))
    end = time.time() + timeout
    while True:
        screen = np.array(ImageGrab.grab().convert("RGB"))
        res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, (mx, my) = cv2.minMaxLoc(res)
        # Runner-up anywhere away from the best spot: the match must clearly
        # beat every other place on screen, not just pass the bar.
        res[max(0, my - 30):my + 30, max(0, mx - 60):mx + 60] = -1
        if score >= NEXT_MATCH and score - res.max() >= NEXT_GAP:
            return (mx + NEXT_HALF_W, my + NEXT_HALF_H)
        if time.time() >= end:
            return None
        time.sleep(0.4)


def same_screen(a, b):
    # Allow a sliver of noise (e.g. font smoothing); anything bigger means
    # the zone shows something else now.
    if a.size != b.size:
        return False
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L")
    changed = sum(diff.point(lambda v: 255 if v > 30 else 0).histogram()[255:])
    return changed <= a.size[0] * a.size[1] * 0.005


def wait_for_change(cfg, before, timeout):
    # Poll until the zone stops looking like `before`; True if it changed.
    end = time.time() + timeout
    while time.time() < end:
        time.sleep(0.3)
        if not same_screen(before, grab(cfg)):
            time.sleep(0.5)   # let the new page finish drawing
            return True
    return False


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
    img = grab(cfg)
    img.save(path)
    (SHOTS / "last.txt").write_text(str(path))
    print(path)
    if cfg.get("markers"):
        found = find_choices(img, cfg)
        print(f"CHOICES: {len(found)} found ({', '.join(LETTERS[i] for i in range(len(found)))})")


def ready_to_click():
    # Only click if the zone still shows exactly what the helper read.
    check_stop()
    cfg = load_config()
    last = SHOTS / "last.txt"
    if not last.exists():
        print("NO SHOT: run `shot` first.")
        sys.exit(1)
    park(cfg)
    time.sleep(0.2)
    seen = Image.open(last.read_text().strip())
    if not same_screen(seen, grab(cfg)):
        print("SCREEN CHANGED: the quiz area no longer matches the screenshot the "
              "helper read. Nothing was clicked.")
        sys.exit(4)
    return cfg, seen


def select_markers(cfg, seen, letters, count):
    """Marker mode: click the chosen markers, then prove exactly those (and
    no others) became selected. Exits 6/7 on any doubt; nothing submitted."""
    before = find_choices(seen, cfg)
    if not before:
        print("NO CHOICES FOUND: couldn't find any answer circles/boxes on screen. Nothing was clicked.")
        sys.exit(7)
    if count is not None and count != len(before):
        print(f"COUNT MISMATCH: the helper saw {count} choices but the screen has "
              f"{len(before)}. Nothing was clicked.")
        sys.exit(7)
    idx = [LETTERS.index(l) for l in letters]
    if max(idx) >= len(before):
        print(f"NO SUCH CHOICE: {','.join(letters)} but only {len(before)} choices "
              f"on screen. Nothing was clicked.")
        sys.exit(7)

    for i in idx:
        press((before[i]["x"], before[i]["y"]))
    park(cfg)
    time.sleep(0.4)

    after = find_choices(grab(cfg), cfg)
    if len(after) != len(before) or any(abs(a["y"] - b["y"]) > 4 for a, b in zip(after, before)):
        print("WRONG SELECTION: the answers moved or changed after clicking. "
              "NOTHING WAS SUBMITTED -- check the page and answer by hand.")
        sys.exit(6)
    picked = [LETTERS[i] for i, (a, b) in enumerate(zip(after, before)) if a["fill"] - b["fill"] >= 0.15]
    if picked != sorted(letters):
        print(f"WRONG SELECTION: wanted {','.join(sorted(letters))} but the screen shows "
              f"{','.join(picked) or 'nothing'} selected. NOTHING WAS SUBMITTED -- "
              f"fix it by hand or re-run test mode.")
        sys.exit(6)
    return picked


def pick(letters_text, count=None):
    # Test mode: click ONLY the answer(s) -- never confidence (which submits
    # on some sites) or Next -- then save what the page shows now.
    cfg, seen = ready_to_click()
    letters = parse_letters(letters_text, cfg.get("markers"))
    if cfg.get("markers"):
        picked = select_markers(cfg, seen, letters, count)
        verdict = f"MATCH: screen shows {','.join(picked)} selected"
    else:
        press(cfg[letters[0]])
        park(cfg)
        time.sleep(0.3)
        verdict = "not checked (marker mode is off)"
    path = SHOTS / f"pick_{time.strftime('%Y%m%d_%H%M%S')}.png"
    grab(cfg).save(path)
    print(f"PICKED: {','.join(letters)} only (no confidence, no Next); {verdict}. "
          f"After-click shot: {path}")


def answer(letters_text, level, count=None, source="none"):
    level = level.lower()
    if level not in ("high", "medium", "low"):
        print("BAD USAGE: answer <letters> <high|medium|low> [count]")
        sys.exit(1)
    cfg, seen = ready_to_click()
    letters = parse_letters(letters_text, cfg.get("markers"))

    if cfg.get("markers"):
        # Check this BEFORE clicking anything: without the picture we could
        # submit but then not find Next.
        if not next_picture_path().exists():
            print("NO NEXT PICTURE: run `/quiz-solver next NAME` while a feedback "
                  "screen with its Next button is showing. Nothing was clicked.")
            sys.exit(1)
        select_markers(cfg, seen, letters, count)
        # Confidence submits the answer here; wait for the feedback screen.
        before = grab(cfg)
        press(cfg[level])
        park(cfg)
        if not wait_for_change(cfg, before, 6):
            print(f"STUCK: page didn't change after pressing {level}. The answer is "
                  f"selected but may not be submitted -- check the page.")
            sys.exit(3)
        # The feedback screen moves the Next button around: find it by its
        # picture; never click a guessed spot.
        spot = find_next_button(8)
        if spot is None:
            print("NO NEXT BUTTON: the answer WAS submitted, but the Next button "
                  "wasn't found on screen, so nothing else was clicked. Press it by "
                  "hand; if it was visible, re-pick it with `/quiz-solver next NAME`.")
            sys.exit(3)
        # Next is showing, so the feedback has finished drawing: record
        # whether the answer was right before moving on.
        feedback = grab(cfg)
        fb_path = SHOTS / f"feedback_{time.strftime('%Y%m%d_%H%M%S')}.png"
        feedback.save(fb_path)
        result = judge_feedback(feedback)
        log_round(letters, level, result, fb_path, source)
        before = ImageGrab.grab()
        press(spot)
        park(cfg)
        end = time.time() + 8
        while same_screen(before, ImageGrab.grab()):
            if time.time() > end:
                print("STUCK: page didn't change after pressing Next (the answer WAS "
                      "submitted).")
                sys.exit(3)
            time.sleep(0.3)
        time.sleep(0.8)   # let the next question finish drawing
        print(f"CLICKED: {','.join(letters)} + {level} + Next (found at {spot[0]},{spot[1]})")
        print(f"RESULT: {result} (feedback shot: {fb_path})")
        return

    next_before = grab_patch(cfg["next"])

    press(cfg[letters[0]])
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
    print(f"CLICKED: {letters[0]} + {level} + Next")


def preset_names():
    return sorted(f.stem for f in PRESETS.glob("*.json")) if PRESETS.exists() else []


def count_arg(text):
    if not text.isdigit() or not 1 <= int(text) <= len(LETTERS):
        print(f"BAD USAGE: count must be a number 1-{len(LETTERS)}.")
        sys.exit(1)
    return int(text)


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
    elif len(args) == 2 and args[0] == "markers" and args[1] in ("on", "off"):
        cfg = load_config()
        cfg["markers"] = args[1] == "on"
        CONFIG.write_text(json.dumps(cfg, indent=2))
        print(f"MARKERS {args[1].upper()}: {CONFIG}")
    elif len(args) == 2 and args[0] == "find":
        # Debug: list the answer markers found in a saved screenshot.
        for i, m in enumerate(find_choices(Image.open(args[1]), load_config())):
            print(LETTERS[i], m)
    elif args == ["shot"]:
        shot()
    elif len(args) in (2, 3) and args[0] == "pick":
        pick(args[1], count_arg(args[2]) if len(args) == 3 else None)
    elif len(args) in (3, 4, 5) and args[0] == "answer":
        answer(args[1], args[2], count_arg(args[3]) if len(args) >= 4 else None,
               args[4] if len(args) == 5 else "none")
    elif len(args) == 3 and args[0] == "remember":
        remember(args[1], args[2])
    elif args == ["memory"]:
        p = memory_path()
        n = len(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else 0
        print(f"MEMORY: {p} ({n} questions)")
    elif len(args) == 2 and args[0] == "judge":
        # Debug: correct / wrong / unknown for a saved feedback screenshot.
        print(judge_feedback(Image.open(args[1])))
    else:
        print(__doc__)
        sys.exit(1)
