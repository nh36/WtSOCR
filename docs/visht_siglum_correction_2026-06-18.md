# ViśT Siglum Correction

## Decision

Source-list review resolves the siglum as `ViśT`, for `Viśeṣastavatīkā`.

This is a citation-siglum normalization only. It is not a broad `$ -> ś`,
`s -> ś`, or Sanskrit-title correction rule.

## Evidence

- The source list distinguishes `Viś` for `Viśeṣastava`.
- The same sigla list gives `ViśT` for Prajñāvarman's
  `Viśeṣastavatīkā`.
- The capital `T` is therefore retained as the siglum marker for `tīkā`.
- `VisṬ` is rejected: the dot belongs neither to the source siglum nor to the
  title abbreviation pattern.

## Implemented Normalization

The sigla registry now uses canonical `ViśT` with OCR/plain variants:

- `Vi$T`
- `Vi$ST`
- `Vis$T`
- `VisT`
- `ViST`
- `VisST`
- `VIST`
- `VIiST`

These variants normalize to `ViśT` only through citation-siglum logic.

## Verification

Run:

```bash
python3 -m py_compile scripts/postprocess_entry_map.py
python3 -m pytest tests/test_postprocess_regressions.py -q
```
