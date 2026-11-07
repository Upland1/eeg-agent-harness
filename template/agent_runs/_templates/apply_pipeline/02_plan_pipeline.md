## Pipeline (G24, G25) — add to 02_plan.md

### Adapter

| Function | What it returns for this study | Source (PARADIGM section, header, measurement) |
|---|---|---|
| `dataset_parts` | | |
| `read` | | |
| `events`: unit, label rule, unit_start/end, code, unit_target | | |
| `condition_of` / `eligible` | | |

### Settings (`configs/pipeline.json`)

<!-- Paste eegpipe.settings.table(cfg). Below it, one row per profile default that
eegpipe.settings.validate returned as unconfirmed: confirm it or change it, with the reason. -->

| Profile default | Kept / changed to | Reason [source] |
|---|---|---|

### Families, primaries, comparator

| Family | Enabled | Primary | Other configurations (exploratory) |
|---|---|---|---|

Comparator: … Holm family = the primaries above; alpha …; min_n …

### Development and confirmation (G19, G25)

- Development data (participants / parts, named): …
- Confirmatory selection: `eegpipe.runner.select`, seed …, excluded files …, reported separately …
- Nothing from development is reported as confirmatory.

### Parts and runtime (G22)

| Part | Device | Expected runtime per data part (how estimated) | Who runs it |
|---|---|---|---|
