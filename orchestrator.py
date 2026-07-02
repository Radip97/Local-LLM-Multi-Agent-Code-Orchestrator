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
    def __init__(self, target_dir: str, files: list[str] = None):
        self.target_dir = os.path.abspath(target_dir)
        self.files = files
        if not os.path.exists(self.target_dir):
            os.makedirs(self.target_dir)
            console.print(f"[yellow]Created target directory: {self.target_dir}[/yellow]")
            
        self.planner = PlannerAgent()
        self.developer = DeveloperAgent()
        self.qa = QAAgent()

    def get_codebase_context(self, user_request: str = "") -> str:
        """
        Walks the target directory, reads files, and formats them into a single context string.
        Selects files based on explicit list or prompt keywords if the repository is large.
        """
        context_parts = []
        
        # 1. If files are explicitly specified, load ONLY those files
        if self.files:
            console.print(f"[cyan]Loading explicit context files: {self.files}[/cyan]")
            for rel_path in self.files:
                full_path = os.path.join(self.target_dir, rel_path)
                if not os.path.exists(full_path):
                    console.print(f"[yellow]Warning: Specified context file '{rel_path}' does not exist on disk.[/yellow]")
                    continue
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    context_parts.append(f"--- File: {rel_path} ---\n{content}\n----------------------")
                except Exception as e:
                    console.print(f"[red]Warning: Could not read {rel_path} ({e})[/red]")
            
            if not context_parts:
                return "(No valid files loaded from the explicit list.)"
            return "\n\n".join(context_parts)
            
        # 2. Walk directory to find all candidate files
        candidate_files = []
        for root, dirs, files in os.walk(self.target_dir):
            dirs[:] = [d for d in dirs if d not in config.IGNORE_DIRS]
            for file in files:
                _, ext = os.path.splitext(file)
                if ext.lower() in config.IGNORE_EXTENSIONS:
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.target_dir)
                candidate_files.append(rel_path)

        if not candidate_files:
            return "(Empty codebase. No files present yet.)"

        # 3. Dynamic RAG-Lite: Filter files if codebase is large
        selected_files = candidate_files
        if len(candidate_files) > 6 and user_request:
            prompt_words = set(re.findall(r'\w+', user_request.lower()))
            prompt_words = {w for w in prompt_words if len(w) > 2}
            
            matched_files = []
            for rel_path in candidate_files:
                path_parts = set(re.findall(r'\w+', rel_path.lower()))
                if prompt_words.intersection(path_parts):
                    matched_files.append(rel_path)
            
            if matched_files:
                selected_files = matched_files
                console.print(f"[cyan]RAG-Lite: Large codebase ({len(candidate_files)} files). Selected {len(selected_files)} relevant files: {selected_files}[/cyan]")
            else:
                selected_files = candidate_files[:6]
                console.print(f"[yellow]RAG-Lite: Large codebase. Loading first {len(selected_files)} files to fit context limit: {selected_files}[/yellow]")

        # 4. Load the selected files
        for rel_path in selected_files:
            full_path = os.path.join(self.target_dir, rel_path)
            try:
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                context_parts.append(f"--- File: {rel_path} ---\n{content}\n----------------------")
            except Exception as e:
                console.print(f"[red]Warning: Could not read {rel_path} ({e})[/red]")

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

    def verify_syntax(self, file_content: str, filepath: str) -> tuple[bool, str]:
        """
        Verifies if the code content is syntactically valid python.
        Returns (is_valid, error_message).
        """
        if not filepath.endswith(".py"):
            return True, ""
            
        try:
            compile(file_content, filepath, 'exec')
            return True, ""
        except SyntaxError as e:
            error_msg = f"SyntaxError in {filepath} at line {e.lineno}, column {e.offset}:\n{e.text}\nError: {e.msg}"
            return False, error_msg
        except Exception as e:
            return False, f"Compilation failed: {e}"

    def should_route_direct(self, prompt: str) -> bool:
        """
        Determines if the request is informational/conversational and should
        bypass the full multi-agent planning/QA loop.
        """
        p = prompt.strip().lower()
        
        # Conversational / investigative phrases at start
        question_starters = (
            "explain", "what", "why", "how does", "how do", "where", 
            "who", "which", "tell me", "describe", "document", "show me",
            "read", "analyze", "list"
        )
        
        return p.startswith(question_starters)

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
        # Fast Path Query Routing
        # ----------------------------------------------------
        if self.should_route_direct(user_request):
            console.print("\n[bold green]=== FAST PATH: DIRECT QUERY ROUTED ===[/bold green]")
            codebase_context = self.get_codebase_context(user_request)
            
            with console.status("[cyan]Querying model directly...[/cyan]"):
                system_prompt = "You are a helpful programming assistant. Answer the user's question directly and concisely based on the provided codebase context."
                user_prompt = f"### Codebase Context:\n{codebase_context}\n\n### User Question:\n{user_request}"
                direct_response = self.planner.call_llm(system_prompt, user_prompt, temperature=0.2)
                
            console.print(Panel(Markdown(direct_response), title="Direct Response", border_style="green"))
            return True

        # ----------------------------------------------------
        # Phase 1: Planning Loop
        # ----------------------------------------------------
        console.print("\n[bold yellow]=== PHASE 1: PLANNING ===[/bold yellow]")
        
        codebase_context = self.get_codebase_context(user_request)
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
                codebase_context = self.get_codebase_context(user_request)
        
        if not approved_plan:
            console.print("[red]QA rejected all plan attempts. Aborting workflow.[/red]")
            return F        # ----------------------------------------------------
        # Phase 2: Development & Coding Loop (Incremental Sub-tasks)
        # ----------------------------------------------------
        console.print("\n[bold yellow]=== PHASE 2: DEVELOPMENT ===[/bold yellow]")
        
        # Parse checklist items from approved plan
        sub_tasks = re.findall(r'\d+\.\s*\[\s*\]\s*(.*)', approved_plan)
        if not sub_tasks:
            sub_tasks = [user_request]
            console.print("[cyan]No sub-task checklist found in the approved plan. Treating the whole request as a single task.[/cyan]")
        else:
            console.print(f"[cyan]Parsed {len(sub_tasks)} sub-tasks from the plan checklist:[/cyan]")
            for i, task in enumerate(sub_tasks, 1):
                console.print(f"  {i}. {task}")
                
        for step_idx, sub_task in enumerate(sub_tasks, 1):
            console.print(Panel(f"[bold cyan]Executing Sub-task {step_idx}/{len(sub_tasks)}: {sub_task}[/bold cyan]", border_style="cyan"))
            
            approved_code = None
            dev_history = ""
            files_to_write = []
            
            sub_task_instruction = f"Current Step to Implement (Step {step_idx} of {len(sub_tasks)}): {sub_task}"
            
            for iteration in range(1, config.MAX_CODE_ITERATIONS + 1):
                console.print(f"\n[bold]Development Iteration {iteration}/{config.MAX_CODE_ITERATIONS}[/bold]")
                
                # Fetch fresh codebase context containing all changes from previous steps
                codebase_context = self.get_codebase_context(user_request)
                
                # 1. Developer implements changes for this step
                with console.status(f"[cyan]Developer is implementing Step {step_idx}...[/cyan]"):
                    code_changes = self.developer.write_code(
                        user_request=f"{user_request}\n\n{sub_task_instruction}",
                        approved_plan=approved_plan,
                        codebase_context=codebase_context,
                        developer_history=dev_history
                    )
                    
                console.print(Panel(Markdown(code_changes), title=f"Developer Output (Step {step_idx} - Iteration {iteration})"))
                
                # 1.5 Local compiler syntax validation
                files_to_validate = self.parse_file_blocks(code_changes)
                syntax_errors = []
                for rel_path, file_content in files_to_validate:
                    is_valid, error_msg = self.verify_syntax(file_content, rel_path)
                    if not is_valid:
                        syntax_errors.append(error_msg)
                        
                if syntax_errors:
                    error_summary = "\n\n".join(syntax_errors)
                    console.print(Panel(f"[bold red]Local compiler check failed![/bold red]\n{error_summary}", title="Syntax Validation Error", border_style="red"))
                    dev_history += f"\n\n[Iteration {iteration} Syntax Error Traceback]\n{error_summary}"
                    continue
                
                # 2. QA reviews the generated code for this step
                with console.status(f"[cyan]QA is reviewing Developer code for Step {step_idx}...[/cyan]"):
                    qa_response = self.qa.review_code(
                        user_request=f"{user_request}\n\n{sub_task_instruction}",
                        approved_plan=approved_plan,
                        code_changes=code_changes,
                        codebase_context=codebase_context
                    )
                    
                is_approved, feedback = self.parse_qa_decision(qa_response)
                console.print(Panel(qa_response, title=f"QA Code Review (Step {step_idx} - Iteration {iteration})", border_style="green" if is_approved else "red"))
                
                if is_approved:
                    files_to_write = self.parse_file_blocks(code_changes)
                    if not files_to_write:
                        console.print("[red]QA approved but no valid file blocks (<file path='...'>) were found in the output. Rejecting locally.[/red]")
                        dev_history += f"\n\n[Iteration {iteration} System Notice]\nNo file blocks parsed. You must output files wrapped in <file path='...'>...</file> tags containing the complete updated file content."
                        continue
                        
                    approved_code = code_changes
                    console.print(f"[bold green]✓ Step {step_idx} approved by QA![/bold green]")
                    break
                else:
                    console.print(f"[yellow]✗ Code changes rejected. Feeding feedback back to developer.[/yellow]")
                    dev_history += f"\n\n[Iteration {iteration} QA Feedback]\n{feedback}"
                    
            if not approved_code:
                console.print(f"[red]QA rejected all developer attempts for Step {step_idx}. Aborting workflow.[/red]")
                return False
                
            # Apply changes for this step to disk so subsequent steps read them
            console.print(f"\n[bold yellow]=== APPLYING CHANGES FOR STEP {step_idx} ===[/bold yellow]")
            self.write_files_to_disk(files_to_write)

        console.print("[bold green]✓ Workflow completed successfully![/bold green]")
        return True
