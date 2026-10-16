"""Print the fleet share: live-and-passing workflows out of 20 (15 ward scenarios + 5 sibling repos).
Input: a JSON file {workflow_id: {"status": "PASS"|..., "replay": bool}}. REPLAY results do not count."""
import json, sys
TOTAL = 20


def share(results):
    n = sum(1 for r in results.values() if r.get("status") == "PASS" and not r.get("replay"))
    return min(n, TOTAL), TOTAL


if __name__ == "__main__":
    n, t = share(json.load(open(sys.argv[1])))
    print(f"{n}/{t} = {100 * n // t}%")
