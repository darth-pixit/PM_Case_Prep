Extract "achievement units" from the résumé / brain-dump below. A unit is ONE
atomic accomplishment. For each, return an object matching the AchievementUnit
schema.

HARD RULES:
- Use ONLY information present in the input. Do NOT invent metrics, employers,
  scale, or outcomes. If a bullet has no number, set "metric": null.
- "competencies" must come from this list: <TAXONOMY>.
- Set "isFailure": true for conflicts, failed launches, or wrong calls.
- "rawEvidence" must quote the source line this came from.

Return a JSON array of AchievementUnit only. No prose.

INPUT:
<CV_OR_BRAINDUMP>
