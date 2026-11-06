# Data profile

Measured by the harness profiler v0.2.0 on 2026-11-05T18:23:57-0600 (runtime 0.43 s). Root: `/tmp/claude-1000/-home-user-Documents-work-eeg-research-03-code-eeg-agent-harness/d31cea52-48c4-4714-9584-6c801a3ed637/scratchpad/e2e/proj/data/raw`. Plugins: none. Every number below is computed from the files; nothing is interpreted. Full detail: `DATA_PROFILE.json`.

## Overview

| Item | Value |
|---|---|
| Files found | 4 |
| Profiled | 3 |
| No reader for the format | 0 |
| Documents (not recordings; read them, G16) | 1 |
| Reader errors | 0 |
| Extensions | `.docx` 1, `.fif` 3 |
| Sampling rates (Hz: files) | 256.0: 3 |
| Duration per file (s) | min 90.0, median 90.0, max 90.0 |

## Folder structure

Digits are shown as `#`.

| Depth | Distinct folders | Name shape | Files below | Examples |
|---|---|---|---|---|
| 0 | 3 | `sub-##` | 3 | `sub-01`, `sub-02`, `sub-03` |
| 1 | 3 | `ses-##` | 3 | `ses-01` |

## File names

| Name (without extension) | Files |
|---|---|
| `bitacora` | 1 |
| `sub-01_ses-01_oddball_raw` | 1 |
| `sub-02_ses-01_oddball_raw` | 1 |
| `sub-03_ses-01_oddball_raw` | 1 |

## Channels

| Channel set | Files |
|---|---|
| Fz, Cz, Pz, Oz, C3, C4, P3, P4, STI 014 | 3 |

## Event codes (all profiled files)

| Code | Files containing it | Total count | Median interval between two events of this code (ms) |
|---|---|---|---|
| 1 | 3 | 214 | 1031.2 |
| 2 | 3 | 48 | 3511.7 |
| 9 | 3 | 3 | — |

## Code sets

| Codes present | Files |
|---|---|
| 1, 2, 9 | 3 |

## Transitions (code followed by code; top 40)

| Transition | Count | Median gap (ms) |
|---|---|---|
| 1->1 | 164 | 1009.8 |
| 2->1 | 48 | 988.3 |
| 1->2 | 47 | 980.5 |
| 9->1 | 2 | 1500.0 |
| 9->2 | 1 | 1500.0 |

## Events per file, by file-name shape

| Name shape | Events per file: files |
|---|---|
| `sub-##_ses-##_oddball_raw` | 88: 2, 89: 1 |

## Documents in the data folder

Written files that are not recordings (lab logs, READMEs, protocol sheets, tables). They are not interpreted here; agents read them before asking a human (G16).

| File | Size (bytes) |
|---|---|
| `bitacora.docx` | 1042 |

## Per file

| File | Reader | fs | Channels | Duration (s) | Events | Codes | Flat / NaN channels | Error |
|---|---|---|---|---|---|---|---|---|
| `sub-01/ses-01/sub-01_ses-01_oddball_raw.fif` | eegprofile.readers.mne_formats | 256.00 | 9 | 90.0 | 89 | 3 | — | |
| `sub-02/ses-01/sub-02_ses-01_oddball_raw.fif` | eegprofile.readers.mne_formats | 256.00 | 9 | 90.0 | 88 | 3 | — | |
| `sub-03/ses-01/sub-03_ses-01_oddball_raw.fif` | eegprofile.readers.mne_formats | 256.00 | 9 | 90.0 | 88 | 3 | — | |
