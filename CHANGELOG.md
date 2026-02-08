# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

### Changed

### Fixed

### Removed

## [0.1.0] - 2026-02-07

### Added
- Integration with eBay via SerpApi for product search and sold validation.
- Integration with AliExpress via Google Shopping (SerpApi) for stable sourcing data.
- Streamlit dashboard with product matching, margin calculation, and trend analysis.
- Robust price parsing using regex for universal currency handling.
- Diagnostic script (`debug_api.py`) for API verification.
- `.gitignore` for security and repository hygiene.

### Fixed
- Resolved `ModuleNotFoundError` for the local package.
- Fixed eBay sort parameters (`_sop`) to use correct numerical codes, resolving the "zero results" issue.
- Switched to `google-search-results` package for reliable class access.
- Bypassed AliExpress scraping blocks by switching to Google Shopping API source.
- Fixed `UnicodeEncodeError` in console outputs for Windows compatibility.

### Changed
- Updated default Streamlit filters to zero for better initial discovery from new data sources.
- Consolidated dependencies in `pyproject.toml`.
- Finalized v0.1.0 and pushed to GitHub.

Any behavior-changing pull request must update this file.
