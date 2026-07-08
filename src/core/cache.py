"""
src/core/cache.py
Implements caching for AST, dependencies, contexts, and prompt embeddings 
to avoid re-reading unchanged files.
"""

import os
import json
import hashlib
from typing import Dict, Any, Optional
from src.core.config import CACHE_DIR

class CacheManager:
    def __init__(self, target_dir: str):
        self.target_dir = target_dir
        self.cache_dir = os.path.join(target_dir, CACHE_DIR)
        self.file_hashes: Dict[str, str] = {}
        self.ast_cache: Dict[str, Any] = {}
        
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)
            
        self._load_hashes()

    def _get_hash_file(self) -> str:
        return os.path.join(self.cache_dir, "file_hashes.json")

    def _load_hashes(self):
        hash_file = self._get_hash_file()
        if os.path.exists(hash_file):
            try:
                with open(hash_file, 'r') as f:
                    self.file_hashes = json.load(f)
            except json.JSONDecodeError:
                self.file_hashes = {}

    def _save_hashes(self):
        with open(self._get_hash_file(), 'w') as f:
            json.dump(self.file_hashes, f, indent=2)

    def compute_file_hash(self, filepath: str) -> str:
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            buf = f.read()
            hasher.update(buf)
        return hasher.hexdigest()

    def is_file_changed(self, filepath: str) -> bool:
        """Checks if a file has changed since it was last cached."""
        if not os.path.exists(filepath):
            return True
        current_hash = self.compute_file_hash(filepath)
        rel_path = os.path.relpath(filepath, self.target_dir)
        return self.file_hashes.get(rel_path) != current_hash

    def update_file_cache(self, filepath: str):
        """Updates the stored hash for a file."""
        if os.path.exists(filepath):
            rel_path = os.path.relpath(filepath, self.target_dir)
            self.file_hashes[rel_path] = self.compute_file_hash(filepath)
            self._save_hashes()

    def get_ast(self, filepath: str) -> Optional[Any]:
        """Retrieve AST from cache if file is unchanged."""
        rel_path = os.path.relpath(filepath, self.target_dir)
        if not self.is_file_changed(filepath) and rel_path in self.ast_cache:
            return self.ast_cache[rel_path]
        return None

    def set_ast(self, filepath: str, ast_data: Any):
        """Store AST in cache and update file hash."""
        rel_path = os.path.relpath(filepath, self.target_dir)
        self.ast_cache[rel_path] = ast_data
        self.update_file_cache(filepath)
