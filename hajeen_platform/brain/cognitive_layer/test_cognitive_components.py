"""
Unit tests for the core cognitive components.

Tests the functionality of:
- Cognitive Compiler
- Cognitive Event System
- Concept Engine
"""

import unittest

from cognitive_compiler import CognitiveCompiler
from cognitive_event_system import CognitiveEventSystem
from concept_engine import ConceptEngine


class TestCognitiveCompiler(unittest.TestCase):
    """Test cases for the Cognitive Compiler."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.compiler = CognitiveCompiler()
    
    def test_compile_input_basic(self):
        """Test basic input compilation."""
        raw_input = "Oil prices are rising due to supply constraints."
        event = self.compiler.compile_input(raw_input)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.raw_input, raw_input)
        self.assertGreater(len(event.results.get('facts', [])), 0)
        self.assertGreater(len(event.results.get('concepts', [])), 0)
    
    def test_fact_extraction(self):
        """Test fact extraction."""
        raw_input = "The sky is blue. Water is essential for life."
        facts = self.compiler.extract_facts(raw_input)
        
        self.assertGreaterEqual(len(facts), 2)
        for fact in facts:
            self.assertIn('text', fact)
            self.assertIn('type', fact)
            self.assertIn('confidence', fact)
    
    def test_concept_extraction(self):
        """Test concept extraction."""
        raw_input = "Oil and Gas are important commodities."
        concepts = self.compiler.extract_concepts(raw_input)
        
        self.assertGreater(len(concepts), 0)
        for concept in concepts:
            self.assertIn('name', concept)
            self.assertIn('type', concept)
    
    def test_relationship_discovery(self):
        """Test relationship discovery."""
        facts = [{'text': 'Oil prices are rising'}]
        concepts = [{'name': 'Oil'}]
        relationships = self.compiler.discover_relationships(facts, concepts)
        
        self.assertGreater(len(relationships), 0)
        for rel in relationships:
            self.assertIn('source', rel)
            self.assertIn('target', rel)
            self.assertIn('type', rel)
    
    def test_confidence_scoring(self):
        """Test confidence scoring."""
        event = self.compiler.compile_input("Test input")
        
        self.assertGreaterEqual(event.confidence_level, 0.0)
        self.assertLessEqual(event.confidence_level, 1.0)


class TestCognitiveEventSystem(unittest.TestCase):
    """Test cases for the Cognitive Event System."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.event_system = CognitiveEventSystem()
    
    def test_create_event(self):
        """Test event creation."""
        event = self.event_system.create_event(
            raw_input="Test input",
            event_type="fact_extraction"
        )
        
        self.assertIsNotNone(event)
        self.assertEqual(event['raw_input'], "Test input")
        self.assertEqual(event['event_type'], "fact_extraction")
    
    def test_store_and_retrieve_event(self):
        """Test storing and retrieving an event."""
        event = self.event_system.create_event(
            raw_input="Test input",
            event_type="fact_extraction"
        )
        event_id = self.event_system.store_event(event)
        
        retrieved = self.event_system.get_event(event_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved['raw_input'], "Test input")
    
    def test_get_events_by_type(self):
        """Test retrieving events by type."""
        # Create multiple events of different types
        event1 = self.event_system.create_event("Input 1", "fact_extraction")
        event2 = self.event_system.create_event("Input 2", "fact_extraction")
        event3 = self.event_system.create_event("Input 3", "concept_extraction")
        
        self.event_system.store_event(event1)
        self.event_system.store_event(event2)
        self.event_system.store_event(event3)
        
        fact_events = self.event_system.get_events_by_type("fact_extraction")
        self.assertEqual(len(fact_events), 2)
    
    def test_search_events(self):
        """Test searching for events."""
        event = self.event_system.create_event(
            raw_input="Oil prices rising",
            event_type="fact_extraction"
        )
        event['confidence_level'] = 0.8
        self.event_system.store_event(event)
        
        results = self.event_system.search_events({
            'event_type': 'fact_extraction',
            'keywords': ['Oil']
        })
        
        self.assertGreater(len(results), 0)
    
    def test_event_statistics(self):
        """Test event statistics."""
        event1 = self.event_system.create_event("Input 1", "fact_extraction")
        event2 = self.event_system.create_event("Input 2", "concept_extraction")
        
        self.event_system.store_event(event1)
        self.event_system.store_event(event2)
        
        stats = self.event_system.get_event_statistics()
        
        self.assertEqual(stats['total_events'], 2)
        self.assertIn('fact_extraction', stats['events_by_type'])
        self.assertIn('concept_extraction', stats['events_by_type'])


