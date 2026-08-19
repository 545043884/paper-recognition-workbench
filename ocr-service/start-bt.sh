#!/usr/bin/env bash
set -e

export OCR_DEVICE=cpu
export OCR_CPU_THREADS=1
export OCR_LAYOUT_MODEL=PP-DocLayout-S
export OCR_FORMULA_MODEL=PP-FormulaNet-S
export OCR_TEXT_DET_MODEL=PP-OCRv5_mobile_det
export OCR_TEXT_REC_MODEL=PP-OCRv5_mobile_rec
export OCR_USE_DOC_UNWARPING=0
export FLAGS_use_mkldnn=0
export PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=0

exec python -m uvicorn app:app --host 127.0.0.1 --port 8000
