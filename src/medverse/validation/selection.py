"""Selection validation: coverage, ownership, duplicate prevention, requested-anatomy checklist."""
from __future__ import annotations

import collections

from medverse.validation import Checks

CHECKLIST = [   # (label, category, subcategory, expected, profile toggle)
    ("cervical vertebrae", "vertebra", "cervical", 7, "anatomy.spine.include_vertebrae"),
    ("thoracic vertebrae", "vertebra", "thoracic", 12, "anatomy.spine.include_vertebrae"),
    ("lumbar vertebrae", "vertebra", "lumbar", 5, "anatomy.spine.include_vertebrae"),
    ("sacrum", "vertebra", "sacral", 1, "anatomy.spine.include_vertebrae"),
    ("intervertebral discs", "intervertebral_disc", None, 23, "anatomy.spine.include_intervertebral_discs"),
    ("spinal cord", "spinal_cord", None, 1, "anatomy.spine.include_spinal_cord"),
    ("cerebellum", "cerebellum", None, 1, None),
    ("pons", "brainstem", "pons", 1, None),
    ("midbrain", "brainstem", "midbrain", 1, None),
    ("medulla oblongata", "brainstem", "medulla_oblongata", 1, None),
]


def validate_selection(decisions, cfg, entity_count: int) -> dict:
    from medverse.config import dotted
    c = Checks()
    c.check("every_entity_has_decision", len(decisions) == entity_count,
            f"{entity_count} entities but {len(decisions)} decisions")
    c.check("no_undecided", all(d.decision in ("included", "excluded", "reference", "review") for d in decisions))
    # ownership / duplicate prevention
    inc = [d for d in decisions if d.decision == "included"]
    by_cat = collections.defaultdict(set)
    for d in inc:
        by_cat[(d.semantic_category, d.matched_target)].add(d.source)
    multi = {k: sorted(v) for k, v in by_cat.items() if len(v) > 1 and k[0]}
    c.check("single_owner_per_category", not multi, f"categories included from several sources: {multi}")
    ident = collections.defaultdict(list)
    for d in inc:
        if d.semantic_category:
            ident[(d.semantic_category, d.semantic_subcategory, d.side, d.label)].append(d.entity_id)
    dups = {k: v for k, v in ident.items() if len({e.split(":")[0] for e in v}) > 1}
    c.check("no_semantic_duplicates_across_sources", not dups, f"same anatomy from two sources: {list(dups.items())[:5]}")
    # unknown / review are never inclusions
    c.check("unknown_never_included", not any(d.decision == "included" and d.rule == "unknown_policy_review"
                                              for d in decisions))
    rev = [d for d in decisions if d.decision == "review"]
    c.check("review_queue", not rev, f"{len(rev)} structures need review (see selection_review.csv)", level="warn",
            detail_ok="empty")
    cnt = collections.Counter((d.semantic_category, d.semantic_subcategory) for d in inc)
    catc = collections.Counter(d.semantic_category for d in inc)
    for label, cat, sub, exp, toggle in CHECKLIST:
        if toggle and not dotted(cfg, toggle, True):
            continue
        got = cnt[(cat, sub)] if sub else catc[cat]
        c.check(f"anatomy:{label}", got >= exp, f"{got}/{exp}", level="warn", detail_ok=f"{got}/{exp}")
    r = c.result()
    r["review"] = [d.entity_id for d in rev]
    return r
