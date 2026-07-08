"""
src/core/memory.py
Tracks previous errors, failed fixes, and successful fixes to avoid repeating mistakes.
"""

import json
import os
from typing import List, Dict, Any



class RepairMemory:
    def __init__(self, memory_file: str = ".agent_memory.json"):
        self.memory_file = memory_file
        self.previous_errors: List[str] = []
        self.failed_patches: List[str] = []
        self.successful_patches: List[str] = []
        
        # Setup Obsidian Vault path dynamically
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.vault_dir = os.path.join(base_dir, 'obsidian_vault')
        
        # Determine Project Name
        target_dir = os.path.dirname(os.path.abspath(self.memory_file))
        self.project_name = os.path.basename(os.path.normpath(target_dir))
        
        self.load()

    def load(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.previous_errors = data.get("previous_errors", [])
                    self.failed_patches = data.get("failed_patches", [])
                    self.successful_patches = data.get("successful_patches", [])
            except json.JSONDecodeError:
                pass
        
        # Sync with Obsidian Vault on startup
        self.sync_obsidian_vault()

    def save(self):
        data = {
            "previous_errors": self.previous_errors,
            "failed_patches": self.failed_patches,
            "successful_patches": self.successful_patches
        }
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            
        # Sync with Obsidian Vault
        self.sync_obsidian_vault()

    def sync_obsidian_vault(self):
        try:
            # Create core Obsidian directories
            projects_dir = os.path.join(self.vault_dir, "Projects", self.project_name)
            learnings_dir = os.path.join(self.vault_dir, "Learnings")
            wiki_dir = os.path.join(self.vault_dir, "Wiki")
            
            os.makedirs(projects_dir, exist_ok=True)
            os.makedirs(learnings_dir, exist_ok=True)
            os.makedirs(wiki_dir, exist_ok=True)
            
            # Create default Coding Guidelines in Wiki if empty
            guidelines_file = os.path.join(wiki_dir, "Coding_Guidelines.md")
            if not os.path.exists(guidelines_file):
                with open(guidelines_file, 'w', encoding='utf-8') as f:
                    f.write("# Coding Guidelines & Best Practices\n\nWrite your project architectural rules, templates, and libraries guidelines here.\nThe agent will read and reference this wiki during execution.\n")

            # 1. Write Project index.md
            index_path = os.path.join(projects_dir, "index.md")
            with open(index_path, 'w', encoding='utf-8') as f:
                f.write(f"# Project Index: {self.project_name}\n\n")
                f.write("## Run Metrics\n")
                f.write(f"- **Errors Logged:** {len(self.previous_errors)}\n")
                f.write(f"- **Failed Patches:** {len(self.failed_patches)}\n")
                f.write(f"- **Successful Patches:** {len(self.successful_patches)}\n\n")
                f.write("## Linked Learnings\n")
                f.write(f"- [[{self.project_name}_errors]]\n")
                f.write(f"- [[{self.project_name}_success]]\n")

            # 2. Write Learnings: Errors
            errors_path = os.path.join(learnings_dir, f"{self.project_name}_errors.md")
            with open(errors_path, 'w', encoding='utf-8') as f:
                f.write(f"# Error Log & Diagnoses: {self.project_name}\n\n")
                f.write("Back to project: [[index]]\n\n")
                if not self.previous_errors:
                    f.write("No errors logged yet.\n")
                else:
                    for i, error in enumerate(self.previous_errors, 1):
                        f.write(f"### Error {i}\n")
                        f.write("```text\n")
                        f.write(f"{error}\n")
                        f.write("```\n\n")

            # 3. Write Learnings: Success
            success_path = os.path.join(learnings_dir, f"{self.project_name}_success.md")
            with open(success_path, 'w', encoding='utf-8') as f:
                f.write(f"# Successful Patches: {self.project_name}\n\n")
                f.write("Back to project: [[index]]\n\n")
                if not self.successful_patches:
                    f.write("No successful patches logged yet.\n")
                else:
                    for i, patch in enumerate(self.successful_patches, 1):
                        f.write(f"### Patch {i}\n")
                        f.write("```diff\n")
                        f.write(f"{patch}\n")
                        f.write("```\n\n")
                        
        except Exception as e:
            print(f"[Obsidian Sync Warning] Failed to update vault notes: {e}")

    def add_error(self, error_summary: str):
        if error_summary not in self.previous_errors:
            self.previous_errors.append(error_summary)
            self.save()

    def add_failed_patch(self, patch_diff: str):
        if patch_diff not in self.failed_patches:
            self.failed_patches.append(patch_diff)
            self.save()

    def add_successful_patch(self, patch_diff: str):
        if patch_diff not in self.successful_patches:
            self.successful_patches.append(patch_diff)
            self.save()
            
    def get_context_string(self) -> str:
        """Returns a string formatted for the LLM to understand what NOT to do."""
        ctx = ""
        if self.previous_errors:
            ctx += "PREVIOUS ERRORS ENCOUNTERED:\n" + "\n".join(self.previous_errors[-5:]) + "\n\n"
        if self.failed_patches:
            ctx += "FAILED PATCHES (DO NOT REPEAT):\n" + "\n".join(self.failed_patches[-3:]) + "\n\n"
        return ctx
