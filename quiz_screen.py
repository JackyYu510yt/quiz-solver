"""Screen helper for the quiz-solver skill.

Usage:
    python quiz_screen.py calibrate          # click 10 spots on a see-through overlay
    python quiz_screen.py calibrate next     # re-pick only the named spot(s), keep the rest
    python quiz_screen.py shot               # screenshot the quiz area (no clicks), print the PNG path
    python quiz_screen.py answer B high      # re-check screen, click answer + confidence, press Next
    python quiz_screen.py answer A,C high 4  # marker mode: several answers; 4 = choices the helper saw
    python quiz_screen.py answer A high 4 URL  # same, plus the helper's source for shots/log.csv
    python quiz_screen.py round A,C high 4 URL  # chime + answer + remember (if correct) + next shot, in one go;
                                             # the helper's WHY:/FEYNMAN: lines may be piped in on stdin
    python quiz_screen.py pick B             # test mode: re-check screen, click ONLY the answer(s), check them
    python quiz_screen.py fill 1             # test mode, fill in the blank: type ONLY (1 = blanks the helper saw);
                                             # the text comes on stdin as `FILL: word` (`FILL: a|b` for two blanks)
    python quiz_screen.py fillround high 1 URL  # chime + type + confidence + Next + next shot (text on stdin too)
    python quiz_screen.py order C,A,B,D      # test mode, ordering: drag the items into that order ONLY
    python quiz_screen.py orderround C,A,B,D high URL  # chime + drag + confidence + Next + next shot
    python quiz_screen.py match C,A,B        # test mode, matching: drag item C to box 1, A to box 2, B to box 3 ONLY
    python quiz_screen.py matchround C,A,B high URL    # chime + drag + confidence + Next + next shot
    python quiz_screen.py markers on|off     # find the answers on screen each round (on) or use saved spots (off)
    python quiz_screen.py memory             # print the answer-memory file path + how many questions it holds
    python quiz_screen.py remember F.json correct|wrong  # save a feedback reading to memory (if consistent)
    python quiz_screen.py popup "why"        # Windows notification: "Quiz solver: run stopped" + why
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
confidence button (which submits on some sites). `shot` also reads the
question and choices off the screenshot itself (Windows' built-in text
recognition) and looks them up in the answer memory: `MEMORY HIT` means the
round needs no helper at all.

Fill in the blank (marker mode): when a screenshot has no answer circles,
`shot` looks for text boxes instead (`BLANKS: N found`). `fill` / `fillround`
click each box in reading order, type its text, and check every box now
shows writing BEFORE pressing a confidence button.

Ordering / matching (marker mode): with no answer circles on screen, `shot`
looks for drag-and-drop boxes before it looks for blanks. Ordering prints
`ORDERING: N items` and the items lettered A, B, C... top to bottom as they
stand; matching prints `MATCHING: N boxes, M items`, the boxes numbered by
their labels and the waiting items lettered in reading order. `order` /
`match` drag one item at a time, re-reading the page before every drag, and
only finish once the page itself shows every item in its place -- BEFORE a
confidence button is pressed.

Exit codes: 0 ok, 1 bad usage / no calibration, 2 selections didn't register,
3 page didn't change after a click that should change it, 4 screen changed since
the last shot (nothing clicked), 5 stopped by the user (nothing done),
6 wrong selection after clicking the answers / typed text not showing /
dragged items not in place (nothing submitted),
7 couldn't find the answer choices or blanks / count didn't match (nothing
clicked).
"""
import ctypes
import json
import re
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
RESERVED = {"reset", "next", "zone", "presets", "default", "stop", "start", "create", "test", "markers"}
STOP_FLAG = HERE / "STOP"   # global: stops every run, whatever preset
LETTERS = "ABCDEFGH"
NEXT_HALF_W, NEXT_HALF_H = 50, 12   # Next-button picture is 100 x 24 px
# How exact a match must be to click it. Measured on the McGraw Hill page:
# the real button scored 0.87 after the page shifted a few px (scrollbar),
# the best look-alike 0.52 -- so: >= 0.75 AND >= 0.2 ahead of the runner-up.
NEXT_MATCH = 0.75
NEXT_GAP = 0.2
SELECT_CHECKS = 3   # looks at the picked answers, 0.4 s apart, before giving up
SELECT_RETRIES = 2  # extra clicks on an answer that didn't register, then stop
NEXT_TRIES = 3 # presses of Next before giving up (the answer is already in)
CONF_TRIES = 3 # presses of the confidence button before giving up

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


def borrow():
    # Where the user's mouse is and which window they're typing in, so both
    # can be handed back right after a click.
    return tuple(pyautogui.position()), ctypes.windll.user32.GetForegroundWindow()


def give_back(held):
    # SetCursorPos, not pyautogui: no pause, no corner emergency stop.
    (x, y), window = held
    ctypes.windll.user32.SetCursorPos(x, y)
    if window:
        ctypes.windll.user32.SetForegroundWindow(window)   # best effort


def press(point, keep=False):
    # Move first, let the cursor settle, then click. A combined fast
    # move+click was seen registering at the PREVIOUS cursor spot.
    # If the mouse isn't where we put it (someone is using it), put it back
    # before clicking, so the click can't land somewhere else.
    # The mouse is only borrowed for the click itself: it goes straight back
    # to where the user had it (keep=True leaves it, for typing into a box).
    held = borrow()
    for _ in range(3):
        pyautogui.moveTo(*point)
        time.sleep(0.08)
        x, y = pyautogui.position()
        if abs(x - point[0]) <= 2 and abs(y - point[1]) <= 2:
            break
    pyautogui.click()
    if not keep:
        give_back(held)


