#!/usr/bin/env python3
"""Fill a Google Form with fake identity data and random Likert scores."""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from faker import Faker
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import sync_playwright


DEFAULT_URL = (
    "https://docs.google.com/forms/d/e/1FAIpQLSeioqvDe8jiZV8mfKIkpHW67IZntd0lW4W-P4Hgzt5fWO2CbQ/viewform"
)
AGE_OPTIONS = [
    "13 - 18 Tahun",
    "19 - 25 Tahun",
    "25 - 35 tahun",
    "35 - 45 Tahun",
    "Lebih dari 45 Tahun",
]
DOMICILE_OPTIONS = [
    "surabaya",
    "surabaya barat",
    "surabaya timur",
    "sidoarjo",
]
NEXT_BUTTON = re.compile(r"^(Berikutnya|Next)$", re.IGNORECASE)
SUBMIT_BUTTON = re.compile(r"^(Kirim|Submit)$", re.IGNORECASE)


@dataclass
class Identity:
    name: str
    age: str
    domicile: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Auto-fill the AT Koffie Lab questionnaire with fake identity data and "
            "random 3-5 Likert scores."
        )
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to JSON config file.",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Google Form view URL (overrides config file URL).",
    )
    parser.add_argument("--count", type=int, default=1, help="Number of form runs")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fill but do not submit. Default behavior is to submit.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode (default headless).",
    )
    parser.add_argument("--min-delay", type=float, default=0.15, help="Min delay (s)")
    parser.add_argument("--max-delay", type=float, default=0.55, help="Max delay (s)")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed")
    parser.add_argument(
        "--locale",
        default="id_ID",
        help="Faker locale for generated identity data",
    )
    parser.add_argument(
        "--min-run-delay",
        type=float,
        default=0.0,
        help="Min random delay in seconds after each successful submit.",
    )
    parser.add_argument(
        "--max-run-delay",
        type=float,
        default=10.0,
        help="Max random delay in seconds after each successful submit.",
    )
    return parser.parse_args()


def load_config(path: str) -> dict[str, object]:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    try:
        with config_path.open("r", encoding="utf-8") as fh:
            config = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Warning: failed to load config '{path}': {exc}", file=sys.stderr)
        return {}
    if not isinstance(config, dict):
        print(f"Warning: config '{path}' must be a JSON object.", file=sys.stderr)
        return {}
    return config


def pause(rng: random.Random, min_delay: float, max_delay: float) -> None:
    time.sleep(rng.uniform(min_delay, max_delay))


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def randomize_first_letter_case(text: str, rng: random.Random) -> str:
    if not text:
        return text
    if rng.choice([True, False]):
        return text[0].upper() + text[1:]
    return text[0].lower() + text[1:]


def build_identity(fake: Faker, rng: random.Random) -> Identity:
    domicile = randomize_first_letter_case(rng.choice(DOMICILE_OPTIONS), rng)
    return Identity(
        name=f"{fake.first_name()} {fake.last_name()}",
        age=rng.choice(AGE_OPTIONS),
        domicile=domicile,
    )


def get_title(card) -> str:
    title = ""
    try:
        title = card.locator("span.M7eMe").first.inner_text(timeout=200)
    except PlaywrightError:
        return ""
    return normalize(title)


def fill_named_text(card, keyword: str, value: str) -> bool:
    title = get_title(card)
    if keyword not in title:
        return False
    text_inputs = card.locator("input[type='text']:visible:not([disabled])")
    if text_inputs.count() == 0:
        return False
    text_inputs.first.fill(value)
    return True


def click_radio_by_label(card, label: str) -> bool:
    locator = card.locator(f"[role='radio'][aria-label='{label}']:visible")
    if locator.count() > 0:
        locator.first.click()
        return True
    radio = card.get_by_role("radio", name=label, exact=True)
    if radio.count() == 0:
        return False
    radio.first.click()
    return True


def fill_age(card, age_value: str, rng: random.Random) -> bool:
    title = get_title(card)
    if "usia" not in title:
        return False
    if click_radio_by_label(card, age_value):
        return True

    radios = card.locator("[role='radio']:visible")
    if radios.count() == 0:
        return False
    radios.nth(rng.randrange(radios.count())).click()
    return True


def is_likert_question(card) -> bool:
    radios = card.locator("[role='radio']:visible")
    return radios.count() >= 5


def fill_likert(card, rng: random.Random) -> bool:
    if not is_likert_question(card):
        return False

    # Skip already answered radio groups.
    checked = card.locator("[role='radio'][aria-checked='true']:visible")
    if checked.count() > 0:
        return False

    radios = card.locator("[role='radio']:visible")
    candidate_indexes: list[int] = []

    for idx in range(radios.count()):
        label = radios.nth(idx).get_attribute("aria-label") or ""
        if re.search(r"(^|\\D)(3|4|5)(\\D|$)", label):
            candidate_indexes.append(idx)

    # Fallback: choose among the 3rd-5th options by position.
    if not candidate_indexes:
        max_idx = radios.count() - 1
        candidate_indexes = [i for i in (2, 3, 4) if i <= max_idx]

    if not candidate_indexes:
        return False

    radios.nth(rng.choice(candidate_indexes)).click()
    return True


