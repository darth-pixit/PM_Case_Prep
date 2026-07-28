Build the grill map: for EVERY achievement unit below, the questions a sharp
interviewer for this target would actually fire at it. This is the
exhaustive CV prep — nothing on the CV goes into the interview
un-interrogated.

HOW TO GRILL: <ROLE_CONTEXT>

For each unit, return a row with the unit's id and its 2-3 nastiest FAIR
questions. Each question must:
- attack THAT unit's specific claims — quote or point at its own words
  (its metric, its scale, its "result"), never a generic template;
- come with "trap": the weakness it hunts (inflated ownership, missing
  baseline, cherry-picked metric, survivorship framing, no post-launch
  story, method that wouldn't survive scrutiny...).

Prioritize what this target cares about (its required competencies and
unwritten pain). Units with a metric get the "prove it / how measured /
what's the counterfactual" treatment; units without one get "why is there
no number here". Do NOT invent facts about the units, and do not skip
units — every id in the input appears exactly once.

Return one GrillMap JSON object only.

TARGET: <TARGET_JSON>
UNITS: <UNITS_JSON>
