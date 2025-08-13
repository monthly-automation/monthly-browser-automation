## Prerequisites

- Python 3.11 or higher
- pip (Python package manager)


## Run to start

1. `.venv\Scripts\activate`
2. `pip install -r requirements.txt`
3. `playwright install`
4. `python main.py`


## Extra Information

When working on this project, keep the following files and directories in mind:

- `browser-automation/` – Contains the automation scripts for Amazon and Bol.com. Update or add scripts here for new automation tasks.
- `main.py` – The main entry point that orchestrates the automation and email sending. Any changes to the workflow should be reflected here.
- `requirements.txt` – Lists all Python dependencies. Add any new packages here and keep it up to date.
- `.github/workflows/monthly.yml` – GitHub Actions workflow for scheduled automation. Update this if you change environment variables, dependencies, or the automation schedule.
- `.env` variables are in GitHub secrets.

## Automations

### Bol
Uses account client id with api credentials to retrieve files through api calls.

### Amazon
The api is not available for this so a `playwright` script is used to simulate a headless browser that follows the similar steps a user would. 
