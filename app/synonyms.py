"""Domain vocabulary bridging: the words staff type vs. the words regulators write.

This is the single highest-value piece of domain knowledge in the system and
the part a model cannot invent — every entry below comes from how compliance
staff actually phrase a question. Extend it from real query logs, not guesses.
"""

from __future__ import annotations

# Maps a colloquial term to the regulatory terms it should also match.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "fake": ("falsified", "counterfeit"),
    "counterfeit": ("falsified",),
    "fridge": ("temperature", "storage", "cold"),
    "freezer": ("temperature", "storage", "cold"),
    "paperwork": ("documentation", "document", "record"),
    "paper": ("documentation", "record"),
    "sop": ("procedure", "written"),
    "checked": ("validated", "validation", "verified"),
    "check": ("validate", "validation"),
    "rerun": ("retest", "result", "deletion"),
    "reinject": ("result", "deletion", "integration"),
    "spreadsheet": ("electronic", "record", "computerised"),
    "excel": ("electronic", "record", "computerised"),
    "signoff": ("approval", "approved", "authorised"),
    "sign": ("approval", "approved", "authorised", "signature"),
    "pressured": ("pressure", "conflict", "integrity"),
    "pressure": ("conflict", "integrity"),
    "changed": ("change", "modify", "modification", "amended"),
    "change": ("modify", "modification"),
    "delete": ("deletion", "obscure", "audit"),
    "deleted": ("deletion", "obscure", "audit"),
    "log": ("audit", "trail", "record"),
    "logs": ("audit", "trail", "record"),
    "unexplained": ("discrepancy", "investigation"),
    "counterfeits": ("falsified",),
    "recall": ("distribution", "withdrawal"),
    "supplier": ("supplier", "distributor", "qualify"),
    "shipping": ("transport", "distribution"),
    "shipment": ("transport", "distribution"),
    "trial": ("clinical", "participant"),
    "method": ("method", "testing", "specification"),
}


def expand(terms: list[str]) -> dict[str, float]:
    """Return term -> weight, originals at full weight and expansions reduced.

    Expansions are deliberately weak. A synonym that outranks a literal match
    turns a precise citation lookup into a fuzzy one, which is the wrong trade
    in a regulated search tool.
    """
    weights: dict[str, float] = {}
    for term in terms:
        weights[term] = max(weights.get(term, 0.0), 1.0)
    for term in terms:
        for synonym in SYNONYMS.get(term, ()):
            if synonym not in terms:
                weights[synonym] = max(weights.get(synonym, 0.0), 0.45)
    return weights
