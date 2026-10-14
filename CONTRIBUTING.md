# Contributing to tabella

Thanks for your interest in contributing! This is a small plugin suite, so the process is lightweight.

## Reporting Issues

Before opening an issue, search [existing issues](https://github.com/dyiapanis/tabella/issues) to avoid duplicates.

**Bug reports** should include:
- OS and version (e.g. Ubuntu 24.04, macOS 15.2)
- Python version (`python --version`)
- Plugin version (`pip show tabella`)
- Minimal steps to reproduce
- Expected vs actual behavior
- Full error output if available

**Feature requests** should describe the use case, not just the solution.

## Submitting Pull Requests

1. Fork the repo and create a branch from `main`
2. Keep PRs focused — one feature or fix per PR
3. Test your changes end-to-end before submitting
4. Follow the existing code style (ruff/black formatting if configured)
5. Update documentation (README, docstrings) if your change affects usage
6. Write a clear commit message following [Conventional Commits](https://www.conventionalcommits.org/):
   - `fix(create): handle empty table cells in docx output`
   - `feat(convert): add epub to pdf conversion`
   - `docs: clarify DOCS_VENV_PYTHON setup`

## Development Setup

```bash
git clone git@github.com:dyiapanis/tabella.git
cd tabella
pip install -e ".[all,dev]"
```

### System Dependencies

- **convert module**: `pandoc` + `texlive-xetex` (`sudo apt install pandoc texlive-xetex`)
- **read module**: LiteParse (`pip install liteparse`)
- **create module**: all Python deps via `pip install -e ".[create]"`

## Project Structure

```
agent_docs/
├── __init__.py    # Config helpers (get_output_dir, get_docs_venv_python)
├── create.py      # Document generation (docx, xlsx, pptx, pdf, odt, ods, odp)
├── convert.py     # Format conversion via pandoc
└── read.py        # Text/metadata extraction via LiteParse
```

## Questions?

Open a [discussion](https://github.com/dyiapanis/tabella/discussions) or an issue with the `question` label.