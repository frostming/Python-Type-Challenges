import glob
import io
import os
import re
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

from mypy import api

ROOT_DIR = Path(__file__).parent.parent
MYPY_CONFIG = ROOT_DIR / "pyproject.toml"


ChallengeName: TypeAlias = str
CODE_SPLITTER = "\n## End of your code ##\n"
EXPECT_ERROR_COMMENT = "expect-type-error"

# Each mypy error should look like: `<filename>:<line_number>: <error|note>: <message>`
# Here we only capture the error messages and line numbers
MYPY_MESSAGE_REGEX = r"^(?:.+?):(\d+):(\s*error:.+)$"


@dataclass
class Challenge:
    name: ChallengeName
    difficulty: str
    code: str
    user_code: str = field(default="", init=False)
    test_code: str = field(default="", init=False)

    def __post_init__(self):
        self.parse_code()

    def parse_code(self):
        self.user_code, _, self.test_code = self.code.partition(CODE_SPLITTER)


@dataclass(frozen=True, slots=True)
class ChallengeInfo:
    name: str
    difficulty: str


@dataclass(frozen=True, slots=True)
class TypeCheckResult:
    stdout: str
    stderr: str
    passed: bool


class ChallengeManager:
    def __init__(self):
        self.challenges = self._load_challenges()
        self.challenge_names = [
            ChallengeInfo(name=name, difficulty=c.difficulty)
            for name, c in self.challenges.items()
        ]

    def has_challenge(self, name: str) -> bool:
        return name in self.challenges

    def get_challenge(self, name: str) -> Challenge:
        return self.challenges[name]

    def run_challenge(self, name: str, user_code: str) -> TypeCheckResult:
        challenge = self.get_challenge(name)
        code = f"{user_code}\n{challenge.test_code}"
        return self._type_check_with_mypy(code)

    @staticmethod
    def _load_challenges() -> dict[ChallengeName, Challenge]:
        challenges = {}
        for filename in glob.glob(f"{ROOT_DIR}/challenges/*/question.py"):
            dir_name = os.path.basename(os.path.dirname(filename))
            difficulty, challenge_name = dir_name.split("-", maxsplit=1)
            with open(filename, "r") as file:
                code = file.read()
            challenges[challenge_name] = Challenge(
                name=challenge_name,
                difficulty=difficulty,
                code=code,
            )

        return challenges

    @staticmethod
    def _type_check_with_mypy(code: str) -> TypeCheckResult:
        buffer = io.StringIO(code)
        tokens = list(tokenize.generate_tokens(buffer.readline))
        # Find all lines that are followed by a comment # expect-type-error
        expect_error_lines = [
            token.start[0]
            for token in tokens
            if token.type == tokenize.COMMENT
            and token.string[1:].strip() == EXPECT_ERROR_COMMENT
        ]
        raw_result = api.run(["--config-file", str(MYPY_CONFIG), "-c", code])
        error_lines: list[str] = []

        for line in raw_result[0].splitlines():
            m = re.match(MYPY_MESSAGE_REGEX, line)
            if m is None:
                continue
            line_number = int(m.group(1))
            message = m.group(2)
            if line_number in expect_error_lines:
                # Each reported error should be attached to a specific line,
                # If it is commented with # expect-type-error, let it pass.
                expect_error_lines.remove(line_number)
                continue
            error_lines.append(f"{line_number}:{message}")

        # If there are any lines that are expected to fail but not reported by mypy,
        # they should be considered as errors.
        for line_number in expect_error_lines:
            error_lines.append(f"{line_number}: error: Expected type error")

        passed = len(error_lines) == 0
        if passed:
            error_lines.append("\nAll tests passed")
        else:
            error_lines.append(f"\nFound {len(error_lines)} errors")
        return TypeCheckResult(
            stdout="\n".join(error_lines), stderr=raw_result[1], passed=passed
        )


challenge_manager = ChallengeManager()
