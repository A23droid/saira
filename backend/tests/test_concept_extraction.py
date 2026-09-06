import pytest

from app.services.concept_service import canonical_key, display_name
from app.services.prompts import CONCEPT_RELATION_TYPES, build_concept_extraction_messages


def test_canonical_key_normalizes_surface_forms():
    """Concept identity folding.

    Replaces the old `_normalize_concept`, which combined identity and display
    in one Title-Cased string. Those are now two functions: `canonical_key`
    produces the lowercase identity used for node IDs, and `display_name`
    produces the human label. Splitting them is what allows "BERT" to keep its
    casing while still matching "bert".
    """
    # Whitespace and case fold away for identity purposes.
    assert canonical_key("  Machine Learning  ") == "machine learning"
    assert canonical_key("machine learning") == canonical_key("Machine Learning")

    # Simple plurals collapse to the singular.
    assert canonical_key("Algorithms") == "algorithm"
    assert canonical_key("Ontologies") == "ontology"

    # A trailing padding word is dropped, so these are one concept.
    assert canonical_key("Transformer Models") == "transformer"
    assert canonical_key("Transformer") == canonical_key("Transformer Models")

    # -ss endings are preserved (the old rule turned "Loss" into "Los").
    assert canonical_key("Loss") == "loss"
    assert canonical_key("Bias") == "bias"

    # Separator variants unify.
    assert canonical_key("self-attention") == canonical_key("Self Attention")

    assert canonical_key("") == ""


def test_display_name_preserves_original_casing():
    assert display_name("  BERT  model ") == "BERT model"
    assert display_name("self-attention") == "self-attention"
    assert display_name("") == ""


def test_distinct_concepts_stay_distinct():
    """Normalization must not over-merge genuinely different concepts."""
    assert canonical_key("self-attention") != canonical_key("cross-attention")
    assert canonical_key("encoder") != canonical_key("decoder")


def test_build_concept_extraction_messages():
    paper = {
        "title": "Attention Is All You Need",
        "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
        "publication_year": 2017,
        "venue": "NIPS"
    }

    messages = build_concept_extraction_messages(paper)

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"

    # Ensure JSON constraints are in system prompt
    system_content = messages[0]["content"]
    assert "JSON object" in system_content
    assert '"concepts":' in system_content

    # The prompt now also requests relationships and per-concept evidence,
    # which is what gives graph edges and provenance.
    assert '"relations":' in system_content
    assert "evidence" in system_content
    for relation_type in CONCEPT_RELATION_TYPES:
        assert relation_type in system_content

    # Ensure paper content is in user prompt
    user_content = messages[1]["content"]
    assert "Attention Is All You Need" in user_content
    assert "2017" in user_content
