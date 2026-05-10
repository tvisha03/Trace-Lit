import pytest
from domain.verification.transformation_classifier import TransformationClassifier, TransformationType

def test_calibration():
    # Create test cases from actual papers
    # Goal: 8-9/10 correct
    
    classifier = TransformationClassifier()
    
    cases = [
        # Direct Quotes
        ("The Transformer is the first sequence transduction model based entirely on attention.", 
         "The Transformer is the first sequence transduction model based entirely on attention.", 0.99, 0.99, TransformationType.DIRECT_QUOTE),
        # Paraphrases
        ("Multi-head attention allows joint attention to different representation subspaces.", 
         "Multi-head attention allows the model to jointly attend to information from different representation subspaces.", 0.85, 0.90, TransformationType.PARAPHRASE),
        # Synthesis
        ("Both models use a similar approach.", 
         "One uses X.", 0.70, 0.60, TransformationType.SYNTHESIS),
        # Inferences
        ("The model handles long sequences better.", 
         "The complexity is reduced to O(1).", 0.65, 0.75, TransformationType.INFERENCE),
        # Unsupported
        ("BERT uses a CNN.", 
         "We use a multi-layer bidirectional Transformer.", 0.20, 0.10, TransformationType.UNSUPPORTED),
    ]
    
    correct = 0
    for claim, source, sem, ce, expected in cases:
        sources = [{"paper_id": "p1", "score": sem}] if expected != TransformationType.SYNTHESIS else [{"paper_id": "p1", "score": 0.65}, {"paper_id": "p2", "score": 0.65}]
        res = classifier.classify(claim, source, sem, ce, sources)
        if res.type == expected.value:
            correct += 1
            
    assert correct >= len(cases) * 0.8, f"Calibration failed: only {correct}/{len(cases)} correct."
