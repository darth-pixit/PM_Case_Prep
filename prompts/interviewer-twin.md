Build a prediction of how THIS interviewer will run the interview, using ONLY
the public signals pasted below — things the candidate can see themselves:
public profile text, talk titles, posts, a bio. Do not speculate about
private facts. If the signals are thin, say so in the rationale instead of
inventing depth.

Return one InterviewerTwin JSON object:
- profile: name, role, publicSignals (each traceable to the pasted text),
  likelyFocus (competencies from <TAXONOMY>).
- predictedQuestions: 5-8 questions THIS person would plausibly ask for THIS
  role, each tagged with the competency it probes.
- prepTips: how to tune existing stories for this audience — emphasis, depth,
  vocabulary. Tuning, never fabrication.
- rationale: two sentences on how strong the signal base is and what drove
  the prediction.

Return JSON only.

INTERVIEWER: <NAME_AND_ROLE>
PUBLIC SIGNALS:
<SIGNALS>
TARGET: <TARGET_JSON>
