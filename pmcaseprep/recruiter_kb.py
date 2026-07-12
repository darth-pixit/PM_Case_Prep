"""Knowledge base for the recruiter experiment (/recruiter).

Everything the copilot knows about TODAY's AI / GenAI / Data-Science interview
landscape lives here, researched from real 2024-2026 sources (interview guides,
company engineering blogs, practitioner writeups) and summarized in ORIGINAL
wording. Structure:

  * GUIDE["roles"]       — the role families the tool covers right now.
  * GUIDE["archetypes"]  — question archetypes actually asked, with example
    questions (paraphrased, never copied), and what good/bad answers look like.
  * GUIDE["concepts"]    — the concepts a non-technical recruiter must grasp,
    each explained assuming zero background.
  * GUIDE["evaluation"]  — how to probe and judge answers you can't verify
    yourself (technique, probe questions, good/bad signals).
  * GUIDE["resources"]   — curated gold-standard learning links.

The static field guide serves this JSON straight to the browser; the chat
endpoint folds it into the system prompt so every conversation is grounded in
the same researched picture, not model vibes.
"""

from __future__ import annotations

import json

# NOTE: populated from the research pass; keep wording original and sources real.
GUIDE: dict = {
    "roles": [
        {
            "key": "data-science",
            "name": "Data Scientist",
            "blurb": (
                "Uses a company's data to answer business questions: why a "
                "number moved, whether a change actually worked, and what to "
                "do next. Part analyst, part statistician, part translator "
                "between the data and the decision-makers."
            ),
        },
        {
            "key": "genai",
            "name": "GenAI / LLM Engineer & AI Engineer",
            "blurb": (
                "Builds product features on top of AI language models (the "
                "technology behind ChatGPT and Claude) — chatbots, assistants, "
                "document Q&A, AI agents. The craft is less about building the "
                "AI itself and more about making it accurate, safe, fast, and "
                "affordable inside a real product."
            ),
        },
    ],
    "archetypes": [
        {
            "name": "SQL & Coding Screen",
            "roles": ["data-science"],
            "description": (
                "A live session (often the first technical gate) where the "
                "candidate writes SQL queries and/or short Python code against "
                "realistic product data — users, orders, click events. It shows "
                "up in the vast majority of data-science loops because someone "
                "who can't pull and shape data can't do anything downstream, "
                "and it's hard to fake live in 30-45 minutes."
            ),
            "example_questions": [
                "From a table of daily logins, work out what share of users who were active one week came back the following week.",
                "In this payments table, find charges that look like accidental duplicates — same card, same shop, same amount, minutes apart.",
                "Build a signup funnel from this data: of the people who landed on our page, what fraction created an account, and what fraction of those bought something within a week?",
                "Here's a messy spreadsheet-style dataset with gaps. Clean it up and give me average order value per month.",
                "Combine these two datasets on customer ID and tell me the top product categories by revenue in each region.",
            ],
            "good": (
                "They ask what the data looks like before writing anything "
                "(what counts as 'active'? can someone appear twice?), narrate "
                "a plan out loud, and sanity-check their own result ('this "
                "percentage should never top 100'). Comfort with edge cases — "
                "missing values, duplicates, ties — matters more than typing "
                "speed."
            ),
            "bad": (
                "Dives straight into typing with no questions, produces "
                "something that runs but quietly answers a different question, "
                "or can't adapt when one requirement changes. Silently ignoring "
                "gaps and duplicates in the data is the classic weak-answer "
                "tell."
            ),
            "seniority": (
                "Juniors handle clean, well-specified asks; mid-level handles "
                "messy data and multi-step logic like retention and funnels. "
                "Seniors are additionally expected to question whether the "
                "metric itself is the right one and to reason about huge data "
                "volumes."
            ),
        },
        {
            "name": "Statistics & Probability Round",
            "roles": ["data-science"],
            "description": (
                "Spoken (not coded) questions testing statistical intuition: "
                "chance puzzles, judging whether a result is real or luck, and "
                "explaining stats ideas in plain words. The 2024-26 shift is "
                "away from formula recall toward reasoning — several big firms "
                "explicitly ask candidates to explain concepts as they would "
                "to a non-technical colleague."
            ),
            "example_questions": [
                "We flip a coin a thousand times and get 550 heads. How would you decide whether the coin is rigged?",
                "One of two coins in my pocket is a trick coin with tails on both sides. I grab one at random, flip it five times, get five tails. How likely is it I'm holding the trick one?",
                "Explain what a p-value means to me as if I've never taken a stats class.",
                "Give me a situation where a result passes the statistical bar but you'd still tell the business not to act on it.",
                "Roughly how many times would you expect to roll a die before you've seen every face at least once — and how would you reason it out?",
            ],
            "good": (
                "They structure the problem out loud before computing — what's "
                "being assumed, what would count as evidence — and can then "
                "restate the whole thing in everyday language. Strong answers "
                "connect the math to a decision: 'real but tiny effect, "
                "probably not worth shipping.'"
            ),
            "bad": (
                "Recites a memorized definition that's subtly wrong (saying a "
                "p-value is 'the probability the hypothesis is true' is the "
                "canonical error), guesses at puzzles without setting them up, "
                "or freezes when asked to drop the formulas and explain "
                "intuitively."
            ),
            "seniority": (
                "Juniors: definitions and one-step puzzles, coaching allowed. "
                "Mid: multi-step reasoning and clean lay explanations. Seniors "
                "get less puzzle and more judgment — when standard tests "
                "mislead, and how to establish cause-and-effect when a clean "
                "experiment isn't possible."
            ),
        },
        {
            "name": "Machine Learning Fundamentals",
            "roles": ["data-science"],
            "description": (
                "Conceptual questioning about how predictive models work, "
                "fail, and get graded — often wrapped in a scenario like "
                "'build something that predicts which customers will cancel.' "
                "Companies run it because models that look great in the lab "
                "and flop with real customers are the most common way data "
                "projects quietly waste money."
            ),
            "example_questions": [
                "Your model aces the data it studied but does badly on fresh data. What's going on and what do you do?",
                "Walk me through building a system to predict which subscribers cancel next month — from raw data to something the business can use.",
                "For catching fraud, is it worse to miss real fraud or to flag innocent customers? How does that change how you build and grade the model?",
                "Only one purchase in a hundred is fraudulent. Why is 'the model is 99% accurate' a meaningless brag here?",
                "When would you tell a team NOT to use machine learning and just write simple rules instead?",
            ],
            "good": (
                "Intuition first, math second, and every technical choice tied "
                "to a business cost ('a missed fraud case costs us real money; "
                "a false alarm costs a support ticket'). They volunteer failure "
                "modes — what happens after launch, how they'd notice the "
                "model going stale — without being prompted."
            ),
            "bad": (
                "Textbook definitions with no ability to apply them, reaching "
                "for the fanciest technique for everything, grading a "
                "rare-event problem with plain accuracy, or resume projects "
                "that fall apart after one follow-up question."
            ),
            "seniority": (
                "Juniors define and distinguish core ideas (overfitting, "
                "precision vs recall) and can walk a simple pipeline with "
                "hints. Mid runs a full scenario unaided. Seniors are graded "
                "on restraint and production judgment — 'do we even need a "
                "model here?', running costs, monitoring — and lately on "
                "knowing when an AI language model is the wrong tool."
            ),
        },
        {
            "name": "A/B Testing & Experiment Design",
            "roles": ["data-science"],
            "description": (
                "The candidate designs and interprets a controlled product "
                "experiment: split users randomly, change one thing, measure "
                "the difference. Consumer-tech companies weight this round "
                "heavily because bad experiment habits ship harmful changes "
                "with a scientific-looking stamp of approval."
            ),
            "example_questions": [
                "We redesigned checkout. Design the test end to end: what you'd measure, who sees what, how many users, how long.",
                "The test has run three days, the new version looks 15% better, and the product manager wants to launch today. What do you say?",
                "Our main number went up 2% but complaints went up 5%. Ship or not — and how do you weigh it?",
                "How would you test a change on a social app where the people who got it interact with the people who didn't?",
                "What goes wrong if the team checks results every day and stops the moment things look good?",
            ],
            "good": (
                "A clear structure: a testable hypothesis, one main success "
                "measure plus tripwire measures for harm, a pre-computed "
                "sample size and duration covering full weeks. They raise the "
                "traps themselves — early excitement that fades, peeking at "
                "results, users influencing each other — and end with a "
                "business recommendation, not just a stats verdict."
            ),
            "bad": (
                "Treats 'statistically significant' as an automatic green "
                "light, never mentions how many users or how long, can't name "
                "a single tripwire metric, or trusts a dramatic three-day "
                "result at face value."
            ),
            "seniority": (
                "Juniors explain the mechanics and read a clean result. Mid "
                "designs a full test unaided and spots the standard traps. "
                "Seniors handle the cases where A/B testing breaks down — "
                "marketplaces, social networks, slow-moving outcomes — and "
                "can describe the alternatives."
            ),
        },
        {
            "name": "Product Sense & Metrics Case",
            "roles": ["data-science", "genai"],
            "description": (
                "An open-ended case about the product: diagnose why a number "
                "dropped, define success measures for a launch, or design (and "
                "sometimes argue against) an AI-powered feature. It tests "
                "whether the candidate thinks like a business owner with data "
                "skills rather than a calculator — and, for AI roles, whether "
                "they can say when AI is the wrong answer."
            ),
            "example_questions": [
                "Sharing activity on our app fell 12% in a month. Talk me through your investigation, step by step.",
                "Active users are up but total time spent is down. How do you reconcile those two facts?",
                "We're adding a 'save for later' button. What one number tells us it's working, and what numbers would warn us it's backfiring?",
                "Sketch an AI assistant feature for our product: the user problem, why AI helps here (or doesn't), and the risks.",
                "A stakeholder wants an AI language model to forecast next quarter's sales. Is that the right tool? What would you use instead?",
            ],
            "good": (
                "Structured triage narrated out loud: first rule out broken "
                "tracking and outside events, then break the number into its "
                "parts and slice by user group to localize the problem, then "
                "name the exact analysis that would confirm each theory. For "
                "AI-feature questions, they start from the user problem, "
                "consider cheaper non-AI options, and design for the times "
                "the AI will be wrong."
            ),
            "bad": (
                "Scattershot guessing with no order ('maybe a competitor? "
                "maybe it's slow?'), never checking whether the number itself "
                "is measured correctly, proposing feel-good metrics untied to "
                "the business, or pitching 'add AI' as inherently valuable "
                "with no fallback plan for failures."
            ),
            "seniority": (
                "Mid-level should run the full diagnosis loop independently "
                "and land on a recommendation. Seniors are expected to "
                "challenge the question itself ('is that even the right "
                "health measure?'), weigh knock-on effects, and show evidence "
                "of having killed a bad AI idea, not just shipped good ones."
            ),
        },
        {
            "name": "LLM Fundamentals",
            "roles": ["genai"],
            "description": (
                "A warm-up filter round checking the candidate understands how "
                "AI language models actually work, not just how to call one "
                "from an app. It separates people who can debug and optimize "
                "model behavior from people who have only ever used the tools "
                "as a black box."
            ),
            "example_questions": [
                "What's a token, and why does the same request cost different amounts on different models?",
                "Explain a context window and what actually happens when a long conversation outgrows it.",
                "Why does letting the model read more text at once cost more money and time?",
                "The same question gives slightly different answers each time. Why, and when is that a problem for a product?",
                "In plain terms, what happens between me hitting enter and the model's answer appearing?",
            ],
            "good": (
                "Explains the mechanics correctly AND ties each one to a "
                "practical consequence — 'these models bill by the token, so "
                "shorter instructions directly cut the bill' or 'stuff too "
                "much into the model's memory and it starts missing things in "
                "the middle.' They can go one level deeper on any point when "
                "pushed."
            ),
            "bad": (
                "Dictionary definitions with no consequences, using 'words' "
                "and 'tokens' interchangeably, assuming a bigger model or "
                "bigger memory is always free and better, or name-dropping "
                "architecture terms without being able to sketch what happens "
                "to a request."
            ),
            "seniority": (
                "Juniors: solid conceptual definitions and why outputs vary. "
                "Mid: the cost and speed mechanics behind those concepts. "
                "Seniors are rarely quizzed on definitions — they're expected "
                "to reason from fundamentals to system decisions, like "
                "diagnosing why responses got slow or expensive."
            ),
        },
        {
            "name": "RAG & Retrieval System Design",
            "roles": ["genai"],
            "description": (
                "The most common GenAI design prompt today: 'build an "
                "assistant that answers questions using our internal "
                "documents.' RAG — having the AI look up relevant company "
                "material before answering — is the standard way enterprises "
                "make a general AI accurate about their own data, so "
                "interviewers probe the whole pipeline and, crucially, how "
                "you'd know it's working."
            ),
            "example_questions": [
                "Design a Q&A helper over our internal wiki. Walk me through how documents get in and how an answer comes out.",
                "Users say it gives wrong answers. How do you tell whether the lookup step failed or the writing step failed — and what's the fix for each?",
                "How do you keep answers current when the documents change every week?",
                "How do you make sure the assistant never shows an employee content from documents they aren't allowed to see?",
                "Why show the sources behind each answer, and what does that cost you?",
            ],
            "good": (
                "Treats it as a system with parts that fail independently, "
                "asks about the documents and users before designing, "
                "justifies choices with trade-offs, and — the real "
                "differentiator — talks unprompted about measuring quality "
                "and diagnosing failures. War stories ('our lookups kept "
                "missing rare product names until we...') beat vocabulary."
            ),
            "bad": (
                "Recites a tutorial recipe with brand-name tools and no "
                "trade-offs, can't say how they'd know the system works, "
                "jumps to exotic variations before nailing basics, and never "
                "mentions permissions, freshness, or evaluation."
            ),
            "seniority": (
                "Juniors explain what RAG is and why it beats cramming "
                "everything into the request. Mid designs the pipeline end to "
                "end with justified choices. Seniors design the feedback "
                "loops — measurement-driven improvement, cost budgets, access "
                "control at scale — and can diagnose failure modes from "
                "symptoms alone."
            ),
        },
        {
            "name": "Adaptation Strategy: Prompt vs RAG vs Fine-tune",
            "roles": ["genai"],
            "description": (
                "A judgment round on the three ways to make a general AI fit "
                "your use case, from cheapest to most expensive: better "
                "instructions (prompting), letting it look up your data (RAG), "
                "or retraining its behavior on your examples (fine-tuning). "
                "Interviewers use it to catch over-engineers who reach for the "
                "expensive option when a cheap one would do — a widely "
                "documented real-world failure pattern."
            ),
            "example_questions": [
                "We want the model to answer questions about our product catalog. Rewrite the instructions, hook it to our data, or retrain it — which and why?",
                "When is retraining a model on your own examples genuinely the right call, and what problems does it NOT fix?",
                "What are the ongoing costs of maintaining a custom-trained model that people usually forget?",
                "Tell me about a time you chose NOT to fine-tune. What did you do instead?",
                "The base model gets upgraded next quarter. What happens to each of the three approaches?",
            ],
            "good": (
                "States the escalation ladder plainly — start with "
                "instructions (hours, near-free), add lookup when the model "
                "needs private or fresh knowledge, retrain only for style and "
                "behavior the other two can't reach — and knows retraining "
                "teaches manner, not facts. Bonus points for cost realism: a "
                "custom model is an ongoing expense, not a one-off."
            ),
            "bad": (
                "'We'd fine-tune it on our data' as the first answer to a "
                "knowledge problem — the exact red flag this round exists to "
                "catch. Also: treating the three as interchangeable, or being "
                "unable to name a single case where their preferred approach "
                "is wrong."
            ),
            "seniority": (
                "Juniors define the three approaches and their rough cost "
                "order. Mid applies the ladder to a concrete scenario. Seniors "
                "should have a story of killing or avoiding a retraining "
                "project, and can defend that call against a pushy "
                "stakeholder."
            ),
        },
        {
            "name": "LLM Evals & Hallucination Measurement",
            "roles": ["genai", "data-science"],
            "description": (
                "The fastest-rising round and the current hiring "
                "differentiator: how do you grade an AI whose answers are "
                "free-form text with no single right answer? Teams that can't "
                "measure quality can't ship safely, and post-mortems of failed "
                "AI products almost always trace back to missing evaluation — "
                "so interviewers push hard here."
            ),
            "example_questions": [
                "You built an AI support assistant. How do you know it's good enough to launch, and how do you catch it getting worse after a change?",
                "How would you measure how often the assistant makes things up?",
                "What's wrong with having the team read a handful of answers and calling it tested?",
                "One popular trick is using a second AI to grade the first one's answers. When does that work, and where does it mislead?",
                "Design the pre-launch and post-launch quality checks for an AI feature that summarizes customer calls.",
            ],
            "good": (
                "Describes a concrete workflow: build a test set from real "
                "user questions and past failures, define written criteria, "
                "combine automated checks with targeted human review, re-run "
                "everything on every change, and keep watching after launch. "
                "They mention actually reading transcripts of the AI's "
                "answers, not just dashboards, and they know AI-graders have "
                "biases that need spot-checking against humans."
            ),
            "bad": (
                "'We tried it and it looked good' — vibe-checking. Also: "
                "treating an AI grader's scores as absolute truth, having no "
                "answer for catching regressions, or describing evaluation as "
                "a one-time pre-launch task instead of a continuous habit."
            ),
            "seniority": (
                "Juniors can define hallucination and explain why AI output "
                "needs testing. Mid designs a test harness for a given "
                "feature. Seniors have run evaluation systems in production "
                "and can talk about who labels the data, how quality gates "
                "releases, and how quality scores tie to business results."
            ),
        },
        {
            "name": "Agents & Tool Use",
            "roles": ["genai"],
            "description": (
                "The newest mainstream round. An 'agent' is an AI that doesn't "
                "just answer — it takes multi-step actions (look things up, "
                "call other software, send messages) in a loop until a job is "
                "done. Because a mistake can now touch real systems, "
                "interviews focus overwhelmingly on reliability and safety "
                "rather than enthusiasm."
            ),
            "example_questions": [
                "Design an AI that resolves a customer ticket end to end — find the order, issue the refund, email the customer. What can go wrong at each step?",
                "When the AI wants to take an action, what actually happens? Who executes it?",
                "How do you stop it looping forever, running up a huge bill, or doing something irreversible?",
                "Which actions would you require a human to approve, and why those?",
                "When is a plain, predictable script better than an agent?",
            ],
            "good": (
                "Gets the mechanics right — the AI requests an action and "
                "ordinary software executes it, never the AI itself — then "
                "goes straight to safety engineering: step limits, spending "
                "caps, human sign-off for irreversible actions like refunds, "
                "and a full log of every step. Healthy skepticism is a green "
                "flag: strong candidates say most jobs don't need an agent at "
                "all."
            ),
            "bad": (
                "Buzzword enthusiasm ('we'd have five agents collaborate') "
                "with no answer for what happens when one makes a mistake, "
                "believing the AI runs things directly on its own, or "
                "proposing an autonomous system for a task a simple script "
                "solves."
            ),
            "seniority": (
                "Juniors explain the basic act-observe-repeat loop. Mid "
                "designs a bounded agent with error handling and permissions. "
                "Seniors architect for fleets of them — audit trails, cost "
                "ceilings, org-wide safety rules — and show judgment about "
                "when not to build one."
            ),
        },
        {
            "name": "Cost, Latency & Serving Optimization",
            "roles": ["genai"],
            "description": (
                "Tests whether the candidate can make an AI feature fast and "
                "affordable. These models bill per unit of text and can take "
                "seconds to respond, so at scale a great feature can be "
                "ruinously expensive or annoyingly slow — this round has "
                "largely replaced classic infrastructure design questions for "
                "AI roles."
            ),
            "example_questions": [
                "Our AI feature costs too much and takes eight seconds to respond. Where do you start?",
                "Ballpark the monthly AI bill for a chat feature with a hundred thousand daily users — talk me through the arithmetic.",
                "When would you send a request to a small cheap model instead of a big expensive one, and how do you check the cheap one is good enough?",
                "What did your last AI system cost to run, and what was the biggest lever you found?",
                "Renting a model through a provider versus running one on your own machines — how do you decide?",
            ],
            "good": (
                "Does the arithmetic out loud (users x requests x length x "
                "price) and names layered levers: shorter instructions, "
                "reusing repeated work instead of recomputing it, showing the "
                "answer word-by-word so it feels faster, and routing easy "
                "questions to cheaper models. Every saving comes with 'and "
                "here's how I'd verify quality didn't drop.'"
            ),
            "bad": (
                "No intuition for what anything costs ('just use the biggest "
                "model'), treating slowness as a fact of life, or proposing "
                "compression tricks with no mention of the quality risk or "
                "how they'd measure it."
            ),
            "seniority": (
                "Juniors know text volume drives cost and that streaming "
                "answers feels faster. Mid applies the standard levers with "
                "real pricing knowledge. Seniors reason about the whole "
                "serving stack plus budgeting — cost per feature, per user, "
                "per answer — as a first-class product constraint."
            ),
        },
        {
            "name": "Safety, Guardrails & Prompt Injection",
            "roles": ["genai"],
            "description": (
                "Can the candidate ship an AI feature that can't be easily "
                "hijacked or made to embarrass the company? Covers the "
                "signature attack (hiding malicious instructions in text the "
                "AI reads), leaking private data, and harmful output. Once a "
                "specialist topic, now asked by mainstream enterprises, and "
                "deeply probed by AI labs."
            ),
            "example_questions": [
                "A user talks our support bot into ignoring its rules and revealing its hidden instructions. How do you defend against that?",
                "Attackers can hide instructions inside a document the AI is asked to summarize. Why is that especially dangerous once the AI can take actions?",
                "What checks would you run on what goes INTO the model and what comes OUT, for a bot that handles customer data?",
                "How would you attack your own feature before launch?",
                "Your safety filter blocks 2% of legitimate customers. How do you think about that trade-off?",
            ],
            "good": (
                "Layered defense, stated plainly: no single filter is enough, "
                "so you check inputs, constrain what the AI is allowed to do, "
                "filter outputs, require human approval for risky actions, "
                "log everything, and keep attacking your own system. Mature "
                "candidates admit there's no complete fix — the goal is "
                "making attacks expensive and limiting the damage when one "
                "lands."
            ),
            "bad": (
                "Believing that telling the model 'never reveal your "
                "instructions' is a defense, treating safety as the model "
                "provider's problem, never having heard of attacks hidden "
                "inside documents, or claiming a product made the system "
                "'secure' with no residual risk discussed."
            ),
            "seniority": (
                "Juniors can define the attack and know outputs need "
                "filtering. Mid designs multi-layer defenses and handles "
                "private data properly. Seniors threat-model whole agent "
                "systems, run attack-your-own-product programs, and own the "
                "safety-versus-usability trade-off with stakeholders."
            ),
        },
        {
            "name": "Take-Home & Project Deep-Dive",
            "roles": ["data-science", "genai"],
            "description": (
                "How skills get verified in practice: a small build-it "
                "assignment defended live, a deep interrogation of one past "
                "project, or (newest) a coding session WITH an AI assistant "
                "where interviewers watch how the candidate directs and "
                "double-checks it. These formats surged because polished "
                "answers are now cheap and working artifacts are not."
            ),
            "example_questions": [
                "Take us through the project you know best, start to finish — we'll interrupt with questions.",
                "Here's a dataset with problems we haven't told you about. Analyze it and bring us three recommendations.",
                "What was messy about the data or the requirements, and what surprised you halfway through?",
                "(Live, AI-assisted) Use the assistant to build this — narrate where you trust its output and where you don't.",
                "What's still wrong with that project today? What would you fix with a free week?",
            ],
            "good": (
                "Real-work texture: they found the planted data problems and "
                "said so, stated assumptions, chose a defensible simple "
                "approach over an impressive complicated one, and led with "
                "the recommendation rather than the method. In AI-assisted "
                "rounds, they treat the assistant like a junior colleague — "
                "precise instructions, checking every output, saying 'I don't "
                "trust this, let me verify' out loud."
            ),
            "bad": (
                "A suspiciously smooth story ('we got the data, built the "
                "model, it worked') — that's the tutorial shape, not the "
                "real-work shape. Also: never noticed the dirty data, can't "
                "explain code they claim to have written, nothing to say "
                "about what happened after launch, or blindly accepting "
                "whatever the AI assistant produced."
            ),
            "seniority": (
                "Juniors: one honest personal project defended well beats "
                "breadth. Mid: production stories with monitoring and costs, "
                "not demos. Seniors get interrogated on framing and "
                "organizational decisions, like a job talk. One caution for "
                "recruiters: multi-day unpaid assignments distort senior "
                "pipelines and occasionally shade into free product work."
            ),
        },
        {
            "name": "Behavioral & Collaboration Round",
            "roles": ["data-science", "genai"],
            "description": (
                "Structured questions about past work: influence, conflict, "
                "failure, and communicating with non-technical partners. "
                "These roles sit between engineering, product, and "
                "leadership, so the job is substantially persuasion with "
                "evidence — and this round decides outcomes more often than "
                "candidates expect."
            ),
            "example_questions": [
                "Tell me about a time your findings contradicted what a stakeholder wanted to hear. What happened?",
                "Describe something you shipped that failed or misbehaved. What went wrong and what changed afterward?",
                "Walk me through your most complex piece of work — then explain it again the way you told your executives.",
                "Tell me about changing a decision with evidence when you had no authority over the people deciding.",
                "Two teams wanted different definitions of success for the same launch. How did you resolve it?",
            ],
            "good": (
                "Specific first-person stories — 'I', not wall-to-wall 'we' — "
                "with an arc from situation to action to a measurable result, "
                "honest ownership of failures with a lesson later applied, "
                "and the ability to tell the same story at technical depth "
                "and in an executive summary. That switching is itself the "
                "job skill being tested."
            ),
            "bad": (
                "Vague generalities that could describe anyone's job, all "
                "credit claimed and all blame deflected, 'failures' that are "
                "secretly humblebrags, badmouthing former colleagues, or "
                "rehearsed stories that crumble when you probe one detail."
            ),
            "seniority": (
                "Juniors: coachability and honest ownership; small stories "
                "are fine. Mid: end-to-end ownership of something ambiguous "
                "plus at least one real stakeholder negotiation. Seniors must "
                "show organizational influence — a candidate whose stories "
                "are all solo technical work is a common down-level trigger."
            ),
        },
        {
            "name": "ML System Design (recommendations, ranking, fraud)",
            "roles": ["data-science", "genai"],
            "description": (
                "A whiteboard round where the candidate designs a complete "
                "prediction system end-to-end — 'design the recommendations "
                "feed', 'design fraud detection for payments' — from what "
                "data to use, to how to train and grade the model, to how it "
                "runs and gets monitored inside the live product. It's the "
                "staple senior round for classic (non-chatbot) AI work at "
                "large tech companies, because it exposes whether someone has "
                "actually shipped a model or only studied them."
            ),
            "example_questions": [
                "Design the system that decides which posts a user sees first in a social feed.",
                "How would you build fraud detection for a payments product, end to end?",
                "Design a system that recommends what to watch next on a streaming service.",
                "We want to predict which deliveries will arrive late — walk me through the whole system, not just the model.",
                "A month after launching your recommender, how do you know it's actually working?",
            ],
            "good": (
                "They spend the first minutes on the goal and constraints "
                "(what are we optimizing? how fast must it answer? what does "
                "a mistake cost?), design the data and the feedback loop "
                "before naming any model, and always cover life after launch "
                "— monitoring, retraining, and how the system can quietly rot "
                "as user behavior changes."
            ),
            "bad": (
                "Jumps straight to naming a sophisticated model, designs only "
                "the training half with no story for how predictions reach "
                "the product, ignores what a wrong prediction costs the "
                "business, and has no answer for 'how do you know it still "
                "works next quarter?'"
            ),
            "seniority": (
                "Rarely asked of juniors. Mid-level should produce a coherent "
                "pipeline with sensible quality measures. Seniors are judged "
                "on tradeoffs (simple-but-shippable vs sophisticated), "
                "failure modes, feedback loops, and cost at scale."
            ),
        },
    ],
    "concepts": [
        {
            "key": "ml-model",
            "name": "Machine Learning & Models",
            "plain_english": (
                "Machine learning means teaching a computer by example instead "
                "of by rules. Nobody writes 'if the email mentions a lottery, "
                "it's spam' — instead you show the computer thousands of past "
                "emails already labeled spam or not, and it works out the "
                "telltale patterns itself. The finished pattern-recognizer is "
                "called a model. It's like training a sniffer dog: you don't "
                "explain the chemistry of contraband, you reward it on examples "
                "until it can flag new bags on its own."
            ),
            "why_asked": (
                "It's the foundation of both role families, and explaining it "
                "simply to non-experts is a daily part of the actual job — so "
                "interviewers test the explanation as much as the knowledge."
            ),
            "green_flags": [
                "Explains it as 'learning patterns from examples' with a concrete business case",
                "Is clear that a model only knows what its examples taught it",
                "Can say when simple hand-written rules beat a model",
            ],
            "red_flags": [
                "Can't explain it without jargon even when asked to simplify",
                "Talks about models as if they 'understand' or 'think' with no caveats",
            ],
        },
        {
            "key": "training-vs-inference",
            "name": "Training vs Inference",
            "plain_english": (
                "Training is the learning phase: the model studies mountains of "
                "example data, which takes serious computing power, time, and "
                "money — like putting a student through medical school. "
                "Inference is the using phase: the trained model answers one "
                "question or makes one prediction, like the graduated doctor "
                "seeing a single patient. Training happens rarely; inference "
                "happens millions of times a day once a product launches, which "
                "is why running costs and speed dominate production "
                "conversations."
            ),
            "why_asked": "Mixing the two up is an instant tell that someone has read about models but never run one for real users.",
            "green_flags": [
                "Distinguishes one-time build cost from per-use running cost naturally",
                "Knows the answering side is what users feel and what teams optimize",
            ],
            "red_flags": [
                "Uses 'training' for everything the model does",
                "Has no sense of what serving answers at scale costs",
            ],
        },
        {
            "key": "sql",
            "name": "SQL",
            "plain_english": (
                "SQL is the standard language for asking questions of a "
                "company's databases — 'how many customers signed up last week, "
                "by country?' is a few lines of it. Think of the database as a "
                "vast filing room and SQL as the request slip that fetches "
                "exactly the folders you need, combined and totaled. It "
                "survived the AI era untouched: it appears in the huge majority "
                "of data-science interviews because someone who can't retrieve "
                "and shape data can't do anything else in the role."
            ),
            "why_asked": "It's a cheap, reliable early filter — a hands-on skill that's easy to test in half an hour and very hard to fake live.",
            "green_flags": [
                "Asks what the data looks like before writing a query",
                "Sanity-checks their own results out loud",
                "Handles data with gaps, duplicates, and ties deliberately",
            ],
            "red_flags": [
                "Gets lost combining information from more than one table",
                "Produces a query that runs but answers a different question",
            ],
        },
        {
            "key": "train-test-overfitting",
            "name": "Train/Test Split & Overfitting",
            "plain_english": (
                "To trust a model, you teach it on one slice of your data and "
                "grade it on a separate slice it has never seen — practice "
                "problems versus a final exam with different questions. "
                "Overfitting is what happens when the model effectively "
                "memorizes the practice set: it scores near-perfectly on data "
                "it studied and badly on anything new, like a student who "
                "memorized last year's exam answers and bombs this year's. The "
                "telltale sign is a big gap between the two scores."
            ),
            "why_asked": (
                "It's the most common way models quietly fail — great in the "
                "lab, useless with real customers — so nearly every ML round "
                "includes a probe on it."
            ),
            "green_flags": [
                "Always grades models on data they never saw during learning",
                "Instantly diagnoses a big practice-vs-exam score gap as memorization",
                "Mentions 'leakage' — answer-revealing clues accidentally sneaking into the practice data",
            ],
            "red_flags": [
                "Brags about a near-perfect score on the data the model studied",
                "Answers every problem with 'use a bigger, fancier model'",
            ],
        },
        {
            "key": "precision-recall",
            "name": "Precision & Recall",
            "plain_english": (
                "Two report cards for anything that flags things — fraud, spam, "
                "disease. Precision: of everything it flagged, how much was "
                "actually right (few false alarms)? Recall: of all the real "
                "cases out there, how many did it catch (few misses)? They pull "
                "against each other — a smoke detector that shrieks at toast "
                "catches every fire but drives you mad. Which matters more "
                "depends entirely on whether a false alarm or a miss costs the "
                "business more."
            ),
            "why_asked": "Choosing between them is a daily judgment call, and it exposes whether a candidate connects model math to business cost.",
            "green_flags": [
                "Picks one for the scenario and justifies it with the cost of each mistake",
                "Knows plain accuracy is meaningless when the thing detected is rare",
            ],
            "red_flags": [
                "Uses overall accuracy as the only measure for a rare-event problem",
                "Can't say which type of error is worse for the case at hand",
            ],
        },
        {
            "key": "p-value",
            "name": "P-value & Statistical Significance",
            "plain_english": (
                "A p-value answers: 'if our change actually did nothing, how "
                "likely is it we'd still see a result this striking just by "
                "luck?' A small value (usually under 0.05, called "
                "'statistically significant') means the result would be a "
                "surprising fluke, so the change probably did something. "
                "Crucially, it says nothing about size: test on millions of "
                "users and a microscopic, worthless improvement can still be "
                "'significant' — like proving beyond doubt that a diet pill "
                "sheds one gram. Real is not the same as worth acting on."
            ),
            "why_asked": (
                "It's the standard yardstick for 'real or just noise?', and "
                "misstating it is the single most common stats error — so "
                "interviewers specifically ask for a plain-English "
                "explanation."
            ),
            "green_flags": [
                "Frames it as 'how surprising would this be if nothing changed'",
                "Volunteers that significant does not mean big or important",
                "Asks 'how large is the effect?' alongside 'is it real?'",
            ],
            "red_flags": [
                "Calls it 'the probability the result is true' — the classic wrong answer",
                "Treats the 0.05 line as an automatic ship/no-ship switch",
            ],
        },
        {
            "key": "ab-testing",
            "name": "A/B Testing",
            "plain_english": (
                "The fairest way to learn whether a change works: randomly "
                "split users into two groups, show one the old version and one "
                "the new, and compare outcomes. Because the split is random, "
                "the only systematic difference between the groups is the "
                "change itself, so it gets the credit or the blame — the same "
                "logic as a clinical drug trial, applied to a product. The "
                "craft is in the details: deciding how many users, running long "
                "enough, and watching for hidden harm."
            ),
            "why_asked": (
                "It's the bread-and-butter decision tool at consumer tech "
                "companies, often with a whole interview round devoted to "
                "designing one properly."
            ),
            "green_flags": [
                "States a hypothesis, one main success measure, and tripwire measures for harm",
                "Plans the number of users and the duration before starting",
                "Names the traps: stopping early, fading novelty excitement, users influencing each other",
            ],
            "red_flags": [
                "Compares this month to last month and calls it a test — no random split",
                "Wants to peek daily and stop the moment results look good",
            ],
        },
        {
            "key": "correlation-vs-causation",
            "name": "Correlation vs Causation",
            "plain_english": (
                "Two things moving together doesn't mean one causes the other. "
                "Ice cream sales and drownings rise together — because of "
                "summer, not because ice cream drowns people. In products: "
                "users of feature X stick around longer, but maybe enthusiastic "
                "users simply do both, and forcing everyone into X would change "
                "nothing. Untangling 'moves together' from 'causes' is a huge "
                "part of the actual job, because companies lose real money "
                "acting on look-alike causes."
            ),
            "why_asked": "Interviewers check whether the candidate reflexively asks 'but did it CAUSE that?' before recommending action.",
            "green_flags": [
                "Distinguishes 'associated with' from 'caused by' without prompting",
                "Proposes a proper experiment before betting big on a pattern",
                "Offers alternative explanations, like seasonality or user self-selection",
            ],
            "red_flags": [
                "Jumps from 'users who do X stay longer' straight to 'make everyone do X'",
                "Never considers a third factor behind the pattern",
            ],
        },
        {
            "key": "north-star-guardrail-metrics",
            "name": "North-Star & Guardrail Metrics",
            "plain_english": (
                "A north-star metric is the one number that best captures "
                "whether the product truly succeeds — say, weekly active "
                "buyers. Guardrail metrics are tripwires watched alongside it "
                "to make sure a 'win' isn't secretly doing damage: uninstalls, "
                "complaints, page speed. Example: more aggressive notifications "
                "boost daily opens (looks great!) while quietly spiking "
                "uninstalls — the guardrail catches it. Good metric design "
                "always pairs the upside number with the tripwires."
            ),
            "why_asked": (
                "Product cases and experiment design both live on metric "
                "choice; candidates who name only upside numbers design "
                "launches that ship harm."
            ),
            "green_flags": [
                "Ties the main metric to the product's real goal, not what's easy to count",
                "Always pairs it with measures that would reveal harm",
                "Distinguishes vanity numbers (raw signups) from meaningful ones (people who stay)",
            ],
            "red_flags": [
                "Maximizes one engagement number with no thought to side effects",
                "Picks metrics the team can't actually measure or move",
            ],
        },
        {
            "key": "llm",
            "name": "LLM (Large Language Model)",
            "plain_english": (
                "The type of AI behind ChatGPT and Claude: a model trained on "
                "enormous amounts of text until it can read and write fluently "
                "on nearly any topic. It works by predicting, one small chunk "
                "at a time, what text should come next — an extraordinarily "
                "well-read autocomplete. That's why it's brilliant at drafting, "
                "summarizing, and answering, and also why it can be confidently "
                "wrong: it produces plausible text, and plausible is not the "
                "same as true."
            ),
            "why_asked": (
                "It's the core technology of GenAI roles and increasingly "
                "shows up in data-science loops too; how someone describes it "
                "reveals how deep their experience goes."
            ),
            "green_flags": [
                "Describes both what it's great at and where it fails, unprompted",
                "Knows fluent-sounding output can still be factually wrong",
            ],
            "red_flags": [
                "Presents it as an all-knowing brain suitable for every problem",
                "Can't explain in plain words what it actually does",
            ],
        },
        {
            "key": "token-context-window",
            "name": "Tokens & the Context Window",
            "plain_english": (
                "Tokens are the small chunks of text an AI model reads and "
                "writes — roughly three-quarters of a word each. Everything is "
                "measured in them: providers bill per token, speed is tokens "
                "per second, and limits are token counts — like the minutes on "
                "an old phone plan, the unit everything is billed and capped "
                "in. The context window is the model's short-term memory: the "
                "maximum text it can consider at once (instructions, "
                "conversation, documents). Overflow gets cut off, and even "
                "within the limit, models can miss things buried in the middle "
                "of very long inputs."
            ),
            "why_asked": (
                "Cost, speed, and 'why did the bot forget what I said?' all "
                "come down to tokens and the window — fluency here instantly "
                "signals real production experience."
            ),
            "green_flags": [
                "Converts naturally between text, tokens, and dollars when estimating",
                "Explains what a product should do when a conversation outgrows the window",
            ],
            "red_flags": [
                "Uses 'words' and 'tokens' interchangeably",
                "Assumes you can stuff everything into the request with no cost or quality downside",
            ],
        },
        {
            "key": "embeddings",
            "name": "Embeddings",
            "plain_english": (
                "A way of turning a piece of text into a long list of numbers "
                "that captures its meaning, so a computer can measure how "
                "similar two pieces of content are. 'How do I reset my "
                "password?' and 'I forgot my login' end up with nearly "
                "identical numbers even though they share no words — like "
                "assigning every document a precise position on a giant map "
                "where things that mean the same sit close together. This is "
                "the technology behind search-by-meaning rather than "
                "search-by-keyword."
            ),
            "why_asked": (
                "Embeddings power the document-lookup step in most enterprise "
                "AI products, so candidates for those roles must understand "
                "and be able to evaluate them."
            ),
            "green_flags": [
                "Explains it as 'meaning turned into numbers so similarity can be measured'",
                "Can contrast meaning-based search with keyword search and say when each wins",
            ],
            "red_flags": [
                "Uses the word without being able to say what problem it solves",
                "Can't tell meaning-based search apart from plain keyword matching",
            ],
        },
        {
            "key": "rag",
            "name": "RAG (Retrieval-Augmented Generation)",
            "plain_english": (
                "The technique of letting an AI look things up before "
                "answering — an open-book exam instead of a memory test. When "
                "a user asks something, the system first searches the "
                "company's own documents for relevant passages, then hands "
                "them to the AI with instructions to answer from that "
                "material. It's how a general-purpose AI becomes accurate "
                "about YOUR products and policies without retraining it, and "
                "it's the most common architecture in enterprise AI today."
            ),
            "why_asked": (
                "'Design a document-answering system' is the new default "
                "GenAI design interview — roughly what 'design a social "
                "network' used to be."
            ),
            "green_flags": [
                "Describes the whole pipeline with trade-offs, not just tool names",
                "Can diagnose whether a wrong answer came from a bad lookup or bad writing",
                "Mentions permissions, keeping documents fresh, and citing sources",
            ],
            "red_flags": [
                "Recites a tutorial recipe with no story about measuring quality",
                "Name-drops tools without explaining what each piece does",
            ],
        },
        {
            "key": "fine-tuning-vs-prompting",
            "name": "Fine-tuning vs Prompting",
            "plain_english": (
                "Prompting means changing the written instructions you give "
                "the AI — cheap, fast, always the first thing to try. "
                "Fine-tuning means additional training that adjusts the "
                "model's behavior using your own examples — like sending an "
                "experienced employee on a specialized course. Fine-tuning "
                "changes HOW the model behaves (tone, format, style) far more "
                "than WHAT it knows, and it's expensive to do and keep "
                "maintaining. Giving the model your knowledge is usually a "
                "lookup problem (see RAG), not a retraining problem."
            ),
            "why_asked": (
                "'When would you fine-tune?' is a deliberate over-engineering "
                "detector; knowing when NOT to is a stronger signal than "
                "knowing how."
            ),
            "green_flags": [
                "States the cheap-to-expensive ladder: instructions, then lookup, then retraining",
                "Knows retraining teaches manner, not facts",
                "Has a story of choosing against fine-tuning",
            ],
            "red_flags": [
                "Proposes retraining as the first answer to 'make it know our data'",
                "Ignores the ongoing cost of maintaining a custom model",
            ],
        },
        {
            "key": "hallucination",
            "name": "Hallucination",
            "plain_english": (
                "When an AI confidently states something false — inventing "
                "facts, citations, numbers, or product features that don't "
                "exist. It isn't lying (there's no intent); it's a built-in "
                "side effect of how these systems generate plausible-sounding "
                "text, like a witness who fills memory gaps with confident "
                "detail. It can't be fully eliminated, only reduced and "
                "managed — grounding answers in real documents, showing "
                "sources, and adding human review where stakes are high."
            ),
            "why_asked": (
                "It's the central quality problem of AI products; candidates "
                "who have measured and reduced it are showing exactly the "
                "production maturity employers want."
            ),
            "green_flags": [
                "Talks about measuring how often it happens, not just that it happens",
                "Names layered defenses: grounding in documents, citations, review for high-stakes answers",
            ],
            "red_flags": [
                "Claims their system 'doesn't hallucinate' or that a better model solves it",
                "Shrugs it off as an unavoidable quirk with no mitigation plan",
            ],
        },
        {
            "key": "evals-llm-judge",
            "name": "Evals & LLM-as-Judge",
            "plain_english": (
                "Evals are the AI world's quality tests. Normal software can "
                "be tested exactly ('input X must always give Y'), but AI "
                "answers vary, so teams build collections of test questions "
                "with written grading criteria and re-run them on every "
                "change — 'do you have evals?' is today's 'do you write "
                "tests?'. LLM-as-judge means using a second AI to grade the "
                "first one's answers at scale, like hiring an external "
                "examiner to mark thousands of essays — useful, but the "
                "examiner has known biases, so good teams spot-check it "
                "against human graders."
            ),
            "why_asked": (
                "Hiring managers cite evaluation rigor as THE differentiator "
                "between professional AI teams and hobbyists; failed AI "
                "products almost always trace back to missing evals."
            ),
            "green_flags": [
                "Builds test sets from real user questions and past failures",
                "Runs the tests on every change to catch regressions",
                "Knows AI graders have biases and validates them against humans",
            ],
            "red_flags": [
                "'We looked at some outputs and they seemed fine' — vibe-checking",
                "Treats an AI grader's scores as absolute truth",
            ],
        },
        {
            "key": "agents-tool-use",
            "name": "Agents & Tool Use",
            "plain_english": (
                "An agent is an AI that doesn't just answer questions but "
                "takes multi-step actions to finish a task — searching, "
                "reading files, calling other software — deciding each next "
                "step itself, in a loop, until the job is done: an intern who "
                "can actually use the computer, not just answer when asked. "
                "Tool use is the mechanism: developers hand the AI a menu of "
                "allowed actions, and when it wants one, it writes a request "
                "that the company's ordinary software then executes. The AI "
                "never runs anything itself — it asks, regular code acts."
            ),
            "why_asked": (
                "Agents are the dominant new product wave, and the hard part "
                "is reliability — interviewers screen for candidates who "
                "engineer around failure rather than radiate enthusiasm."
            ),
            "green_flags": [
                "Correctly describes the ask-execute-report-back loop",
                "Raises step limits, spending caps, and human approval for risky actions unprompted",
                "Says some problems don't need an agent at all",
            ],
            "red_flags": [
                "Believes the AI directly runs code or touches systems on its own",
                "Multi-agent buzzwords with no answer for what happens when one errs",
            ],
        },
        {
            "key": "latency-cost",
            "name": "Latency & Cost Trade-offs",
            "plain_english": (
                "Every AI answer costs real money (billed per token, the "
                "chunks of text) and takes real time — 'latency' is the wait "
                "before the answer arrives. At scale these add up "
                "shockingly fast, so production teams constantly balance "
                "three dials: answer quality, speed, and cost — like "
                "shipping, where fast, cheap, and perfect never come "
                "together. Standard levers include shortening instructions, "
                "reusing repeated work instead of recomputing it, and "
                "routing easy questions to smaller, cheaper models."
            ),
            "why_asked": (
                "A feature that's great but unaffordable never ships; "
                "candidates with concrete cost wins on their record are in "
                "high demand, and having no idea what their last system cost "
                "is a strong tell."
            ),
            "green_flags": [
                "Estimates costs with actual arithmetic, out loud",
                "Pairs every cost-saving idea with how they'd verify quality held up",
            ],
            "red_flags": [
                "Proposes the biggest model for everything",
                "Doesn't know what their previous system cost to run",
            ],
        },
        {
            "key": "guardrails-safety",
            "name": "Guardrails, Safety & Prompt Injection",
            "plain_english": (
                "Guardrails are safety checks wrapped around an AI feature — "
                "filters inspecting what goes in and what comes out, blocking "
                "leaked personal data, harmful content, or dangerous actions: "
                "a bouncer at both the entrance and the exit. Prompt "
                "injection is the signature attack they guard against: hiding "
                "malicious instructions in text the AI will read — a chat "
                "message, an email, even a document it's asked to summarize — "
                "to hijack it into breaking its rules. There's no complete "
                "fix, so serious teams layer several defenses and limit the "
                "damage any single breach can do."
            ),
            "why_asked": (
                "Every customer-facing AI feature needs them, the attack gets "
                "more dangerous as AIs gain the power to act, and 'safety and "
                "guardrails' is now a named line in AI hiring rubrics."
            ),
            "green_flags": [
                "Describes layered checks on input, output, and actions — never one filter",
                "Knows attacks can hide inside documents the AI reads, not just user messages",
                "Admits no complete defense exists and talks about limiting blast radius",
            ],
            "red_flags": [
                "Thinks telling the model 'be safe' in its instructions is protection",
                "Treats safety as entirely the AI provider's job",
            ],
        },
    ],
    "evaluation": [
        {
            "name": "The teach-back probe",
            "description": (
                "Ask the candidate to explain a concept or their own project "
                "as if you know nothing — because you genuinely might not, "
                "which makes you the perfect test instrument. True experts "
                "can simplify without losing the substance; shallow "
                "candidates hide behind jargon, and the point where they can "
                "no longer simplify is exactly where their understanding "
                "ends."
            ),
            "probes": [
                "Explain that to me as if I've never heard of this field — no shortcuts.",
                "You just used the word 'embeddings' — what does that mean in everyday terms?",
                "If you had two minutes with our CEO, how would you describe this project and why it mattered?",
            ],
            "good": (
                "They reach for analogies willingly and without irritation, "
                "check that you're following, and the simple version still "
                "carries the why — purpose, decision, outcome. Any jargon "
                "word they introduced, they can define instantly and simply."
            ),
            "bad": (
                "They restate the same jargon more slowly, get condescending, "
                "or the 'simple' version turns vague and content-free ('we "
                "used AI to make it better'). If simplifying changes the "
                "story, the original was memorized, not understood."
            ),
        },
        {
            "name": "The drill-down",
            "description": (
                "Take one claimed accomplishment and ask three to five "
                "follow-ups on the SAME story instead of moving on. Real "
                "experiences are anchored to actual details — constraints, "
                "people, dead ends — so they survive probing; inflated ones "
                "run out of detail by the second follow-up. You don't need "
                "to understand the technology to notice detail running out."
            ),
            "probes": [
                "What was the hardest part of that project?",
                "Who disagreed with your approach, and what did they say?",
                "What did you do when it didn't work the first time?",
                "Walk me through one specific week of it — what were you actually doing?",
            ],
            "good": (
                "Detail INCREASES with each follow-up: named tools, named "
                "roles, specific numbers, wrong turns. Answers stay "
                "consistent with what they said earlier, and setbacks get "
                "owned rather than blamed on others."
            ),
            "bad": (
                "Detail DECREASES under probing — each answer more abstract "
                "than the last, looping back to the rehearsed summary, "
                "numbers or timelines shifting between tellings, or "
                "defensiveness when you push."
            ),
        },
        {
            "name": "The trade-off probe",
            "description": (
                "Every real technical decision had alternatives and costs, so "
                "ask 'why this and not that?' and 'what did it cost you?'. "
                "This tests judgment rather than memorization, and hiring "
                "managers in these fields consistently call trade-off "
                "reasoning the true separator between levels."
            ),
            "probes": [
                "What else did you consider, and why did you reject it?",
                "What did that choice cost you — money, speed, accuracy, complexity?",
                "When would your approach be the WRONG choice?",
                "A teammate wanted to do it differently — make their case for me as fairly as you can.",
            ],
            "good": (
                "Names concrete alternatives unprompted, reasons from "
                "constraints ('we needed explainable answers, so we accepted "
                "lower accuracy'), can argue the other side fairly, and puts "
                "numbers on costs where possible."
            ),
            "bad": (
                "'It's the best, most modern approach' with no alternative "
                "ever considered, 'always use X' absolutism, inability to "
                "name any situation where their choice fails, or treating "
                "your counter-suggestion as an attack."
            ),
        },
        {
            "name": "The failure probe",
            "description": (
                "Ask where their system fails and what broke. People who ran "
                "something for real users know its failure modes intimately; "
                "people who did a tutorial only know the happy path. This is "
                "especially sharp for AI roles, where systems fail constantly "
                "and the actual skill is building around failure."
            ),
            "probes": [
                "Tell me about a time it gave a wrong or embarrassing answer. What did you do?",
                "How would you know if it started performing badly next month?",
                "What would break first if usage grew a hundred times?",
                "How did you deal with the AI making things up? Walk me through the actual defenses.",
            ],
            "good": (
                "Immediate, specific, lived failure stories, plus a "
                "monitoring habit — they describe watching the thing after "
                "launch, not just building it. Defenses come in layers, not "
                "one-liners."
            ),
            "bad": (
                "'It worked really well' with no failure story at all — "
                "everything real fails somehow. Also: no concept of watching "
                "quality after launch, or every failure blamed on another "
                "team's data."
            ),
        },
        {
            "name": "The constraint twist",
            "description": (
                "Take the candidate's own answer and change one variable — "
                "budget, scale, speed, privacy — and watch them adapt. "
                "Memorized and AI-fed answers are brittle because the script "
                "no longer applies; genuine understanding adapts in real "
                "time. Twists referencing the candidate's OWN earlier words "
                "are also the best defense against live AI-assisted "
                "cheating, whose tell is a uniform pause before every "
                "suspiciously essay-like answer."
            ),
            "probes": [
                "Same problem, but you have a tenth of the data — what changes?",
                "Now the answer has to come back in under a second. What do you do differently?",
                "What if we couldn't send any data to outside AI providers — how does your design change?",
                "Earlier you said [their detail] — how does that square with what you just told me?",
            ],
            "good": (
                "Thinks out loud immediately, asks a clarifying question back "
                "(itself a strong signal), and the adapted answer connects "
                "logically to what they said before. 'I'd have to test, but "
                "my instinct is...' with reasoning is a great response."
            ),
            "bad": (
                "A long unnatural pause followed by a suddenly polished "
                "essay, the twist answered with the same generic script as "
                "the original, contradiction of their own earlier specifics, "
                "or freezing because no memorized answer fits."
            ),
        },
        {
            "name": "The ownership audit",
            "description": (
                "Team projects are the easiest place to inflate a resume, so "
                "systematically separate what the candidate personally did "
                "from what the team did. You're auditing pronouns and "
                "specificity, not technology — fully runnable with zero "
                "technical background, and it doubles as your best leveling "
                "instrument."
            ),
            "probes": [
                "That sounds like a team effort — what was YOUR specific piece?",
                "Which decisions were yours alone, and which were made for you?",
                "If I called a teammate from that project, what would they say you contributed?",
            ],
            "good": (
                "Cleanly separates 'I' from 'we' and comfortably credits "
                "others ('the search piece was my colleague's; mine was the "
                "quality testing'). Their claimed piece stays the same size "
                "all interview, and it's the part they can go deepest on."
            ),
            "bad": (
                "Wall-to-wall 'we' that never resolves into an 'I' even when "
                "asked directly, claimed ownership that grows as the "
                "interview goes on, or claiming the whole project while only "
                "describing it at press-release level."
            ),
        },
        {
            "name": "The impact anchor",
            "description": (
                "Ask what the work changed for the business or users, and how "
                "they know. Technical work is notoriously easy to describe "
                "impressively while having delivered nothing measurable — "
                "and connecting work to outcomes is fully assessable by a "
                "non-technical interviewer."
            ),
            "probes": [
                "What changed for the business because of this, and how was it measured?",
                "Who used what you built — and are they still using it today?",
                "What number moved, by how much, and how sure are you it was your work that moved it?",
            ],
            "good": (
                "Concrete numbers with honest caveats ('signups rose about "
                "8%, though it overlapped a marketing push'), knowing who "
                "their users were, and mention of life after launch — "
                "adoption and maintenance are the signature of real "
                "production work."
            ),
            "bad": (
                "Only activity metrics ('I trained twelve models') with no "
                "line to a business outcome, not knowing whether anyone used "
                "the thing, or implausibly clean causal wins claimed without "
                "a single caveat — overclaiming is itself a signal."
            ),
        },
    ],
    "resources": [
        # 40 URL-verified picks from the research pass (each fetched live).
        {
            "topic": "Machine learning basics",
            "title": "But what is a neural network? | Deep Learning Chapter 1 (3Blue1Brown)",
            "url": "https://www.youtube.com/watch?v=aircAruvnKk",
            "kind": "video",
            "time": "18 min",
            "why": "The single most-recommended intro to neural nets on the internet (190M+ channel views). Grant Sanderson's animations let you SEE a network recognize a handwritten digit layer by layer — zero math background needed,…",
        },
        {
            "topic": "Machine learning basics",
            "title": "A Gentle Introduction to Machine Learning (StatQuest with Josh Starmer)",
            "url": "https://www.youtube.com/watch?v=Gv9_4yMHFhI",
            "kind": "video",
            "time": "13 min",
            "why": "StatQuest's trademark 'silly songs + dead-simple pictures' style strips ML to its two core ideas: making predictions and testing them. Gives a recruiter the exact mental model (training data vs. testing data) that…",
        },
        {
            "topic": "Machine learning basics",
            "title": "Machine Learning Crash Course (Google)",
            "url": "https://developers.google.com/machine-learning/crash-course",
            "kind": "course",
            "time": "15 hours (modular — do 2-3 hours for conversational level)",
            "why": "Google's own internal ML onboarding, rebuilt in 2024 with interactive visualizations, short videos, and 130+ self-check questions — now including LLM modules. The most polished free structured path from zero to…",
        },
        {
            "topic": "Machine learning basics",
            "title": "AI for Everyone (Andrew Ng, Coursera)",
            "url": "https://www.coursera.org/learn/ai-for-everyone",
            "kind": "course",
            "time": "6-8 hours",
            "why": "Andrew Ng built this specifically for non-engineers — it explains what AI can and cannot do, what data scientists vs. ML engineers actually do all day, and how AI teams are structured. That role-taxonomy lecture…",
        },
        {
            "topic": "Machine learning basics",
            "title": "Introduction to Machine Learning Interviews Book (Chip Huyen)",
            "url": "https://huyenchip.com/ml-interviews-book/",
            "kind": "article",
            "time": "3-5 hours (Part I is the recruiter-relevant core)",
            "why": "A free full-length book by a Stanford instructor that maps the entire ML hiring landscape from BOTH sides of the table: role types, interview loop formats, what each round tests, plus 200+ real knowledge questions.…",
        },
        {
            "topic": "Statistics & A/B testing",
            "title": "Seeing Theory: A Visual Introduction to Probability and Statistics (Brown University)",
            "url": "https://seeing-theory.brown.edu/",
            "kind": "interactive",
            "time": "2-3 hours",
            "why": "Arguably the most beautiful statistics education ever put on the web — you drag, drop, and roll dice in D3.js visualizations and watch concepts like confidence intervals and Bayesian inference emerge live. Used in…",
        },
        {
            "topic": "Statistics & A/B testing",
            "title": "p-values: What they are and how to interpret them (StatQuest)",
            "url": "https://www.youtube.com/watch?v=vemZtEM63GY",
            "kind": "video",
            "time": "12 min",
            "why": "The p-value is the single most misunderstood term in data-science conversations, and this is the clearest 12-minute correction available anywhere. After it, a recruiter can follow (and sanity-check) any candidate's…",
        },
        {
            "topic": "Statistics & A/B testing",
            "title": "What is an A/B Test? (Netflix TechBlog, 'Decision Making at Netflix' series)",
            "url": "https://netflixtechblog.com/what-is-an-a-b-test-b08cc1b57962",
            "kind": "article",
            "time": "8 min (series: ~45 min)",
            "why": "Experimentation explained by the company most famous for it, in plain English with real product examples (the 'upside-down Netflix' thought experiment). Part of a series — the follow-ups on false positives and…",
        },
        {
            "topic": "SQL",
            "title": "SQLBolt — Learn SQL with interactive exercises",
            "url": "https://sqlbolt.com/",
            "kind": "interactive",
            "time": "3-4 hours",
            "why": "The fastest zero-friction way to actually WRITE SQL: every lesson runs queries live in your browser, no signup, no install. In an afternoon a non-technical person goes from nothing to writing JOINs — which transforms…",
        },
        {
            "topic": "SQL",
            "title": "Select Star SQL (Zi Chong Kao)",
            "url": "https://selectstarsql.com/",
            "kind": "interactive",
            "time": "3-4 hours (4 chapters, ~30 min each + projects)",
            "why": "An interactive SQL 'book' where you investigate a real, gripping dataset (Texas death-row records) query by query in the browser. Teaches the mental model of query-writing, not just syntax — widely called the…",
        },
        {
            "topic": "SQL",
            "title": "Mode SQL Tutorial (Basic → Intermediate → Advanced)",
            "url": "https://mode.com/sql-tutorial/",
            "kind": "interactive",
            "time": "2-3 hours for Basic track; 8-10 hours complete",
            "why": "The most complete free SQL curriculum, written in plain English for analysts rather than engineers, with practice problems drawn from real analytics-team cases. Where SQLBolt gets you started, Mode's intermediate…",
        },
        {
            "topic": "LLM fundamentals",
            "title": "Large Language Models explained briefly (3Blue1Brown)",
            "url": "https://www.3blue1brown.com/lessons/mini-llm/",
            "kind": "video",
            "time": "8 min",
            "why": "Made with the Computer History Museum as the definitive 8-minute museum-grade answer to 'what is an LLM?'. The best possible first touch: after this, every other resource on this list makes more sense. Page includes…",
        },
        {
            "topic": "LLM fundamentals",
            "title": "[1hr Talk] Intro to Large Language Models (Andrej Karpathy)",
            "url": "https://www.youtube.com/watch?v=zjkBMFhNj_g",
            "kind": "video",
            "time": "1 hour",
            "why": "A founding member of OpenAI explains LLMs to a general audience in one sitting — training as 'compressing the internet', finetuning, tool use, jailbreaks, and the 'LLM as operating system' mental model. The single…",
        },
        {
            "topic": "LLM fundamentals",
            "title": "Deep Dive into LLMs like ChatGPT (Andrej Karpathy)",
            "url": "https://www.youtube.com/watch?v=7xTGNNLPyMI",
            "kind": "video",
            "time": "3.5 hours (chaptered — watch in segments)",
            "why": "The full story of how ChatGPT-class models are built — pretraining, supervised finetuning, RLHF — explicitly made for a general audience with no math. Its 'LLM psychology' section (why models hallucinate, why they…",
        },
        {
            "topic": "LLM fundamentals",
            "title": "How I use LLMs (Andrej Karpathy)",
            "url": "https://www.youtube.com/watch?v=EWvNQjAaOHw",
            "kind": "video",
            "time": "2 hours 11 min",
            "why": "The practical companion to Karpathy's theory talks: a live tour of ChatGPT, Claude, Gemini, Cursor and NotebookLM showing tool use, deep research, file uploads, and voice. For a recruiter it doubles as a map of the…",
        },
        {
            "topic": "LLM fundamentals",
            "title": "What Is ChatGPT Doing … and Why Does It Work? (Stephen Wolfram)",
            "url": "https://writings.stephenwolfram.com/2023/02/what-is-chatgpt-doing-and-why-does-it-work/",
            "kind": "article",
            "time": "2-3 hours",
            "why": "The essay that taught the world's executives how ChatGPT works in 2023 — 'it just adds one word at a time' — built up patiently with pictures and real GPT-2 examples. Long, but no prerequisite beyond curiosity; later…",
        },
        {
            "topic": "LLM fundamentals",
            "title": "Generative AI for Everyone (Andrew Ng, Coursera)",
            "url": "https://www.coursera.org/learn/generative-ai-for-everyone",
            "kind": "course",
            "time": "5-6 hours",
            "why": "Coursera's fastest-growing course of 2023, designed for people with no coding or AI background: what GenAI can/can't do, hands-on prompting exercises, and how it changes jobs and businesses. The 'lifecycle of a GenAI…",
        },
        {
            "topic": "How transformers work",
            "title": "But what is a GPT? Visual intro to transformers | Chapter 5 (3Blue1Brown)",
            "url": "https://www.youtube.com/watch?v=wjZofJX0v4M",
            "kind": "video",
            "time": "27 min",
            "why": "The moment 'transformer' stops being a buzzword: animated data flowing through embeddings, attention blocks and MLPs of an actual GPT. Nobody else visualizes what the T in GPT literally does at this level of beauty…",
        },
        {
            "topic": "How transformers work",
            "title": "Attention in transformers, step-by-step | Chapter 6 (3Blue1Brown)",
            "url": "https://www.youtube.com/watch?v=eMlx5fFNoYc",
            "kind": "video",
            "time": "26 min",
            "why": "'Attention' is the mechanism every GenAI candidate will name-drop, and this is the only explanation that makes it visually obvious — words 'looking at' other words to update their meaning. Watch after Chapter 5 and…",
        },
        {
            "topic": "How transformers work",
            "title": "The Illustrated Transformer (Jay Alammar)",
            "url": "https://jalammar.github.io/illustrated-transformer/",
            "kind": "paper-explainer",
            "time": "45-60 min",
            "why": "The canonical illustrated walkthrough of the 'Attention Is All You Need' paper — used as course material at Stanford, MIT, Harvard and CMU and translated into 10+ languages. Alammar's step-by-step diagrams are how…",
        },
        {
            "topic": "How transformers work",
            "title": "LLM Visualization (Brendan Bycroft)",
            "url": "https://bbycroft.net/llm",
            "kind": "interactive",
            "time": "30-45 min",
            "why": "A jaw-dropping 3D fly-through of a real GPT model running in your browser — you can zoom from the whole architecture down to individual multiplications, with a guided walkthrough. The fastest way to feel (not just…",
        },
        {
            "topic": "How transformers work",
            "title": "Generative AI exists because of the transformer (Financial Times visual story)",
            "url": "https://ig.ft.com/generative-ai/",
            "kind": "interactive",
            "time": "15 min",
            "why": "A scroll-driven newsroom masterpiece: as you scroll, an LLM predicts text before your eyes, with fact-checking help from the transformer paper's own authors. The most shareable 'explain it to my team' link on this…",
        },
        {
            "topic": "Embeddings",
            "title": "The Illustrated Word2vec (Jay Alammar)",
            "url": "https://jalammar.github.io/illustrated-word2vec/",
            "kind": "article",
            "time": "30 min",
            "why": "Starts from a personality quiz to explain how meaning becomes numbers — the gentlest on-ramp to embeddings ever written, and the famous 'king − man + woman = queen' finally clicks. Foundational for understanding…",
        },
        {
            "topic": "Embeddings",
            "title": "Embeddings: What they are and why they matter (Simon Willison)",
            "url": "https://simonwillison.net/2023/Oct/23/embeddings/",
            "kind": "article",
            "time": "30 min",
            "why": "A practitioner's talk-turned-essay that connects embeddings to things you can picture: 'related articles' features, semantic search, and clustering — with live demos. Perfect second step after Alammar: it answers 'so…",
        },
        {
            "topic": "RAG — retrieval-augmented generation",
            "title": "What is Retrieval-Augmented Generation (RAG)? (IBM Research, Marina Danilevsky)",
            "url": "https://www.youtube.com/watch?v=T-D1OfcDW1M",
            "kind": "video",
            "time": "6 min",
            "why": "A senior IBM research scientist explains RAG with one whiteboard anecdote (which planet has the most moons?) — retrieval, grounding, and citations in six minutes. The most-watched RAG explainer on YouTube for good…",
        },
        {
            "topic": "RAG — retrieval-augmented generation",
            "title": "What Is Retrieval-Augmented Generation, aka RAG? (NVIDIA Blog)",
            "url": "https://blogs.nvidia.com/blog/what-is-retrieval-augmented-generation/",
            "kind": "article",
            "time": "10 min",
            "why": "The definitive plain-English written reference on RAG, complete with the 'open-book vs. closed-book exam' analogy and the history of the term from the researchers who coined it. Great for converting the IBM video's…",
        },
        {
            "topic": "Fine-tuning vs prompting",
            "title": "RAG vs Fine-Tuning vs Prompt Engineering: Optimizing AI Models (IBM Technology)",
            "url": "https://www.youtube.com/watch?v=zYGDpG-pTho",
            "kind": "video",
            "time": "13 min",
            "why": "The three ways companies customize LLMs, compared honestly on cost, effort and freshness in 13 minutes. This exact trade-off is what half of all GenAI engineering interviews probe, so it's disproportionately valuable…",
        },
        {
            "topic": "Fine-tuning vs prompting",
            "title": "Finetuning Large Language Models (DeepLearning.AI short course, Sharon Zhou)",
            "url": "https://www.deeplearning.ai/short-courses/finetuning-large-language-models/",
            "kind": "course",
            "time": "1 hour",
            "why": "A one-hour guided lab showing when to fine-tune vs. prompt, how training data is prepared, and how results are evaluated — with runnable notebooks you can just watch. Turns 'fine-tuning' from a magic word into a…",
        },
        {
            "topic": "Evaluating AI quality (evals)",
            "title": "Your AI Product Needs Evals (Hamel Husain)",
            "url": "https://hamel.dev/blog/posts/evals/",
            "kind": "article",
            "time": "45-60 min",
            "why": "THE essay that made 'evals' a discipline — written by the consultant top AI teams hire, built around a real case study (Rechat) with unit tests, human review, and LLM-as-judge. If a candidate mentions evals, this is…",
        },
        {
            "topic": "Evaluating AI quality (evals)",
            "title": "Beyond vibe checks: A PM's complete guide to evals (Aman Khan, Lenny's Newsletter)",
            "url": "https://www.lennysnewsletter.com/p/beyond-vibe-checks-a-pms-complete",
            "kind": "article",
            "time": "25 min",
            "why": "The non-engineer's version of evals, by the Arize AI product director who co-created an evals course with Andrew Ng: what evals are, why 'vibe checks' fail, and how PMs run them — in product language, not code. Ideal…",
        },
        {
            "topic": "AI agents",
            "title": "Building Effective Agents (Anthropic Engineering)",
            "url": "https://www.anthropic.com/engineering/building-effective-agents",
            "kind": "article",
            "time": "20 min",
            "why": "The most-cited taxonomy in the agents field: Anthropic's crisp distinction between 'workflows' and true 'agents', plus five named design patterns (routing, orchestrator-worker, evaluator-optimizer...) that candidates…",
        },
        {
            "topic": "AI agents",
            "title": "Agents (Chip Huyen)",
            "url": "https://huyenchip.com/2025/01/07/agents.html",
            "kind": "article",
            "time": "40 min",
            "why": "An 8,000-word chapter from her O'Reilly book 'AI Engineering', free on her blog: agents = model + tools + planning, with an unusually honest section on failure modes. The best single deep-read for understanding what…",
        },
        {
            "topic": "AI agents",
            "title": "Claude Cookbooks (Anthropic, official GitHub)",
            "url": "https://github.com/anthropics/claude-cookbooks",
            "kind": "interactive",
            "time": "1-2 hours browsing",
            "why": "Anthropic's official recipe collection — tool use, agent patterns, RAG, and evaluation as runnable notebooks. Even without running code, skimming the folder names and READMEs shows a recruiter exactly what day-to-day…",
        },
        {
            "topic": "Prompt engineering",
            "title": "Prompt engineering overview (Anthropic Claude Docs)",
            "url": "https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview",
            "kind": "article",
            "time": "30-45 min for the section",
            "why": "The industry-reference prompt engineering guide, straight from the lab that builds Claude: clarity, examples, role prompting, chain-of-thought and prompt chaining, ordered from most to least effective. Reading the…",
        },
        {
            "topic": "Prompt engineering",
            "title": "Anthropic's Interactive Prompt Engineering Tutorial (GitHub)",
            "url": "https://github.com/anthropics/prompt-eng-interactive-tutorial",
            "kind": "interactive",
            "time": "3-4 hours",
            "why": "A 9-chapter hands-on course where you fix broken prompts exercise by exercise — the same material Anthropic uses to train customers. Learning-by-doing makes prompting knowledge stick in a way reading never does.",
        },
        {
            "topic": "Prompt engineering",
            "title": "ChatGPT Prompt Engineering for Developers (DeepLearning.AI, Isa Fulford & Andrew Ng)",
            "url": "https://www.deeplearning.ai/short-courses/chatgpt-prompt-engineering-for-developers/",
            "kind": "course",
            "time": "1.5 hours",
            "why": "The original viral prompt-engineering course, co-taught by OpenAI and Andrew Ng. Despite 'for Developers' in the name, the two core prompting principles and the summarize/infer/transform framework are perfectly…",
        },
        {
            "topic": "Prompt engineering",
            "title": "Prompt Engineering Guide (DAIR.AI, promptingguide.ai)",
            "url": "https://www.promptingguide.ai/",
            "kind": "article",
            "time": "2-3 hours for core sections; great as a reference",
            "why": "The Wikipedia of prompting — 3M+ learners, 13 languages, open source. It's the one place where every named technique a candidate might mention (zero-shot, few-shot, chain-of-thought, ReAct) has a clear, current,…",
        },
        {
            "topic": "Prompt engineering",
            "title": "OpenAI Cookbook",
            "url": "https://developers.openai.com/cookbook",
            "kind": "interactive",
            "time": "1-2 hours browsing",
            "why": "OpenAI's official example library — embeddings, fine-tuning, agents, and model-specific prompting guides (GPT-4.1, GPT-5) as browsable articles and notebooks. Alongside Anthropic's cookbooks, it defines what…",
        },
        {
            "topic": "AI product metrics",
            "title": "What We've Learned From A Year of Building with LLMs (Applied LLMs)",
            "url": "https://applied-llms.org/",
            "kind": "article",
            "time": "1.5-2 hours",
            "why": "Six of the field's best-known practitioners (Eugene Yan, Hamel Husain, Shreya Shankar et al.) distilled a year of shipping LLM products into tactical, operational and strategic lessons — originally an O'Reilly…",
        },
        {
            "topic": "AI product metrics",
            "title": "The AI Product Success Metrics Interview: Your Complete Guide (Aakash Gupta, Product Growth)",
            "url": "https://www.news.aakashg.com/p/ai-success-metrics-interview",
            "kind": "article",
            "time": "20-25 min",
            "why": "Written for exactly the hiring context: how AI product metrics questions are asked and answered in interviews — task completion, output acceptance, retention vs. novelty — from a 236K-subscriber PM newsletter. Lets a…",
        },
        {
            "topic": "Safety & guardrails",
            "title": "OWASP Top 10 for LLM Applications",
            "url": "https://owasp.org/www-project-top-10-for-large-language-model-applications/",
            "kind": "article",
            "time": "45-60 min",
            "why": "THE industry-standard list of ways LLM apps get attacked or go wrong (prompt injection first among them) — when a candidate mentions it unprompted, that's a green flag in itself.",
        },
        {
            "topic": "Safety & guardrails",
            "title": "Prompt injection series",
            "url": "https://simonwillison.net/series/prompt-injection/",
            "kind": "article",
            "time": "1-2 hours (read the first 3 posts)",
            "why": "Simon Willison coined the term; this running series is the clearest plain-english explanation of why LLMs can be tricked by the text they read, and why the problem is still unsolved.",
        },
    ],
}


