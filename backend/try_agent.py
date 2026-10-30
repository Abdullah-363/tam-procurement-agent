"""
Quick real-API smoke test (uses a few cents of credit at most).
Run from the backend folder:   python try_agent.py
"""
from app import agent, store

store.reset()
msg = ("I need 10 developer laptops for the new software team joining next month, urgent. "
       "Preferred vendor Zawaya.")
print("You:", msg, "\n")
out = agent.run("requester", msg, session_id="smoke")
for t in out["trace"]:
    if t["type"] == "tool":
        print(f"  [{t['tool']}] {'ok' if t['ok'] else 'ERROR'}")
    elif t["type"] == "thought":
        print("  (agent)", t["text"][:160])
print("\nTam:", out["reply"])
print("\nTokens:", out["usage"], "| model:", out["model"])
