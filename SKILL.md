---
name: quiz-solver
description: Auto-play the multiple-choice quiz on screen (built for the Minecraft trivia practice site). Screenshots a pre-calibrated screen area, spawns a subagent to read the question and look up the answer (confidence = whether a source confirmed it), then clicks the answer, a confidence level (high/medium/low), and Next — looping until the quiz ends. Use when the user says "/quiz-solver", "solve the quiz", "auto-play the quiz", "answer the quiz for me". `/quiz-solver reset` (or "recalibrate the quiz solver", "pick a new zone") only re-picks the screen zone and click spots; `/quiz-solver next` re-picks only the Next button spot; `/quiz-solver zone` re-picks only the quiz area's two corners. `/quiz-solver NAME` plays a saved preset (named set of spots); `/quiz-solver create NAME` makes a new one; `reset NAME` / `next NAME` / `zone NAME` edit that preset; `/quiz-solver presets` lists them. `/quiz-solver stop` stops a run in progress. `/quiz-solver test [NAME]` does one dry round that clicks only the answer (no confidence, no Next) to check the click lands right. Presets can use marker mode (finds the answer circles/checkboxes on screen each round; handles "select all that apply").
---

# Quiz Solver

Plays a 4-choice quiz shown in a browser window by looking at the screen and
clicking real mouse positions. All screen work goes through one script:

    SCRIPT = python "<BASE>\quiz_screen.py"

where `<BASE>` is this skill's base directory (shown as "Base directory for
this skill" when the skill loads) — never a hard-coded user path, so the skill
works on any PC.

## Arguments — what to do

Read the argument(s) the skill was invoked with and pick ONE row:

| Invoked as | Do |
|---|---|
| `/quiz-solver` | Play, using the default saved spots |
| `/quiz-solver NAME` | Play, using preset NAME. If NAME doesn't exist: don't open setup — show `SCRIPT presets` and say `/quiz-solver create NAME` makes it |
| `/quiz-solver create NAME` | Make a NEW preset NAME (see "create" below), then stop |
| `/quiz-solver reset` / `reset NAME` | Pick a new zone (default / preset NAME), then stop |
| `/quiz-solver next` / `next NAME` | Re-pick ONLY the Next spot (default / NAME), then stop |
| `/quiz-solver zone` / `zone NAME` | Re-pick ONLY the quiz area's two corners (default / NAME), then stop |
| `/quiz-solver presets` | Run `SCRIPT presets`, show the list, stop |
| `/quiz-solver stop` | Stop the current run (see "stop" below) |
| `/quiz-solver test` / `test NAME` | ONE dry round (default / NAME): stop right before the confidence button (see "test" below) |
| `/quiz-solver markers on` / `markers on NAME` (or `off`) | Turn marker mode on/off (default / NAME): run `SCRIPT [--preset NAME] markers on\|off`, show its message, stop. If NAME isn't in `SCRIPT presets` → say `/quiz-solver create NAME` makes it; don't create it |

### test — one dry round, never submits

For checking that the answer click lands on the right choice. Same rules as
playing (preset check, `--preset NAME` on every call), but ONE round only:

1. `SCRIPT start`, then `SCRIPT shot`.
2. Get the answer exactly as in "The loop" steps 1–2 (a `MEMORY HIT` needs
   no helper), reading a helper reply the same strict way. `NO_QUESTION` or
   `CHOICES: 0 found` without a `BLANKS:` line → say no question is
   showing; stop. A `FILL=` reply (fill in the blank) → run `SCRIPT fill
   <BLANKS>` with the `FILL:` line on stdin (see "Fill in the blank")
   instead of step 3; it types ONLY, and prints an after-typing screenshot
   path to report from in step 4. An `ORDER=` / `MATCH=` reply (see
   "Ordering / matching") → run `SCRIPT order <LETTERS>` / `SCRIPT match
   <LETTERS>` instead; it drags ONLY.
3. Run `SCRIPT pick <LETTERS> [<COUNT>]` instead of `answer` (COUNT only in
   marker mode — see "Marker mode"). It clicks ONLY the answer(s) — never
   confidence, never Next — and prints an after-click screenshot path. In
   marker mode it also checks the selection itself (`MATCH: …`, or exit 6/7).
   Exit 4/5/6/7 → same as in the loop.
4. Read that after-click image yourself and report: the question, the
   helper's answer (letters + their text, confidence, source), and which
   choices the screenshot shows as selected — say plainly whether it MATCHES.
   Then stop: the user finishes the question by hand. Never call `answer` here.