class TestConceptEngine(unittest.TestCase):
    """Test cases for the Concept Engine."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.concept_engine = ConceptEngine()
    
    def test_create_concept(self):
        """Test concept creation."""
        concept = self.concept_engine.create_concept(
            name="Oil",
            definition="A naturally occurring liquid mineral"
        )
        
        self.assertIsNotNone(concept)
        self.assertEqual(concept.name, "Oil")
        self.assertEqual(concept.definition, "A naturally occurring liquid mineral")
    
    def test_get_concept_by_id(self):
        """Test retrieving a concept by ID."""
        concept = self.concept_engine.create_concept(
            name="Water",
            definition="Essential liquid for life"
        )
        
        retrieved = self.concept_engine.get_concept(concept.concept_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Water")
    
    def test_get_concept_by_name(self):
        """Test retrieving a concept by name."""
        concept = self.concept_engine.create_concept(
            name="Energy",
            definition="Capacity to do work"
        )
        
        retrieved = self.concept_engine.get_concept_by_name("Energy")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.concept_id, concept.concept_id)
    
    def test_add_cause_and_effect(self):
        """Test adding causes and effects to a concept."""
        concept = self.concept_engine.create_concept(
            name="Inflation",
            definition="Increase in price levels"
        )
        
        self.concept_engine.add_cause(concept.concept_id, "Increased money supply")
        self.concept_engine.add_effect(concept.concept_id, "Reduced purchasing power")
        
        updated = self.concept_engine.get_concept(concept.concept_id)
        self.assertIn("Increased money supply", updated.causes)
        self.assertIn("Reduced purchasing power", updated.effects)
    
    def test_add_rule_and_exception(self):
        """Test adding rules and exceptions to a concept."""
        concept = self.concept_engine.create_concept(
            name="Supply and Demand",
            definition="Economic principle"
        )
        
        self.concept_engine.add_rule(concept.concept_id, "Higher demand increases price")
        self.concept_engine.add_exception(concept.concept_id, "During crisis, demand may not affect price")
        
        updated = self.concept_engine.get_concept(concept.concept_id)
        self.assertIn("Higher demand increases price", updated.rules)
        self.assertIn("During crisis, demand may not affect price", updated.exceptions)
    
    def test_link_concepts(self):
        """Test linking two concepts."""
        concept1 = self.concept_engine.create_concept("Oil", "Fossil fuel")
        concept2 = self.concept_engine.create_concept("Energy", "Capacity to do work")
        
        self.concept_engine.link_concepts(concept1.concept_id, concept2.concept_id)
        
        related = self.concept_engine.get_related_concepts(concept1.concept_id)
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0].name, "Energy")
    
    def test_add_evidence(self):
        """Test adding evidence to a concept."""
        concept = self.concept_engine.create_concept("Climate Change", "Global warming")
        
        evidence = {
            'source': 'IPCC Report',
            'data': 'Temperature increased by 1.1°C',
            'confidence': 0.95
        }
        
        self.concept_engine.add_evidence(concept.concept_id, evidence)
        
        updated = self.concept_engine.get_concept(concept.concept_id)
        self.assertEqual(len(updated.evidence), 1)
        self.assertEqual(updated.evidence[0]['source'], 'IPCC Report')
    
    def test_update_confidence(self):
        """Test updating concept confidence."""
        concept = self.concept_engine.create_concept("Test", "Test concept")
        initial_confidence = concept.confidence
        
        self.concept_engine.update_concept(concept.concept_id, {'confidence': 0.9})
        
        updated = self.concept_engine.get_concept(concept.concept_id)
        self.assertEqual(updated.confidence, 0.9)
    
    def test_concept_statistics(self):
        """Test concept statistics."""
        self.concept_engine.create_concept("Concept1", "First concept")
        self.concept_engine.create_concept("Concept2", "Second concept")
        
        stats = self.concept_engine.get_concept_statistics()
        
        self.assertEqual(stats['total_concepts'], 2)
        self.assertGreaterEqual(stats['average_confidence'], 0.0)


if __name__ == '__main__':
    unittest.main()
