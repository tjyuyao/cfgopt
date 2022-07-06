
## Invoke pytest


```bash
pip install pytest pytest-cov
cd <cfgopt_repo_root>/tests
pytest --cov=../cfgopt --cov-report html
```

Coverage report is in htmlcov subdir. With "Live Server" plugin in VSCode you can preview the `index.html` file.

## Tests organization

Each new feature can be organized in a new subdirectory, with its config subdirs and test scripts.