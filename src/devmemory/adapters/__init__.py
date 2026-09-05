"""Adapters isolate external systems (git, Entire, test runners, Databricks).

Each returns normalized :mod:`devmemory.domain.models` types. The domain and
services layers never see a ``subprocess`` result, a git flag, or an Entire CLI
detail directly.
"""