def park(cfg, force=False):
    # Rest the mouse on a harmless spot just inside the quiz area so hover
    # colors don't show up in screenshots. A mouse that's already off the
    # quiz area (the user working elsewhere) causes no hover: leave it be.
    if not force:
        mx, my = pyautogui.position()
        x1, y1, x2, y2 = region_box(cfg)
        if not (x1 <= mx <= x2 and y1 <= my <= y2):
            return
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


def _blank_edge(c):
    r, g, b = c[:3]
    return abs(r - 92) <= 14 and abs(g - 123) <= 14 and abs(b - 133) <= 14


def find_blanks(img, cfg):
    """Fill-in-the-blank text boxes in reading order, as [{"x", "y" (screen
    px, the box's middle), "box" (left, top, right, bottom in the image)}].
    Measured on the McGraw Hill page: a box is a 1 px outline colored
    (92, 123, 133), about 160 x 34 px, white inside."""
    img = img.convert("RGB")
    px = img.load()
    W, H = img.size
    ox, oy = region_box(cfg)[:2]
    runs = {}   # y -> [(x0, x1)] outline-colored stretches at least 60 px long
    for y in range(H):
        x = 0
        while x < W:
            if not _blank_edge(px[x, y]):
                x += 1
                continue
            x0 = x
            while x < W and _blank_edge(px[x, y]):
                x += 1
            if 60 <= x - x0 <= 500:
                runs.setdefault(y, []).append((x0, x - 1))
    found = []
    for y, row in runs.items():
        for x0, x1 in row:
            for h in range(24, 61):
                if any(abs(a - x0) <= 1 and abs(b - x1) <= 1 for a, b in runs.get(y + h, [])):
                    mid = y + h // 2
                    # Rounded corners: the side lines sit ~2 px outside the
                    # ends of the top line.
                    sides = [any(_blank_edge(px[x, mid]) for x in range(max(0, c - 3), min(W, c + 4)))
                             for c in (x0, x1)]
                    if all(sides):
                        found.append({"x": (x0 + x1) // 2 + ox, "y": mid + oy,
                                      "box": (x0, y, x1, y + h)})
                    break
    # Reading order: top to bottom, and left to right on the same line.
    found.sort(key=lambda b: b["y"])
    for i in range(1, len(found)):
        if found[i]["y"] - found[i - 1]["y"] <= 15:
            found[i]["y"] = found[i - 1]["y"]
    return sorted(found, key=lambda b: (b["y"], b["x"]))


def blank_ink(img, blank):
    # How many dark (text) pixels sit inside a blank's box.
    l, t, r, b = blank["box"]
    return sum(1 for v in img.convert("L").crop((l + 4, t + 4, r - 3, b - 3)).getdata() if v < 90)


WHITE, SLOT_FILL, LABEL_FILL = (255, 255, 255), (240, 243, 244), (209, 219, 222)


def _near(c, want):
    return all(abs(a - b) <= 6 for a, b in zip(c[:3], want))


def find_boxes(img):
    """Every outlined box in the image, top to bottom, as [{"box" (left, top,
    right, bottom in the image), "fill" (the color inside)}]. Measured on the
    McGraw Hill page: drag-and-drop boxes have the same 1 px outline as a
    fill-in-the-blank box; a draggable item is white inside, a box to drop
    into (and the panel the items wait in) is (240, 243, 244), and the label
    beside a drop box is (209, 219, 222)."""
    img = img.convert("RGB")
    px = img.load()
    W, H = img.size
    runs = {}   # y -> [(x0, x1)] outline-colored stretches at least 60 px long
    for y in range(H):
        x = 0
        while x < W:
            if not _blank_edge(px[x, y]):
                x += 1
                continue
            x0 = x
            while x < W and _blank_edge(px[x, y]):
                x += 1
            if x - x0 >= 60:
                runs.setdefault(y, []).append((x0, x - 1))
    found, bottoms = [], set()
    for y in sorted(runs):
        for x0, x1 in runs[y]:
            # A line already used as one box's bottom isn't the next box's top
            # (stacked boxes sit only ~10 px apart).
            if (y, x0, x1) in bottoms:
                continue
            for h in range(24, 601):
                hit = [r for r in runs.get(y + h, []) if abs(r[0] - x0) <= 1 and abs(r[1] - x1) <= 1]
                if hit:
                    bottoms.add((y + h, *hit[0]))
                    mid = y + h // 2
                    # Rounded corners: the side lines sit up to ~4 px outside
                    # the ends of the top line.
                    if all(any(_blank_edge(px[x, mid]) for x in range(max(0, c - 5), min(W, c + 6)))
                           for c in (x0, x1)):
                        found.append({"box": (x0, y, x1, y + h), "fill": px[x0 + 8, y + 5]})
                    break
    return sorted(found, key=lambda b: (b["box"][1], b["box"][0]))


def _inside(point, box):
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def _middle(box):
    return ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)


def box_text(words, box):
    # The text recognition's words whose middle sits inside the box.
    inside = [w for w in words if _inside((w[1] + w[3] / 2, w[2] + w[4] / 2), box)]
    return " ".join(w[5] for w in sorted(inside))


