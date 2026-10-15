"""Cost ledger: append-only JSONL priced against a versioned price table.

Row shape matches engine-decision/recommendation.md so the catalog backend
can ingest it as-is:
    (ts, user_id, job_id, artefact_id, provider, model, unit, qty,
     unit_price, usd, price_table)
Per-asset, per-kit and per-user totals are just group-bys over these rows.
"""
from __future__ import annotations

import json
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .generators.base import Usage


class Unpriced(KeyError):
    pass


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class PriceTable:
    version: str
    prices: tuple[tuple[str, str, str, float], ...]   # (provider, model, unit, usd per unit)
    placeholders: frozenset[tuple[str, str, str]] = frozenset()

    @classmethod
    def load(cls, path: str | Path) -> "PriceTable":
        raw = tomllib.loads(Path(path).read_text())
        return cls(
            version=str(raw["meta"]["version"]),
            prices=tuple((p["provider"], p["model"], p["unit"], float(p["usd"])) for p in raw["price"]),
            placeholders=frozenset((p["provider"], p["model"], p["unit"]) for p in raw["price"] if p.get("placeholder")),
        )

    def unit_price(self, u: Usage) -> float:
        for provider, model, unit, usd in self.prices:
            if (provider, model, unit) == (u.provider, u.model, u.unit):     # exact, like the catalog
                return usd
        raise Unpriced(f"no price for provider={u.provider} model={u.model} unit={u.unit} "
                       f"in price table {self.version}")

    def cost(self, usage: list[Usage]) -> float:
        return sum(self.unit_price(u) * u.qty for u in usage)


@dataclass(frozen=True)
class LedgerRow:
    ts: str
    user_id: str
    job_id: str
    artefact_id: str
    provider: str
    model: str
    unit: str
    qty: float
    unit_price: float
    usd: float
    price_table: str


class Ledger:
    def __init__(self, path: Path, prices: PriceTable, user_id: str, job_id: str, budget_usd: float | None):
        self.path, self.prices = path, prices
        self.user_id, self.job_id, self.budget_usd = user_id, job_id, budget_usd
        self.spent_this_job = 0.0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def check(self, estimate: list[Usage], what: str) -> float:
        """Budget is enforced before generation, never after."""
        est = self.prices.cost(estimate)
        if self.budget_usd is not None and self.spent_this_job + est > self.budget_usd + 1e-12:
            raise BudgetExceeded(f"{what}: estimated ${est:.4f} would exceed job budget "
                                 f"${self.budget_usd:.4f} (spent ${self.spent_this_job:.4f})")
        return est

    def record(self, artefact_id: str, usage: list[Usage]) -> list[LedgerRow]:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = []
        for u in usage:
            up = self.prices.unit_price(u)
            rows.append(LedgerRow(ts, self.user_id, self.job_id, artefact_id, u.provider, u.model,
                                  u.unit, u.qty, up, round(up * u.qty, 6), self.prices.version))
        with self.path.open("a") as f:
            for r in rows:
                f.write(json.dumps(asdict(r)) + "\n")
        self.spent_this_job += sum(r.usd for r in rows)
        return rows


def read_rows(path: Path) -> list[LedgerRow]:
    if not path.exists():
        return []
    return [LedgerRow(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


def sync_prices(client, path: Path) -> list[str]:
    """Add rows the catalog lacks or prices differently (non-local only).
    The catalog keeps history by effective_from, so this never edits a row."""
    table = PriceTable.load(path)
    rows = sorted(client.prices(), key=lambda p: (p["effective_from"], p["id"]))   # latest wins
    current = {(p["provider"], p["model"], p["unit"]): p["usd_per_unit"] for p in rows}
    done = []
    for provider, model, unit, usd in table.prices:
        if provider == "local":
            continue
        key = (provider, model, unit)
        if key in current and abs(current[key] - usd) < 1e-12:
            continue
        note = f"terrella_assets prices.toml {table.version}" + (" PLACEHOLDER, not a quote" if key in table.placeholders else "")
        client.add_price(provider, model, unit, usd, note)
        done.append(f"{provider}/{model}/{unit} = {usd} ({note})")
    return done
