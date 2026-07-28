"""Plain-English glossary for the PM Field Guide's "explain this" popover.

The guide is the one surface with no login and no model spend, and its readers
are the people least likely to have an account — someone who doesn't yet know
what a PM is shouldn't hit a sign-in wall to look up "funnel". So the terms the
guide itself uses are answered from this curated list: instant, free, and
available logged-out. The model is only a fallback for words that aren't here.

Rules for entries:
  * Explain it the way you'd explain it to a friend who has never worked in
    tech. No PM jargon inside a PM jargon definition.
  * Two or three sentences. The first one must stand alone.
  * `example` grounds it in something concrete and everyday.

Keys are normalized (see `normalize`): lowercased, punctuation stripped,
plurals and -ing forms folded, so "Funnels", "funnel," and "FUNNEL" all hit
the same entry. `ALIASES` maps the other ways people write a term.
"""

from __future__ import annotations

import re

# term -> {"term": display name, "plain": explanation, "example": concrete case}
GLOSSARY: dict[str, dict[str, str]] = {}


def _g(term: str, plain: str, example: str, *aliases: str) -> None:
    entry = {"term": term, "plain": plain, "example": example}
    GLOSSARY[normalize(term)] = entry
    for a in aliases:
        GLOSSARY[normalize(a)] = entry


_PUNCT = re.compile(r"[^a-z0-9\s/&-]+")
_SPACE = re.compile(r"\s+")


def normalize(term: str) -> str:
    """Fold the ways people type the same word into one key.

    Selection-based lookup means we get whatever the user's cursor grabbed:
    trailing commas, capitals, a plural, a gerund. Folding here is far cheaper
    than storing every variant."""
    t = _PUNCT.sub(" ", str(term or "").lower()).strip()
    t = _SPACE.sub(" ", t)
    words = []
    for w in t.split(" "):
        if len(w) > 4 and w.endswith("ing"):
            w = w[:-3]  # segmenting -> segment
        elif len(w) > 3 and w.endswith("es") and not w.endswith("ses"):
            w = w[:-2]
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]  # funnels -> funnel
        words.append(w)
    return " ".join(words).strip()


# --- The guide's own vocabulary ------------------------------------------------