def read_drag(img, path):
    """An ordering or matching question read off a saved screenshot, or None.
    Ordering: {"kind": "ordering", "items": [{"box", "text"}]} -- the stacked
    full-width boxes, top to bottom. Matching: {"kind": "matching", "slots":
    [{"box", "text" (its label)}], "items": [{"box", "text"}]} -- the drop
    boxes top to bottom and the waiting items in reading order."""
    boxes = find_boxes(img)
    white = [b for b in boxes if _near(b["fill"], WHITE)]
    light = [b for b in boxes if _near(b["fill"], SLOT_FILL)]
    labels = [b for b in boxes if _near(b["fill"], LABEL_FILL)]
    slots = []
    for lab in labels:
        row = [b for b in light if b["box"][0] > lab["box"][2]
               and abs(_middle(b["box"])[1] - _middle(lab["box"])[1]) <= 10]
        if len(row) != 1:
            return None
        slots.append(row[0])
    if slots:
        panels = [b for b in light if b not in slots]
        items = [b for b in white if any(_inside(_middle(b["box"]), p["box"]) for p in panels)]
        # Reading order: top to bottom, and left to right on the same line.
        items.sort(key=lambda b: b["box"][1])
        rows = [b["box"][1] for b in items]
        for i in range(1, len(items)):
            if items[i]["box"][1] - items[i - 1]["box"][1] <= 15:
                rows[i] = rows[i - 1]
        items = [b for _, b in sorted(zip(rows, items), key=lambda p: (p[0], p[1]["box"][0]))]
        if not items:
            return None
        words = ocr_words(Path(path).resolve())
        return {"kind": "matching",
                "slots": [{"box": s["box"], "label": lab["box"], "text": box_text(words, lab["box"])}
                          for s, lab in zip(slots, labels)],
                "items": [{"box": b["box"], "text": box_text(words, b["box"])} for b in items]}
    # Ordering: wider than any fill-in-the-blank box, all the same width.
    wide = [b for b in white if b["box"][2] - b["box"][0] > 500]
    wide = [b for b in wide if abs(b["box"][0] - wide[0]["box"][0]) <= 2
            and abs(b["box"][2] - wide[0]["box"][2]) <= 2]
    if len(wide) < 2:
        return None
    words = ocr_words(Path(path).resolve())
    return {"kind": "ordering",
            "items": [{"box": b["box"], "text": box_text(words, b["box"])} for b in wide]}


def report_drag(q):
    # Printed by `shot` for an ordering / matching question.
    if q["kind"] == "ordering":
        print(f"ORDERING: {len(q['items'])} items (drag into order)")
    else:
        print(f"MATCHING: {len(q['slots'])} boxes, {len(q['items'])} items (drag each item to its box)")
        print("BOXES: " + " | ".join(f"{i + 1}) {s['text']}" for i, s in enumerate(q["slots"])))
    keys = [text_key(i["text"]) for i in q["items"]]
    if len(q["items"]) > len(LETTERS) or not all(keys) or len(set(keys)) != len(keys):
        print("ITEMS: failed -- couldn't read every item's text off the screenshot.")
        return
    print("ITEMS: " + " | ".join(f"{LETTERS[i]}) {it['text']}" for i, it in enumerate(q["items"])))


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


def chime():
    # Alert sound when an answer is ready: chime.mp3 next to this script
    # (per-PC, not in git), played by a detached windowless process so this
    # command returns at once; Windows' alert sound if the file is missing.
    sound = HERE / "chime.mp3"
    if not sound.exists():
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
        print("CHIME: Windows alert (no chime.mp3 next to the script)")
        return
    import subprocess
    pyw = Path(sys.executable).with_name("pythonw.exe")
    code = ("import ctypes; m=ctypes.windll.winmm.mciSendStringW; "
            f"m('open \"{sound}\" type mpegvideo alias quizchime',None,0,0); "
            "m('play quizchime wait',None,0,0); m('close quizchime',None,0,0)")
    subprocess.Popen([str(pyw if pyw.exists() else sys.executable), "-c", code],
                     creationflags=0x00000008 | 0x08000000)  # DETACHED, NO_WINDOW
    print("CHIME: played")


_POPUP_PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$x = New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml('<toast scenario="reminder"><visual><binding template="ToastGeneric"><text>Quiz solver: run stopped</text><text></text></binding></visual><actions><action activationType="system" arguments="dismiss" content=""/></actions></toast>')
$x.GetElementsByTagName('text').Item(1).InnerText = $env:QUIZ_POPUP_TEXT
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($x))
"""


def popup(text):
    # Windows notification in the screen corner (like a Chrome one) saying
    # the run stopped and why; it stays up until dismissed. Shown by a
    # windowless process so this command returns at once.
    import base64
    import os
    import subprocess
    subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand",
         base64.b64encode(_POPUP_PS.encode("utf-16-le")).decode()],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=0x08000000,   # no console window
        env={**os.environ, "QUIZ_POPUP_TEXT": text[:200]})
    print("POPUP: shown")


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

    save_memory(q, choices, correct)


def text_key(text):
    # How questions/choices are compared: letters and digits only, so case,
    # spacing, punctuation and the "_____" of a blank never matter.
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def save_memory(q, choices, correct, notes=None):
    # notes = {"why": ..., "feynman": ...} from the helper, shown again when
    # the question comes back and is answered from memory.
    path = memory_path()
    mem = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    key = (text_key(q), sorted(map(text_key, choices)))
    mem = [m for m in mem if (text_key(m["question"]), sorted(map(text_key, m["choices"]))) != key]
    mem.append({"question": q, "choices": choices, "correct": correct, **(notes or {}),
                "saved": time.strftime("%Y-%m-%d %H:%M:%S")})
    path.write_text(json.dumps(mem, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"SAVED TO MEMORY ({len(mem)} questions): {q[:70]} -> {correct}")


def memory_lookup(reading):
    """(letters, memory item) when the memory holds exactly this question
    with exactly these choices; None on any doubt (the helper answers then)."""
    path = memory_path()
    if not path.exists():
        return None
    qk = text_key(reading["question"])
    ck = [text_key(c) for c in reading["choices"]]
    if len(set(ck)) != len(ck):
        return None
    hits = []
    for m in json.loads(path.read_text(encoding="utf-8")):
        want = [text_key(c) for c in m["correct"]]
        if (text_key(m["question"]) == qk and sorted(map(text_key, m["choices"])) == sorted(ck)
                and want and all(w in ck for w in want)):
            hits.append((sorted(LETTERS[ck.index(w)] for w in want), m))
    if not hits or any(h[0] != hits[0][0] for h in hits):
        return None
    return hits[-1]


# Windows' built-in text recognition, run through PowerShell so nothing has
# to be installed. Prints one word per row: line number, x, y, w, h, text.
_OCR_PS = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.RandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait() | Out-Null
    $task.Result
}
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { return }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($env:QUIZ_OCR_PATH)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$n = 0
foreach ($line in $result.Lines) {
    foreach ($w in $line.Words) {
        $r = $w.BoundingRect
        "{0}`t{1}`t{2}`t{3}`t{4}`t{5}" -f $n, [int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height, $w.Text
    }
    $n++
}
"""

