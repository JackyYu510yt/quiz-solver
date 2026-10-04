---
name: quiz-solver
description: Auto-play the multiple-choice quiz on screen (built for the Minecraft trivia practice site). Screenshots a pre-calibrated screen area, spawns a subagent to read the question and look up the answer (confidence = whether a source confirmed it), then clicks the answer, a confidence level (high/medium/low), and Next — looping until the quiz ends. Use when the user says "/quiz-solver", "solve the quiz", "auto-play the quiz", "answer the quiz for me". `/quiz-solver reset` (or "recalibrate the quiz solver", "pick a new zone") only re-picks the screen zone and click spots; `/quiz-solver next` re-picks only the Next button spot. `/quiz-solver NAME` plays a saved preset (named set of spots); `/quiz-solver create NAME` makes a new one; `reset NAME` / `next NAME` edit that preset; `/quiz-solver presets` lists them. `/quiz-solver stop` stops a run in progress.
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
`_`; `reset`, `next`, `presets`, `default`, `stop`, `start`, `create` are taken. To tell if NAME
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
   > multiple-choice trivia question with four answers labeled A, B, C, D.
   > If the image does NOT show a question with four answer choices (for
   > example it's a score/results screen), reply with exactly: `NO_QUESTION`
   > Otherwise, look the answer up before answering. Use WebSearch and/or
   > WebFetch to find a page that directly states the fact; prefer the
   > official Minecraft Wiki (minecraft.wiki). Don't trust your memory alone,
   > even if you feel sure.
   > Set confidence by evidence, not by feeling:
   > - high = a page you actually read directly states the answer
   > - medium = you couldn't confirm it on a page; answering from memory
   > - low = you're guessing
   > Reply with exactly one line and nothing else:
   > `ANSWER=<A|B|C|D> CONFIDENCE=<high|medium|low> SOURCE=<url you read, or none>`

   Why look-ups: on the same 10 questions, Sonnet from memory scored 6–7/10
   and Opus from memory 9/10; Sonnet with look-ups scored 10/10 (~9 s per
   question instead of ~3 s). Memory-only "high" was often wrong; evidence-
   based "high" wasn't.

3. **Read the reply strictly.**
   - `NO_QUESTION` → the quiz is over. Go to "Finish".
   - Matches `ANSWER=([ABCD]) CONFIDENCE=(high|medium|low) SOURCE=(\S+)` →
     continue. Keep the source for the report.
   - `CONFIDENCE=high` with `SOURCE=none` breaks the rule — treat it as
     `medium` and note it in the report.
   - Anything else → STOP. Show the user the reply verbatim. Never guess an
     answer the subagent didn't give.

4. **Click.** Run `SCRIPT answer <LETTER> <level>`.
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
