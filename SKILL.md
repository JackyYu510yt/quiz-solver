---
name: quiz-solver
description: Auto-play the multiple-choice quiz on screen (built for the Minecraft trivia practice site). Screenshots a pre-calibrated screen area, spawns a subagent to read the question and look up the answer (confidence = whether a source confirmed it), then clicks the answer, a confidence level (high/medium/low), and Next — looping until the quiz ends. Use when the user says "/quiz-solver", "solve the quiz", "auto-play the quiz", "answer the quiz for me". `/quiz-solver reset` (or "recalibrate the quiz solver", "pick a new zone") only re-picks the screen zone and click spots; `/quiz-solver next` re-picks only the Next button spot. `/quiz-solver NAME` plays a saved preset (named set of spots); `/quiz-solver create NAME` makes a new one; `reset NAME` / `next NAME` edit that preset; `/quiz-solver presets` lists them. `/quiz-solver stop` stops a run in progress. `/quiz-solver test [NAME]` does one dry round that clicks only the answer (no confidence, no Next) to check the click lands right. Presets can use marker mode (finds the answer circles/checkboxes on screen each round; handles "select all that apply").
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
| `/quiz-solver presets` | Run `SCRIPT presets`, show the list, stop |
| `/quiz-solver stop` | Stop the current run (see "stop" below) |
| `/quiz-solver test` / `test NAME` | ONE dry round (default / NAME): stop right before the confidence button (see "test" below) |
| `/quiz-solver markers on` / `markers on NAME` (or `off`) | Turn marker mode on/off (default / NAME): run `SCRIPT [--preset NAME] markers on\|off`, show its message, stop. If NAME isn't in `SCRIPT presets` → say `/quiz-solver create NAME` makes it; don't create it |

### test — one dry round, never submits

For checking that the answer click lands on the right choice. Same rules as
playing (preset check, `--preset NAME` on every call), but ONE round only:

