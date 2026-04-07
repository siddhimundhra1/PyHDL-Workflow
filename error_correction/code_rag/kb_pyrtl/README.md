# kb_pyrtl

This folder contains 50 curated PyRTL-ready RAG entries converted from the original `knowledge_base` corpus.

Selection criteria:
- high signal-to-noise examples instead of metadata, logs, or malformed entries
- broad coverage across combinational logic, arithmetic, memories, counters, shift registers, edge detectors, and FSMs
- designs that are practical to express cleanly in PyRTL using `WireVector`, `Register`, `MemBlock`, and `RomBlock`

Notes:
- file names intentionally match the selected source entries so retrieval stays traceable
- disabled RAM/ROM outputs are driven to zero in the PyRTL versions instead of high impedance
- some sources with external helper modules were refined to compact self-contained PyRTL behavior
- `error_correction/code_rag/index.py` still points at `knowledge_base`; update the watched directory if you want to index `kb_pyrtl`
