"""Output folder for report tables, figures and the evidence registry, kept OUTSIDE the repository.

Default: ~/Documents/Siyaq_GP_Report   (override with the environment variable SIYAQ_REPORT_DIR)
    figures/                       images inserted into the report (generated)
    tables/                        Markdown copies of the result tables (generated, for checking)
    evidence_registry.csv          source of every number in the report
    (verified references are in the repository: docs/references.bib)
"""
import os
from pathlib import Path

REPORT_DIR = Path(os.environ.get("SIYAQ_REPORT_DIR", Path.home() / "Documents" / "Siyaq_GP_Report")).expanduser()
FIGURES = REPORT_DIR / "figures"
TABLES = REPORT_DIR / "tables"
REPORT_DOCX = REPORT_DIR / "Siyaq_GP_Report_Updated.docx"


def ensure():
    FIGURES.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
