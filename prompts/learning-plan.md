Design the candidate's learning plan for this target role: what to study,
in what order, with what practice — driven by the JD's own demands and the
coverage heatmap's ambers and reds. This is "become qualified", not
"sound qualified": every item must build real skill the interview will
then find.

ROLE FAMILY: <ROLE_CONTEXT>

For each competency worth studying (all ambers and reds; a green only when
the JD weights it 4-5 and polish would pay), return a LearningItem:
- priority 1-5: from the JD weight and how red the cell is.
- why: tie it to the JD's own phrases and the heatmap — one sentence.
- topics: the 3-6 concrete subtopics to actually study for THIS role (not
  "learn statistics" but the specific ideas an interviewer will probe).
- resources: pick 1-3 from the RESOURCES list below, chosen for fit with
  the topics. HARD RULE: recommend ONLY resources from that list, matched
  by their exact "url" — never invent, adapt, or recall a link from
  memory. If nothing in the list fits, return an empty resources array.
- practice: one concrete exercise with the candidate's own context (their
  units show what they already know) that produces an artifact or a number
  — the do-something that proves the studying stuck.

Also return "sequence": one short paragraph on what to do first and why —
respect dependencies (statistics before experiment design, SQL before
analytics cases) and the interview's likely order of fire.

Return one LearningPlan JSON object only.

TARGET: <TARGET_JSON>
HEATMAP: <CELLS_JSON>
WHAT THEY ALREADY HAVE: <UNITS_SUMMARY_JSON>
RESOURCES (the only allowed links): <RESOURCES_JSON>