_g(
    "funnel",
    "The set of steps someone walks through to finish something, from start to "
    "done. It's called a funnel because fewer people are left at each step — "
    "some drop out along the way.",
    "Visit the shop → add to cart → enter your address → pay. If 100 people "
    "start and 30 finish, the other 70 leaked out somewhere in between.",
    "funnels", "funnel breakdown",
)
_g(
    "cart abandonment",
    "When someone puts things in their online basket and then leaves without "
    "buying. It's one of the most-watched numbers in online shopping.",
    "You add trainers to your basket, see the delivery cost, and close the tab. "
    "That's an abandoned cart.",
    "abandonment", "abandon", "abandoned cart", "cart abandonment rate",
)
_g(
    "checkout",
    "The last part of buying something online — where you confirm what you're "
    "getting, enter your address and card, and pay.",
    "The three or four screens between 'buy now' and 'thanks for your order'.",
)
_g(
    "conversion",
    "The share of people who do the thing you were hoping for. Anything can be "
    "the hoped-for thing: buying, signing up, finishing a form.",
    "If 100 people visit and 3 buy, that's 3% conversion.",
    "convert", "conversion rate", "converting",
)
_g(
    "a/b test",
    "Showing one version to half your users and a different version to the "
    "other half, at the same time, to see which does better. It's how teams "
    "find out whether a change actually helped instead of guessing.",
    "Half of visitors see a green button, half see a blue one. Blue gets more "
    "clicks, so blue wins.",
    "ab test", "a b test", "split test", "experiment",
)
_g(
    "segment",
    "Splitting your users into groups and looking at each group on its own, "
    "instead of lumping everyone into one average.",
    "Overall sales looked flat — but split by phone and computer, phone was up "
    "a lot and computer was down. The average hid both.",
    "segmentation", "segmenting", "segments",
)
_g(
    "retention",
    "Whether people come back after their first visit. High retention means "
    "they keep returning; low means they try it once and disappear.",
    "Of everyone who signed up in January, how many were still using it in "
    "March?",
    "retain", "retained",
)
_g(
    "activation",
    "The moment a new user first gets real value out of a product — the point "
    "where it 'clicks' and stops feeling like setup.",
    "On a photo app, activation might be uploading your first picture, not "
    "just creating the account.",
    "activate", "activated",
)
_g(
    "onboarding",
    "Everything a brand-new user goes through before they're properly up and "
    "running: sign-up, setup, the first walkthrough.",
    "The screens between downloading an app and actually using it.",
    "onboard",
)
_g(
    "churn",
    "People leaving — cancelling, deleting the app, or simply never coming "
    "back. The opposite of retention.",
    "If 100 people subscribe and 5 cancel that month, monthly churn is 5%.",
    "churned", "churning",
)
_g(
    "margin",
    "What's left of the money after you pay the costs of delivering the thing. "
    "Selling more doesn't help if the margin is tiny or negative.",
    "Sell a mug for £10 that costs £7 to make and ship, and your margin is £3.",
    "margins",
)
_g(
    "sprint",
    "A short fixed stretch of work a software team commits to — usually one or "
    "two weeks — ending with something finished.",
    "'We'll get it out next sprint' usually means in the next week or two.",
    "sprints",
)
_g(
    "ship",
    "To release something to real users. In software, 'shipping' is the moment "
    "it stops being internal and people can actually use it.",
    "'We shipped dark mode on Tuesday' — it's live, not just built.",
    "shipped", "shipping", "ship it",
)
_g(
    "feature flag",
    "A switch in the code that turns part of a product on or off for some or "
    "all users — without rebuilding and re-releasing anything.",
    "You launch on schedule but leave the one buggy screen switched off until "
    "it's fixed next week.",
    "flag", "feature flags", "behind a flag",
)
_g(
    "qa",
    "Quality assurance — the people and the process that deliberately try to "
    "break new software before real users see it.",
    "QA finds that the receipt shows the wrong name in one rare case, the night "
    "before launch.",
    "quality assurance",
)
_g(
    "hotfix",
    "A small urgent repair pushed out on its own, straight away, rather than "
    "waiting for the next planned release.",
    "The app crashes on opening, so the team ships a one-line hotfix the same "
    "afternoon.",
    "hot fix",
)
_g(
    "roadmap",
    "The rough plan of what a team intends to build over the coming months, and "
    "roughly in what order. It's a statement of intent, not a promise.",
    "'Search improvements are on the roadmap for next quarter.'",
)
_g(
    "spec",
    "A short written document describing what's being built and why, clearly "
    "enough that engineers and designers can act on it without the author in "
    "the room.",
    "Two pages that turn 'we should improve search' into something buildable.",
    "specification", "specs", "mini spec",
)
_g(
    "stakeholder",
    "Anyone with a stake in what you decide — the people affected by it or who "
    "can block it. Often sales, support, legal, or leadership.",
    "Sales wants their biggest customer's request built first; they're a "
    "stakeholder in that call.",
    "stakeholders",
)
_g(
    "prioritization",
    "Deciding what to do first when you can't do everything — and being able to "
    "explain why the top thing is the top thing.",
    "Two good ideas, one team, three months. Prioritizing is choosing which one "
    "actually gets built.",
    "prioritize", "prioritizing", "prioritise",
)
_g(
    "teardown",
    "A short written critique of a product: what works, what doesn't, and what "
    "you'd change. A common way to show PM thinking before you have the job.",
    "One page on why a food-delivery app's checkout loses people, and what "
    "you'd fix first.",
    "product teardown", "teardowns",
)
_g(
    "moat",
    "Whatever makes a product hard for competitors to copy — and so protects it "
    "over time.",
    "Years of listening history make a music app's recommendations hard for a "
    "newcomer to match.",
    "moats",
)
_g(
    "marketplace",
    "A product whose job is matching two sides — people who want something and "
    "people who supply it — rather than making the thing itself.",
    "A ride app owns no cars: it matches riders with drivers.",
    "marketplaces", "two sided marketplace",
)
_g(
    "power user",
    "Someone who uses a product far more deeply than most people — and is "
    "usually the loudest about it. Easy to mistake for the typical user.",
    "The 1% who use every keyboard shortcut and post about missing features.",
    "power users",
)
_g(
    "dau",
    "Daily active users — how many distinct people used the product on a given "
    "day. A quick pulse on whether a product is growing or shrinking.",
    "'DAU dropped 10% overnight' means far fewer people showed up yesterday.",
    "daily active users", "mau", "monthly active users",
)
_g(
    "eval",
    "A repeatable test of how good an AI system's answers are — a marking "
    "scheme for a model, run every time it changes.",
    "Before shipping a new version, you run 500 saved questions through it and "
    "check the answers didn't get worse.",
    "evals", "evaluation",
)
_g(
    "default",
    "What happens if the user does nothing. Defaults are powerful because most "
    "people never change them.",
    "The next episode playing automatically unless you stop it.",
    "defaults",
)
_g(
    "metric",
    "A number a team watches to tell whether things are getting better or "
    "worse.",
    "Sign-ups per week, or the share of people who finish checkout.",
    "metrics",
)
_g(
    "user research",
    "Learning how people actually behave by talking to them and watching them "
    "use the thing — rather than guessing from a meeting room.",
    "Watching five people try a new signup flow and noting where each gets "
    "stuck.",
    "user interview", "user interviews", "research",
)
_g(
    "star",
    "A way to structure an interview answer about your past work: Situation, "
    "Task, Action, Result. It stops a story from wandering.",
    "'Sales were dropping (situation), I owned the fix (task), I did X "
    "(action), it recovered 12% (result).'",
    "star method", "situation task action result",
)
_g(
    "product sense",
    "Judgment about what's worth building and why — the ability to pick a real "
    "user problem and a sensible solution for it.",
    "An interviewer asks how you'd improve a maps app for tourists; they're "
    "testing product sense.",
)
_g(
    "mece",
    "A checklist for breaking a problem into parts: the parts shouldn't overlap, "
    "and together they should cover everything. It stops you double-counting or "
    "missing a whole cause.",
    "Splitting 'why did sales fall?' into new customers vs returning customers "
    "— nobody is in both, and nobody is left out.",
)
_g(
    "north star metric",
    "The single number a team agrees matters most, used to settle arguments "
    "about what to work on.",
    "For a music app it might be hours listened, not app downloads.",
    "north star",
)
_g(
    "mvp",
    "The smallest version of an idea you can put in front of real users and "
    "still learn whether it works.",
    "Instead of building the whole app, you ship one screen to see if anyone "
    "uses it.",
    "minimum viable product",
)