# Page furniture above the question on the McGraw Hill page (as text_key).
HEADER_LINES = {"multiplechoicequestion", "multipleselectquestion", "selectallthatapply",
                "trueorfalsequestion", "truefalsequestion"}


def ocr_words(path):
    """[(line, x, y, w, h, text)] for every word in the image; [] if the
    text recognition isn't available."""
    import base64
    import os
    import subprocess
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand",
             base64.b64encode(_OCR_PS.encode("utf-16-le")).decode()],
            capture_output=True, stdin=subprocess.DEVNULL, timeout=30,
            creationflags=0x08000000,   # no console window
            env={**os.environ, "QUIZ_OCR_PATH": str(path)}).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired):
        return []
    words = []
    for row in out.lstrip("\ufeff").splitlines():
        parts = row.split("\t", 5)
        if len(parts) == 6 and all(p.lstrip("-").isdigit() for p in parts[:5]):
            words.append((*map(int, parts[:5]), parts[5]))
    return words


def read_question(path, cfg, markers):
    """The question and its choices as text, read off a saved screenshot:
    {"question", "choices" (one per marker, top to bottom), "clipped"}.
    None if it can't be read. Each choice is the text on its marker's row
    (plus wrapped lines right below); the question is everything above the
    first marker."""
    if len(markers) < 2:
        return None
    img = Image.open(path).convert("L")
    width = img.size[0]
    ox, oy = region_box(cfg)[:2]
    col = markers[0]["x"] - ox
    ys = [m["y"] - oy for m in markers]
    lines = {}
    for n, x, y, w, h, text in ocr_words(path):
        lines.setdefault(n, []).append((x, y, w, h, text))
    rows = []
    for ws in lines.values():
        cy = sum(y + h / 2 for _, y, _, h, _ in ws) / len(ws)
        if any(abs(cy - my) <= 14 for my in ys):
            # The circle/box itself is read as a stray "O" -- drop it.
            ws = [w for w in ws if w[0] + w[2] / 2 > col + 12]
        if ws:
            rows.append({"cy": cy, "top": min(w[1] for w in ws),
                         "bottom": max(w[1] + w[3] for w in ws),
                         "text": " ".join(w[4] for w in sorted(ws))})
    rows.sort(key=lambda r: r["cy"])

    used = [r for r in rows if r["cy"] < ys[0] - 14 and text_key(r["text"]) not in HEADER_LINES]
    question = " ".join(r["text"] for r in used)
    choices = []
    for i, my in enumerate(ys):
        end = ys[i + 1] - 14 if i + 1 < len(ys) else float("inf")
        block = []
        for r in rows:
            if not my - 14 <= r["cy"] < end:
                continue
            if not block:
                if abs(r["cy"] - my) > 14:
                    break
            elif r["top"] - block[-1]["bottom"] > 0.9 * (block[-1]["bottom"] - block[-1]["top"]):
                break
            block.append(r)
        choices.append(" ".join(r["text"] for r in block))
        used += block
    if not text_key(question) or not all(text_key(c) for c in choices):
        return None
    # Clipped = text runs off the right edge of the zone (dark pixels in the
    # last columns of a text row), so part of the wording is missing.
    edge = img.crop((width - 3, 0, width, img.size[1])).load()
    clipped = any(edge[x, y] < 110 for r in used
                  for y in range(max(0, r["top"] - 2), min(img.size[1], r["bottom"] + 4))
                  for x in range(3))
    return {"question": question, "choices": choices, "clipped": clipped}


def report_reading(path, cfg, markers, save=True):
    # Printed after `shot`: what the script read and whether the memory
    # already knows the answer. Saved so `round` can remember it later.
    reading = read_question(path, cfg, markers)
    if save:
        (SHOTS / "last_read.json").write_text(
            json.dumps({"shot": str(path), "reading": reading}, ensure_ascii=False), encoding="utf-8")
    if reading is None:
        print("READ: failed -- couldn't read the question off the screenshot (memory not used).")
        return
    if reading["clipped"]:
        print("READ: clipped -- the text runs off the right edge of the quiz zone, so the "
              "memory isn't used or added to. (Widen the zone: `calibrate region_br`.)")
        return
    print("READ: " + reading["question"] + "".join(
        f" | {LETTERS[i]}) {c}" for i, c in enumerate(reading["choices"])))
    hit = memory_lookup(reading)
    if hit is None:
        print("MEMORY MISS")
        return
    letters, item = hit
    print(f"MEMORY HIT: ANSWER={','.join(letters)} COUNT={len(reading['choices'])}")
    for tag in ("why", "feynman"):
        if item.get(tag):
            print(f"{tag.upper()}: {item[tag]}")


