"""CLI entry point for NovelMaker.

Usage:
    python -m novel_maker "로그라인"
    python -m novel_maker "로그라인" --chapters 5 --model gemini-2.5-flash
    python -m novel_maker "로그라인" --resume output/checkpoint_ch2_finalized.json
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from .models import ChapterResult
from .workflow import NovelPipeline

console = Console()


def _build_status_panel(
    phase: str,
    chapter: int = 0,
    total: int = 0,
    revision: int = 0,
    errors: list[str] | None = None,
    tracker=None,
) -> Panel:
    """Build a Rich panel showing current pipeline status."""
    lines: list[str] = []
    lines.append(f"[bold cyan]📝 Chapter {chapter}/{total}[/bold cyan]")

    phase_icons = {
        "planning": "🗺️  기획 중...",
        "writing": "✍️  집필 중...",
        "checking": "🔍 검수 중...",
        "refining": f"🔧 교정 중... (Rev {revision})",
        "updating_state": "💾 상태 업데이트 중...",
        "replanning": "🔄 줄거리 재조정 중...",
        "done": "✅ 완료!",
        "resumed": f"♻️  체크포인트에서 재개 (Ch {chapter})",
    }
    lines.append(phase_icons.get(phase, f"⏳ {phase}"))

    if errors:
        lines.append(f"[red]오류: {', '.join(errors)}[/red]")

    if tracker:
        cost = tracker.estimated_cost_usd
        lines.append(f"[dim]토큰: {tracker.total_tokens:,} (≈ ${cost:.4f})[/dim]")

    return Panel(
        "\n".join(lines),
        title="[bold]📖 NovelMaker[/bold]",
        border_style="blue",
    )


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="NovelMaker — AI 멀티 에이전트 소설 자동 집필 시스템",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "logline",
        type=str,
        help="소설의 로그라인 (한 줄 아이디어)",
    )
    parser.add_argument(
        "--chapters",
        type=int,
        default=3,
        help="생성할 챕터 수 (기본: 3)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Gemini 모델 (기본: gemini-2.5-flash)",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="ko",
        help="소설 언어 (기본: ko)",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="체크포인트 파일에서 이어쓰기",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output",
        help="출력 디렉토리 (기본: output)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="상세 로그 출력",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load environment
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        console.print(
            "[bold red]❌ GOOGLE_API_KEY 환경변수가 설정되지 않았습니다.[/bold red]\n"
            "[dim]https://aistudio.google.com/ 에서 API 키를 발급받으세요.[/dim]\n"
            "[dim].env 파일에 GOOGLE_API_KEY=your_key 형태로 추가하세요.[/dim]"
        )
        sys.exit(1)

    model = args.model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    output_dir = Path(args.output)
    resume_path = Path(args.resume) if args.resume else None

    # Initialize Gemini client
    client = genai.Client(api_key=api_key)

    # Build pipeline
    pipeline = NovelPipeline(
        client=client,
        model=model,
        output_dir=output_dir,
    )

    # Rich live display state
    live_state = {
        "phase": "planning",
        "chapter": 0,
        "total": args.chapters,
        "revision": 0,
        "errors": [],
    }

    def on_phase_change(phase: str, **kwargs):
        live_state["phase"] = phase
        live_state.update(kwargs)

    def on_chapter_complete(ch_num: int, result: ChapterResult):
        console.print(
            f"  [green]✅ {ch_num}장 완료[/green] "
            f"({result.char_count}자) — {result.summary}"
        )

    pipeline.on_phase_change = on_phase_change
    pipeline.on_chapter_complete = on_chapter_complete

    # Header
    console.print()
    console.print(
        Panel(
            f"[bold]📖 NovelMaker v0.1[/bold]\n\n"
            f"로그라인: [cyan]{args.logline}[/cyan]\n"
            f"챕터: {args.chapters}장 | 모델: {model} | 언어: {args.lang}",
            border_style="blue",
        )
    )

    # Run the pipeline
    try:
        final_state = asyncio.run(
            pipeline.run(
                logline=args.logline,
                total_chapters=args.chapters,
                language=args.lang,
                resume_from=resume_path,
            )
        )

        # Print summary
        console.print("\n")
        console.print("[bold green]✨ 소설 생성 완료![/bold green]\n")

        # Token usage table
        console.print(pipeline.tracker.get_summary_table())
        console.print(
            f"\n[dim]예상 비용: ${pipeline.tracker.estimated_cost_usd:.4f} USD[/dim]"
        )

        # Output files
        console.print(f"\n📁 출력 파일:")
        console.print(f"  - 전체 원고: [cyan]{output_dir / 'novel.md'}[/cyan]")
        console.print(f"  - 상태 로그: [cyan]{output_dir / 'state_log.json'}[/cyan]")
        console.print(f"  - 토큰 사용량: [cyan]{output_dir / 'token_usage.json'}[/cyan]")

        for ch in final_state.chapters_written:
            console.print(f"  - {ch.chapter}장: [cyan]{output_dir / f'chapter_{ch.chapter:02d}.md'}[/cyan]")

    except KeyboardInterrupt:
        console.print("\n[yellow]⏸️  중단됨. 체크포인트에서 이어서 실행할 수 있습니다.[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]❌ 오류 발생: {e}[/bold red]")
        if args.verbose:
            console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
