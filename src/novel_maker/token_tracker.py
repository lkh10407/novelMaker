"""Token Tracker — monitors API token usage and estimated cost.

Records per-agent, per-chapter token counts and provides
a Rich-formatted summary for the CLI.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from rich.table import Table

logger = logging.getLogger(__name__)

# Approximate pricing for Gemini 2.5 Flash (USD per 1M tokens)
# These are rough estimates — update as pricing changes.
PRICING = {
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
}


class TokenTracker:
    """Accumulates and reports token usage across the pipeline."""

    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name
        self.records: list[dict] = []
        self._totals = {"input": 0, "output": 0}

    def record(
        self,
        agent: str,
        chapter: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record a single API call's token usage."""
        entry = {
            "agent": agent,
            "chapter": chapter,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        self.records.append(entry)
        self._totals["input"] += input_tokens
        self._totals["output"] += output_tokens
        logger.debug(
            "Tokens [%s ch%d]: in=%d out=%d",
            agent, chapter, input_tokens, output_tokens,
        )

    @property
    def total_input(self) -> int:
        return self._totals["input"]

    @property
    def total_output(self) -> int:
        return self._totals["output"]

    @property
    def total_tokens(self) -> int:
        return self.total_input + self.total_output

    @property
    def estimated_cost_usd(self) -> float:
        """Estimate cost in USD based on model pricing."""
        prices = PRICING.get(self.model_name, PRICING["gemini-2.5-flash"])
        cost_in = (self.total_input / 1_000_000) * prices["input"]
        cost_out = (self.total_output / 1_000_000) * prices["output"]
        return cost_in + cost_out

    def get_summary_table(self) -> Table:
        """Build a Rich Table summarizing usage by agent."""
        table = Table(title="📊 토큰 사용량", show_lines=True)
        table.add_column("에이전트", style="cyan")
        table.add_column("입력 토큰", justify="right", style="green")
        table.add_column("출력 토큰", justify="right", style="yellow")
        table.add_column("합계", justify="right", style="bold")

        # Aggregate by agent
        by_agent: dict[str, dict[str, int]] = {}
        for rec in self.records:
            agent = rec["agent"]
            if agent not in by_agent:
                by_agent[agent] = {"input": 0, "output": 0}
            by_agent[agent]["input"] += rec["input_tokens"]
            by_agent[agent]["output"] += rec["output_tokens"]

        for agent, counts in by_agent.items():
            total = counts["input"] + counts["output"]
            table.add_row(
                agent,
                f"{counts['input']:,}",
                f"{counts['output']:,}",
                f"{total:,}",
            )

        table.add_row(
            "[bold]합계[/bold]",
            f"[bold]{self.total_input:,}[/bold]",
            f"[bold]{self.total_output:,}[/bold]",
            f"[bold]{self.total_tokens:,}[/bold]",
        )

        return table

    def save(self, output_dir: Path) -> Path:
        """Persist usage data to JSON."""
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "token_usage.json"
        data = {
            "model": self.model_name,
            "total_input_tokens": self.total_input,
            "total_output_tokens": self.total_output,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
            "records": self.records,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Token usage saved: %s", path)
        return path