def read_notes():
    # The helper's WHY: / FEYNMAN: lines (optional) and, for a fill in the
    # blank, its FILL: line, piped in on stdin.
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        text = sys.stdin.buffer.read().decode("utf-8", "replace")
    except (OSError, ValueError):
        return {}
    notes = {}
    for line in text.splitlines():
        line = line.strip().strip("`")
        for tag in ("why", "feynman", "fill"):
            if line.lower().startswith(tag + ":") and line[len(tag) + 1:].strip():
                notes[tag] = line[len(tag) + 1:].strip()
    return notes


def auto_remember(result, letters, fb_path, shot_path, source, notes):
    """After a submitted answer: a CORRECT one is its own answer key, so save
    what the script read before clicking. A wrong one needs the reader."""
    if result == "wrong":
        print(f"READER NEEDED: the answer was wrong -- read the answer key off {fb_path}")
        return
    if result != "correct":
        print("NOT REMEMBERED: couldn't tell whether the answer was right.")
        return
    if source == "memory":
        return   # already in memory, with its notes
    try:
        last = json.loads((SHOTS / "last_read.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        last = {}
    reading = last.get("reading")
    if last.get("shot") != shot_path or not reading:
        print("NOT REMEMBERED: the script couldn't read this question off the screenshot.")
        return
    if reading["clipped"]:
        print("NOT REMEMBERED: the question text runs off the edge of the quiz zone.")
        return
    idx = [LETTERS.index(l) for l in letters]
    if max(idx) >= len(reading["choices"]):
        print("NOT REMEMBERED: the reading has fewer choices than the answer.")
        return
    save_memory(reading["question"], reading["choices"],
                [reading["choices"][i] for i in sorted(idx)], notes)


def play_round(letters_text, level, count, source):
    # One call per round: chime, submit, remember, then the next screenshot.
    notes = read_notes()
    chime()
    last = SHOTS / "last.txt"
    shot_path = last.read_text().strip() if last.exists() else ""
    done = answer(letters_text, level, count, source)
    if done:
        auto_remember(*done, shot_path, source, notes)
    shot()


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


def note_next_failure(why, kind="NEXT"):
    # Every failed try at Next (or at a confidence button) leaves a full-screen picture and a line in
    # shots/next_failures.log, so the cause can be looked up afterwards.
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = SHOTS / f"nextfail_{stamp}.png"
    try:
        ImageGrab.grab().save(path)
    except OSError:
        path = "no screenshot"
    with (SHOTS / "next_failures.log").open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {CONFIG.stem} | {why} | "
                f"mouse {tuple(pyautogui.position())} | {path}\n")
    print(f"{kind} TROUBLE: {why} (screenshot: {path})")


def find_next_after_scroll(cfg, why):
    # A long feedback screen can push Next below the visible page: scroll
    # down (mouse resting on the quiz area) and look again, twice at most.
    note_next_failure(why)
    for _ in range(2):
        try:
            held = borrow()
            park(cfg, force=True)
            pyautogui.scroll(-600)
            give_back(held)
            park(cfg)
        except pyautogui.FailSafeException:
            return None
        time.sleep(0.6)
        spot = find_next_button(3)
        if spot is not None:
            return spot
    return None


def press_next(cfg, spot):
    """Press Next until the page moves on (up to NEXT_TRIES); return the spot
    that worked. Retrying is safe: the answer is already submitted, and each
    click only goes where the Next picture matches right then."""
    corner_stops = 0
    for attempt in range(1, NEXT_TRIES + 1):
        if STOP_FLAG.exists():
            print("STOPPED: the run was stopped by the user. The answer WAS "
                  "submitted; Next was not pressed.")
            sys.exit(5)
        before = ImageGrab.grab()
        try:
            press(spot)
            park(cfg)
        except pyautogui.FailSafeException:
            # The mouse read as the top-left corner (pyautogui's emergency
            # stop). Once can be a glitch; twice means someone wants out.
            corner_stops += 1
            note_next_failure(f"try {attempt}: mouse read as the top-left corner")
            if corner_stops >= 2:
                print("CORNER STOP: the mouse was in the top-left corner twice "
                      "while pressing Next. The answer WAS submitted; press Next "
                      "by hand.")
                sys.exit(3)
            time.sleep(1)
        end = time.time() + 8
        while time.time() < end:
            if not same_screen(before, ImageGrab.grab()):
                return spot
            time.sleep(0.3)
        if attempt == NEXT_TRIES:
            note_next_failure(f"try {attempt}: page didn't change after pressing Next")
            break
        found = find_next_button(3)
        if found is None:
            found = find_next_after_scroll(
                cfg, f"try {attempt}: page didn't change and Next is no longer found")
            if found is None:
                print("NO NEXT BUTTON: the answer WAS submitted, but pressing Next "
                      "didn't move the page on and the button can't be found now. "
                      "Press it by hand.")
                sys.exit(3)
        else:
            note_next_failure(f"try {attempt}: page didn't change after pressing Next")
        spot = found
    print(f"STUCK: page didn't change after pressing Next {NEXT_TRIES} times (the "
          f"answer WAS submitted). Press it by hand.")
    sys.exit(3)


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
        # Before the blanks: a matching question's drop boxes look like them.
        drag_q = None if found else read_drag(img, path)
        if drag_q:
            report_drag(drag_q)
            return
        blanks = [] if found else find_blanks(img, cfg)
        if blanks:
            print(f"BLANKS: {len(blanks)} found (fill in the blank)")
            return
        report_reading(path, cfg, found)


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

    todo = idx
    for attempt in range(1 + SELECT_RETRIES):
        for i in todo:
            press((before[i]["x"], before[i]["y"]))
        park(cfg)

        # The page can be slow to draw a selection: check up to SELECT_CHECKS
        # times, 0.4 s apart, and pass on the first check that looks right
        # (so a normal round takes no longer than before).
        for _ in range(SELECT_CHECKS):
            time.sleep(0.4)
            after = find_choices(grab(cfg), cfg)
            moved = len(after) != len(before) or any(
                abs(a["y"] - b["y"]) > 4 for a, b in zip(after, before))
            picked = [] if moved else [LETTERS[i] for i, (a, b) in enumerate(zip(after, before))
                                       if a["fill"] - b["fill"] >= 0.15]
            if not moved and picked == sorted(letters):
                return picked
        if moved:
            print("WRONG SELECTION: the answers moved or changed after clicking. "
                  "NOTHING WAS SUBMITTED -- check the page and answer by hand.")
            sys.exit(6)
        # A click that missed: click again ONLY the wanted answers that still
        # aren't selected. Anything unwanted selected is never retried.
        if set(picked) - set(letters) or attempt == SELECT_RETRIES:
            break
        todo = [i for i in idx if LETTERS[i] not in picked]
        print(f"RETRY: {','.join(LETTERS[i] for i in todo)} not selected after "
              f"click {attempt + 1}; clicking again.")
    print(f"WRONG SELECTION: wanted {','.join(sorted(letters))} but the screen shows "
          f"{','.join(picked) or 'nothing'} selected. NOTHING WAS SUBMITTED -- "
          f"fix it by hand or re-run test mode.")
    sys.exit(6)


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


def need_next_picture():
    # Check this BEFORE clicking anything: without the picture we could
    # submit but then not find Next.
    if not next_picture_path().exists():
        print("NO NEXT PICTURE: run `/quiz-solver next NAME` while a feedback "
              "screen with its Next button is showing. Nothing was clicked.")
        sys.exit(1)


def submit(cfg, level, given, source):
    """Marker mode, with the answer already showing on the page: press the
    confidence level (which submits), record the feedback, press Next.
    given = the letters picked, or ["type:<text>"] for a fill in the blank."""
    # Confidence submits the answer here; wait for the feedback screen.
    # A press that does nothing is pressed again: wait_for_change only says
    # "no change" while the zone still looks exactly as it did before the
    # first press (answer showing, nothing submitted), so the same spot is
    # still the same button.
    before = grab(cfg)
    for attempt in range(1, CONF_TRIES + 1):
        if attempt > 1:
            check_stop()
        press(cfg[level])
        park(cfg)
        if wait_for_change(cfg, before, 6):
            break
        note_next_failure(f"try {attempt}: page didn't change after pressing {level}",
                          "CONFIDENCE")
    else:
        print(f"STUCK: page didn't change after pressing {level} {CONF_TRIES} "
              f"times. The answer is entered but not submitted -- check the page.")
        sys.exit(3)
    # The feedback screen moves the Next button around: find it by its
    # picture; never click a guessed spot.
    spot = find_next_button(8)
    # Next is showing (or 8 s have passed), so the feedback has finished
    # drawing: record whether the answer was right before moving on --
    # and before any scrolling moves the badge out of the zone.
    feedback = grab(cfg)
    fb_path = SHOTS / f"feedback_{time.strftime('%Y%m%d_%H%M%S')}.png"
    feedback.save(fb_path)
    result = judge_feedback(feedback)
    log_round(given, level, result, fb_path, source)
    if spot is None:
        spot = find_next_after_scroll(cfg, "Next button not found after submitting")
    if spot is None:
        print("NO NEXT BUTTON: the answer WAS submitted, but the Next button "
              "wasn't found on screen (even after scrolling down), so nothing "
              "else was clicked. Press it by hand; if it was visible, re-pick "
              "it with `/quiz-solver next NAME`.")
        sys.exit(3)
    spot = press_next(cfg, spot)
    time.sleep(0.8)   # let the next question finish drawing
    print(f"CLICKED: {','.join(given)} + {level} + Next (found at {spot[0]},{spot[1]})")
    print(f"RESULT: {result} (feedback shot: {fb_path})")
    return result, fb_path


def fill_texts():
    # The text for each blank, from the `FILL: a|b` line on stdin.
    texts = [t.strip() for t in read_notes().get("fill", "").split("|")]
    if not all(texts) or any(not (32 <= ord(ch) < 127) for t in texts for ch in t):
        print("BAD USAGE: pipe in `FILL: <text>` (`|` between blanks), plain "
              "keyboard characters only. Nothing was typed.")
        sys.exit(1)
    return texts


def type_blanks(cfg, seen, texts, count):
    """Fill in the blank: click each text box in reading order and type its
    text, then prove every box now shows writing. Exits 6/7 on any doubt;
    nothing submitted."""
    blanks = find_blanks(seen, cfg)
    if not blanks:
        print("NO BLANKS FOUND: couldn't find any text box on screen. Nothing was typed.")
        sys.exit(7)
    if count != len(blanks) or len(texts) != len(blanks):
        print(f"COUNT MISMATCH: the helper saw {count} blank(s) and gave {len(texts)} "
              f"answer(s) but the screen has {len(blanks)}. Nothing was typed.")
        sys.exit(7)
    empty = [blank_ink(seen, b) for b in blanks]
    held = borrow()
    for b, text in zip(blanks, texts):
        press((b["x"], b["y"]), keep=True)   # the typing needs the box focused
        pyautogui.hotkey("ctrl", "a")   # replace anything already in the box
        pyautogui.write(text, interval=0.02)
    give_back(held)
    park(cfg)
    for _ in range(SELECT_CHECKS):
        time.sleep(0.4)
        now = grab(cfg)
        if all(blank_ink(now, b) - e >= 15 for b, e in zip(blanks, empty)):
            return
    print("NOT TYPED: at least one blank shows no writing after typing. NOTHING "
          "WAS SUBMITTED -- check the page and answer by hand.")
    sys.exit(6)


def fill(count):
    # Test mode: type ONLY -- never confidence (which submits) or Next --
    # then save what the page shows now.
    texts = fill_texts()
    cfg, seen = ready_to_click()
    type_blanks(cfg, seen, texts, count)
    path = SHOTS / f"pick_{time.strftime('%Y%m%d_%H%M%S')}.png"
    grab(cfg).save(path)
    print(f"TYPED: {' | '.join(texts)} only (no confidence, no Next). After-typing shot: {path}")


def fill_round(level, count, source):
    # One call per fill-in-the-blank round: chime, type, submit, next shot.
    level = level.lower()
    if level not in ("high", "medium", "low"):
        print("BAD USAGE: fillround <high|medium|low> <blanks> [source]")
        sys.exit(1)
    texts = fill_texts()
    chime()
    cfg, seen = ready_to_click()
    if not cfg.get("markers"):
        print("BAD USAGE: fill in the blank needs marker mode (`markers on`).")
        sys.exit(1)
    need_next_picture()
    type_blanks(cfg, seen, texts, count)
    submit(cfg, level, ["type:" + "|".join(texts)], source)
    shot()


def drag(src, dst):
    # Press, move in small steps (a drag-and-drop page ignores a jump), let go.
    held = borrow()
    pyautogui.moveTo(*src)
    time.sleep(0.1)
    pyautogui.mouseDown()
    try:
        time.sleep(0.15)
        pyautogui.moveTo(src[0], src[1] + (10 if dst[1] > src[1] else -10), duration=0.2)
        pyautogui.moveTo(*dst, duration=0.6)
        time.sleep(0.3)
    finally:
        pyautogui.mouseUp()
    give_back(held)


def look(cfg):
    # The quiz area as it is right now, saved so its text can be read.
    if STOP_FLAG.exists():
        print("STOPPED: the run was stopped by the user. NOTHING WAS SUBMITTED "
              "(items may have been moved).")
        sys.exit(5)
    park(cfg)
    time.sleep(0.5)
    path = SHOTS / "drag_now.png"
    img = grab(cfg)
    img.save(path)
    return img, path


def same_text(a, b):
    # Two readings of the same words (the text recognition can slip a letter).
    import difflib
    a, b = text_key(a), text_key(b)
    return bool(a) and (a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.9)


def lost(why):
    print(f"LOST TRACK: {why}. NOTHING WAS SUBMITTED -- check the page and "
          f"answer by hand.")
    sys.exit(6)


def drag_question(seen, kind, letters):
    """The ordering / matching question in the last shot, plus the item text
    each letter stands for. Exits 7 on any doubt; nothing moved."""
    q = read_drag(seen, (SHOTS / "last.txt").read_text().strip())
    keys = [text_key(i["text"]) for i in q["items"]] if q else []
    if not q or q["kind"] != kind or not all(keys) or len(set(keys)) != len(keys):
        print(f"NO {kind.upper()} QUESTION: couldn't find one (with every item "
              f"readable) in the last screenshot. Nothing was moved.")
        sys.exit(7)
    need = len(q["items"]) if kind == "ordering" else len(q["slots"])
    if len(letters) != need or max(LETTERS.index(l) for l in letters) >= len(q["items"]):
        print(f"COUNT MISMATCH: got {len(letters)} letter(s) but the screen has "
              f"{len(q['items'])} items" + ("" if kind == "ordering" else f" and {need} boxes")
              + ". Nothing was moved.")
        sys.exit(7)
    return q, [q["items"][LETTERS.index(l)]["text"] for l in letters]


def put_in_order(cfg, q, want):
    """Ordering: drag one item at a time to its place, top first, re-reading
    the page before every drag, until the page shows exactly the wanted
    order. Exits 6 on any doubt; nothing submitted."""
    ox, oy = region_box(cfg)[:2]
    tries = 2 * len(want) + 1
    for attempt in range(tries + 1):
        img, path = look(cfg)
        now = read_drag(img, path)
        if not now or now["kind"] != "ordering" or len(now["items"]) != len(want):
            lost("the items can't all be found on the page any more")
        texts = [i["text"] for i in now["items"]]
        wrong = [i for i, (t, w) in enumerate(zip(texts, want)) if not same_text(t, w)]
        if not wrong:
            return
        if attempt == tries:
            break
        src = [j for j, t in enumerate(texts) if same_text(t, want[wrong[0]])]
        if len(src) != 1:
            lost(f"can't tell which item is '{want[wrong[0]]}'")
        a, b = (_middle(now["items"][i]["box"]) for i in (src[0], wrong[0]))
        drag((a[0] + ox, a[1] + oy), (b[0] + ox, b[1] + oy))
    print(f"WRONG ORDER: after {tries} drags the page still doesn't show the "
          f"wanted order. NOTHING WAS SUBMITTED -- fix it by hand.")
    sys.exit(6)


def put_in_boxes(cfg, q, want):
    """Matching: drag each waiting item into its box, re-reading the page
    before every drag, until every box shows its item. Exits 6 on any doubt
    (a box showing a different item is never touched); nothing submitted."""
    ox, oy = region_box(cfg)[:2]
    tries = 2 * len(want) + 1
    for attempt in range(tries + 1):
        img, path = look(cfg)
        boxes = find_boxes(img)
        labels = [b for b in boxes if _near(b["fill"], LABEL_FILL)]
        if len(labels) != len(want):
            lost("the boxes can't all be found on the page any more")
        # A filled box may look different: go by its label's row.
        slots = [(s["box"][0], lab["box"][1], s["box"][2], lab["box"][3])
                 for s, lab in zip(q["slots"], labels)]
        words = ocr_words(path)
        have = [box_text(words, s) for s in slots]
        for i, (h, w) in enumerate(zip(have, want)):
            if text_key(h) and not same_text(h, w):
                print(f"WRONG MATCH: box {i + 1} shows '{h}' but should hold '{w}'. "
                      f"NOTHING WAS SUBMITTED -- fix it by hand.")
                sys.exit(6)
        todo = [i for i, h in enumerate(have) if not text_key(h)]
        if not todo:
            return
        if attempt == tries:
            break
        src = [b for b in boxes if _near(b["fill"], WHITE)
               and not any(_inside(_middle(b["box"]), s) for s in slots)
               and same_text(box_text(words, b["box"]), want[todo[0]])]
        if len(src) != 1:
            lost(f"can't find the waiting item '{want[todo[0]]}'")
        a, b = _middle(src[0]["box"]), _middle(slots[todo[0]])
        drag((a[0] + ox, a[1] + oy), (b[0] + ox, b[1] + oy))
    print(f"NOT MATCHED: after {tries} drags some boxes are still empty. NOTHING "
          f"WAS SUBMITTED -- fix it by hand.")
    sys.exit(6)


def drag_answer(kind, letters_text, level=None, source="none"):
    # An ordering / matching question. No level = test mode: move the items
    # ONLY -- never confidence (which submits) or Next. With a level it is the
    # whole round: chime, move, submit, next shot.
    if level is not None:
        level = level.lower()
        if level not in ("high", "medium", "low"):
            print("BAD USAGE: orderround|matchround <letters> <high|medium|low> [source]")
            sys.exit(1)
        chime()
    cfg, seen = ready_to_click()
    if not cfg.get("markers"):
        print("BAD USAGE: ordering / matching needs marker mode (`markers on`).")
        sys.exit(1)
    letters = parse_letters(letters_text, True)
    q, want = drag_question(seen, kind, letters)
    if level is not None:
        need_next_picture()
    (put_in_order if kind == "ordering" else put_in_boxes)(cfg, q, want)
    if level is None:
        path = SHOTS / f"pick_{time.strftime('%Y%m%d_%H%M%S')}.png"
        grab(cfg).save(path)
        print(f"MOVED: {','.join(letters)} only (no confidence, no Next); the page "
              f"shows them in place. After-move shot: {path}")
        return
    submit(cfg, level, [("order:" if kind == "ordering" else "match:") + "-".join(letters)], source)
    shot()


def answer(letters_text, level, count=None, source="none"):
    level = level.lower()
    if level not in ("high", "medium", "low"):
        print("BAD USAGE: answer <letters> <high|medium|low> [count]")
        sys.exit(1)
    cfg, seen = ready_to_click()
    letters = parse_letters(letters_text, cfg.get("markers"))

    if cfg.get("markers"):
        need_next_picture()
        select_markers(cfg, seen, letters, count)
        result, fb_path = submit(cfg, level, letters, source)
        return result, letters, fb_path

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
    sys.stdout.reconfigure(errors="replace")   # screen text can hold any character
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
    elif len(args) in (3, 4, 5) and args[0] == "round":
        play_round(args[1], args[2], count_arg(args[3]) if len(args) >= 4 else None,
                   args[4] if len(args) == 5 else "none")
    elif len(args) == 2 and args[0] == "fill":
        fill(count_arg(args[1]))
    elif len(args) in (3, 4) and args[0] == "fillround":
        fill_round(args[1], count_arg(args[2]), args[3] if len(args) == 4 else "none")
    elif len(args) == 2 and args[0] in ("order", "match"):
        drag_answer("ordering" if args[0] == "order" else "matching", args[1])
    elif len(args) in (3, 4) and args[0] in ("orderround", "matchround"):
        drag_answer("ordering" if args[0] == "orderround" else "matching", args[1], args[2],
                    args[3] if len(args) == 4 else "none")
    elif len(args) == 2 and args[0] == "blanks":
        # Debug: list the fill-in-the-blank boxes found in a saved screenshot.
        for b in find_blanks(Image.open(args[1]), load_config()):
            print(b, "ink", blank_ink(Image.open(args[1]), b))
    elif len(args) == 2 and args[0] == "drag":
        # Debug: the ordering / matching question found in a saved screenshot.
        q = read_drag(Image.open(args[1]), args[1])
        if q:
            report_drag(q)
            for part in ("slots", "items"):
                for b in q.get(part, []):
                    print(part, b)
        else:
            print("no ordering / matching question found")
    elif len(args) == 2 and args[0] == "read":
        # Debug: what the script reads off a saved screenshot + memory lookup.
        cfg = load_config()
        report_reading(args[1], cfg, find_choices(Image.open(args[1]), cfg), save=False)
    elif len(args) == 3 and args[0] == "remember":
        remember(args[1], args[2])
    elif args == ["chime"]:
        chime()
    elif len(args) == 2 and args[0] == "popup":
        popup(args[1])
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
