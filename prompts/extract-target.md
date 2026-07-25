Read the job description below and infer what the role is TRULY testing.
Read between the lines: name the unwritten pain the role exists to solve.

ROLE FAMILY: <ROLE_CONTEXT>

Return one TargetProfile JSON object:
- requiredCompetencies: choose from <TAXONOMY>, each with weight 1-5 and the
  phrase in the JD that justifies it.
- seniority: one of <SENIORITY_LADDER> — infer from scope, not title inflation.
- archetype: the closest fit in spirit to <ARCHETYPES>, in the JD's own words.
- unwrittenPain: one sentence on the real problem behind the hire.
- companyValues: if stated or well-known; else [].

Return JSON only.

JD:
<JOB_DESCRIPTION>
