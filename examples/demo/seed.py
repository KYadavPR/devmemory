"""Build a self-contained DevMemory demo repository.

    python examples/demo/seed.py /tmp/devmemory-demo
    cd /tmp/devmemory-demo
    devmemory history
    devmemory serve

Creates a small `pricing` package and records six Development Versions across
three features - including two regressions and a repeated failed approach - so
every dashboard view and `devmemory` command has something real to show.

Requires `pip install -e ".[dev]"` (or `pip install devmemory`) first.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

CORE_V0 = '''\
"""Pricing core."""


def base_rate(region):
    return {"us": 1.0, "eu": 1.1, "apac": 0.9}.get(region, 1.0)


def apply_discount(amount, region):
    return amount * base_rate(region) * 0.95


def line_total(qty, unit_price, region):
    return apply_discount(qty * unit_price, region)


def cart_total(items, region):
    return sum(line_total(i["qty"], i["price"], region) for i in items)


def quote(customer, items):
    return {"customer": customer["id"], "total": cart_total(items, customer["region"])}
'''

INVOICE_V0 = '''\
from pricing.core import apply_discount, line_total


def invoice_row(item, region):
    return {"sku": item["sku"], "amount": line_total(item["qty"], item["price"], region)}


def refund_amount(item, region):
    return apply_discount(item["price"], region)
'''


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python examples/demo/seed.py <target-dir>")
    root = Path(sys.argv[1]).resolve()
    if root.exists():
        if input(f"{root} exists - delete and recreate? [y/N] ").strip().lower() != "y":
            sys.exit("aborted")
        shutil.rmtree(root)
    root.mkdir(parents=True)

    demo = Demo(root)
    demo.git("init", "-q", "-b", "main")
    demo.git("config", "user.email", "demo@example.com")
    demo.git("config", "user.name", "DevMemory Demo")
    demo.git("config", "commit.gpgsign", "false")

    demo.write("pricing/__init__.py", "")
    demo.write("pricing/core.py", CORE_V0)
    demo.write("pricing/invoice.py", INVOICE_V0)
    demo.write("metrics.json", json.dumps({"quote_latency_ms": 42}))
    demo.commit("chore: initial pricing package")

    demo.devmemory("init", "--name", "Pricing", "--project-id", "pricing")
    cfg = root / ".devmemory" / "config.json"
    data = json.loads(cfg.read_text())
    data["metrics"] = {"file": "metrics.json"}
    data["graph"] = {"enabled": True}  # harmless if the plugin isn't installed
    cfg.write_text(json.dumps(data, indent=2))
    demo.commit("chore: enable devmemory")

    from devmemory.domain.enums import VersionStatus
    from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
    from devmemory.services.context import ProjectContext

    ctx = ProjectContext.load(root)

    def checkpoint(intent: str, feature: str, status: VersionStatus | None = None) -> None:
        run_checkpoint(
            ctx,
            CheckpointRequest(
                allow_no_entire=True,
                intent=intent,
                feature=feature,
                status=status,
                tests_passed=24,
                tests_failed=0,
            ),
        )

    # v1 - Tax: a clean feature add
    demo.write(
        "pricing/core.py",
        CORE_V0
        + "\n\ndef with_tax(amount, region):\n"
        "    rate = 0.2 if region == 'eu' else 0.08\n"
        "    return amount * (1 + rate)\n",
    )
    demo.commit("feat(pricing): add a regional tax helper")
    checkpoint("Add a with_tax helper for regional tax rates", "Tax", VersionStatus.SUCCESS)

    # v2 - Discounts: signature change, latency regression
    core = (root / "pricing" / "core.py").read_text()
    core = core.replace(
        "def apply_discount(amount, region):\n    return amount * base_rate(region) * 0.95",
        "def apply_discount(amount, region, *, tier='standard'):\n"
        "    mult = {'standard': 0.95, 'premium': 0.90}[tier]\n"
        "    return amount * base_rate(region) * mult",
    ).replace(
        "    return apply_discount(qty * unit_price, region)",
        "    return apply_discount(qty * unit_price, region, tier='standard')",
    )
    demo.write("pricing/core.py", core)
    demo.write("metrics.json", json.dumps({"quote_latency_ms": 47}))
    demo.commit("refactor(pricing): add discount tiers")
    checkpoint("Add a tier parameter to apply_discount", "Discounts", VersionStatus.REGRESSION)

    # v3 - Discounts: a failed retry that touches the same files again
    demo.write("pricing/core.py", core.replace("'premium': 0.90", "'premium': 0.80"))
    demo.write("metrics.json", json.dumps({"quote_latency_ms": 49}))
    demo.commit("fix(pricing): widen premium discount to offset the change")
    checkpoint("Widen the premium discount to win back the regression", "Discounts",
               VersionStatus.REGRESSION)

    # v4 - Discounts: the real fix
    demo.write(
        "pricing/invoice.py",
        INVOICE_V0.replace(
            '    return apply_discount(item["price"], region)',
            '    return apply_discount(item["price"], region, tier="standard")',
        ),
    )
    demo.write("metrics.json", json.dumps({"quote_latency_ms": 43}))
    demo.commit("fix(pricing): update the invoice caller for the new signature")
    checkpoint("Fix refund_amount to pass the new tier argument", "Discounts",
               VersionStatus.SUCCESS)

    # v5 - Rounding: a clean feature
    demo.write(
        "pricing/core.py",
        (root / "pricing" / "core.py").read_text()
        + "\n\ndef rounded(amount):\n    return round(amount + 1e-9, 2)\n",
    )
    demo.commit("feat(pricing): round money to cents")
    checkpoint("Round all money values to two decimal places", "Rounding", VersionStatus.SUCCESS)

    # v6 - Rounding: a metric win
    demo.write("metrics.json", json.dumps({"quote_latency_ms": 38}))
    demo.write(
        "pricing/core.py",
        (root / "pricing" / "core.py").read_text().replace(
            'return sum(line_total(i["qty"], i["price"], region) for i in items)',
            "return round(sum(line_total(i[\"qty\"], i[\"price\"], region) for i in items), 2)",
        ),
    )
    demo.commit("perf(pricing): fold rounding into cart_total")
    checkpoint("Compute cart_total in one pass with rounding", "Rounding", VersionStatus.SUCCESS)

    ctx.close()
    print(f"\nDone. {root}\n")
    print("  cd", root)
    print("  devmemory history")
    print("  devmemory analytics")
    print("  devmemory serve")


class Demo:
    def __init__(self, root: Path) -> None:
        self.root = root

    def git(self, *args: str) -> None:
        subprocess.run(
            ["git", "-c", "core.autocrlf=false", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
        )

    def devmemory(self, *args: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "devmemory", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
        )

    def write(self, rel: str, content: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-m", message, "--no-verify")


if __name__ == "__main__":
    main()
