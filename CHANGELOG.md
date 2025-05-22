# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-05-22

### Added
- Caching mechanism for PubMed API responses, configurable via command-line arguments (`--cache-file`, `--no-cache`).
- Command-line arguments for specifying cache file path and disabling caching.
- `LICENSE` file (MIT License).
- `CHANGELOG.md` file to track project changes.
- Enhanced docstrings and type hints throughout the `PubMedProcessor` class for better code understanding and maintainability.
- Usage of `pathlib` for all path manipulations, replacing `os.path`.
- Code formatting applied using `black`.

### Changed
- Major refactoring of the `PyRefPmid.py` script for improved readability, maintainability, and performance.
- Optimized citation processing:
    - `extract_pmid_groups` now returns span information for each PMID group.
    - `replace_citations` updated to use this span information for more accurate and efficient replacement of in-text citations.
- `PubMedProcessor.process_file` method signature updated to accept `Path` objects.
- Default reference item format (`DEFAULT_REFERENCE_ITEM_FORMAT`) updated to include a clickable PubMed link: `[{pubmed_id}](https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/)`.
- `README.md` updated with detailed usage instructions, information about caching, command-line arguments, license, and a link to the changelog.

### Removed
- Redundant `extract_pmids` method; its functionality was integrated into `extract_pmid_groups`.

### Fixed
- Ensured consistent use of `Path` objects for file paths internally.

## [0.1.0] - 2025-03-14

### Added
- Initial release of `PyRefPmid`.
- Feature to extract PMIDs from Markdown files using regular expressions.
- Feature to fetch publication details (title, authors, journal, year, DOI) from the PubMed API (Entrez).
- Feature to generate a "References" section at the end of the Markdown file, listing fetched publication details.
- Feature to replace in-text citations (e.g., `[PMID:123456, PMID:789012]`) with sequential numbers (e.g., `[1, 2]`).
- Basic command-line interface for specifying input and output files.
- Automatic detection of the header level for the "References" section based on existing headers in the input file.
- GUI file dialog for input file selection if no input file is provided via the command line.
