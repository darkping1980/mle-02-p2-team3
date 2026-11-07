"""청크 표본 선정, 프롬프트 크기 추정, 추출 배치 실행 명령."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .batch import run_batch, summarize_batch
from .diagnose import diagnose_empty_results
from .llm_adapter import create_llm_call
from .pilot import estimate_prompt_size, select_pilot_chunks
from .verify import verify_results
from .locate_diagnose import diagnose_locations, TYPES
from .relocate import relocate_results
from .eval.variance import compare_variance

_REPO_ROOT = Path(__file__).resolve().parents[5]


def _outside_repo(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == _REPO_ROOT or _REPO_ROOT in resolved.parents:
        raise ValueError("출력 경로는 저장소 밖에 지정해야 합니다.")
    return resolved


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    select = commands.add_parser("select", help="결정적 시범 청크 목록을 만든다")
    select.add_argument("--index-csv", type=Path, required=True)
    select.add_argument("--chunk-dir", type=Path, required=True)
    select.add_argument("--count", type=int, default=10)
    select.add_argument("--seed", type=int, default=17)
    select.add_argument("--output", type=Path, required=True)

    estimate = commands.add_parser("estimate", help="선정 청크 프롬프트 크기를 계산한다")
    estimate.add_argument("--chunk-dir", type=Path, required=True)
    estimate.add_argument("--chunk-ids", type=Path, required=True, help="select가 만든 JSON 배열")

    summarize = commands.add_parser("summarize", help="기존 결과 JSON만 다시 집계한다(LLM 호출 없음)")
    summarize.add_argument("--chunk-dir", type=Path, required=True)
    summarize.add_argument("--output-dir", type=Path, required=True, help="기존 결과 JSON 폴더")
    summarize.add_argument("--chunk-ids", type=Path, help="지정 시 해당 청크 결과만 집계")

    run = commands.add_parser("run", help="드라이런 또는 명시적 실제 호출")
    run.add_argument("--chunk-dir", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--chunk-ids", type=Path, help="select가 만든 JSON 배열 (지정 시 해당 청크만 처리)")
    run.add_argument("--model")
    run.add_argument("--temperature", type=float)
    run.add_argument("--api-key-env", default="OPENAI_API_KEY")
    run.add_argument("--max-chunks", type=int, default=5)
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--retries", type=int, default=2)
    run.add_argument("--no-fail-fast", action="store_true", help="반복 비재시도 오류에 대한 배치 중단을 끈다")
    run.add_argument("--max-estimated-tokens", type=int, default=200000)
    run.add_argument("--allow-large", action="store_true")
    run.add_argument("--execute", action="store_true", help="실제 LLM 호출을 허용")

    verify = commands.add_parser("verify", help="저장된 결과의 거친 자동 점검 신호를 만든다")
    verify.add_argument("--result-dir", type=Path, required=True)
    verify.add_argument("--chunk-dir", type=Path, required=True)
    verify.add_argument("--output-dir", type=Path, required=True)

    pilot_run = commands.add_parser("pilot-run", help="표본 선정부터 그래프 CSV까지 순서대로 수행")
    pilot_run.add_argument("--index-csv", type=Path, required=True)
    pilot_run.add_argument("--chunk-dir", type=Path, required=True)
    pilot_run.add_argument("--work-dir", type=Path, required=True)
    pilot_run.add_argument("--count", type=int, required=True)
    pilot_run.add_argument("--model", required=True)
    pilot_run.add_argument("--workers", type=int, default=1)
    pilot_run.add_argument("--execute", action="store_true")
    pilot_run.add_argument("--temperature", type=float)

    diagnose_locate = commands.add_parser("diagnose-locate", help="인용 위치 실패를 원문 없이 분류")
    diagnose_locate.add_argument("--result-dir", type=Path, required=True)
    diagnose_locate.add_argument("--chunk-dir", type=Path, required=True)
    diagnose_locate.add_argument("--output-dir", type=Path, required=True)

    relocate = commands.add_parser("relocate", help="공백·문장부호 차이만 보수적으로 위치 재탐색")
    relocate.add_argument("--result-dir", type=Path, required=True)
    relocate.add_argument("--chunk-dir", type=Path, required=True)
    relocate.add_argument("--output-dir", type=Path, required=True)

    variance = commands.add_parser("variance", help="반복 실행 결과의 청크별 편차 비교")
    variance.add_argument("--result-dirs", type=Path, nargs="+", required=True)
    variance.add_argument("--output-dir", type=Path, required=True)

    diagnose = commands.add_parser("diagnose-empty", help="빈 추출 결과를 원문 없이 분류한다")
    diagnose.add_argument("--chunk-dir", type=Path, required=True)
    diagnose.add_argument("--results-dir", type=Path, required=True)
    diagnose.add_argument("--output-dir", type=Path, required=True)

    result_a = commands.add_parser("result-a", help="DRAFT stage 7 Result A JSONL")
    result_a.add_argument("--result-dir", type=Path, required=True)
    result_a.add_argument("--chunk-dir", type=Path, required=True)
    result_a.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "select":
            output = _outside_repo(args.output)
            ids = select_pilot_chunks(args.index_csv, args.chunk_dir, args.count, args.seed)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(ids, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"chunks": len(ids), "output": str(output)}, ensure_ascii=False))
        elif args.command == "estimate":
            ids = json.loads(args.chunk_ids.read_text(encoding="utf-8"))
            print(json.dumps(estimate_prompt_size(ids, args.chunk_dir), ensure_ascii=False))
        elif args.command == "summarize":
            output = _outside_repo(args.output_dir)
            files = sorted(args.chunk_dir.glob("*.chunks.json"))
            ids = json.loads(args.chunk_ids.read_text(encoding="utf-8")) if args.chunk_ids else None
            result = summarize_batch(files, output, chunk_ids=ids)
            print(json.dumps({"documents": len(result["documents"]), "output_dir": str(output)}, ensure_ascii=False))
        elif args.command == "diagnose-empty":
            output = _outside_repo(args.output_dir)
            result = diagnose_empty_results(args.results_dir, args.chunk_dir, output)
            print(json.dumps({
                "empty_result_chunks": result["count"],
                "output": result["output"],
            }, ensure_ascii=False))
        elif args.command == "verify":
            output = _outside_repo(args.output_dir)
            result = verify_results(args.result_dir, args.chunk_dir, output)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        elif args.command == "diagnose-locate":
            output = _outside_repo(args.output_dir)
            result = diagnose_locations(args.result_dir, args.chunk_dir, output)
            print(json.dumps({"by_type": result["by_type"], "by_chunk": result["by_chunk"]}, ensure_ascii=False, sort_keys=True))
        elif args.command == "relocate":
            output = _outside_repo(args.output_dir)
            result = relocate_results(args.result_dir, args.chunk_dir, output)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        elif args.command == "variance":
            output = _outside_repo(args.output_dir)
            print(json.dumps(compare_variance(args.result_dirs, output), ensure_ascii=False, sort_keys=True))
        elif args.command == "pilot-run":
            from .pilot_run import run_pilot
            plan = run_pilot(args.index_csv, args.chunk_dir, args.work_dir, args.count,
                             args.model, args.workers, args.execute, args.temperature)
            print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        elif args.command == "result-a":
            from .result_a import export_result_a
            print(json.dumps(export_result_a(args.result_dir, args.chunk_dir, _outside_repo(args.output_dir)), ensure_ascii=False, sort_keys=True))
        else:
            output = _outside_repo(args.output_dir)
            files = sorted(args.chunk_dir.glob("*.chunks.json"))
            ids = json.loads(args.chunk_ids.read_text(encoding="utf-8")) if args.chunk_ids else None
            if args.execute:
                if not args.model:
                    raise ValueError("실제 호출에는 --model이 필요합니다.")
                estimate_ids = ids if ids is not None else [
                    chunk["chunk_id"] for path in files
                    for chunk in json.loads(path.read_text(encoding="utf-8")).get("chunks", [])
                ][:args.max_chunks]
                estimate = estimate_prompt_size(estimate_ids, args.chunk_dir)
                if estimate["estimated_tokens"] > args.max_estimated_tokens and not args.allow_large:
                    raise ValueError(f"예상 토큰 {estimate['estimated_tokens']}가 한도 {args.max_estimated_tokens}를 초과합니다. --allow-large로 허용하세요.")
                call = create_llm_call(args.model, args.api_key_env, temperature=args.temperature)
                result = run_batch(files, call, output, max_chunks=args.max_chunks, chunk_ids=ids,
                                   workers=args.workers, retries=args.retries, fail_fast=not args.no_fail_fast)
                print(json.dumps({"documents": len(result["documents"]), "output_dir": str(output)}, ensure_ascii=False))
            else:
                estimate_ids = ids if ids is not None else [
                    chunk["chunk_id"] for path in files
                    for chunk in json.loads(path.read_text(encoding="utf-8")).get("chunks", [])
                ][:args.max_chunks]
                print(json.dumps({"mode": "dry-run", **estimate_prompt_size(estimate_ids, args.chunk_dir)}, ensure_ascii=False))
                print("실제 호출을 하려면 --execute와 --model을 지정하세요.", file=sys.stderr)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
