# Google Form Filler (Python)

Reads form URL from `config.json` by default.

Behavior:

- Generates fake identity data with Faker (`Nama`, `Domisili`)
- Name is generated as first + last name only (no degree suffix)
- Randomly selects an `Usia` option
- For each Likert question, randomly chooses score `3`, `4`, or `5`
- Adds a random delay after each successful submit (default `0..10s`)
- Supports multi-page forms (`Berikutnya`/`Next`)
- Submits by default

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Usage

Submit one response (default):

```bash
python form_filler.py --count 1
```

Use a different config file:

```bash
python form_filler.py --config my-config.json --count 1
```

Dry-run one pass (no submit):

```bash
python form_filler.py --count 1 --dry-run --headed
```

Useful options:

- `--config config.json`
- `--url <form-url>` (overrides config file)
- `--locale id_ID`
- `--seed 42`
- `--min-delay 0.2 --max-delay 0.8`
- `--min-run-delay 2 --max-run-delay 10`
- `--dry-run` (fills only, no submit)
- `--headed` (show browser window)

## Config

Default file is `config.json`:

```json
{
  "url": "https://docs.google.com/forms/d/e/1FAIpQLSeioqvDe8jiZV8mfKIkpHW67IZntd0lW4W-P4Hgzt5fWO2CbQ/viewform"
}
```
