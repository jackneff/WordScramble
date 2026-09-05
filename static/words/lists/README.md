# Vocabulary lists

Drop a `.txt` file in this folder and it appears in the game's "Which words?"
picker on the home screen — no restart, no code change.

- One word per line, any mix of lengths
- The filename becomes the display name: `week-12.txt` shows as "Week 12"
- Use letters, digits, hyphens and underscores in the filename only
- Blank lines and anything that isn't a plain 3–12 letter word are skipped,
  so comment lines starting with `#` are fine
- Duplicates are removed automatically

Delete a file and the list disappears from the picker. Rounds already played
from it keep the name in the score history.

`example-week.txt` is a sample; delete it whenever you like.
