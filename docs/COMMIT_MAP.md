# Commit map

This public repository is a cleaned copy of the private development repository. Its history
was rewritten (2026-11-24) to remove the raw v0.2.0 end-to-end run archives and personal paths,
addresses and folder names, so every commit hash changed. BACKLOG.md, CHANGELOG.md and the docs
cite the original hashes; this table maps each one to its commit here. A commit marked `(dropped)`
became empty after the cleaning.

| Original | Here | Date and subject |
|---|---|---|
| `d82af01` | `13a6e48` | 2026-11-02 harness v0.1.0 |
| `c89b06b` | `c2b116b` | 2026-11-05 v0.2: rules G9-G16, plan audit, human-contact log, workflow and agent updates |
| `5868f53` | `48a3052` | 2026-11-05 v0.2: eegharness package - versioned outputs with provenance, compare_runs |
| `7b84a74` | `a59991b` | 2026-11-05 v0.2: guard tokenizes shell commands; read-only shell for the methods-auditor |
| `68041bf` | `865ab94` | 2026-11-05 v0.2: per-agent token and time log; vendored eegharness; skeleton commit |
| `feac787` | `a49d6bb` | 2026-11-05 v0.2: README, hooks README and CHANGELOG |
| `59161ef` | `ae2d4c8` | 2026-11-05 v0.2: guard tracks cd/pushd and the shell's cwd into data/raw, .harness, eeghar |
| `ba3a85e` | `30fcfda` | 2026-11-05 v0.2: guard resolves every path before checking it (L26) |
| `0ebbac4` | `692932b` | 2026-11-05 v0.2: CHANGELOG and hooks README for L26 |
| `76b5b77` | `657ac06` | 2026-11-05 v0.2: document reader for the paradigm-analyst; G16 self-contained |
| `0f03d24` | `068993c` | 2026-11-05 v0.2: control-arm cost from transcripts after the run (cost_report.py) |
| `3508c62` | `b134d19` | 2026-11-05 v0.2: fixes from the end-to-end run; release date |
| `011a8b4` | `c22fe11` | 2026-11-05 harness v0.2.0 |
| `6c3d48c` | `c8f2287` | 2026-11-05 docs: v0.2.0 end-to-end validation report and archive of the synthetic run |
| `0402ad0` | `10ff13c` | 2026-11-05 docs: redact personal identifiers from the v0.2.0 validation archive; frozen-ve |
| `47757e9` | `44c0ffb` | 2026-11-06 backlog: L27 for v0.3 (results-analyst derivations only through committed, test |
| `976b3b0` | `235a8b1` | 2026-11-06 docs: v0.3 spec with Sebastian's decisions and L28 |
| `fd42011` | `3c99696` | 2026-11-06 v0.3: eegharness splits, permutation, chance (core) and seeds, folds (torch opt |
| `8cf54f8` | `1d3c2bb` | 2026-11-06 v0.3: rules G17-G23 and G2 amendment, method checklists, compute limits |
| `885d4da` | `60ce04c` | 2026-11-06 v0.3: version 0.3.0, changelog, README, backlog |
| `8802e67` | `74646b0` | 2026-11-06 harness v0.3.0 |
| `aef7eaf` | `d5be6c2` | 2026-11-06 compute limits: 2 h per CPU/GPU job, longer work as resumable parts |
| `244712f` | `1e4e1c1` | 2026-11-06 v0.3.1: guard blocks blocked folders and searches that contain them |
| `87691aa` | `55ad9fb` | 2026-11-06 harness v0.3.1 |
| `e66298f` | `611078d` | 2026-11-07 docs: v0.4 spec with Sebastian's decisions |
| `15d8cb2` | `ec5d733` | 2026-11-07 v0.4: eegpipe filtering, gates, epochs, dataset, folds and synthetic recordings |
| `7398ebb` | `685ed46` | 2026-11-07 v0.4: eegpipe cca, classical suite, k-class evaluation and per-stratum permutat |
| `7b9c566` | `296ebef` | 2026-11-07 v0.4: eegpipe paired statistics (Wilcoxon exact/Pratt, sign test, HL bootstrap, |
| `e4ee958` | `2b3a73c` | 2026-11-07 v0.4: eegpipe networks (EEGNet, ShallowConvNet, trainer; k classes; shift and s |
| `c63cfc2` | `6bb8aa9` | 2026-11-07 v0.4: eegpipe phase features, condition-level connectivity (declared two-class  |
| `bd1e991` | `729b6e3` | 2026-11-07 v0.4: eegpipe edge-gated GNN (k classes), with moved tests |
| `d031174` | `2e020ac` | 2026-11-07 v0.4: eegpipe SSVEP option: continuous filter banks with IIR span gate, FBCCA ( |
| `4acaab2` | `fa7d61b` | 2026-11-07 v0.4: eegpipe settings validator and runner (part runner, label-free selection, |
| `2cbe800` | `002a61e` | 2026-11-07 v0.4: vendor eegpipe into projects, guard protects it (G24), rules G24-G25, /ap |
| `bb2a498` | `f6d432c` | 2026-11-07 v0.4: eegpipe SSVEP CCNN and generalised DualBranchFusionCNN (channels by name, |
| `df717c2` | `78de7b0` | 2026-11-07 v0.4: version 0.4.0 (untagged), changelog, README, requirements |
| `31b4dc4` | `b7a519e` | 2026-11-07 backlog: L29 headless orchestrator left a subagent running |
| `79a8748` | `e849852` | 2026-11-07 v0.4: fix five eegpipe gaps found by the ssvep-apply plan audit (FBCSP bank, FB |
| `ddf0316` | `62567fa` | 2026-11-07 v0.4: union feature step fbcsp+fbcca registers the SSVEP steps in spawned worke |
| `01d9573` | `b17b78d` | 2026-11-07 v0.4: network parts record torch version and build in results.json (gap 7), wit |
| `bed106f` | `add93b7` | 2026-11-09 v0.4: P300 Stage-2 lessons D-018 and DEV-2 in the method library: a file with 0 |
| `f11889a` | `fe34bf2` | 2026-11-09 v0.4: lessons L30 and L31 from the P300 Stage-2 run, and unit_label known-broke |
| `f6c238c` | `cf5dca7` | 2026-11-09 v0.4: P300 golden regression (step 0, D3) and the shuffle code-set fix it found |
| `3233ff4` | `66d7a9c` | 2026-11-10 v0.4.1: MAS's P20 network protocol in eegpipe (network_windows: MAS broadband I |
| `77ad345` | `c0f66ec` | 2026-11-10 CHANGELOG: 0.4.1 heading records the tag (v0.4.1 at 3233ff4) |
| `79a5267` | `851471d` | 2026-11-11 BACKLOG: lessons L32-L35 from cold-pressor onboarding (proposals for the next k |
| `0669b3d` | `491a8cd` | 2026-11-11 BACKLOG: revise L32-L35 (G10 and G16 amendments, L34 promotes cold-pressor's G2 |
| `1a17d80` | `c8b2bff` | 2026-11-13 v0.5-dev: lessons L37 (every measurement and reporting output records its compu |
| `26db915` | `4d0d4a3` | 2026-11-15 v0.5-dev: L38 attribution check (a configured name and an ISO date within 60 ch |
| `15d146a` | `0a324df` | 2026-11-15 v0.5-dev: L38 approved (Sebastian 2026-11-16): G15 extended in template/CLAUDE. |
| `03c00f6` | `ae9858f` | 2026-11-15 v0.5.0 release candidate (untagged): check_install.py (packages, tools, smoke s |
| `67defdb` | `d24f76a` | 2026-11-15 v0.5.0: approved rule wordings (Sebastian 2026-11-16, all seven as worded): G22 |
| `1bbf1ff` | `526dd8c` | 2026-11-15 CHANGELOG: 0.5.0 heading records the tag (v0.5.0 at 67defdb) |
| `6bedebf` | `d26e05c` | 2026-11-15 run_cost.py: cost of a finished run (agent USD from cumulative total_cost_usd p |
| `939ebeb` | `02225c2` | 2026-11-17 run_cost.py: job tables (tab-separated, header job/start_utc, as the cold-press |
| `cc6a257` | `93ba9af` | 2026-11-17 BACKLOG: L39 (working thread count for long runs and a temperature log; cold-pr |
| `bfa0b6a` | `c6a2033` | 2026-11-17 BACKLOG: L41 (new_project.py without --case creates neither data/ nor inputs/), |
| `f89b429` | `5d5b8a0` | 2026-11-17 BACKLOG: L45 (wording-only audit failures get one bounded fix round outside the |
| `ed49d0d` | `b8af97d` | 2026-11-17 BACKLOG: L45 adds the orchestrator summing running totals when it reports cost  |
| `8065a05` | `b58864b` | 2026-11-19 BACKLOG: L48 (the template approval line 'Approved by Sebastian: [x]   Date:' f |
| `b361f81` | `520ddd6` | 2026-11-19 BACKLOG: L48 wording (where the check was reproduced; assignment SKILL.md lines |
| `a08b149` | `fb97da4` | 2026-11-23 BACKLOG: L49-L55 from the imagined-speech-eeg hi-word-decoding run (attempts ki |
| `61005fc` | `4d9b61e` | 2026-11-23 run_cost.py: waits between jobs per phase (gaps of at least --min-wait-h hours, |
| `f29b0f2` | `246cf55` | 2026-11-23 L41: new_project.py creates data/ and inputs/ in every project (harness and con |
| `9d25e2a` | `c402e9d` | 2026-11-23 L43 (reduced form; --venv waits): the per-project .venv is the documented inter |
| `9968244` | `edd9618` | 2026-11-23 L48: sources check accepts the template's approval box ticked and dated (Approv |
| `2d8098f` | `02f9aee` | 2026-11-23 L40: kit rule G27 (a group statistic takes only estimates that exist at that sa |
| `a18b6d6` | `3a47bb8` | 2026-11-23 L50: the methods-auditor's hook allows python -m eegharness.outputs check and p |
| `07055d1` | `146090c` | 2026-11-23 L45+L47: audit rounds in /onboard, /assignment and /apply-pipeline (fixes label |
| `8a23e6e` | `1de04b2` | 2026-11-23 L42+L46: tools/check_inputs.py (shipped in .harness/tools) reports template pla |
| `1ab7e2c` | `2a44111` | 2026-11-23 L55 (option a): template tests/conftest.py registers a slow marker and leaves s |
| `01cd8f6` | `7fb220e` | 2026-11-23 L39: docs/COMPUTE.md gets cpu_working_threads (no default, set by Sebastian; ne |
| `e7c1c23` | `394b667` | 2026-11-23 L54+L44: docs/COMPUTE.md gets memory_max_gb (no default; new_project.py says Se |
| `e1da0d5` | `d3148bd` | 2026-11-23 L49: eegpipe.runner.stage records every attempt before its job starts (status r |
| `58369fe` | `eb4d1ac` | 2026-11-23 L52: python -m eegharness.outputs check --paths-file <file> (one folder per lin |
| `e5b7b0d` | `1ab55e3` | 2026-11-23 L53+L51: eegharness.numbers reads tab-separated files (.tsv, or "delimiter"), e |
| `ab0d3c2` | `d643c5c` | 2026-11-23 0.6.0: VERSION, eegharness and eegpipe __version__, CHANGELOG (L39-L55 as appro |
| `7ad1c35` | `4f14faa` | 2026-11-23 CHANGELOG 0.6.0: run_cost.py waits between jobs (61005fc, evaluator tool, not a |
| `25e942c` | `98fd537` | 2026-11-23 L56 (approved 2026-11-23): every quantity a plan's gate or decision rule uses i |
| `446b65c` | `ae706c1` | 2026-11-23 CHANGELOG 0.6.0: checks paragraph from the clean run on the final code 25e942c  |
| `06aa9dc` | `c87b1b2` | 2026-11-24 CHANGELOG: 0.6.0 heading records the tag (v0.6.0 at 446b65c) |
| `bae1bc3` | `0975099` | 2026-11-24 BACKLOG: L39-L55 approved and done in 0.6.0 (Sebastian 2026-11-23, with the app |
| `06c9801` | `f8ed3bf` | 2026-11-24 Public wording: the human who approves, answers and runs jobs is 'the superviso |
| `e73ec49` | `277768a` | 2026-11-24 results-analyst: the requester's summary is written in English (was Spanish) |
| `202b9c0` | `7be9ab6` | 2026-11-24 docs/validation/v0.2.0_e2e: raw run archives (project, transcripts, headless st |
| `dab8e16` | (dropped) | 2026-11-24 BACKLOG L44 and its storage test: the mount path and drive label are generic (/ |
