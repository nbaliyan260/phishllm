"""Reporting utilities: plots, tables, and the one-page case study."""

from .plots import generate_all_plots
from .tables import generate_all_tables
from .case_study import generate_case_study

__all__ = ["generate_all_plots", "generate_all_tables", "generate_case_study"]
