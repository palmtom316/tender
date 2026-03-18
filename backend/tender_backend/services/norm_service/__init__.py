"""norm_service — Standard/regulation PDF processing pipeline.

Modules:
  layout_compressor  — page-level text window construction
  scope_splitter     — chapter / commentary boundary detection
  prompt_builder     — LLM prompt templates for clause extraction
  tree_builder       — flat entries → hierarchical clause tree
  norm_processor     — orchestrator: compress → split → AI → merge → persist
"""
