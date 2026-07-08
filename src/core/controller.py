"""
src/core/controller.py
Iteration Controller: Loop until success or max iterations.
"""

from typing import Dict, Any
from src.core.config import MAX_ITERATIONS
from src.core.logger import logger
from src.core.memory import RepairMemory

from src.indexer.scanner import ProjectScanner
from src.indexer.dependency import DependencyBuilder
from src.indexer.symbol import SymbolIndexer
from src.context.retriever import ContextRetriever
from src.agents.planner import PlanningAgent
from src.agents.implementation import ImplementationAgent
from src.patcher.generator import PatchGenerator
from src.patcher.validator import SearchReplaceValidator
from src.runner.compiler import CompilerRunner
from src.runner.tester import TestRunner
from src.analyzer.error_parser import ErrorParser
from src.analyzer.root_cause import RootCauseAnalyzer

class IterationController:
    def __init__(self, target_dir: str, llm_client: Any):
        self.target_dir = target_dir
        self.llm_client = llm_client
        
        # Initialize modules
        import os
        self.memory = RepairMemory(os.path.join(target_dir, ".agent_memory.json"))
        self.scanner = ProjectScanner(target_dir)
        self.dep_builder = DependencyBuilder(target_dir)
        self.sym_indexer = SymbolIndexer(target_dir)
        self.retriever = ContextRetriever(target_dir)
        
        self.planner = PlanningAgent(llm_client)
        self.implementer = ImplementationAgent(llm_client)
        
        self.compiler = CompilerRunner(target_dir)
        self.tester = TestRunner(target_dir)
        
        self.error_parser = ErrorParser()
        self.rc_analyzer = RootCauseAnalyzer(target_dir)
        
        self.patch_gen = PatchGenerator(llm_client)
        self.patch_val = SearchReplaceValidator()
        
        # Initialize Wiki
        from src.core.wiki import WikiSearcher
        self.wiki_searcher = WikiSearcher(self.memory.vault_dir)

    def run(self, task: str):
        # 1. Scan and Index
        manifest = self.scanner.scan()
        dep_graph = self.dep_builder.build_graph()
        self.sym_indexer.build_index()
        
        build_commands = manifest.get("build_commands", [])
        build_cmd = build_commands[0] if build_commands else "echo 'No build command detected'"
        
        test_commands = manifest.get("test_commands", [])
        test_cmd = test_commands[0] if test_commands else "echo 'No test command detected'"
        
        # Iteration Loop
        for i in range(1, MAX_ITERATIONS + 1):
            logger.start_iteration()
            print(f"--- Iteration {i} ---")
            
            # Context
            context = self.retriever.retrieve(task)
            context += "\n" + self.memory.get_context_string()
            
            # Query and append LLM Wiki Guidelines
            wiki_context = self.wiki_searcher.search(task)
            if wiki_context:
                context += "\n" + wiki_context
            
            # Plan
            plan = self.planner.plan(task, context, dep_graph)
            
            # Implement
            patch = self.implementer.implement(plan, context)
            
            # Validate
            apply_failed = False
            apply_error = ""
            
            if not self.patch_val.validate(patch):
                print("Patch validation failed. Skipping apply.")
                patch = ""
                apply_failed = True
                apply_error = "Validation Failed: You must use the EXACT block format requested (### OVERWRITE ALL:, <<<<, >>>>). Your output was missing required tags."
            
            # Extract and Apply Patch
            files_modified = []
            
            if patch:
                print("Applying SEARCH/REPLACE patch...")
                import re, os
                
                blocks = re.findall(r"### FILE:\s*(.+?)\n<<<<\n(.*?)\n====\n(.*?)\n>>>>", patch, re.DOTALL)
                overwrite_blocks = re.findall(r"### OVERWRITE ALL:\s*(.+?)\n<<<<\n(.*?)\n>>>>", patch, re.DOTALL)
                if not blocks and not overwrite_blocks:
                    apply_failed = True
                    apply_error = "Could not find valid SEARCH/REPLACE or OVERWRITE ALL blocks in the output."
                else:
                    for file_path, new_code in overwrite_blocks:
                        file_path = file_path.strip()
                        # Strip target directory prefix if present
                        dir_name = os.path.basename(os.path.normpath(self.target_dir))
                        if file_path.startswith(dir_name + "/") or file_path.startswith(dir_name + "\\"):
                            file_path = file_path[len(dir_name)+1:]
                            
                        if "test_" in file_path:
                            print(f"Skipping unauthorized patch to test file: {file_path}")
                            continue
                        full_path = os.path.join(self.target_dir, file_path)
                        os.makedirs(os.path.dirname(full_path), exist_ok=True)
                        with open(full_path, 'w', encoding='utf-8') as f:
                            f.write(new_code)
                        files_modified.append(file_path)
                        print(f"Overwrote file: {file_path}")
                        
                    for file_path, old_code, new_code in blocks:
                        file_path = file_path.strip()
                        # Strip target directory prefix if present
                        dir_name = os.path.basename(os.path.normpath(self.target_dir))
                        if file_path.startswith(dir_name + "/") or file_path.startswith(dir_name + "\\"):
                            file_path = file_path[len(dir_name)+1:]
                            
                        if "test_" in file_path:
                            print(f"Skipping unauthorized patch to test file: {file_path}")
                            continue
                        full_path = os.path.join(self.target_dir, file_path)
                        
                        if not os.path.exists(full_path):
                            # Create new file if old_code is empty or file doesn't exist
                            os.makedirs(os.path.dirname(full_path), exist_ok=True)
                            with open(full_path, 'w', encoding='utf-8') as f:
                                f.write(new_code)
                            files_modified.append(file_path)
                            print(f"Created new file: {file_path}")
                        else:
                            with open(full_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                                
                            if old_code:
                                pattern = re.escape(old_code.strip())
                                # Make all whitespace flexible (1 or more spaces/newlines matches any spaces/newlines)
                                pattern = re.sub(r'\\\s+', r'\\s*', pattern)
                                
                                if not re.search(pattern, content):
                                    apply_failed = True
                                    apply_error += f"\nCould not find the exact old code block in {file_path}. Make sure it exactly matches."
                                else:
                                    # Use a lambda to preserve the leading whitespace of the match if possible, or just replace it
                                    content = re.sub(pattern, new_code, content, count=1)
                            else:
                                content += "\n" + new_code # append if no old code
                                
                            with open(full_path, 'w', encoding='utf-8') as f:
                                f.write(content)
                                files_modified.append(file_path)
                                print(f"Patched file: {file_path}")
            
            # Compile / Test
            if apply_failed:
                # If apply fails, treat it as a compiler error so the LLM fixes its diff format
                comp_res = {
                    "success": False,
                    "stdout": "",
                    "stderr": f"SEARCH/REPLACE FAILED: Your patch format was corrupt or invalid.\n{apply_error}\nEnsure you use the exact format requested and that old_code perfectly matches existing file content."
                }
                test_res_str = ""
            else:
                comp_res = self.compiler.run(build_cmd)
                if comp_res["success"]:
                    test_res_str = self.tester.run_tests(test_cmd)
                    if "Tests Passed" not in test_res_str:
                        comp_res["success"] = False
                        comp_res["stderr"] += "\n" + test_res_str
                else:
                    test_res_str = ""
            
            if comp_res["success"] and "Failed" not in test_res_str:
                print("Build and Tests Passed!")
                logger.end_iteration(i, 0, 0.0, files_modified, "Passed", "Passed", True)
                break
            
            # Analyze Error
            parsed_error = self.error_parser.parse(comp_res["stdout"], comp_res["stderr"])
            root_cause = self.rc_analyzer.analyze(parsed_error, dep_graph)
            
            print("Errors detected:", root_cause)
            self.memory.add_error(root_cause)
            if patch:
                self.memory.add_failed_patch(patch)
                
            logger.end_iteration(i, 0, 0.0, files_modified, "Failed", "Failed", False)
            
        print("Workflow finished.")
