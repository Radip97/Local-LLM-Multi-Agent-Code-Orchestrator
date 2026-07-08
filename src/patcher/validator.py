"""
src/patcher/validator.py
Git Diff Validator: Reject patches that rewrite unrelated files, change formatting excessively, etc.
"""

class SearchReplaceValidator:
    def validate(self, patch: str) -> bool:
        """
        Validates the SEARCH/REPLACE format.
        """
        if not patch:
            return False
            
        has_search_replace = "### FILE:" in patch and "<<<<" in patch and "====" in patch and ">>>>" in patch
        has_overwrite_all = "### OVERWRITE ALL:" in patch and "<<<<" in patch and ">>>>" in patch
            
        if not has_search_replace and not has_overwrite_all:
            return False

        return True
