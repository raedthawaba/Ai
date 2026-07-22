"""
Hajeen Repository Comprehensive Audit
====================================

This script performs a complete audit of the repository including:
1. Runtime Audit
2. Source Code Audit
3. Dependency Audit
4. Import Audit
5. Circular Dependency Audit
6. Duplicate Code Audit
7. Feature Coverage Audit
8. API Compatibility Audit
"""

import os
import sys
import re
import ast
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
from collections import defaultdict

# Add hajeen_platform to path
sys.path.insert(0, 'hajeen_platform')

BRAIN_DIR = Path("hajeen_platform/brain")
ARCHIVE_DIR = Path("hajeen_platform/brain/archive")


class RepositoryAuditor:
    """Complete repository auditor."""
    
    def __init__(self):
        self.files: Dict[str, Path] = {}
        self.classes: Dict[str, Dict] = {}
        self.functions: Dict[str, Dict] = {}
        self.imports: Dict[str, Set[str]] = {}
        self.imported_by: Dict[str, Set[str]] = defaultdict(set)
        self.duplicates: Dict[str, List[Path]] = defaultdict(list)
        self.versioned_files: Dict[str, List[Path]] = defaultdict(list)
        self.circular_deps: List[Tuple[str, str]] = []
        self.contracts: Dict[str, Path] = {}
        self.engines: Dict[str, Dict] = {}
        self.capabilities: Dict[str, Set[str]] = defaultdict(set)
        self.all_imports_graph: Dict[str, Set[str]] = {}
        
    def scan_files(self):
        """Scan all Python files in brain directory."""
        print("\n" + "=" * 100)
        print("SCANNING FILES")
        print("=" * 100)
        
        self.files = {}
        self.versioned_files = defaultdict(list)
        
        for py_file in BRAIN_DIR.rglob("*.py"):
            rel_path = py_file.relative_to(BRAIN_DIR)
            self.files[str(rel_path)] = py_file
            
            # Check for versioned files
            filename = py_file.name
            for pattern in ['_v2', '_v3', '_legacy', '_old', '_deprecated', '_new', '_latest', '_copy']:
                if pattern in filename.lower():
                    self.versioned_files[pattern].append(py_file)
            
            # Check for archive
            if 'archive' in str(rel_path):
                continue
                
        print(f"\n📊 Total Python files: {len(self.files)}")
        print(f"📊 Versioned files found:")
        for pattern, files in self.versioned_files.items():
            print(f"   - {pattern}: {len(files)} files")
            for f in files:
                print(f"     • {f.name}")
    
    def parse_python_file(self, file_path: Path) -> ast.Module:
        """Parse a Python file and return AST."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return ast.parse(f.read(), filename=str(file_path))
        except Exception as e:
            print(f"   ⚠️ Error parsing {file_path}: {e}")
            return None
    
    def extract_definitions(self):
        """Extract all class and function definitions."""
        print("\n" + "=" * 100)
        print("EXTRACTING DEFINITIONS")
        print("=" * 100)
        
        self.classes = {}
        self.functions = {}
        self.contracts = {}
        
        for file_path, full_path in self.files.items():
            if 'archive' in file_path:
                continue
                
            tree = self.parse_python_file(full_path)
            if not tree:
                continue
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self.classes[node.name] = {
                        'file': file_path,
                        'full_path': full_path,
                        'methods': [n.name for n in node.body if isinstance(n, ast.FunctionDef)],
                        'decorators': [d.id if isinstance(d, ast.Name) else str(d) for d in node.decorator_list]
                    }
                elif isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                    self.functions[node.name] = {
                        'file': file_path,
                        'full_path': full_path
                    }
                
                # Check for contracts
                if isinstance(node, ast.ClassDef):
                    if 'Contract' in node.name or 'Request' in node.name or 'Response' in node.name or 'Result' in node.name:
                        self.contracts[node.name] = file_path
        
        print(f"\n📊 Classes found: {len(self.classes)}")
        print(f"📊 Functions found: {len(self.functions)}")
        print(f"📊 Contracts found: {len(self.contracts)}")
        
        print("\n📊 CLASSES BY ENGINE:")
        for cls_name, info in sorted(self.classes.items()):
            print(f"   • {cls_name}: {info['file']}")
        
        print("\n📊 CONTRACTS:")
        for contract_name, file in sorted(self.contracts.items()):
            print(f"   • {contract_name}: {file}")
    
    def extract_imports(self):
        """Extract all imports from files."""
        print("\n" + "=" * 100)
        print("EXTRACTING IMPORTS")
        print("=" * 100)
        
        self.imports = {}
        self.imported_by = defaultdict(set)
        self.all_imports_graph = {}
        
        for file_path, full_path in self.files.items():
            if 'archive' in file_path:
                continue
                
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                tree = ast.parse(content, filename=str(full_path))
                
                file_imports = set()
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            file_imports.add(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            file_imports.add(node.module)
                
                self.imports[file_path] = file_imports
                
                # Build reverse map
                for imp in file_imports:
                    self.imported_by[imp].add(file_path)
                
                self.all_imports_graph[file_path] = file_imports
                
            except Exception as e:
                print(f"   ⚠️ Error reading {file_path}: {e}")
        
        print(f"\n📊 Files with imports analyzed: {len(self.imports)}")
        
        # Find imports pointing to versioned files
        print("\n📊 IMPORTS TO VERSIONED FILES:")
        versioned_imports = []
        for file_path, imports in self.imports.items():
            for imp in imports:
                for pattern in self.versioned_files:
                    if pattern in imp or pattern.replace('_', '.') in imp:
                        versioned_imports.append((file_path, imp))
        
        if versioned_imports:
            for file_path, imp in versioned_imports[:10]:
                print(f"   ⚠️ {file_path} imports {imp}")
        else:
            print("   ✅ No imports to versioned files")
    
    def find_circular_dependencies(self):
        """Find circular dependencies."""
        print("\n" + "=" * 100)
        print("CIRCULAR DEPENDENCY AUDIT")
        print("=" * 100)
        
        self.circular_deps = []
        
        # Build file dependency graph
        file_deps = {}
        for file_path, full_path in self.files.items():
            if 'archive' in file_path:
                continue
            file_deps[file_path] = set()
            
            tree = self.parse_python_file(full_path)
            if tree:
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        if node.module and 'hajeen_platform.brain' in node.module:
                            # Get relative import
                            rel_imp = node.module.replace('hajeen_platform.brain.', '')
                            if rel_imp.startswith('.'):
                                continue
                            file_deps[file_path].add(rel_imp.split('.')[0])
        
        # Simple cycle detection
        for file_a in file_deps:
            for file_b in file_deps:
                if file_a != file_b:
                    if file_a in file_deps[file_b] and file_b in file_deps[file_a]:
                        if (file_b, file_a) not in self.circular_deps:
                            self.circular_deps.append((file_a, file_b))
        
        if self.circular_deps:
            print(f"\n⚠️ Found {len(self.circular_deps)} potential circular dependencies:")
            for dep_a, dep_b in self.circular_deps[:5]:
                print(f"   • {dep_a} ↔ {dep_b}")
        else:
            print("\n✅ No circular dependencies found")
    
    def find_duplicate_code(self):
        """Find duplicate classes or functions."""
        print("\n" + "=" * 100)
        print("DUPLICATE CODE AUDIT")
        print("=" * 100)
        
        # Group by class/function name
        name_to_files = defaultdict(list)
        
        for cls_name, info in self.classes.items():
            name_to_files[cls_name].append(info['file'])
        
        self.duplicates = {}
        for name, files in name_to_files.items():
            if len(files) > 1:
                self.duplicates[name] = files
        
        if self.duplicates:
            print(f"\n⚠️ Found {len(self.duplicates)} duplicate definitions:")
            for name, files in self.duplicates.items():
                print(f"   • {name} appears in:")
                for f in files:
                    print(f"     - {f}")
        else:
            print("\n✅ No duplicate definitions found")
    
    def analyze_engines(self):
        """Analyze engine components."""
        print("\n" + "=" * 100)
        print("ENGINE ANALYSIS")
        print("=" * 100)
        
        self.engines = {
            'brain': {'files': [], 'classes': [], 'capabilities': set()},
            'reasoning': {'files': [], 'classes': [], 'capabilities': set()},
            'planning': {'files': [], 'classes': [], 'capabilities': set()},
            'decision': {'files': [], 'classes': [], 'capabilities': set()},
            'model_router': {'files': [], 'classes': [], 'capabilities': set()},
            'memory': {'files': [], 'classes': [], 'capabilities': set()},
            'knowledge': {'files': [], 'classes': [], 'capabilities': set()},
            'task_decomposer': {'files': [], 'classes': [], 'capabilities': set()},
            'graph_planner': {'files': [], 'classes': [], 'capabilities': set()},
            'policy': {'files': [], 'classes': [], 'capabilities': set()},
            'execution': {'files': [], 'classes': [], 'capabilities': set()},
            'reflection': {'files': [], 'classes': [], 'capabilities': set()},
            'learning': {'files': [], 'classes': [], 'capabilities': set()},
        }
        
        for file_path, full_path in self.files.items():
            if 'archive' in file_path:
                continue
            
            file_lower = file_path.lower()
            
            # Match file to engine
            for engine_name in self.engines:
                if engine_name.replace('_', '') in file_lower.replace('_', ''):
                    self.engines[engine_name]['files'].append(file_path)
        
        # Add classes to engines
        for cls_name, info in self.classes.items():
            cls_lower = cls_name.lower()
            for engine_name in self.engines:
                if engine_name.replace('_', '') in cls_lower.replace('_', ''):
                    self.engines[engine_name]['classes'].append(cls_name)
        
        print("\n📊 ENGINE COVERAGE:")
        for engine_name, data in sorted(self.engines.items()):
            print(f"\n   {engine_name.upper()}:")
            print(f"      Files: {len(data['files'])}")
            print(f"      Classes: {len(data['classes'])}")
            for f in data['files']:
                print(f"        • {f}")
    
    def generate_dependency_graph(self):
        """Generate dependency graph."""
        print("\n" + "=" * 100)
        print("DEPENDENCY GRAPH")
        print("=" * 100)
        
        dep_graph = defaultdict(set)
        
        for file_path, imports in self.imports.items():
            for imp in imports:
                if imp.startswith('brain.'):
                    module = imp.replace('brain.', '')
                    dep_graph[file_path].add(module)
        
        print("\n📊 DEPENDENCY GRAPH (top-level):")
        for file_path, deps in sorted(dep_graph.items())[:15]:
            print(f"   {file_path}:")
            for dep in sorted(deps)[:5]:
                print(f"      → {dep}")
    
    def generate_import_graph(self):
        """Generate import graph."""
        print("\n" + "=" * 100)
        print("IMPORT GRAPH")
        print("=" * 100)
        
        print("\n📊 IMPORT GRAPH (key files):")
        
        key_files = [
            'brain.py',
            'hajeen_brain.py',
            'contracts.py',
            'reasoning_engine.py',
            'decision_engine.py',
            'model_router.py',
            'memory_fabric.py',
            'knowledge_graph.py',
            'goal_manager.py',
            'task_decomposer.py',
            'graph_planner.py',
            'policy_engine.py',
            'execution_engine.py',
            'self_reflection.py',
        ]
        
        for key in key_files:
            for file_path, full_path in self.files.items():
                if file_path.endswith(key):
                    imports = self.imports.get(file_path, set())
                    print(f"\n   {file_path}:")
                    print(f"      Imports: {len(imports)} modules")
                    print(f"      Imported by: {len(self.imported_by.get(file_path, set()))} files")
                    break
    
    def run_full_audit(self) -> Dict[str, Any]:
        """Run complete audit and return results."""
        self.scan_files()
        self.extract_definitions()
        self.extract_imports()
        self.find_circular_dependencies()
        self.find_duplicate_code()
        self.analyze_engines()
        self.generate_dependency_graph()
        self.generate_import_graph()
        
        return {
            'total_files': len(self.files),
            'total_classes': len(self.classes),
            'total_functions': len(self.functions),
            'total_contracts': len(self.contracts),
            'versioned_files': {k: len(v) for k, v in self.versioned_files.items()},
            'circular_deps': len(self.circular_deps),
            'duplicates': {k: len(v) for k, v in self.duplicates.items()},
            'engines': {k: {'files': len(v['files']), 'classes': len(v['classes'])} 
                       for k, v in self.engines.items()},
        }
    
    def generate_report(self) -> str:
        """Generate comprehensive audit report."""
        report = """
