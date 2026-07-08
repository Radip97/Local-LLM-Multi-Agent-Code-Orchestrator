import os
import re
from typing import List, Dict

class WikiSearcher:
    def __init__(self, vault_dir: str):
        self.wiki_dir = os.path.join(vault_dir, "Wiki")
        self.stop_words = {
            'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 'any', 'are', 'as', 'at', 
            'be', 'because', 'been', 'before', 'being', 'below', 'between', 'both', 'but', 'by', 'can', 'did', 'do', 
            'does', 'doing', 'down', 'during', 'each', 'few', 'for', 'from', 'further', 'had', 'has', 'have', 'having', 
            'he', 'her', 'here', 'hers', 'herself', 'him', 'himself', 'his', 'how', 'i', 'if', 'in', 'into', 'is', 
            'it', 'its', 'itself', 'me', 'more', 'most', 'my', 'myself', 'no', 'nor', 'not', 'of', 'off', 'on', 'once', 
            'only', 'or', 'other', 'our', 'ours', 'ourselves', 'out', 'over', 'own', 'same', 'she', 'should', 'so', 
            'some', 'such', 'than', 'that', 'the', 'their', 'theirs', 'them', 'themselves', 'then', 'there', 'these', 
            'they', 'this', 'those', 'through', 'to', 'too', 'under', 'until', 'up', 'very', 'was', 'we', 'were', 
            'what', 'when', 'where', 'which', 'while', 'who', 'whom', 'why', 'with', 'you', 'your', 'yours', 'yourself', 'yourselves'
        }

    def search(self, task_description: str) -> str:
        """
        Scans the Wiki directory for markdown files matching keywords in the task description.
        Returns a formatted markdown string of all matched Wiki notes to inject into the LLM prompt.
        """
        if not os.path.exists(self.wiki_dir):
            return ""

        # Extract search keywords from task
        words = re.findall(r'[a-zA-Z0-9_-]+', task_description.lower())
        keywords = {w for w in words if w not in self.stop_words and len(w) > 2}

        if not keywords:
            return ""

        matched_notes: Dict[str, str] = {}

        try:
            for file_name in os.listdir(self.wiki_dir):
                if not file_name.endswith(".md"):
                    continue

                note_name = file_name[:-3]
                file_path = os.path.join(self.wiki_dir, file_name)

                # Check if note name matches any keywords
                note_name_lower = note_name.lower()
                is_match = any(kw in note_name_lower for kw in keywords)

                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # If name didn't match, scan file content keywords
                if not is_match:
                    content_lower = content.lower()
                    # Count how many keywords appear in the content
                    match_count = sum(1 for kw in keywords if kw in content_lower)
                    # If at least 2 keywords match, or 1 highly specific word matches
                    if match_count >= 1:
                        is_match = True

                if is_match:
                    matched_notes[note_name] = content

        except Exception as e:
            print(f"[Wiki Search Warning] Failed to scan wiki: {e}")

        if not matched_notes:
            return ""

        # Format matches for LLM prompt context injection
        context_str = "--- REFERENCED WIKI NOTES ---\n"
        for title, body in matched_notes.items():
            context_str += f"### WIKI NOTE: {title}\n"
            context_str += f"{body}\n\n"
        context_str += "-----------------------------\n\n"

        return context_str
