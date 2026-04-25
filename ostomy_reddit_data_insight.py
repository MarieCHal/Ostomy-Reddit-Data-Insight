"""
Raccourci « tout en un » : extraction Reddit + analyse (identique à l’ancien script unique).

Pour séparer les étapes, préférer :
  - reddit_extract.py   (réseau → .jsonl)
  - ostomy_analyze.py  (.jsonl → Excel, sans réseau)
"""

from ostomy_common import run

if __name__ == "__main__":
    run()