╔══════════════════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                              ║
║                        HAJEEN REPOSITORY COMPREHENSIVE AUDIT REPORT                           ║
║                                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════════════════════════╝
"""
        report += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. FILE STATISTICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   Total Python Files: {len(self.files)}
   Total Classes: {len(self.classes)}
   Total Functions: {len(self.functions)}
   Total Contracts: {len(self.contracts)}

"""
        
        report += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. VERSIONED FILES (TO BE CONSOLIDATED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        for pattern, files in self.versioned_files.items():
            if files:
                report += f"\n   {pattern}: {len(files)} files\n"
                for f in files:
                    report += f"      • {f.name}\n"
        
        report += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. DUPLICATE DEFINITIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        if self.duplicates:
            for name, files in self.duplicates.items():
                report += f"\n   {name}:\n"
                for f in files:
                    report += f"      • {f}\n"
        else:
            report += "\n   ✅ No duplicates found\n"
        
        report += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4. ENGINE COVERAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        for engine_name, data in sorted(self.engines.items()):
            report += f"\n   {engine_name.upper()}:\n"
            report += f"      Files: {len(data['files'])}\n"
            report += f"      Classes: {len(data['classes'])}\n"
            for f in data['files']:
                report += f"      • {f}\n"
        
        report += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
5. CONTRACTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        for contract_name, file in sorted(self.contracts.items()):
            report += f"   • {contract_name}: {file}\n"
        
        report += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
6. CIRCULAR DEPENDENCIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        if self.circular_deps:
            for dep_a, dep_b in self.circular_deps:
                report += f"   ⚠️ {dep_a} ↔ {dep_b}\n"
        else:
            report += "   ✅ No circular dependencies\n"
        
        return report


def main():
    """Run comprehensive audit."""
    auditor = RepositoryAuditor()
    results = auditor.run_full_audit()
    report = auditor.generate_report()
    print(report)
    
    # Save report
    with open('AUDIT_REPORT.txt', 'w', encoding='utf-8') as f:
        f.write(report)
    
    print("\n✅ Audit report saved to AUDIT_REPORT.txt")
    
    return auditor


if __name__ == "__main__":
    auditor = main()
