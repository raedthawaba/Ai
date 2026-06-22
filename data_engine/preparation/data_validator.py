
import re

class DataValidator:
    def __init__(self):
        pass

    def validate_sample(self, sample: dict) -> dict:
        errors = []
        # Check for empty fields
        if not sample.get('instruction') or not sample.get('output'):
            errors.append('Empty instruction or output field')

        # Check for corrupted text (simple regex for now, can be expanded)
        if not re.match(r'^[\s\S]*$', sample.get('instruction', '')):
            errors.append('Corrupted instruction text')
        if not re.match(r'^[\s\S]*$', sample.get('output', '')):
            errors.append('Corrupted output text')

        # Check encoding (assuming UTF-8, basic check)
        try:
            sample.get('instruction', '').encode('utf-8').decode('utf-8')
            sample.get('output', '').encode('utf-8').decode('utf-8')
        except UnicodeDecodeError:
            errors.append('Encoding error detected')

        # Check sample length (example: min 10 chars, max 2000 chars)
        instruction_length = len(sample.get('instruction', ''))
        output_length = len(sample.get('output', ''))
        if instruction_length < 10 or output_length < 10:
            errors.append('Sample too short')
        if instruction_length > 2000 or output_length > 2000:
            errors.append('Sample too long')

        sample['validation_errors'] = errors
        sample['is_valid'] = not bool(errors)
        return sample

    def validate_dataset(self, dataset: list[dict]) -> list[dict]:
        validated_dataset = [self.validate_sample(sample) for sample in dataset]
        return validated_dataset
