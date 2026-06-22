
from typing import List, Dict
from datasketch import MinHash, MinHashLSH

class Deduplicator:
    def __init__(self, threshold: float = 0.8, num_perm: int = 128):
        self.threshold = threshold
        self.num_perm = num_perm
        self.lsh = MinHashLSH(threshold=self.threshold, num_perm=self.num_perm)
        self.minhashes = {}

    def _generate_minhash(self, text: str) -> MinHash:
        m = MinHash(num_perm=self.num_perm)
        for d in text.split():
            m.update(d.encode('utf8'))
        return m

    def deduplicate_dataset(self, dataset: List[Dict]) -> List[Dict]:
        unique_samples = []
        seen_exact = set()
        
        # First pass for exact duplicates
        for i, sample in enumerate(dataset):
            instruction_output = sample.get('instruction', '') + sample.get('output', '')
            if instruction_output not in seen_exact:
                seen_exact.add(instruction_output)
                unique_samples.append(sample)
        
        # Second pass for near duplicates using LSH
        final_unique_samples = []
        for i, sample in enumerate(unique_samples):
            instruction_output = sample.get('instruction', '') + sample.get('output', '')
            m = self._generate_minhash(instruction_output)
            
            # Check for near duplicates
            is_near_duplicate = False
            if self.lsh.query(m):
                is_near_duplicate = True
            
            if not is_near_duplicate:
                self.lsh.insert(str(i), m) # Use index as key for LSH
                final_unique_samples.append(sample)
        
        return final_unique_samples