1. `SCRIPT start`, then `SCRIPT shot`.
2. Spawn the helper exactly as in "The loop" step 2, and read its reply the
   same strict way. `NO_QUESTION` → say no question is showing; stop.
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
selected and stops with exit 6 (nothing submitted) if not. The feedback screen
shown after submitting moves its Next button around, so in marker mode the
script finds Next by a saved PICTURE of it (`presets/NAME.next.png`) and
never clicks a guessed spot: no confident match → exit 3, answer submitted
but nothing else clicked. The picture is taken by `/quiz-solver next NAME`
— run it while a feedback screen with its Next button is showing (click
the button's middle). Without the picture, `answer` refuses before
clicking anything. `/quiz-solver markers off NAME`
goes back to the saved spots. The default (Minecraft) setup leaves it off.

### stop — end a run now

1. Run `SCRIPT stop` FIRST, before anything else. From then on, `shot` and
   `answer` refuse to act (exit 5) — so even a helper reply that arrives
   later can't cause a click.
2. Don't take more screenshots, don't spawn helpers, don't click. Ignore any
   helper result that arrives after this; don't act on it.
3. Report: how many questions were answered, the table so far (question #,
   answer, confidence, source), and that `/quiz-solver [NAME]` starts a fresh
   run. Also treat a plain "stop" from the user mid-run the same way.

**Presets:** a preset is a named set of saved spots (`presets/NAME.json`) so
different quiz pages/layouts can each keep their own. Whenever a preset NAME
is in play, put `--preset NAME` right after `SCRIPT` on EVERY call this run
(e.g. `SCRIPT --preset mgh shot`). Names: lowercase letters, numbers, `-`,
`_`; `reset`, `next`, `presets`, `default`, `stop`, `start`, `create`, `test`, `markers` are taken. To tell if NAME
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

(The script accepts any spot names the same way, e.g. `calibrate high medium
low`, if the user asks to re-pick other single spots.)

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

## The loop (max 30 rounds, then stop and report)

Start every play run with `SCRIPT start` (clears a stop flag left by an
earlier `/quiz-solver stop`). The run then continues until the quiz is fully
complete — unless a stop arrives. Any time `shot` or `answer` exits 5, the
user stopped the run: end it right there and report as in "stop" above.

For each round:

1. **Screenshot.** Run `SCRIPT shot`. It prints the PNG path.

2. **Solve with a subagent.** Spawn an Agent (`subagent_type: general-purpose`,
   `model: sonnet`) and wait for it to finish. Don't look at the image yourself.
   Use this prompt, with the path filled in:

   > Use the Read tool to view the image at `<PATH>`. It's a screenshot of a
   > quiz question with answer choices. Call the choices A, B, C, D… from TOP
   > to BOTTOM, whether or not the page shows letters.
   > - If the image shows no question with choices (e.g. a score/results or
   >   answer-feedback screen), reply with exactly: `NO_QUESTION`
   > - If it's a question you can't answer by picking choices (fill in the
   >   blank, matching, ordering, typing), reply with exactly: `UNSUPPORTED`
   > - If it says "select all that apply" (or has checkboxes), give EVERY
   >   correct choice; otherwise give exactly one.
   > Look the answer up before answering. Use WebSearch and/or WebFetch to
   > find a page that directly states the fact. For game trivia prefer the
   > official wiki (e.g. minecraft.wiki); for textbook/course questions,
   > search the key term or phrase from the question and prefer a page that
   > defines it. Don't trust your memory alone, even if you feel sure.
   > Set confidence by evidence, not by feeling:
   > - high = a page you actually read directly states the answer
   > - medium = you couldn't confirm it on a page; answering from memory
   > - low = you're guessing
   > Reply with exactly one line and nothing else (COUNT = how many choices
   > the question shows; ANSWER = letters, comma-separated if several):
   > `ANSWER=<letters, e.g. B or A,C,D> COUNT=<n> CONFIDENCE=<high|medium|low> SOURCE=<url you read, or none>`

   Why look-ups: on the same 10 questions, Sonnet from memory scored 6–7/10
   and Opus from memory 9/10; Sonnet with look-ups scored 10/10 (~9 s per
   question instead of ~3 s). Memory-only "high" was often wrong; evidence-
   based "high" wasn't.

3. **Read the reply strictly.** Look ONLY at the reply's last non-empty
   line; ignore any explaining above it (the helper sometimes adds a
   sentence first). Every rule below applies to that last line, which must
   match exactly — if it doesn't, STOP as in "Anything else".
   - `NO_QUESTION` → the quiz is over. Go to "Finish".
   - `UNSUPPORTED` → STOP; tell the user this question type needs answering
     by hand, then `/quiz-solver [NAME]` continues.
   - Matches `ANSWER=([A-H](?:,[A-H])*) COUNT=(\d+) CONFIDENCE=(high|medium|low) SOURCE=(\S+)` →
     continue. Keep the source for the report. Without marker mode only a
     single letter A–D is valid — several letters → STOP and say this
     preset needs `markers on` for select-all questions.
   - In marker mode, if `shot` printed `CHOICES: N found` and N ≠ COUNT →
     STOP (the script would refuse anyway).
   - `CONFIDENCE=high` with `SOURCE=none` breaks the rule — treat it as
     `medium` and note it in the report.
   - Anything else (including a last line that only partly matches) →
     STOP. Show the user the whole reply verbatim. Never guess an
     answer the subagent didn't give.

4. **Click.** Run `SCRIPT answer <LETTERS> <level>` — in marker mode add
   COUNT: `SCRIPT answer <LETTERS> <level> <COUNT>`.
   - Exit 6 (wrong selection) or 7 (choices not found / count mismatch) →
     STOP. Nothing was submitted. Show the message.
   - Exit 0 → next round. Note question number, letter, confidence, source.
   - Exit 2 (selections didn't register) or 3 (page didn't change) → STOP.
     Show the printed message and suggest recalibrating. Don't retry blindly —
     a second click could change an answer.
   - Exit 4 (screen changed since the helper's screenshot — the quiz got
     covered, moved, or scrolled) → STOP. Nothing was clicked. Show the
     message; tell the user to bring the quiz back exactly where it was, or
     run `/quiz-solver reset` if it moved.

   `shot` never clicks. `answer` only clicks after confirming the zone still
   matches the screenshot the helper read.

## Finish

Run `SCRIPT shot` once more and Read that final image yourself so you can
report the score shown on screen. Report to the user:

- the score from the screen (or "not visible" if it isn't),
- a short table: question #, answer picked, confidence, source,
- any round that stopped early, with its exact message.

Screenshots pile up in `shots/` next to the script; mention the folder.
