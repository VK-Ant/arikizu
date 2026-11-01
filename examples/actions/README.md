# Custom action rules

Each file in this directory shows ONE custom action rule you can drop
into `workers/video_worker/video_worker/actions.py` to extend the 12
built-in actions. Rules are pure Python functions over MediaPipe pose
landmarks; no training needed.

## How to add one

1. Open `workers/video_worker/video_worker/actions.py`.
2. Paste the rule function (e.g. `is_squatting`) alongside the existing
   `is_sitting`, `is_standing`, etc.
3. In `recognize()`, add a line to the `scores` dict:
   ```python
   "squatting": is_squatting(pose),
   ```
4. In `ACTIONS_KNOWN`, add `"squatting"` to the list.
5. In `action_definitions()`, add a row describing it.
6. Add a test in `workers/video_worker/tests/test_actions.py` using the
   same canned-landmarks pattern.
7. Restart the worker.

## Available examples

| File | Action | Rough signature |
|---|---|---|
| `squatting.py` | squatting | hips low + knees bent + feet planted |
| `reaching_up.py` | reaching_up | one arm extended, wrist above head |
| `thumbs_up.py` | thumbs_up (approximate) | hand near face, thumb estimated from pose+optical flow |
| `looking_down.py` | looking_down | nose below shoulder line |
| `hugging.py` | hugging (two-person) | two people's wrist regions overlap |

Rules in this directory are intentionally simple to show the pattern.
Replace the heuristics with your own domain knowledge.

For actions that are hard to reduce to pose rules (yoga pose
variations, specific sign-language signs, cooking actions, etc.),
use the Video Studio's reference-image path instead; it routes through
the VLM.
