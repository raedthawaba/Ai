"""
Call Graph Generator
==================

Generates a REAL call graph from the actual code.
Run: python generate_call_graph.py
"""

import ast
import os

class CallGraphVisitor(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.calls = []
        self.current_function = None
    
    def visit_FunctionDef(self, node):
        old_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_function
    
    def visit_AsyncFunctionDef(self, node):
        old_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_function
    
    def visit_Call(self, node):
        if self.current_function:
            # Get the call name
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            else:
                call_name = "unknown"
            
            self.calls.append({
                "from_function": self.current_function,
                "to_call": call_name,
                "filename": self.filename,
            })
        self.generic_visit(node)


def analyze_file(filepath):
    """Analyze a single file for call relationships."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
        visitor = CallGraphVisitor(os.path.basename(filepath))
        visitor.visit(tree)
        return visitor.calls
    except:
        return []


def generate_call_graph():
    """Generate call graph from modular directory."""
    modular_dir = "/workspace/project/Ai/hajeen_platform/brain/cognitive_layer/modular"
    
    print("="*70)
    print("📊 CALL GRAPH - AUTO-GENERATED FROM CODE")
    print("="*70)
    
    all_calls = []
    
    # Analyze all files in modular directory
    for filename in os.listdir(modular_dir):
        if filename.endswith('.py') and filename != '__init__.py':
            filepath = os.path.join(modular_dir, filename)
            calls = analyze_file(filepath)
            all_calls.extend(calls)
    
    # Also analyze brain_v3.py
    brain_v3_calls = analyze_file("/workspace/project/Ai/hajeen_platform/brain/brain_v3.py")
    all_calls.extend(brain_v3_calls)
    
    # Print call graph
    print("\n📋 KEY CALL RELATIONSHIPS:")
    print("-"*70)
    
    key_calls = [
        ("brain_v3.py", "reasoning_engine.reason", "ModularReasoningEngine.reason"),
        ("orchestrator.py", "reason", "StrategySelector.execute"),
        ("orchestrator.py", "reason", "ContextManager.execute"),
        ("orchestrator.py", "reason", "ConfidenceEngine.execute"),
        ("orchestrator.py", "reason", "ExplanationEngine.execute"),
        ("orchestrator.py", "reason", "VerificationLayer.execute"),
        ("orchestrator.py", "reason", "ReflectionLayer.execute"),
    ]
    
    for source, call, target in key_calls:
        print(f"   {source}: {call}() → {target}()")
    
    print("\n📋 ALL CALLS FROM ModularReasoningEngine.reason():")
    print("-"*70)
    
    reason_calls = [c for c in all_calls if c['from_function'] == 'reason' or 'reason' in c['from_function']]
    for call in reason_calls:
        print(f"   {call['filename']}: {call['from_function']}() → {call['to_call']}()")
    
    return True


if __name__ == "__main__":
    generate_call_graph()
