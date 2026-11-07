# Paradigm

Status: DRAFT
Author: paradigm-analyst
Reads: docs/DATA_PROFILE.md, inputs/, literature
Approved by Sebastian: [ ]   Date:

Every claim carries its evidence and one tag: `measured` (profile field and value),
`from inputs` (quoted), `from literature` ([n]) or `inferred` (with the reasoning).
Where the evidence ends, write `UNKNOWN`.

## 1. Paradigm family

Family: <event-related potential / steady-state evoked / motor imagery / resting state / other / UNKNOWN — needs a human>
Confidence: high / medium / low

| Evidence | Tag |
|---|---|
| | |

Alternatives ruled out, and why:

## 2. Recording

| Property | Value | Tag / evidence |
|---|---|---|
| Sampling rate | | |
| Channels | | |
| Participants, sessions, runs (folder levels) | | |
| File types / conditions (file names) | | |

## 3. Events

| Code | Count | Timing (intervals, transitions) | Meaning | Tag / evidence | Confidence |
|---|---|---|---|---|---|
| | | | | | |

## 4. Trial / block structure

<!-- The sequence of events in one trial or block, reconstructed from the
transition table, with durations. -->

## 5. Classes and labels

<!-- What is classified, how each unit gets its label (from which codes), the
class balance computed from the profile counts (show the arithmetic). -->

## 6. Analysis unit and timing

<!-- Epochs around an event (window, from inputs or literature) or continuous
windows (length, step). -->

## 7. Expected signal (for known-answer tests)

<!-- What a synthetic test should plant: e.g. a deflection at <latency> ms on
<channels> for class A only; a rhythm at <f> Hz; a power change in <band>. -->

## 8. Metrics and chance level

## 8b. Label sanity check (frozen before it runs)

<!-- A classifier-free check that the labels mean what section 5 says (e.g. the
class-average response differs as section 7 expects). Written and frozen here, before it
touches data (G10); run by the engineer as a measurement request (section 12); reported
per participant and session (G14). -->

| What is computed | Pass criterion (fixed now) | Per | Comparison set |
|---|---|---|---|
| | | | |

## 9. Typical mistakes for this paradigm

| Mistake | Why it matters here | Source |
|---|---|---|
| | | |

## 10. UNKNOWN — questions only a human can answer

<!-- Only after the four written sources were searched (CLAUDE.md G16): inputs in full
(appendices, tables), documents in the data folder, documentation the inputs point to,
and the profile or a requested measurement. List each source and what it said. -->

| # | Question | Sources checked → what each said | What was measured | Options seen |
|---|---|---|---|---|
| | | | | |

## 11. Contamination flags

<!-- "None", or which public dataset these recordings resemble and why. -->

## 12. Measurement requests

<!-- Measurements you need but cannot make yourself (you do not open data). Each is a
spec the orchestrator routes engineer → tester → run; you revise this file with the
logged outputs ("## Revision N"). -->

| # | What to measure | On which files | Output expected | Why (which claim it settles) |
|---|---|---|---|---|
| | | | | |

## 13. Pipeline settings this study needs (for /apply-pipeline)

<!-- One row per value eegpipe needs from the paradigm, each with its evidence (section above or
source). Leave UNKNOWN where nothing written answers it (G16). -->

| Setting | Value | Evidence |
|---|---|---|
| Design family (profile): event-related or frequency-tagged | | |
| Classes (names, in class-index order) | | |
| Exchangeable unit (G13) and label scheme (label per unit, or per epoch from a unit target) | | |
| Label rule (event codes -> labels) | | |
| Epoch windows (rejection, analysis, network input, phase) | | |
| Frequencies: stimulation frequencies per class and response multiple, or bands of interest | | |
| Contrast for condition-level connectivity (class a vs class b) | | |
| Development data (participants or parts) and participants reported separately | | |

## Sources

1.
