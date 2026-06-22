
class QualityScorer:
    def __init__(self, min_length_score=50, max_length_score=100, validation_penalty=30):
        self.min_length_score = min_length_score
        self.max_length_score = max_length_score
        self.validation_penalty = validation_penalty

    def score_sample(self, sample: dict) -> dict:
        score = 100  # Start with a perfect score

        # Penalize for validation errors
        if not sample.get('is_valid', True):
            score -= self.validation_penalty * len(sample.get('validation_errors', []))

        # Score based on length (example logic)
        instruction_length = len(sample.get('instruction', ''))
        output_length = len(sample.get('output', ''))
        total_length = instruction_length + output_length

        if total_length < 50:
            score -= (50 - total_length) * 0.5 # Small penalty for being too short
        elif total_length > 1000:
            score -= (total_length - 1000) * 0.01 # Small penalty for being too long

        # Ensure score is within 0-100 range
        sample['quality_score'] = max(0, min(100, int(score)))
        return sample

    def score_dataset(self, dataset: list[dict]) -> list[dict]:
        scored_dataset = [self.score_sample(sample) for sample in dataset]
        return scored_dataset
