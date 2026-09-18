"""Tester for the nds course. Belongs in the checker fork, as
`checker/testers/nds.py`; `deploy/checker/README.md` has the two-line patch
that registers it.

It is deliberately thin. Everything that knows about labs — assembling the
scratch tree, the determinism scan, cmake, ctest, the seed offset — is
`nds-grade`, which ships in the grading image and runs by hand for a dry run.
What lives here is the checker's side of the contract: where the three
directories are, how long to wait, and what fraction of the score was earned.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..exceptions import BuildFailedError, ExecutionFailedError, TestsFailedError
from ..utils.print import print_info
from .tester import Tester


class NdsTester(Tester):

    SOURCE_FILES_EXTENSIONS = ['.cpp', '.hpp', '.proto']

    @dataclass
    class TaskTestConfig(Tester.TaskTestConfig):
        allow_change: list[str] = field(default_factory=lambda: ['src/*'])
        ctest_filter: str = ''
        sanitize: bool = True
        timeout: float = 1800.

        def __post_init__(self) -> None:
            assert self.ctest_filter, '.tester.json must name the graded tests'

    def _gen_build(  # type: ignore[override]
            self,
            test_config: TaskTestConfig,
            build_dir: Path,
            source_dir: Path,
            public_tests_dir: Path,
            private_tests_dir: Path,
            sandbox: bool = True,
            verbose: bool = False,
            normalize_output: bool = False,
    ) -> None:
        # nds-grade builds and tests in one pass, so the work happens in
        # _run_tests; what this stage owes it is the three directories.
        #
        # Resolved here, while the cwd is still the one `checker grade` was
        # started in: the driver hands out paths relative to it, and the
        # sandbox runs nds-grade from the build directory instead.
        self._nds_dirs = (source_dir.resolve(), public_tests_dir.resolve(),
                          private_tests_dir.resolve())

    def _clean_build(  # type: ignore[override]
            self,
            test_config: TaskTestConfig,
            build_dir: Path,
            verbose: bool = False,
    ) -> None:
        self._executor(['rm', '-rf', str(build_dir)], check=False, verbose=verbose)

    def _run_tests(  # type: ignore[override]
            self,
            test_config: TaskTestConfig,
            build_dir: Path,
            sandbox: bool = False,
            verbose: bool = False,
            normalize_output: bool = False,
    ) -> float:
        source_dir, public_tests_dir, private_tests_dir = self._nds_dirs
        # Under the sandbox nds-grade runs as nobody; build_dir is the one
        # place the checker has already made writable for it.
        report = build_dir / 'verdict.json'

        print_info('Building and running the graded suites...', color='orange')
        self._executor(
            ['nds-grade',
             '--source', str(source_dir),
             '--public', str(public_tests_dir),
             '--private', str(private_tests_dir),
             '--build', str(build_dir),
             '--ctest-filter', test_config.ctest_filter,
             '--sanitize', 'ON' if test_config.sanitize else 'OFF',
             '--report', str(report)],
            # A partial score is a normal outcome, not an execution failure.
            check=False,
            sandbox=sandbox,
            cwd=build_dir,
            verbose=True,
            capture_output=False,
            timeout=test_config.timeout,
        )

        if not report.exists():
            raise ExecutionFailedError('nds-grade left no verdict')
        result = json.loads(report.read_text())

        if result.get('reason') == 'build failed':
            raise BuildFailedError('Your solution does not compile')
        if result.get('reason') == 'determinism scan':
            raise TestsFailedError('Your solution uses something the course forbids')
        if not result['total']:
            raise TestsFailedError('No graded test ran')

        passed, total = result['passed'], result['total']
        print_info(f'{passed}/{total} graded tests passed '
                   f'(seed base {result["seed_base"]})',
                   color='green' if passed == total else 'orange')
        return passed / total
