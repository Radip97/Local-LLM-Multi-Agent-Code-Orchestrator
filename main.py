import patch_env
import argparse
import os
import sys
from rich.console import Console

from orchestrator import Orchestrator

console = Console()

def main():
    parser = argparse.ArgumentParser(description="Local LLM Multi-Agent Code Writing Workflow")
    parser.add_argument(
        "--target-dir", 
        type=str, 
        default=os.path.join(os.getcwd(), "target_workspace"),
        help="Path to the directory where code should be written (default: './target_workspace')"
    )
    parser.add_argument(
        "--prompt", 
        type=str, 
        help="The coding task description. If not provided, you will be prompted."
    )
    
    args = parser.parse_args()
    
    target_dir = args.target_dir
    prompt = args.prompt
    
    if not prompt:
        console.print("[bold cyan]Welcome to the Local LLM Multi-Agent Coding Workflow![/bold cyan]")
        console.print("Please describe the feature, refactor, or bugfix you want to implement.")
        try:
            prompt = input("\nCoding Task > ").strip()
        except KeyboardInterrupt:
            console.print("\n[yellow]Exiting.[/yellow]")
            sys.exit(0)
            
    if not prompt:
        console.print("[red]Error: Prompt cannot be empty.[/red]")
        sys.exit(1)
        
    orchestrator = Orchestrator(target_dir)
    try:
        success = orchestrator.run(prompt)
        if success:
            console.print("\n[bold green]✓ Done! All changes have been safely written to disk.[/bold green]")
        else:
            console.print("\n[bold red]✗ Workflow did not complete successfully.[/bold red]")
            sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Workflow interrupted by user. Exiting.[/yellow]")
        sys.exit(0)

if __name__ == "__main__":
    main()
