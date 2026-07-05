"""Web app: always-on mic, live transcript + delivery meters, simultaneous text.

Standard FastAPI backend + a static browser frontend, reusing the same
interviewer / grader / skill-graph as the CLI. Keys stay server-side. Designed to
deploy unchanged behind HTTPS when you move online (see README > Going online).
"""
