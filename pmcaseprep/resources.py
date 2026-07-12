"""Curated "learn more" resources, attached to weak spots on the scorecard.

Every link is a canonical, widely-cited, free resource, corroborated against
current search results (title + author + liveness). Two kinds of keys:
  * the six rubric dimension keys — shown on a dimension card when the score
    says there's room (<=2: up to two links; ==3: one link; 4: none), and
  * concept tags (a case lists its own under `resource_tags`) — shown in a
    "go deeper on this case" section regardless of score.

Keep this list SHORT and gold-standard. One great link beats five decent ones.
"""

from __future__ import annotations

from .models import Case, ScoreCard


def _r(title: str, author: str, url: str, why: str, type_: str = "article") -> dict[str, str]:
    return {"title": title, "author": author, "url": url, "why": why, "type": type_}


# key -> ordered list of resources, best first.
RESOURCES: dict[str, list[dict[str, str]]] = {
    # --- rubric dimensions ---------------------------------------------------
    "structure": [
        _r(
            "Issue Trees: The Definitive Guide",
            "Crafting Cases (ex-MBB)",
            "https://www.craftingcases.com/issue-tree-guide/",
            "How to break an ambiguous problem into a MECE tree, with worked examples.",
        ),
        _r(
            "Issue Trees — What Are They and How Do You Use Them?",
            "Paul Millerd, StrategyU",
            "https://strategyu.co/issue-tree/",
            "Ex-McKinsey primer on hypothesis-driven problem decomposition.",
        ),
    ],
    "user_empathy": [
        _r(
            "The Jobs to Be Done Framework & Real-World Examples",
            "Harvard Business School Online",
            "https://online.hbs.edu/blog/post/jobs-to-be-done-examples",
            "Understand what users hire your product for — before proposing solutions.",
        ),
        _r(
            "Understanding the Job (the milkshake talk)",
            "Clayton Christensen",
            "https://www.youtube.com/watch?v=sfGtw2C95Ms",
            "The canonical 5-minute JTBD story, told by Christensen himself.",
            "video",
        ),
    ],
    "prioritization": [
        _r(
            "RICE: Simple prioritization for product managers",
            "Sean McBride, Intercom",
            "https://www.intercom.com/blog/rice-simple-prioritization-for-product-managers/",
            "The original RICE post — score Reach × Impact × Confidence / Effort out loud.",
        ),
        _r(
            "RICE Scoring Model",
            "ProductPlan",
            "https://www.productplan.com/glossary/rice-scoring-model/",
            "A concrete walkthrough of RICE with usable scoring scales.",
        ),
    ],
    "creativity": [
        _r(
            "Product Sense Interview Prep",
            "Exponent",
            "https://www.tryexponent.com/blog/product-sense-interview",
            "Generating differentiated ideas: cross-domain analogies, underserved segments, moonshots.",
        ),
        _r(
            "How to Prepare for the Product Sense Interview",
            "Product School",
            "https://productschool.com/blog/job-search/product-sense-interview",
            "Structured ideation — multiple solutions with explicit trade-offs.",
        ),
    ],
    "communication": [
        _r(
            "Pyramid Principle: Communicate Top-Down",
            "Paul Millerd, StrategyU",
            "https://strategyu.co/pyramid-principle-part-2-communicate-top-down/",
            "Answer first, then supporting structure — the single biggest verbal upgrade.",
        ),
        _r(
            "Minto Pyramid & SCQA",
            "ModelThinkers",
            "https://modelthinkers.com/mental-model/minto-pyramid-scqa",
            "Compact explainer of both Pyramid Principle and SCQA framing.",
        ),
    ],
    "data_business": [
        _r(
            "Every Product Needs a North Star Metric",
            "John Cutler, Amplitude",
            "https://amplitude.com/blog/product-north-star-metric",
            "Choosing a success metric tied to customer value and the business.",
        ),
        _r(
            "The North Star Playbook: About the Framework",
            "Amplitude",
            "https://amplitude.com/books/north-star/about-north-star-framework",
            "The free full playbook — north star plus its input metrics.",
        ),
    ],
    # --- case concept tags ---------------------------------------------------
    "metric_debugging": [
        _r(
            "The definitive guide to mastering analytical thinking interviews",
            "Ben Erez, Lenny's Newsletter",
            "https://www.lennysnewsletter.com/p/the-definitive-guide-to-mastering-f81",
            "Diagnosing a metric change step by step: segment, check launches, then external causes.",
        ),
        _r(
            "How to crack product metrics questions in PM interviews",
            "IGotAnOffer",
            "https://igotanoffer.com/blogs/product-manager/product-metric-interview-questions",
            "A structured playbook for root-causing metric changes.",
        ),
    ],
    "ab_testing": [
        _r(
            "What are A/B tests: A guide for product managers",
            "GoPractice",
            "https://gopractice.io/product/ab-tests-guide-for-product-managers/",
            "Experiment arms, rollout, and reading results without fooling yourself.",
        ),
        _r(
            "How Not To Run an A/B Test",
            "Evan Miller",
            "https://www.evanmiller.org/how-not-to-run-an-ab-test.html",
            "Why peeking at significance mid-test burns you, and what to do instead.",
        ),
    ],
    "ai_evals": [
        _r(
            "Your AI Product Needs Evals",
            "Hamel Husain",
            "https://hamel.dev/blog/posts/evals/",
            "The most-cited practitioner guide to LLM eval systems and regression testing.",
        ),
        _r(
            "Beyond vibe checks: A PM's complete guide to evals",
            "Aman Khan, Lenny's Newsletter",
            "https://www.lennysnewsletter.com/p/beyond-vibe-checks-a-pms-complete",
            "PM-oriented framing: evals as regression tests across model versions.",
        ),
    ],
    "growth_loops": [
        _r(
            "Growth Loops are the New Funnels",
            "Brian Balfour, Reforge",
            "https://www.reforge.com/blog/growth-loops",
            "Why compounding loops beat linear funnels — the mental model growth cases reward.",
        ),
    ],
    "north_star": [
        _r(
            "Every Product Needs a North Star Metric",
            "John Cutler, Amplitude",
            "https://amplitude.com/blog/product-north-star-metric",
            "Choosing one metric tied to customer value, plus the input-metric tree under it.",
        ),
    ],
    "api_design": [
        _r(
            "API Design Guide",
            "Google Cloud",
            "https://cloud.google.com/apis/design",
            "The canonical public guide to resource-oriented API design and its tradeoffs.",
        ),
    ],
    "sql_metrics": [
        _r(
            "Mode SQL Tutorial",
            "Mode Analytics",
            "https://mode.com/sql-tutorial/",
            "Hands-on SQL from zero through analytical joins — the standard free tutorial.",
        ),
    ],
}


def resources_for(card: ScoreCard, case: Case) -> dict:
    """Pick the links this candidate should actually see.

    Returns {"dimensions": {dim_key: [resource, ...]}, "case": [resource, ...]}.
    """
    by_dim: dict[str, list[dict[str, str]]] = {}
    for ds in card.dimension_scores:
        pool = RESOURCES.get(ds.dimension, [])
        if not pool:
            continue
        if ds.score <= 2:
            by_dim[ds.dimension] = pool[:2]
        elif ds.score == 3:
            by_dim[ds.dimension] = pool[:1]
    case_links = [r for tag in case.resource_tags for r in RESOURCES.get(tag, [])[:1]]
    return {"dimensions": by_dim, "case": case_links}
