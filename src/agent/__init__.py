"""src/agent/

Orchestrates test generation, execution, and reporting. Coordinates all analyzers,
generators, and runners into cohesive workflows.
"""

from src.agent.generate_command import run_generation, GenerationReport
from src.agent.core import run_loop, RunReport

__all__ = ["run_generation", "GenerationReport", "run_loop", "RunReport"]
