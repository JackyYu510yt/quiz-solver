# quiz-solver (Claude Code skill)

Auto-plays a 4-choice quiz on screen: screenshots a zone you pick, a helper
looks up each answer (confidence = whether a source confirmed it), then it
clicks the answer, a confidence level, and Next until the quiz ends.

Windows only. Needs Python 3 and Claude Code.

## Install on a PC

```
git clone https://github.com/JackyYu510yt/quiz-solver.git "%USERPROFILE%\.claude\skills\quiz-solver"
pip install -r "%USERPROFILE%\.claude\skills\quiz-solver\requirements.txt"
```

Then in Claude Code: `/quiz-solver create NAME` to pick your click spots,
and `/quiz-solver NAME` to play. Update later with `git pull` in that folder.

## Commands

| Command | Does |
|---|---|
| `/quiz-solver create NAME` | Make a new preset (pick 10 spots) |
| `/quiz-solver NAME` | Play using preset NAME |
| `/quiz-solver` | Play using the default spots |
| `/quiz-solver reset [NAME]` | Re-pick all spots |
| `/quiz-solver next [NAME]` | Re-pick only the Next spot |
| `/quiz-solver presets` | List presets |
| `/quiz-solver stop` | Stop a run in progress |

Saved spots, presets and screenshots stay on each PC (not in this repo).
