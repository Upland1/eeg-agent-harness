"""Synthetic auditory oddball recordings for the harness end-to-end test (no real data).

3 participants x 1 session, 8 EEG channels + STI 014, 256 Hz, 90 s. Code 9 at the start,
then a tone every 0.9-1.1 s: code 1 (standard, ~80 %) or code 2 (target, ~20 %, never two in a
row). Targets carry a positive deflection peaking ~350 ms (Pz > Cz > Fz), 6 uV at Pz.
Noise: pink-ish background + 10 Hz alpha. Also writes a lab-log .docx that is the only
written source of the code meanings, and the professor's notes.
"""

import sys
import zipfile
from pathlib import Path

import mne
import numpy as np

proj = Path(sys.argv[1])
raw_dir = proj / "data" / "raw"
fs, dur = 256.0, 90.0
chs = ["Fz", "Cz", "Pz", "Oz", "C3", "C4", "P3", "P4"]
gain = {"Fz": 0.4, "Cz": 0.7, "Pz": 1.0, "Oz": 0.3, "C3": 0.5, "C4": 0.5, "P3": 0.8, "P4": 0.8}
for sub in (1, 2, 3):
  rng = np.random.default_rng(100 + sub)
  n = int(fs * dur)
  t = np.arange(n) / fs
  white = rng.standard_normal((len(chs), n))
  spec = np.fft.rfft(white, axis=1) / np.maximum(np.fft.rfftfreq(n, 1 / fs), 1.0) ** 0.5
  x = np.fft.irfft(spec, n=n, axis=1)
  x = x / x.std(axis=1, keepdims=True) * 8e-6 + 4e-6 * np.sin(2 * np.pi * 10 * t + rng.uniform(0, 6.28))
  stim = np.zeros(n)
  stim[int(0.5 * fs)] = 9
  onset, prev = 2.0, 1
  while onset < dur - 1.5:
    code = 2 if (prev != 2 and rng.random() < 0.2) else 1
    i = int(onset * fs)
    stim[i] = code
    if code == 2:
      tt = np.arange(int(0.8 * fs)) / fs
      p3 = 6e-6 * np.exp(-((tt - 0.35) ** 2) / (2 * 0.06 ** 2))
      for k, ch in enumerate(chs):
        x[k, i:i + len(tt)] += gain[ch] * p3
    prev = code
    onset += rng.uniform(0.9, 1.1)
  info = mne.create_info(chs + ["STI 014"], fs, ["eeg"] * len(chs) + ["stim"])
  raw = mne.io.RawArray(np.vstack([x, stim]), info, verbose="error")
  out = raw_dir / f"sub-{sub:02d}" / "ses-01"
  out.mkdir(parents=True, exist_ok=True)
  raw.save(out / f"sub-{sub:02d}_ses-01_oddball_raw.fif", overwrite=False, verbose="error")

w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
paras = ["Bitácora de registro - experimento auditivo, laboratorio de señales",
         "Tres voluntarios, una sesión cada uno, 90 s por registro, 256 Hz, 8 electrodos (Fz Cz Pz Oz C3 C4 P3 P4), referencia a mastoides enlazadas.",
         "Códigos de evento en el canal STI 014: 9 = inicio del registro; 1 = tono estándar (1000 Hz); 2 = tono objetivo (2000 Hz).",
         "Instrucción a los participantes: contar en silencio los tonos objetivo. Intervalo entre tonos 0.9 a 1.1 s.",
         "sub-03: el electrodo Oz se despegó al minuto 1 y se volvió a colocar."]
body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paras)
with zipfile.ZipFile(raw_dir / "bitacora.docx", "w") as z:
  z.writestr("[Content_Types].xml", "<Types/>")
  z.writestr("word/document.xml", f'<w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>')

(proj / "inputs").mkdir(exist_ok=True)
(proj / "inputs" / "professor_notes.md").write_text(
  "# Notas del profesor\n\nTenemos registros EEG de un experimento auditivo con tres voluntarios. "
  "Antes de cualquier análisis, describan el conjunto de datos y el paradigma: qué eventos hay, "
  "qué se podría clasificar y cómo evaluarlo sin fugas de información. Los detalles del registro "
  "están en la carpeta de datos.\n")
print("ok")
