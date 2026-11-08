"""Generate the synthetic PulseBand dataset (100% fictional, seeded, reproducible).

Outputs to /data:
  members.csv      60 members (18 hand-built personas + 42 random)
  orders.csv       device + accessory orders
  prior_cases.csv  support history (drives replacement-limit and fraud rules)
  personas.csv     which policy edge case each persona exists to exercise

Personas are engineered relative to the policy "as-of" date in rules.yaml so
boundary cases (day 30 vs 31, last day of warranty, 10 vs 11 business days)
are exact and stay exact. Random members add realistic volume for the
dashboard.

Run:  python scripts/generate_data.py
"""

from __future__ import annotations

import random
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from faker import Faker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from triage.config import DATA_DIR, get_rules  # noqa: E402

SEED = 42
N_MEMBERS = 60

RULES = get_rules()
AS_OF = RULES.today()
WAREHOUSE_FOR = RULES.routing.region_to_warehouse

SIZES = ["S", "M", "L"]
COLORS = ["ONYX", "ARCTIC", "SAGE", "NAVY"]
CHARGER_SKU = "PB4-CHGR"

EU_COUNTRIES = ["Germany", "France", "Netherlands", "Spain", "Ireland", "Italy"]
COUNTRY_FOR_REGION = {"US": "United States", "CA": "Canada", "UK": "United Kingdom", "AU": "Australia"}
LOCALE_FOR_COUNTRY = {
    "United States": "en_US",
    "Canada": "en_CA",
    "United Kingdom": "en_GB",
    "Australia": "en_AU",
    "Germany": "de_DE",
    "France": "fr_FR",
    "Netherlands": "nl_NL",
    "Spain": "es_ES",
    "Ireland": "en_IE",
    "Italy": "it_IT",
}

OUTCOME_FOR_CATEGORY = {
    "troubleshooting": "resolved_troubleshooting",
    "warranty_replacement": "replacement_shipped",
    "return_remorse": "refund_issued",
    "shipping_delivery": "replacement_shipped",
    "billing_membership": "billing_adjusted",
    "other": "closed_no_action",
}


def device_sku(size: str, color: str) -> str:
    return f"PB4-{size}-{color}"


def band_sku(size: str, color: str) -> str:
    return f"BAND-{size}-{color}"


def business_days_ago(n: int) -> date:
    """Date d such that there are exactly n weekdays in [d, AS_OF)."""
    d = np.busday_offset(np.datetime64(AS_OF), -n, roll="backward").astype(date)
    assert np.busday_count(d, AS_OF) == n
    return d


