"""Unit coverage for app/services/knowledge_relation.py's deterministic fast
path -- the cheap, free CONFIRMS shortcut that never spends an LLM call. The
LLM-backed CONTRADICTS/UNCERTAIN paths are covered in
tests/routes/test_category_knowledge_contradiction.py instead, where the
provider is monkeypatched against the real moderation flow.
"""

from app.services import knowledge_relation


def test_confirms_on_affirmative_opener():
    result = knowledge_relation.classify_relation(
        "The cafe closes at 10 PM.", "Yes, still true.", "Food & Drink", "ABC Cafe"
    )
    assert result.relation == knowledge_relation.RELATION_CONFIRMS
    assert result.new_knowledge_text is None


def test_confirms_on_no_change_opener_despite_leading_no():
    result = knowledge_relation.classify_relation(
        "The cafe closes at 10 PM.", "No change, it's still 10 PM.", "Food & Drink", "ABC Cafe"
    )
    assert result.relation == knowledge_relation.RELATION_CONFIRMS


def test_confirms_on_high_token_overlap_paraphrase():
    result = knowledge_relation.classify_relation(
        "The cafe closes at 10 PM every night.",
        "The cafe closes at 10 PM every night, confirmed today.",
        "Food & Drink",
        "ABC Cafe",
    )
    assert result.relation == knowledge_relation.RELATION_CONFIRMS


def test_deterministic_fast_path_never_returns_contradicts():
    fast = knowledge_relation._classify_deterministic(
        "The cafe closes at 10 PM.", "No, it closes at 8 PM now."
    )
    # The fast path only ever returns CONFIRMS or None (defer to the LLM) --
    # never a guessed CONTRADICTS, which requires generative judgement.
    assert fast is None


def test_jaccard_and_tokens_are_symmetric_and_bounded():
    a = knowledge_relation._tokens("The cafe closes at 10 PM.")
    b = knowledge_relation._tokens("Closes at ten PM, the cafe.")
    score_ab = knowledge_relation._jaccard(a, b)
    score_ba = knowledge_relation._jaccard(b, a)
    assert score_ab == score_ba
    assert 0.0 <= score_ab <= 1.0
