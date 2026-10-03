# ATC Main Table - Complete v3 Test

## Referenced baselines

| Method | ASR Exact (%) | ASR WER | Entity F1 (%) | v6 Exact (%) | v6 WER | R1 Exact (%) | R1 WER |
|---|---:|---:|---:|---:|---:|---:|---:|
| XLS-R-300M (ATCOSIM) | 0.00 | 0.9862 | 5.64 | 0.00 | 1.0886 | 0.00 | 1.0879 |
| XLS-R-300M (UWB-ATCC + ATCOSIM) | 0.25 | 0.8924 | 22.67 | 0.25 | 1.0224 | 0.25 | 1.0190 |
| Whisper large-v3 | 22.64 | 0.6767 | 38.97 | 24.23 | 0.6529 | 25.21 | 0.6404 |
| Whisper large-v3-turbo | 21.53 | 0.6912 | 36.92 | 22.82 | 0.6810 | 23.78 | 0.6660 |
| Whisper large-v3 fine-tuned for ATC | 14.93 | 0.6183 | 49.18 | 14.66 | 0.7269 | 15.47 | 0.6976 |
## Matched v3 methods

| Method | ASR Exact (%) | ASR WER | Entity F1 (%) | v6 Exact (%) | v6 WER | R1 Exact (%) | R1 WER |
|---|---:|---:|---:|---:|---:|---:|---:|
| Whisper ATCO2 domain base | 22.44 | 0.5679 | 52.43 | 22.69 | 0.6668 | 24.23 | 0.6328 |
| Domain base + matched LoRA control | 33.96 | 0.5593 | 67.11 | 29.66 | 0.6938 | 33.36 | 0.6192 |
| Domain base + entity-token weighting | 34.28 | 0.5418 | 67.88 | 29.77 | 0.6755 | 33.63 | 0.5971 |
| Domain base + entity auxiliary LoRA + R1 (ours) | 33.56 | 0.5255 | 67.76 | 28.91 | 0.6618 | 32.85 | 0.5857 |

## Subset Counts

| Subset | Rows |
|---|---:|
| 02/01 | 1368 |
| 02/02 | 99 |
| 03 | 2420 |
| 04 | 600 |
