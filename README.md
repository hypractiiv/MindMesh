# MindMesh
MindMesh is an adaptive CLI spaced-repetition tool that pairs local memory decay math with answer evaluation. Built with Python and SQLite, it manages learning sessions through a 6-state FSM, ensuring seamless session recovery and deterministic schedule calculations.

## Quick start

```bash
python /home/runner/work/MindMesh/MindMesh/main.py --db /tmp/mindmesh.db start
python /home/runner/work/MindMesh/MindMesh/main.py --db /tmp/mindmesh.db answer <session_id> --text "The base case is when list is empty, return 1." --self-rating 4
python /home/runner/work/MindMesh/MindMesh/main.py --db /tmp/mindmesh.db answer <session_id> --text "It should return 0." 
python /home/runner/work/MindMesh/MindMesh/main.py --db /tmp/mindmesh.db history <session_id>
```