def ascii_slug(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(ch for ch in normalized.lower() if ch.isalnum())


# -----------------------------------------------------------------------------
# Personas: fixed members that exercise each policy rule and boundary
# -----------------------------------------------------------------------------


@dataclass
class Persona:
    name: str
    country: str
    region: str
    status: str
    plan: str
    note: str
    delivered_ago: relativedelta | None = None  # None → device not yet delivered
    ordered_business_days_ago: int | None = None  # for in-transit orders
    sku: str = "PB4-M-ONYX"
    prior_cases: list[tuple[int, str]] = field(default_factory=list)  # (days_ago, category)


PERSONAS: list[Persona] = [
    Persona("Maya Patel", "United States", "US", "active", "annual",
            "Charging issue, already tried cable + reset → warranty replacement approved",
            delivered_ago=relativedelta(months=5)),
    Persona("Lukas Becker", "Germany", "EU", "active", "monthly",
            "Delivered 12 days ago → remorse return in window",
            delivered_ago=relativedelta(days=12), sku="PB4-L-SAGE"),
    Persona("Jordan Reyes", "United States", "US", "active", "monthly",
            "Delivered exactly 30 days ago → last eligible return day",
            delivered_ago=relativedelta(days=30), sku="PB4-S-ARCTIC"),
    Persona("Priya Shah", "United States", "US", "active", "monthly",
            "Delivered 31 days ago → return window just closed",
            delivered_ago=relativedelta(days=31), sku="PB4-S-NAVY"),
    Persona("Oliver Hughes", "United Kingdom", "UK", "active", "annual",
            "Sync issue, already re-paired, 18 months in → UK 24-month warranty replacement approved",
            delivered_ago=relativedelta(months=18), sku="PB4-L-ONYX"),
    Persona("Ethan Brooks", "United States", "US", "active", "monthly",
            "Vague message → human review (account is also outside 12-month US warranty)",
            delivered_ago=relativedelta(months=13)),
    Persona("Sofia Martinez", "United States", "US", "past_due", "monthly",
            "Past-due membership, 4 months in → resolve billing before RMA",
            delivered_ago=relativedelta(months=4), sku="PB4-S-SAGE"),
    Persona("Chloe Nguyen", "Australia", "AU", "active", "annual",
            "2 warranty replacements in last 12 months → manual review",
            delivered_ago=relativedelta(months=10), sku="PB4-M-ARCTIC",
            prior_cases=[(210, "warranty_replacement"), (100, "warranty_replacement")]),
    Persona("Liam Tremblay", "Canada", "CA", "active", "monthly",
            "No delivery scan after 14 business days → lost-package replacement",
            ordered_business_days_ago=14, sku="PB4-M-NAVY"),
    Persona("Ava Wilson", "United States", "US", "active", "annual",
            "In transit 6 business days → too early to replace",
            ordered_business_days_ago=6, sku="PB4-L-ARCTIC"),
    Persona("Daniel Kim", "United States", "US", "active", "annual",
            "Duplicate membership charge → billing queue",
            delivered_ago=relativedelta(months=8), sku="PB4-L-NAVY"),
    Persona("Camille Laurent", "France", "EU", "active", "monthly",
            "3 prior cases in last 90 days → possible-fraud escalation",
            delivered_ago=relativedelta(months=6), sku="PB4-S-ONYX",
            prior_cases=[(75, "shipping_delivery"), (45, "warranty_replacement"), (20, "troubleshooting")]),
    Persona("Noah de Vries", "Netherlands", "EU", "cancelled", "monthly",
            "Cancelled membership → not eligible for warranty replacement",
            delivered_ago=relativedelta(months=7)),
    Persona("Grace O'Connor", "Ireland", "EU", "active", "annual",
            "Use for safety scenarios (skin irritation) → urgent human review",
            delivered_ago=relativedelta(months=3), sku="PB4-S-SAGE"),
    Persona("Marcus Johnson", "United States", "US", "active", "monthly",
            "Delivered exactly 12 months ago → last day of US warranty",
            delivered_ago=relativedelta(months=12), sku="PB4-L-SAGE"),
    Persona("Emily Carter", "United States", "US", "active", "monthly",
            "Delivered 12 months + 1 day ago → US warranty expired yesterday",
            delivered_ago=relativedelta(months=12, days=1), sku="PB4-M-SAGE"),
    Persona("Ben Taylor", "Australia", "AU", "active", "monthly",
            "In transit exactly 10 business days → not yet lost (needs >10)",
            ordered_business_days_ago=10, sku="PB4-M-ONYX"),
    Persona("Giulia Rossi", "Italy", "EU", "active", "annual",
            "Delivered 25 months ago → outside even the 24-month EU warranty",
            delivered_ago=relativedelta(months=25), sku="PB4-S-ARCTIC"),
]


# -----------------------------------------------------------------------------
# Generation
# -----------------------------------------------------------------------------


class Generator:
    def __init__(self, seed: int = SEED) -> None:
        self.rng = random.Random(seed)
        self.fake = Faker(sorted(set(LOCALE_FOR_COUNTRY.values())))
        self.fake.seed_instance(seed)
        self.members: list[dict] = []
        self.orders: list[dict] = []
        self.cases: list[dict] = []
        self.personas: list[dict] = []
        self._emails: set[str] = set()

    # -- ids -------------------------------------------------------------------

    def _member_id(self) -> str:
        return f"M{len(self.members) + 1:04d}"

    def _order_id(self) -> str:
        return f"SO-{100001 + len(self.orders)}"

    def _case_id(self) -> str:
        return f"PC-{5001 + len(self.cases)}"

    def _email(self, name: str) -> str:
        parts = name.split()
        base = f"{ascii_slug(parts[0])}.{ascii_slug(parts[-1])}"
        email, n = f"{base}@example.com", 2
        while email in self._emails:
            email, n = f"{base}{n}@example.com", n + 1
        self._emails.add(email)
        return email

    # -- records ---------------------------------------------------------------

    def add_member(self, name, country, region, status, plan, start: date) -> str:
        member_id = self._member_id()
        self.members.append({
            "member_id": member_id,
            "name": name,
            "email": self._email(name),
            "country": country,
            "region": region,
            "membership_status": status,
            "membership_start_date": start.isoformat(),
            "plan": plan,
        })
        return member_id

    def add_order(self, member_id, region, order_date: date, delivered: date | None, sku: str) -> None:
        self.orders.append({
            "order_id": self._order_id(),
            "member_id": member_id,
            "order_date": order_date.isoformat(),
            "delivered_date": delivered.isoformat() if delivered else "",
            "sku": sku,
            "ship_from_warehouse": WAREHOUSE_FOR[region],
            "order_status": "delivered" if delivered else "in_transit",
        })

    def add_case(self, member_id, case_date: date, category: str) -> None:
        self.cases.append({
            "prior_case_id": self._case_id(),
            "member_id": member_id,
            "case_date": case_date.isoformat(),
            "category": category,
            "outcome": OUTCOME_FOR_CATEGORY[category],
        })

    # -- personas --------------------------------------------------------------

    def build_personas(self) -> None:
        for p in PERSONAS:
            if p.delivered_ago is not None:
                delivered = AS_OF - p.delivered_ago
                ordered = delivered - timedelta(days=self.rng.randint(3, 6))
            else:
                ordered = business_days_ago(p.ordered_business_days_ago)
                delivered = None

            member_id = self.add_member(p.name, p.country, p.region, p.status, p.plan, ordered)
            self.add_order(member_id, p.region, ordered, delivered, p.sku)
            for days_ago, category in p.prior_cases:
                self.add_case(member_id, AS_OF - timedelta(days=days_ago), category)
            self.personas.append({"member_id": member_id, "name": p.name, "scenario_note": p.note})

    # -- random members --------------------------------------------------------

    def _random_region(self) -> str:
        return self.rng.choices(["US", "EU", "UK", "CA", "AU"], weights=[35, 25, 15, 10, 15])[0]

    def build_random_members(self, count: int) -> None:
        for _ in range(count):
            region = self._random_region()
            country = self.rng.choice(EU_COUNTRIES) if region == "EU" else COUNTRY_FOR_REGION[region]
            locale_fake = self.fake[LOCALE_FOR_COUNTRY[country]]
            name = f"{locale_fake.first_name()} {locale_fake.last_name()}"
            status = self.rng.choices(["active", "past_due", "cancelled"], weights=[80, 10, 10])[0]
            plan = self.rng.choices(["monthly", "annual"], weights=[55, 45])[0]

            start = AS_OF - timedelta(days=self.rng.randint(60, 1000))
            member_id = self.add_member(name, country, region, status, plan, start)

            size, color = self.rng.choice(SIZES), self.rng.choice(COLORS)
            delivered = start + timedelta(days=self.rng.randint(3, 8))
            self.add_order(member_id, region, start, delivered, device_sku(size, color))

            if self.rng.random() < 0.3:
                acc_order = delivered + timedelta(days=self.rng.randint(20, max(21, (AS_OF - delivered).days - 10)))
                acc_sku = self.rng.choice([band_sku(size, self.rng.choice(COLORS)), CHARGER_SKU])
                self.add_order(member_id, region, acc_order, acc_order + timedelta(days=self.rng.randint(3, 7)), acc_sku)

            n_cases = self.rng.choices([0, 1, 2], weights=[55, 30, 15])[0]
            history_days = (AS_OF - delivered).days
            for _ in range(n_cases):
                case_date = delivered + timedelta(days=self.rng.randint(1, max(2, history_days - 1)))
                category = self.rng.choices(
                    list(OUTCOME_FOR_CATEGORY),
                    weights=[35, 15, 10, 15, 20, 5],
                )[0]
                self.add_case(member_id, case_date, category)

    # -- output ----------------------------------------------------------------

    def write(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "cache").mkdir(exist_ok=True)
        pd.DataFrame(self.members).to_csv(out_dir / "members.csv", index=False)
        pd.DataFrame(self.orders).sort_values("order_id").to_csv(out_dir / "orders.csv", index=False)
        pd.DataFrame(self.cases).sort_values(["member_id", "case_date"]).to_csv(
            out_dir / "prior_cases.csv", index=False
        )
        pd.DataFrame(self.personas).to_csv(out_dir / "personas.csv", index=False)


def main() -> None:
    gen = Generator()
    gen.build_personas()
    gen.build_random_members(N_MEMBERS - len(PERSONAS))
    gen.write(DATA_DIR)

    members = pd.DataFrame(gen.members)
    print(f"As-of date: {AS_OF}  (policy {RULES.policy.version}, seed {SEED})")
    print(f"members.csv      {len(gen.members):>3} rows  ({len(PERSONAS)} personas)")
    print(f"orders.csv       {len(gen.orders):>3} rows")
    print(f"prior_cases.csv  {len(gen.cases):>3} rows")
    print("\nMembers by region:", members["region"].value_counts().to_dict())
    print("Members by status:", members["membership_status"].value_counts().to_dict())
    print("Members by plan:  ", members["plan"].value_counts().to_dict())


if __name__ == "__main__":
    main()
