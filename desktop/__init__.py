"""ARVEN desktop application (frontend around the existing ARVEN backend).

The desktop package implements the *application shell* only:
  UI view state -> AppController -> existing Brain/AgentLoop -> existing tools.

It does NOT re-implement any intelligence, memory, actions, voice engines etc.
Those all live in the existing ARVEN backend and are reused as-is.
"""
