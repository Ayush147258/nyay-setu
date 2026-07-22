# NyaySetu Extraction Golden Corpus

This directory contains 40 synthetic legal-document fixtures with controlled
ground truth. No real complainant, litigant, FIR, judgment, or personal data is
included.

Coverage:

| Category | Count |
| --- | ---: |
| Scanned FIR-style PDFs | 8 |
| Digital judgments | 8 |
| Legal forms | 5 |
| Structured PDF tables | 5 |
| Mixed Hindi/English PDFs | 6 |
| DOCX memoranda | 3 |
| XLSX case registers | 3 |
| Standalone scanned images | 2 |

Regenerate the corpus:

```powershell
python tests/golden_corpus/build_corpus.py
```

Measure extraction:

```powershell
python tests/golden_corpus/evaluate_corpus.py --output golden-metrics.json
python tests/golden_corpus/evaluate_corpus.py --strict
```

The strict gate measures parse success, expected-fragment recall, structured
table recall, and page-diagnostic coverage. OCR scores depend on the installed
Tesseract language packs. Production workers should install both `eng` and
`hin`.
