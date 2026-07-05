"""Launch the local web app:  python run_web.py

Then open http://127.0.0.1:8000 in Chrome. (localhost is a secure context, so the
browser mic works over plain http locally — no HTTPS needed for local dev.)
"""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "pmcaseprep.web.app:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        reload=bool(os.environ.get("PMCP_RELOAD")),
    )
