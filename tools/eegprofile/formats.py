"""File-format lists shared by the profiler and the document reader (no dependencies)."""

# Recording formats read through MNE-Python (mne.io.read_raw dispatches on the extension).
MNE_EXTENSIONS = (".edf", ".bdf", ".gdf", ".vhdr", ".fif", ".set", ".cnt", ".mff", ".nxe")

# Written documents (lab logs, READMEs, protocol sheets, spreadsheets): listed for the agents to
# read (CLAUDE.md G16), never counted as recordings without a reader. A reader plugin wins.
DOCUMENT_EXTS = {".txt", ".md", ".rst", ".pdf", ".doc", ".docx", ".odt", ".rtf", ".html", ".htm",
                 ".csv", ".tsv", ".json", ".xls", ".xlsx", ".ods", ".log", ".ini", ".yaml", ".yml"}
