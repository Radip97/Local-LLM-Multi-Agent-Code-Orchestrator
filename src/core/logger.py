"""
src/core/logger.py
Comprehensive logging for duration, tokens, cost, and files modified.
"""

import logging
import time
import json
from dataclasses import dataclass, asdict
from typing import List, Optional

@dataclass
class IterationLog:
    iteration_number: int
    duration_sec: float
    total_tokens: int
    llm_cost: float
    files_modified: List[str]
    compiler_result: str
    test_result: str
    success: bool

class AgentLogger:
    def __init__(self, log_file: str = "agent_run.log"):
        self.logger = logging.getLogger("AgentOrchestrator")
        self.logger.setLevel(logging.DEBUG)
        
        # File handler
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(fh)
            self.logger.addHandler(ch)
            
        self.iterations: List[IterationLog] = []
        self._start_time = None

    def start_iteration(self):
        self._start_time = time.time()
        self.info("Starting new iteration...")

    def end_iteration(self, iter_num: int, tokens: int, cost: float, files: List[str], 
                      compile_res: str, test_res: str, success: bool):
        duration = time.time() - self._start_time if self._start_time else 0
        log_entry = IterationLog(
            iteration_number=iter_num,
            duration_sec=duration,
            total_tokens=tokens,
            llm_cost=cost,
            files_modified=files,
            compiler_result=compile_res,
            test_result=test_res,
            success=success
        )
        self.iterations.append(log_entry)
        self.info(f"Iteration {iter_num} finished in {duration:.2f}s. Success: {success}")
        
    def dump_metrics(self, path: str = "agent_metrics.json"):
        with open(path, "w") as f:
            json.dump([asdict(i) for i in self.iterations], f, indent=2)

    def info(self, msg: str):
        self.logger.info(msg)

    def error(self, msg: str):
        self.logger.error(msg)
        
    def debug(self, msg: str):
        self.logger.debug(msg)

# Global logger instance
logger = AgentLogger()
