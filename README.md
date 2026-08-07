# WtSOCR

WtSOCR produces a reviewed, reproducible OCR edition of the four-volume *Wörterbuch der tibetischen Schriftsprache*. Development policy is conservative: the base OCR is authoritative, Google Vision is only an alternate witness, and linguistic corrections are normally exact reviewed decisions rather than broad character substitutions.

Start here:

- [Current operational status](docs/STATUS.md)
- [Repository structure and sources of truth](docs/PROJECT_STRUCTURE.md)
- [Current deployable release](release/current)
- [Current release manifest](release/current/manifest.md)
- [Release input locks](release/inputs)
- [Correction-family ledger](data/correction_families.tsv)
- [Release reproduction procedure](docs/current_release_workflow.md)

The continuing integration base is `main`. Dated reports in `docs/` are historical audit records unless `docs/STATUS.md` explicitly identifies them as current.
