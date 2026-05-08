"""
src/workflows/__init__.py
=========================
Marks the workflows directory as a Python package and re-exports the two
top-level workflow classes for convenient importing.

  from workflows import IngestionWorkflow, GitPublisherWorkflow
"""

from .ingestion import IngestionWorkflow
from .publisher import GitPublisherWorkflow

__all__ = ["IngestionWorkflow", "GitPublisherWorkflow"]
