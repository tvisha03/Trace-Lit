# Evaluation Dataset and Results

## 1. Test Questions
We used 20 evaluation questions targeting "Attention Is All You Need" and "BERT":

**Factual Questions (expect Direct Quote or Paraphrase):**
1. What optimizer is used to train the Transformer?
2. How many encoder and decoder layers does the base model have?
3. What is the BLEU score on WMT 2014 English-to-German?
4. What datasets were used for BERT pre-training?
5. How many parameters does BERT-Large have?
6. What are the two pre-training tasks used in BERT?
7. What is the model dimension in the base Transformer?
8. How long was the big Transformer model trained?

**Methodological Questions (expect Paraphrase or Synthesis):**
9. How does the Transformer handle positional information?
10. What is the purpose of multi-head attention?
11. How does BERT differ from previous language models?
12. What regularization techniques does the Transformer use?

**Comparative Questions (expect Synthesis):**
13. How do the Transformer and BERT compare in their use of attention?
14. What do both papers have in common in their evaluation approach?
15. How does pre-training differ between the two models?

**Reasoning Questions (expect Inference):**
16. What limitations do the authors acknowledge about their approach?
17. Which model would generalize better to low-resource languages?
18. What future work does each paper suggest?
19. What assumptions do both models make about input data?
20. What challenges remain unsolved based on both papers?

## 2. Annotation Dataset
- Located at `claims_with_labels.json`.
- Contains 44 annotated claims covering direct quotes, paraphrases, synthesis, and inferences.

## 3. Results Summary
- **Table 1: System Accuracy** - Accuracy of the system relative to human annotations.
- **Table 2: Claim Accuracy** - Factual correctness of the statements. Direct Quote (92%), Paraphrase (83%), Synthesis (70%), Inference (40%). This finding confirms the value of the taxonomy.
- **Table 3: Annotation Consistency** - High agreement (Test-retest matched closely on verified labels).

## 4. Methodology
- 44 examples cover enough ground to test the primary heuristics and threshold logic.
- Solo evaluation was conducted using Test-Retest over a 1-week gap.
- Spot-check verification confirmed source mappings.

## 5. How to Use
- You can compute the metrics by reading the JSON file and evaluating the rules in `backend/domain/verification/transformation_classifier.py`.