def fill_visible_page(
    page: Page,
    identity: Identity,
    rng: random.Random,
    min_delay: float,
    max_delay: float,
) -> dict[str, int]:
    result = {"name": 0, "domicile": 0, "age": 0, "likert": 0}
    cards = page.locator("div[role='listitem']:visible")
    count = cards.count()

    for idx in range(count):
        card = cards.nth(idx)
        try:
            if fill_named_text(card, "nama", identity.name):
                result["name"] += 1
                pause(rng, min_delay, max_delay)
                continue
            if fill_named_text(card, "domisili", identity.domicile):
                result["domicile"] += 1
                pause(rng, min_delay, max_delay)
                continue
            if fill_age(card, identity.age, rng):
                result["age"] += 1
                pause(rng, min_delay, max_delay)
                continue
            if fill_likert(card, rng):
                result["likert"] += 1
                pause(rng, min_delay, max_delay)
                continue
        except PlaywrightError:
            continue
    return result


def click_if_available(page: Page, button_name: re.Pattern[str]) -> bool:
    button = page.get_by_role("button", name=button_name)
    if button.count() == 0:
        return False
    try:
        button.first.click(timeout=1500)
    except PlaywrightError:
        return False
    return True


def run_once(
    page: Page,
    url: str,
    identity: Identity,
    rng: random.Random,
    min_delay: float,
    max_delay: float,
    min_run_delay: float,
    max_run_delay: float,
    should_submit: bool,
) -> None:
    page.goto(url, wait_until="domcontentloaded")
    pause(rng, min_delay, max_delay)

    filled = {"name": 0, "domicile": 0, "age": 0, "likert": 0}
    for _ in range(25):
        current = fill_visible_page(page, identity, rng, min_delay, max_delay)
        for key in filled:
            filled[key] += current[key]
        if click_if_available(page, NEXT_BUTTON):
            page.wait_for_timeout(rng.randint(300, 900))
            pause(rng, min_delay, max_delay)
            continue
        break

    print(
        "Filled fields:",
        f"name={filled['name']}",
        f"domicile={filled['domicile']}",
        f"age={filled['age']}",
        f"likert={filled['likert']}",
        flush=True,
    )

    if should_submit:
        submitted = click_if_available(page, SUBMIT_BUTTON)
        print(f"Submitted: {submitted}", flush=True)
        if submitted and max_run_delay > 0:
            post_submit_delay = rng.uniform(min_run_delay, max_run_delay)
            print(f"Post-submit delay: {post_submit_delay:.2f}s", flush=True)
            time.sleep(post_submit_delay)
        pause(rng, min_delay, max_delay)
    else:
        print("Dry-run mode: submission skipped.", flush=True)


def main() -> int:
    args = parse_args()
    if args.count < 1:
        print("--count must be >= 1", file=sys.stderr)
        return 1
    if args.min_delay < 0 or args.max_delay < 0:
        print("Delays must be >= 0", file=sys.stderr)
        return 1
    if args.min_delay > args.max_delay:
        print("--min-delay cannot be greater than --max-delay", file=sys.stderr)
        return 1
    if args.min_run_delay < 0 or args.max_run_delay < 0:
        print("--min-run-delay and --max-run-delay must be >= 0", file=sys.stderr)
        return 1
    if args.min_run_delay > args.max_run_delay:
        print("--min-run-delay cannot be greater than --max-run-delay", file=sys.stderr)
        return 1

    config = load_config(args.config)
    configured_url = config.get("url")
    if configured_url is not None and not isinstance(configured_url, str):
        print("Warning: config key 'url' must be a string.", file=sys.stderr)
        configured_url = None
    url = args.url or configured_url or DEFAULT_URL

    rng = random.Random(args.seed)
    fake = Faker(args.locale)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        context = browser.new_context()
        page = context.new_page()
        try:
            for run_idx in range(1, args.count + 1):
                identity = build_identity(fake, rng)
                print(
                    f"Run {run_idx}/{args.count}: "
                    f"name='{identity.name}', age='{identity.age}', domicile='{identity.domicile}'",
                    flush=True,
                )
                run_once(
                    page=page,
                    url=url,
                    identity=identity,
                    rng=rng,
                    min_delay=args.min_delay,
                    max_delay=args.max_delay,
                    min_run_delay=args.min_run_delay,
                    max_run_delay=args.max_run_delay,
                    should_submit=not args.dry_run,
                )
        finally:
            context.close()
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
