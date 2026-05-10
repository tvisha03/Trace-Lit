import pytest
import asyncio
from domain.verification.transformation_classifier import classify_transformations, TransformationType

class MockVerificationItem:
    def __init__(self, claim, source_sentence, semantic_score, cross_encoder_score, paper_id=None):
        self.claim = claim
        self.source_sentence = source_sentence
        self.semantic_score = semantic_score
        self.cross_encoder_score = cross_encoder_score
        self.paper_id = paper_id
        self.score = semantic_score

@pytest.mark.asyncio
async def test_integration_transformation():
    # 1. HAVF returns results
    mock_results = [
        MockVerificationItem(
            claim="Identical claim.",
            source_sentence="Identical claim.",
            semantic_score=0.95,
            cross_encoder_score=0.95,
            paper_id="paper1"
        ),
        MockVerificationItem(
            claim="An inferred statement.",
            source_sentence="Facts that lead to the statement.",
            semantic_score=0.60,
            cross_encoder_score=0.75,
            paper_id="paper2"
        )
    ]
    
    # 2. Classifier receives correct fields
    # 3. Transformation type added to response
    updated_results = await classify_transformations(mock_results)
    
    assert len(updated_results) == 2
    assert updated_results[0].transformation_type == TransformationType.DIRECT_QUOTE.value
    assert updated_results[0].transformation_confidence == 0.94
    assert "High string" in updated_results[0].transformation_reason
    
    assert updated_results[1].transformation_type == TransformationType.INFERENCE.value
    assert updated_results[1].transformation_confidence == 0.70
    assert "Moderate semantic" in updated_results[1].transformation_reason
    
    # 4. Schema validation passes (simulated by structure)
    # 5. Frontend receives three new fields (verified by attrs existing)
    assert hasattr(updated_results[0], 'transformation_type')
    assert hasattr(updated_results[0], 'transformation_confidence')
    assert hasattr(updated_results[0], 'transformation_reason')