### Marker mode (per preset)

Some sites (e.g. the McGraw Hill one, preset `mgh`) move the answers around
between questions and have "select all that apply" questions. For those,
`/quiz-solver markers on NAME` makes the script find the radio circles /
checkboxes on screen every round (in the column of the saved A spot) and
label them A, B, C… top to bottom; the saved B–D spots are ignored. `shot`
then also prints `CHOICES: N found`. On these sites pressing a confidence
button SUBMITS, so `answer` first proves exactly the chosen answers show as
selected and stops with exit 6 (nothing submitted) if not. That check looks
up to 3 times, 0.4 s apart; a wanted answer that still isn't selected is
clicked again (`RETRY: …`, 2 extra clicks at most) and re-checked the same
way — an unwanted answer showing as selected is never retried. A confidence
press that doesn't move the page on is pressed again (3 presses at most,
and only while the screen still looks exactly as it did before the first
press); each miss prints `CONFIDENCE TROUBLE: …` and is logged like a Next
miss. Only then → exit 3, answer entered but not submitted. The feedback screen
shown after submitting moves its Next button around, so in marker mode the
script finds Next by a saved PICTURE of it (`presets/NAME.next.png`) and
never clicks a guessed spot. It doesn't give up on the first miss: if the
picture isn't found it scrolls the page down and looks again, and if a
press of Next doesn't move the page on it finds the picture again and
presses again (3 presses at most — safe, the answer is already in). Only
then → exit 3, answer submitted, Next not pressed. Every miss prints
`NEXT TROUBLE: …` (or `CONFIDENCE TROUBLE: …`) and leaves a line in `shots/next_failures.log` plus a
full-screen `shots/nextfail_*.png`; a run that printed any → mention it in
the report. The picture is taken by `/quiz-solver next NAME`
— run it while a feedback screen with its Next button is showing (click
the button's middle). Without the picture, `answer` refuses before
clicking anything. `/quiz-solver markers off NAME`
goes back to the saved spots. The default (Minecraft) setup leaves it off.

### Fill in the blank (marker mode only)

When a screenshot has no answer circles, the script looks for empty text
boxes instead and `shot` prints `BLANKS: N found (fill in the blank)` (no
`READ:` / memory lines — these questions always go to the helper and are
not saved to the answer memory). The helper replies with a `FILL=` last
line, and the round is played with `fillround` instead of `round`, the text
going in on stdin so nothing needs escaping (Bash tool):

```
python "<BASE with forward slashes>/quiz_screen.py" [--preset NAME] fillround <level> <BLANKS> <SOURCE> <<'EOF'
FILL: <the FILL= text, exactly as the helper gave it>
EOF
```

It plays the chime, re-checks the screen, clicks each box in reading order
and types its text (`|` separates blanks), proves every box now shows
writing BEFORE pressing the confidence button (else exit 6, nothing
submitted). That check looks up to 3 times, 0.4 s apart; a box that still
shows no writing is clicked and typed again (`RETRY: blank N …`, 2 extra
typings at most — safe, it replaces whatever is in the box) and re-checked
the same way; boxes that already show writing are left alone. Then it submits, logs the result, presses Next and takes the next
screenshot exactly as `round` does. Exit codes mean the same as for
`round`; exit 7 = blanks not found / count mismatch (nothing typed).
`SCRIPT fill <BLANKS>` (same stdin) is the dry version for test mode.

### Ordering / matching (marker mode only)

Drag-and-drop questions. With no answer circles on screen the script looks
for their boxes first, and `shot` prints (no `READ:` / memory lines — these
always go to the helper and are not saved to the answer memory):

- ordering: `ORDERING: N items (drag into order)` then
  `ITEMS: A) <text> | B) <text> | …` — the items lettered top to bottom as
  they stand now;
- matching: `MATCHING: N boxes, M items (…)`, then
  `BOXES: 1) <label> | 2) <label> | …` and `ITEMS: A) <text> | …` — the
  boxes numbered top to bottom, the waiting items lettered in reading order.

`ITEMS: failed …` → the script couldn't read an item: STOP, by hand. The
helper must use the script's letters, so its prompt gets the printed lines
added after the image path (still one line):

> Read `<BASE>\helper_prompt.md` and follow it exactly. IMAGE: `<PATH>` BOXES: `<the BOXES line's text, matching only>` ITEMS: `<the ITEMS line's text>`

It replies with an `ORDER=` or `MATCH=` last line; the round is then ONE
command (Bash tool), with the same exit codes as `round`:

```
python "<BASE with forward slashes>/quiz_screen.py" [--preset NAME] orderround <LETTERS> <level> <SOURCE>
python "<BASE with forward slashes>/quiz_screen.py" [--preset NAME] matchround <LETTERS> <level> <SOURCE>
```

`orderround C,A,B,D` = item C goes first/top, then A, B, D. `matchround
C,A,B` = item C into box 1, A into box 2, B into box 3. It plays the chime,
re-checks the screen, drags one item at a time (re-reading the page before
every drag), and only when the page itself shows every item in its place
presses the confidence button — else exit 6, nothing submitted (items may
have been moved). Then it logs the result, presses Next and takes the next
screenshot as `round` does. Exit 7 = question not found / letter count
doesn't fit (nothing moved). `SCRIPT order <LETTERS>` / `SCRIPT match
<LETTERS>` are the dry versions for test mode (drag only, then an
after-move screenshot path). Matching was built from one saved screenshot
and has NOT yet been tried on a live page — say so in the report the first
time it runs, and use `/quiz-solver test NAME` on it first if the user is
there.

### stop — end a run now

1. Run `SCRIPT stop` FIRST, before anything else. From then on, `shot` and
   `answer` refuse to act (exit 5) — so even a helper reply that arrives
   later can't cause a click.
2. Don't take more screenshots, don't spawn helpers, don't click. Ignore any
   helper result that arrives after this; don't act on it.
3. Report: how many questions were answered, the table so far (question #,
   answer, confidence, source, result), and that `/quiz-solver [NAME]` starts a fresh
   run. Also treat a plain "stop" from the user mid-run the same way.

### Popup — when a run stops by itself

Whenever a play run ends early for any reason other than the user stopping
it — every STOP in "The loop" (exit 2/3/6/7, a second exit 4, `UNSUPPORTED`,
a count mismatch, two helper replies that don't match, a question that
needs answering by hand) and the 30-round limit — run this BEFORE writing
the report:

    SCRIPT popup "Q<n>: <one short plain sentence saying why>"

It shows a Windows notification in the screen corner, "Quiz solver: run
stopped" plus that sentence, which stays until dismissed (it may sit over
the quiz zone — the user dismisses it before the next run). Not for a user
stop (exit 5), not for a first exit 4 (that one restarts by itself), not
for a quiz that finished normally, and not in `test`.

**Presets:** a preset is a named set of saved spots (`presets/NAME.json`) so
different quiz pages/layouts can each keep their own. Whenever a preset NAME
is in play, put `--preset NAME` right after `SCRIPT` on EVERY call this run
(e.g. `SCRIPT --preset mgh shot`). Names: lowercase letters, numbers, `-`,
`_`; `reset`, `next`, `zone`, `presets`, `default`, `stop`, `start`, `create`, `test`, `markers` are taken. To tell if NAME
exists, run `SCRIPT presets`. New presets are made ONLY by `create NAME` —
never by playing or by `reset`/`next` on a name that doesn't exist.

### create — make a new preset (only on purpose)

1. Run `SCRIPT presets`. If NAME is already listed → don't overwrite it;
   say it exists and that `/quiz-solver reset NAME` redoes its spots. Stop.
2. Say "Creating new preset 'NAME'", then the overlay instructions (as in
   reset below). Run `SCRIPT --preset NAME create` (timeout 300000) — the
   script refuses if NAME already exists.
3. `SAVED:` → say `/quiz-solver NAME` now plays it. `CANCELLED:` → nothing
   saved. Never start playing in the same call.

### reset — pick a new zone only

Do ONLY this, then stop — don't screenshot, don't spawn a helper, don't click
anything on the page:

1. If NAME was given and isn't in `SCRIPT presets` → don't create it here;
   say `/quiz-solver create NAME` makes it. Stop. (The script refuses too.)
2. Tell the user: "A see-through overlay will appear. Click the 10 spots it
   names, in order: the quiz area's top-left corner, its bottom-right corner,
   answers A–D, High, Medium, Low, then Next. Esc cancels (the old spots are
   kept)."
3. Run `SCRIPT [--preset NAME] calibrate` (timeout 300000).
4. `SAVED:` → say which preset (or default) was saved, and that
   `/quiz-solver [NAME]` plays it. `CANCELLED:` → nothing changed.

### next — re-pick ONLY the Next spot

1. Tell the user: "A see-through overlay will appear. Click the Next button
   (just that one spot). Esc cancels; everything else stays as it was."
2. Run `SCRIPT [--preset NAME] calibrate next` (timeout 300000).
3. `SAVED:` → say only the Next spot changed. `CANCELLED:` → nothing changed.

### zone — re-pick ONLY the quiz area's corners

For when the zone is too narrow (`READ: clipped`, or a fill-in-the-blank
box the script can't find because it runs off the edge).

1. If NAME was given and isn't in `SCRIPT presets` → don't create it here;
   say `/quiz-solver create NAME` makes it. Stop.
2. Tell the user: "A see-through overlay will appear. Click the quiz area's
   top-left corner, then its bottom-right corner (just those two spots) —
   wide enough to hold the longest question line and any text box. Esc
   cancels; everything else stays as it was."
3. Run `SCRIPT [--preset NAME] calibrate region_tl region_br` (timeout 300000).
4. `SAVED:` → say only the quiz area changed. `CANCELLED:` → nothing changed.

(The script accepts any spot names the same way, e.g. `calibrate high medium
low`, if the user asks to re-pick other single spots.)

### Unattended run on a different screen size (fresh chat)

Playing `/quiz-solver mgh` needs no setup or recalibration on a new screen
size or RDP window. Every run the script re-finds the page itself: the McGraw
Hill logo (top) and the confidence bar (bottom), tried at several zoom sizes,
move and scale every saved spot (`ADAPT: top ... bottom ... spots moved.` is
normal; one anchor found is enough). Nothing is cached, so a moved window
can't leave stale spots. Only `ADAPT: anchor not found (neither picture)` is a
problem. Before stopping on it: run `SCRIPT --preset NAME start`, wait 3 s,
and run `shot` again, up to 3 times (the page may still be loading or a window
covering it); stop with the popup only if it still fails. Never run `reset`
or `create` yourself during an unattended run.

## Before starting

1. The quiz must be open in a browser, fully visible, and NOT covered by the
   terminal. Don't move, resize, or zoom the browser after calibrating.

2. If the default spots (`config.json`) are missing and no preset was named,
   or a run fails with exit code 2:
   - Tell the user: "A see-through overlay will appear. Click the 10 spots it
     names, in order: the quiz area's top-left corner, its bottom-right corner,
     answers A–D, High, Medium, Low, then Next. Esc cancels."
   - Run `SCRIPT [--preset NAME] calibrate` (timeout 300000). It blocks until they finish.
   - The quiz area should cover the question AND all four answers.

### Screen size changed (e.g. RDP) — not a stop

A `WARNING: screen size is …` line followed by `ADAPT: … spots shifted.` is
normal: the script found its anchor pictures and moved the saved spots for
this screen by itself. Carry on playing, and mention it once in the report.
Only `ADAPT: anchor … not found` / `no anchor pictures` is a problem: the quiz
isn't fully visible (or the preset has no anchors) — STOP and say so.
High/Medium/Low are also found by their own saved pictures
(`presets/NAME.spot_*.png`, made by `SCRIPT --preset NAME learn` while the
question screen shows); `ADAPT: 'medium' button found by picture …` is normal.
Exit 8 (`MOUSE STUCK`) = the cursor wouldn't go to the click spot; nothing was
clicked — STOP, popup, tell the user.

## The loop (max 30 rounds, then stop and report)

Start every play run with `SCRIPT start` (clears a stop flag left by an
earlier `/quiz-solver stop`), then `SCRIPT shot` for the first question.
After that, ONE command per round (`round`, step 3) submits the answer AND
takes the next screenshot — don't call `chime`, `answer`, `remember` or
`shot` separately. The run continues until the quiz is fully complete —
unless a stop arrives. Any time `shot` or `round` exits 5, the user stopped
the run: end it right there and report as in "stop" above. Any other early
stop → run `SCRIPT popup "…"` first (see "Popup").

What `shot` prints (and `round`, at its end, for the NEXT question):

- marker mode, only when the screenshot shows no question (or drag items
  it can't read): `LOOK AGAIN: …` — the page may still be drawing, so it
  waits 1 s and takes the screenshot again, 2 extra looks at most, before
  printing the lines below for the last look. It never clicks. Nothing to
  act on;
- the PNG path;
- marker mode: `CHOICES: N found (A, B, …)`;
- marker mode, no choices but drag-and-drop boxes on screen: `ORDERING: …`
  or `MATCHING: …` with `BOXES:` / `ITEMS:` lines (see "Ordering /
  matching"), and nothing after them;
- marker mode, no choices but text boxes on screen: `BLANKS: N found (fill
  in the blank)`, and nothing after it;
- marker mode: `READ: <question> | A) <choice> | B) <choice> | …` — the
  script's own reading of the screenshot (Windows' built-in text
  recognition: no helper, no tokens). `READ: failed` or `READ: clipped`
  means it couldn't use the reading; the helper answers as usual;
- after a `READ:` line: `MEMORY HIT: ANSWER=<letters> COUNT=<n>` (plus
  `WHY:` / `FEYNMAN:` lines when the memory has them) when the answer memory
  holds exactly this question with exactly these choices, else `MEMORY MISS`.

For each round:

1. **Get the answer.** Pick the first that applies:
   - an `ORDERING:` or `MATCHING:` line → a drag-and-drop question: solve
     it with a subagent as in "Otherwise" below, with the `BOXES:` /
     `ITEMS:` text added to the prompt (see "Ordering / matching").
     `ITEMS: failed` → STOP, by hand.
   - `CHOICES: 0 found` with a `BLANKS: N found` line → a fill in the
     blank: solve it with a subagent exactly as in "Otherwise" below.
   - `CHOICES: 0 found` (marker mode) and no `BLANKS:` line → there is no
     pickable question. Don't spawn a helper; go to "Finish". (If the final
     image shows a question without choices — matching, ordering, a blank
     the script didn't find — STOP instead and say it needs answering by
     hand; if it shows an answer-feedback screen, say its Next button needs
     pressing by hand.)
   - `MEMORY HIT` → use its letters and COUNT with CONFIDENCE=high,
     SOURCE=memory. No helper, no web search. Take the question and choices
     from the `READ:` line.
   - Otherwise **solve with a subagent.** Spawn an Agent — `subagent_type:
     quiz-answer` if that agent type is available, else `subagent_type:
     general-purpose` with `model: sonnet` — and wait for it to finish. Don't
     look at the image yourself. The whole prompt is this one line, with the
     paths filled in (the instructions live in `helper_prompt.md`, so don't
     retype them):

     > Read `<BASE>\helper_prompt.md` and follow it exactly. IMAGE: `<PATH>`

   Why look-ups: on the same 10 questions, Sonnet from memory scored 6–7/10
   and Opus from memory 9/10; Sonnet with look-ups scored 10/10 (~9 s per
   question instead of ~3 s). Memory-only "high" was often wrong; evidence-
   based "high" wasn't. Why Sonnet: Opus used too much usage (~44k tokens
   per question). Earlier, on McGraw Hill course questions Sonnet rarely
   found a source and missed easy ones, and Opus was the stronger fallback
   when no page confirms the answer — so this is a trial: check
   `shots/log.csv` results, and switch back to `model: opus` if accuracy
   drops. (`quiz-answer` is an optional per-PC agent,
   `~/.claude/agents/quiz-answer.md`, limited to Read/WebSearch/WebFetch so
   each helper starts with less overhead.)

2. **Show the question, then read the reply strictly.** Post each question
   in chat so the user can scroll back to it — display only, never used to
   decide anything. This is REQUIRED every round and comes BEFORE the click
   in step 3: never skip it, never save it for later, and post it even when
   the round then stops (exit 6, UNSUPPORTED, ...). Post it as a code block
   in exactly this layout — the `=` lines box the answer off so it's easy
   to spot; the answer line has no `Answer:` label and gives every picked
   letter with its text; `Why:` and `Feynman:` are one sentence each:

   ```
   ===============
   Q<n>: <question>
     A) …
     B) … (each choice on its own line, indented; after every choice
          that was NOT picked, add its reason from the helper's `WRONG:`
          line in brackets, e.g. `B) <choice text> (<short reason>)`)
   ===============
   <letter>) <choice text>, <letter>) <choice text>
   ===============
   Why: <WHY line>
   Feynman: <FEYNMAN line>
   ```

   (Missing QUESTION/WHY/FEYNMAN/WRONG lines → show what's there; never
   write a wrong-choice reason the helper didn't give — a `MEMORY HIT` has
   none. The `WRONG:` line is display only: don't pass it to `round`. On a
   `MEMORY HIT` use the `WHY:` / `FEYNMAN:` lines `shot` printed; if it
   printed none, write `Why: answered from the answer memory (no
   explanation saved).` and leave Feynman out.) A `MEMORY HIT` needs no
   further checking — go to step 3. For a helper reply, look
   ONLY at its answer line; ignore any explaining above it (the helper
   sometimes adds a sentence first). Code-fence lines (```` ``` ````) don't
   count as lines, and backticks wrapping a whole line are removed first
   (helpers copy the prompt's formatting) — nothing else is cleaned up.
   The answer line is the ONE line that starts with `ANSWER=`, `FILL=`,
   `ORDER=` or `MATCH=`,
   or is exactly `NO_QUESTION` or `UNSUPPORTED`. It must be the reply's
   last non-empty line, with one exception: the helper's search tool makes
   it add a source list, so a line that is exactly `Sources:` followed only
   by link bullets (`- [title](url)` or `- url`) may come after it and is
   ignored. No such line, two or more of them, or any other text after it →
   "Anything else". Every rule below applies to that answer line, which must
   match exactly — if it doesn't, handle it as in "Anything else".
   - `NO_QUESTION` → the quiz is over. Go to "Finish".
   - `UNSUPPORTED` → STOP; tell the user this question type needs answering
     by hand, then `/quiz-solver [NAME]` continues.
   - Matches `ANSWER=([A-H](?:,[A-H])*) COUNT=(\d+) CONFIDENCE=(high|medium|low) SOURCE=(\S+)` →
     continue. Keep the source for the report. Without marker mode only a
     single letter A–D is valid — several letters → STOP and say this
     preset needs `markers on` for select-all questions.
   - In marker mode, if `shot` printed `CHOICES: N found` and N ≠ COUNT →
     STOP (the script would refuse anyway).
   - Matches `FILL=(.+) BLANKS=(\d+) CONFIDENCE=(high|medium|low) SOURCE=(\S+)` →
     a fill in the blank; valid only when `shot` printed `BLANKS: N found`
     with N = BLANKS and the FILL text has N parts (split on `|`) —
     otherwise STOP. In the posted block show the question with no choice
     lines and, as the answer line, `Type: <text>` (`<text> | <text>` for
     several blanks). In step 3 run `fillround` (see "Fill in the blank")
     instead of `round`.
   - Matches `(ORDER|MATCH)=([A-H](?:,[A-H])*) COUNT=(\d+) CONFIDENCE=(high|medium|low) SOURCE=(\S+)` →
     valid only when `shot` printed the same kind (`ORDER` ↔ `ORDERING:`,
     `MATCH` ↔ `MATCHING:`), no letter repeats, every letter is one of the
     printed `ITEMS`, and the number of letters = COUNT = the items
     (ordering) or the boxes (matching) — otherwise STOP. In the posted
     block list the items lettered as `shot` printed them (matching: the
     boxes too) with no bracketed reasons, and as the answer line give the
     order (`1. <item text>`, `2. …` on separate lines) or the pairs
     (`<box label> ← <item text>`, one per line). In step 3 run
     `orderround` / `matchround` instead of `round`.
   - `CONFIDENCE=high` with `SOURCE=none` breaks the rule — treat it as
     `medium` and note it in the report.
   - Anything else (including an answer line that only partly matches) →
     ask again ONCE: spawn a fresh helper with the same one-line prompt on
     the same image (nothing has been clicked, so this is safe) and read
     its reply by the same rules; note the re-ask in the report. If the
     second reply doesn't match either → STOP. Show the user both replies
     verbatim. Never guess an answer the subagent didn't give, and never
     piece one together from a reply that didn't match — two failed replies
     that happen to agree are still two failed replies.

3. **Click and take the next screenshot — one command.** Run `round` with
   the **Bash tool** (not PowerShell), passing the helper's WHY and FEYNMAN
   lines on stdin so they are saved with the answer. The quoted `'EOF'`
   means nothing inside needs escaping:

   ```
   python "<BASE with forward slashes>/quiz_screen.py" [--preset NAME] round <LETTERS> <level> <COUNT> <SOURCE> <<'EOF'
   WHY: <the helper's WHY line>
   FEYNMAN: <the helper's FEYNMAN line>
   EOF
   ```

   (Without marker mode: `round <LETTER> <level>`. On a `MEMORY HIT`:
   `round <LETTERS> high <COUNT> memory`, and the stdin lines can be left
   out.) In order, it: plays the chime (`chime.mp3` next to the script, or
   the Windows alert sound); re-checks the screen and clicks the answer(s),
   the confidence level and Next exactly as `answer` does; in marker mode
   prints `RESULT: correct|wrong|unknown` read off the feedback screen,
   saves that screen as `shots/feedback_*.png` and adds a row to
   `shots/log.csv`; saves a CORRECT answer to the answer memory by itself
   (`SAVED TO MEMORY …`, or `NOT REMEMBERED: <why>` — note it, carry on);
   then takes the next screenshot and prints the same lines as `shot`.
   Record the result for the report; a `wrong` does NOT stop the run.
   - Exit 0 → next round, from the `shot` lines it just printed. Note
     question number, letter, confidence, source.
   - Exit 6 (wrong selection) or 7 (choices not found / count mismatch) →
     STOP. Nothing was submitted. Show the message.
   - Exit 2 (selections didn't register) or 3 (page didn't change) → STOP.
     Show the printed message and suggest recalibrating. Don't retry blindly —
     a second click could change an answer.
   - Exit 4 (screen changed since the helper's screenshot — the quiz got
     covered, moved, or scrolled). Nothing was clicked, so start this
     question over ONCE: run `SCRIPT shot` and treat what it prints as a
     new round 1 step (0 choices → as in step 1; `MEMORY HIT` → use it).
     If it prints a `READ:` line with real text (not `failed`/`clipped`)
     that is identical to the one the answer was read from, and the same
     `CHOICES:` count, reuse the answer you already have; otherwise get a
     new answer from a helper on the new image and post its block. Then
     run `round` again. A second exit 4 on the same question → STOP. Show
     the message; tell the user to bring the quiz back exactly where it
     was, or run `/quiz-solver reset` if it moved. Note any restart in the
     report.

   `shot` never clicks. `round` only clicks after confirming the zone still
   matches the screenshot the answer was read from.

4. **Only after a WRONG answer: read the answer key (marker mode).** `round`
   prints `READER NEEDED: … <FEEDBACK PATH>`. Spawn a reader Agent
   (`subagent_type: general-purpose`, `model: haiku`) on that path. Don't
   wait for it — carry on with the next round and handle its reply when it
   arrives (it never clicks):

   > Use the Read tool to view the image at `<FEEDBACK PATH>`. It's a quiz
   > answer-feedback screen shown after an answer was submitted. Copy all
   > text EXACTLY as shown on screen (same words, spelling and punctuation).
   > If the image doesn't fully show the question, every answer choice, and
   > a "Correct Answer" section, reply with exactly: `INCOMPLETE`
   > Otherwise reply with exactly one line of JSON and nothing else:
   > {"question": "<the question text>", "choices": ["<every answer choice, top to bottom>"], "selected": ["<the choices that are ticked/selected>"], "correct": ["<the choices listed under Correct Answer>"]}

   Take the reply's last non-empty line, skipping code-fence lines (```` ``` ````,
   ```` ```json ````). `INCOMPLETE` or not JSON → skip
   (note it). Otherwise write that line to `<BASE>\shots\reading.json` and
   run `SCRIPT remember "<BASE>\shots\reading.json" wrong`. It saves only
   if the record is consistent with the badge; `NOT SAVED: …` → note it in
   the report and carry on. Memory problems never stop the run. (A reader
   reply arriving after a stop may still be remembered.)

`READ: clipped` on many questions means the quiz zone is too narrow for the
page's text: tell the user once that `SCRIPT [--preset NAME] calibrate
region_br` (re-pick only the bottom-right corner, further right) lets those
questions use the memory too.

## Finish

The last `round` (or `shot`) already took the final screenshot: Read that
image yourself so you can report the score shown on screen. Report to the
user:

- the score from the screen (or "not visible" if it isn't),
- a short table: question #, answer picked, confidence, source, result
  (✅ correct / ❌ wrong / ? unknown — marker mode only), plus the run's
  score from those results, and how many rounds were answered from memory,
- any round that stopped early, with its exact message,
- if any round's Answer / Why / Feynman block wasn't posted during the run,
  post it now in the same format.

Screenshots pile up in `shots/` next to the script; mention the folder, and
that `shots/log.csv` keeps every submitted answer's result across runs, and
how many questions the answer memory now holds (`SCRIPT memory`).
