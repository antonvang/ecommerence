"""P2 research: point-in-time replay of the observation journal.

Read-only on the journal. Fills come only from journaled Jupiter quotes; a
missing quote is a missing trade, never an invented price. Every evaluation
writes one new file and none is ever rewritten. No profit claim follows from
a replay on data a strategy was developed on.
"""
