import os
import re
import sys
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live

import config
from agents.planner import PlannerAgent
from agents.developer import DeveloperAgent
from agents.qa import QAAgent

console = Console()

class Orchestrator:
    def __init__(self, target_dir: str):
        self.target_dir = os.path.abspath(target_dir)
        if not os.path.exists(self.target_dir):
            os.makedirs(self.target_dir)
            console.print(f"[yellow]Created target directory: {self.target_dir}[/yellow]")
            
        self.planner = PlannerAgent()
        self.developer = DeveloperAgent()
        self.qa = QAAgent()

    def get_codebase_context(self) -> str:
        """
        Walks the target directory, reads files, and formats them into a single context string.
        """
        context_parts = []
        for root, dirs, files in os.walk(self.target_dir):
            # Prune directories in place
            dirs[:] = [d for d in dirs if d not in config.IGNORE_DIRS]
            
            for file in files:
                _, ext = os.path.splitext(file)
                if ext.lower() in config.IGNORE_EXTENSIONS:
                    continue
                    
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.target_dir)
                
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    context_parts.append(f"--- File: {rel_path} ---\n{content}\n----------------------")
                except Exception as e:
                    console.print(f"[red]Warning: Could not read {rel_path} ({e})[/red]")
                    
        if not context_parts:
            return "(Empty codebase. No files present yet.)"
            
        return "\n\n".join(context_parts)

    def parse_qa_decision(self, response: str) -> tuple[bool, str]:
        """
        Parses QA response to check if it approved or rejected, along with feedback.
        Returns (is_approved, feedback_details).
        """
        is_approved = False
        feedback = ""
        
        # Look for DECISION line
        match = re.search(r"DECISION:\s*(APPROVED|REJECTED)", response, re.IGNORECASE)
        if match:
            decision = match.group(1).upper()
            is_approved = (decision == "APPROVED")
            
        # Extract everything after FEEDBACK: if rejected
        feedback_match = re.search(r"FEEDBACK:\s*([\s\S]*)", response, re.IGNORECASE)
        if feedback_match:
            feedback = feedback_match.group(1).strip()
        else:
            # Fallback: if rejected but no feedback marker, use entire response minus the decision
            feedback = response.replace(f"DECISION: {decision}" if match else "", "").strip()
            
        return is_approved, feedback

    def parse_file_blocks(self, content: str) -> list[tuple[str, str]]:
        """
        Parses xml file blocks from the developer agent's response.
        Returns a list of (filepath, content) tuples.
        """
        pattern = r'<file\s+path=["\']([^"\']+)["\']>\s*([\s\S]*?)\s*</file>'
        return re.findall(pattern, content)

    def write_files_to_disk(self, files: list[tuple[str, str]]):
        """
        Writes parsed file blocks to the target directory.
        """
        for rel_path, file_content in files:
            # Ensure path is safe/relative
            rel_path = os.path.normpath(rel_path)
            if os.path.isabs(rel_path) or rel_path.startswith(".."):
                console.print(f"[red]Error: Agent attempted to write to unsafe path: {rel_path}[/red]")
                continue
                
            full_path = os.path.join(self.target_dir, rel_path)
            parent_dir = os.path.dirname(full_path)
            if not os.path.exists(parent_dir):
                os.makedirs(parent_dir)
                
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(file_content)
            console.print(f"[green]✓ Wrote file: {rel_path}[/green]")

    def run(self, user_request: str):
        console.print(Panel(f"[bold blue]Starting Agent Workflow[/bold blue]\n[bold]Target Directory:[/bold] {self.target_dir}\n[bold]Task:[/bold] {user_request}", title="Local Agent Orchestrator"))

        # Verify API is working by calling get_model on one of the agents
        with console.status("[cyan]Connecting to local LLM server...[/cyan]") as status:
            try:
                active_model = self.planner.get_model()
                console.print(f"[green]Connected successfully! Using model: [bold]{active_model}[/bold][/green]")
            except Exception as e:
                console.print(f"[red]Error: Could not connect to local LLM server at {config.API_BASE_URL}. Ensure LM Studio/Ollama is running. Details: {e}[/red]")
                sys.exit(1)

        # ----------------------------------------------------
        # Phase 1: Planning Loop
        # ----------------------------------------------------
        console.print("\n[bold yellow]=== PHASE 1: PLANNING ===[/bold yellow]")
        
        codebase_context = self.get_codebase_context()
        approved_plan = None
        plan_history = []
        
        for iteration in range(1, config.MAX_PLAN_ITERATIONS + 1):
            console.print(f"\n[bold]Planning Iteration {iteration}/{config.MAX_PLAN_ITERATIONS}[/bold]")
            
            # 1. Planner drafts plan
            with console.status("[cyan]Planner is drafting implementation plan...[/cyan]"):
                proposed_plan = self.planner.plan(user_request, codebase_context)
                
            console.print(Panel(Markdown(proposed_plan), title=f"Proposed Plan (Iteration {iteration})"))
            
            # 2. QA reviews plan
            with console.status("[cyan]QA is reviewing proposed plan...[/cyan]"):
                qa_response = self.qa.review_plan(user_request, proposed_plan, codebase_context)
                
            is_approved, feedback = self.parse_qa_decision(qa_response)
            console.print(Panel(qa_response, title=f"QA Review Result (Iteration {iteration})", border_style="green" if is_approved else "red"))
            
            if is_approved:
                approved_plan = proposed_plan
                console.print("[bold green]✓ Implementation plan approved by QA![/bold green]")
                break
            else:
                console.print(f"[yellow]✗ Plan rejected. Feeding feedback back to planner.[/yellow]")
                plan_history.append(f"--- Iteration {iteration} proposed plan ---\n{proposed_plan}\n\nQA Feedback:\n{feedback}")
                # Combine user request with planning history for next iteration
                user_request_with_history = f"{user_request}\n\nPlanning History:\n" + "\n\n".join(plan_history)
                # We update the codebase context just in case, but it remains the same
                codebase_context = self.get_codebase_context()
        
        if not approved_plan:
            console.print("[red]QA rejected all plan attempts. Aborting workflow.[/red]")
            return False

        # ----------------------------------------------------
        # Phase 2: Development & Coding Loop
        # ----------------------------------------------------
        console.print("\n[bold yellow]=== PHASE 2: DEVELOPMENT ===[/bold yellow]")
        
        approved_code = None
        dev_history = ""
        files_to_write = []
        
        for iteration in range(1, config.MAX_CODE_ITERATIONS + 1):
            console.print(f"\n[bold]Development Iteration {iteration}/{config.MAX_CODE_ITERATIONS}[/bold]")
            
            # 1. Developer implements changes
            with console.status("[cyan]Developer is implementing changes...[/cyan]"):
                code_changes = self.developer.write_code(
                    user_request=user_request,
                    approved_plan=approved_plan,
                    codebase_context=codebase_context,
                    developer_history=dev_history
                )
                
            # Render a summary of what the developer did without printing full massive file dumps if they are long
            console.print(Panel(Markdown(code_changes), title=f"Developer Output (Iteration {iteration})"))
            
            # 2. QA reviews the generated code
            with console.status("[cyan]QA is reviewing developer code...[/cyan]"):
                qa_response = self.qa.review_code(
                    user_request=user_request,
                    approved_plan=approved_plan,
                    code_changes=code_changes,
                    codebase_context=codebase_context
                )
                
            is_approved, feedback = self.parse_qa_decision(qa_response)
            console.print(Panel(qa_response, title=f"QA Code Review (Iteration {iteration})", border_style="green" if is_approved else "red"))
            
            if is_approved:
                # Validate if developer actually output valid file blocks
                files_to_write = self.parse_file_blocks(code_changes)
                if not files_to_write:
                    console.print("[red]QA approved but no valid file blocks (<file path='...'>) were found in the output. Rejecting locally.[/red]")
                    dev_history += f"\n\n[Iteration {iteration} Code Output]\n{code_changes}\n\nSystem Notice: No file blocks parsed. You must output files wrapped in <file path='...'>...</file> tags containing the complete updated file content."
                    continue
                    
                approved_code = code_changes
                console.print("[bold green]✓ Code changes approved by QA![/bold green]")
                break
            else:
                console.print(f"[yellow]✗ Code changes rejected. Feeding feedback back to developer.[/yellow]")
                dev_history += f"\n\n[Iteration {iteration} Code Output]\n{code_changes}\n\nQA Feedback:\n{feedback}"
                
        if not approved_code:
            console.print("[red]QA rejected all developer code attempts. Aborting workflow.[/red]")
            return False

        # ----------------------------------------------------
        # Phase 3: Applying Code Changes
        # ----------------------------------------------------
        console.print("\n[bold yellow]=== PHASE 3: APPLYING CHANGES ===[/bold yellow]")
        self.write_files_to_disk(files_to_write)
        console.print("[bold green]✓ Workflow completed successfully![/bold green]")
        return True