def recruiter_guide() -> dict:
    """The browser-safe field guide (it IS the knowledge base — nothing hidden)."""
    return GUIDE


def recruiter_system_prompt() -> str:
    """System prompt for the recruiter copilot: persona + the full researched
    knowledge base as grounding context. Serialized once at import — GUIDE is
    immutable, and byte-identical output is what makes the prompt-cache
    "stable prefix" guarantee structural instead of incidental."""
    return _SYSTEM_PROMPT


def _build_system_prompt() -> str:
    kb = json.dumps(GUIDE, ensure_ascii=False)
    return (
        "You are an interview-design copilot for RECRUITERS hiring for AI, GenAI, "
        "and Data-Science roles. The person you're helping is smart but "
        "non-technical, and they must screen and evaluate candidates on topics "
        "they don't know. Your job, in conversation:\n"
        "1. UNDERSTAND THE ROLE. Ask what the job is about — team, product, what "
        "the hire will actually do, seniority — a couple of focused questions at "
        "a time, not a form to fill. Read between the lines of vague answers.\n"
        "2. MAP IT TO TODAY'S MARKET. Tell them what this kind of role is "
        "actually being tested on in today's interviews (use the knowledge base "
        "below): which question archetypes apply, with concrete example "
        "questions they could ask, and what strong vs weak answers sound like.\n"
        "3. TEACH THE CONCEPTS. When a concept comes up, explain it like the "
        "recruiter has NEVER heard of it — plain words, one concrete analogy, "
        "no jargon left undefined. Point to the best learning resource from the "
        "knowledge base when they want depth.\n"
        "4. MAKE THEM A CREDIBLE EVALUATOR. Give them probe questions that "
        "expose depth without requiring expertise ('what would break this?', "
        "'what did you try first that failed?'), and tell them what signals to "
        "listen for in the answers.\n\n"
        "Style: warm, concrete, zero condescension. Prefer short paragraphs and "
        "tight bullet lists. When you give example questions, give the "
        "listen-for alongside each one. Never invent sources — only recommend "
        "links present in the knowledge base. If asked about a role family the "
        "knowledge base doesn't cover yet, say so plainly and help from first "
        "principles.\n\n"
        "KNOWLEDGE BASE (researched, current):\n" + kb
    )


_SYSTEM_PROMPT = _build_system_prompt()
