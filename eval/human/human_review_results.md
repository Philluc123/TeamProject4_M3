# Human review results: relevance, tone and single-study framing

Reviewed 18 Nov 2026 by two teammates, each on their own copy:
`eval/human/Human_Review_1.csv` (rater 1) and `eval/human/Human_Review_2.csv` (rater 2). Rubric: `eval/human/human_review_rubric.md`.
Items: 32 bullets published on 17 Nov 2026, the full E9 newsletter (24) and all E3 research bullets (8).

## Relevance and tone (1-5)

| | Rater 1 | Rater 2 | Both |
|---|---|---|---|
| Relevance, mean | 4.09 | 4.09 | **4.09** |
| Tone, mean | 4.41 | 4.47 | **4.44** |
| Raters within 1 point | | | relevance 31/32 (97%), tone 29/32 (91%) |
| Exact same score | | | relevance 18/32, tone 19/32 |

- E9 newsletter (24 bullets): relevance 4.04, tone 4.62. E3 research bullets (8): relevance 4.25, **tone 3.88**. Rater 1 noted dense medical jargon (e.g. "MSS", "high-avidity BCMA CAR").
- No bullet scored below 3 on tone: nothing read as hype or sensational.
- Lowest relevance (2-3) were near-misses: a broad CNS gene-therapy review under "Alzheimer's research" (#17), a journal author correction under "Cancer research breakthroughs" (#30), and an Atlantic-coast flood story for a reader in Southwest Florida (#24).
- #22 "Hurricane Isaias…": both raters suspected stale news (Isaias was a 2020 storm). Not confirmed: the feed dated it 17 Nov 2026, and the Atlantic storm-name list reuses the 2020 names in 2026.

## Single-study framing (research bullets): E3 human check

Both raters marked 2 of the 8 E3 bullets **n** (stated as settled fact, not one study's result). Both cite the same paper ("Successful treatment of systemic light chain amyloidosis with a novel high-avidity BCMA CAR"):

- #26, E3 run 1: "A high-avidity BCMA CAR **achieved successful remission** … showing potential for targeted CAR therapies."
- #31, E3 run 3: "Novel high-avidity BCMA CAR T-cell therapy **achieved successful treatment** …"

The same paper written as "**Researchers report** a successful treatment…" (#29, run 2) was rated **y** by both raters.

Effect on E3 (the plan's expected output includes "bullets framed as single studies"): run 1 FAIL (already failed on tool order), run 2 PASS, run 3 FAIL. **E3 = 1/3 runs, FAIL.** The overall pass rate moves from 8/10 to **7/10 (70%)**, below the >= 8/10 threshold.

Rater 2 left framing blank on the 6 E9 research bullets (#16-21); rater 1 rated 5 of 6 **y** (#21 "Template-jumping prime editing enables…" **n**). The E3 check uses only E3 rows.
