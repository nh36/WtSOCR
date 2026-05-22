# Sanskrit Recovery Policy

The postprocess workflow treats Sanskrit/Indic normalization as source recovery, not as editorial replacement of the printed dictionary. In Sanskrit contexts, the working assumption is that the dictionary generally intends correct Sanskrit/IAST, and apparent unmarked forms such as `Iśvara`, `Isvara`, `Mahesvara`, or `Avalokitesvara` may reflect OCR or diacritic-recovery failures.

Expected Sanskrit is therefore evidence for the printed target. Page-image evidence remains important, but OCR witnesses often lose macrons and diacritics, so absence of a mark in OCR text is not decisive by itself. Corrections must remain exact, context-gated, and auditable; broad character rules are not appropriate for this material.

Every recovered form must preserve the original OCR/source token in the changes TSV. The current īśvara pass is limited to exact standalone īśvara-family forms in Sanskrit/Indic contexts. Related compounds and names such as `Avalokitesvara`, `Mahesvara`, and `Maheśvara` are deliberately deferred to separate family-level audits.