# Everyday English that needs no explaining. Selection-based lookup means a
# stray double-click lands on words like "changes" or "everyone"; on an open,
# login-free endpoint each of those would otherwise be a real model call spent
# on nothing. Checked AFTER the glossary, so terms that are also common words
# ("ship", "default", "margin", "spec") are answered rather than skipped.
#
# Stored NORMALIZED, because that's what the endpoint compares against: the
# normalizer folds plurals and -ing forms ("changes" -> "chang"), so a raw
# word list would silently miss exactly the variants a text selection yields.
STOPWORDS = frozenset(
    normalize(w)
    for w in """
a about after all also an and any are as at back be because been before being
but by can could day did do does down each even every everyone first for from
get give go good has have he her here him his how i if in into is it its just
know like little long look made make man many me more most much must my never
new no not now of on one only or other our out over own people put said same
say see she should since so some still such take than that the their them then
there these they thing think this those through time to too two under up us
use very want was way we well were what when where which while who why will
with work would year you your change changes changed everything something
anything nothing another between during without within around always
""".split()
)


def lookup(term: str) -> dict[str, str] | None:
    """Exact (normalized) match only.

    A fuzzy match here would be worse than no match: the model fallback gives a
    real answer for anything we don't know, so guessing wrong would replace a
    correct explanation with a confidently wrong one."""
    return GLOSSARY.get(normalize(term))


def terms() -> list[str]:
    """Distinct display names, for the guide's own glossary listing."""
    seen: dict[str, None] = {}
    for entry in GLOSSARY.values():
        seen.setdefault(entry["term"], None)
    return sorted(seen)
