import unittest

from scripts.record_frozen_final_ng_family import validate_echo_decisions


def echo(token_index: str) -> dict[str, str]:
    return {
        "volume": "wts_1_34",
        "page": "1",
        "line": "2",
        "token_index": token_index,
    }


class ExplicitEchoDecisionTests(unittest.TestCase):
    def test_missing_echo_decision_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "lack explicit decisions"):
            validate_echo_decisions(
                [echo("3")],
                accepted=set(),
                deferred=set(),
                rejected=set(),
                resolved=set(),
            )

    def test_duplicate_echo_decision_fails(self) -> None:
        row_key = "wts_1_34:1:2:3"
        with self.assertRaisesRegex(ValueError, "multiple decisions"):
            validate_echo_decisions(
                [echo("3")],
                accepted={row_key},
                deferred={row_key},
                rejected=set(),
                resolved=set(),
            )

    def test_non_frozen_echo_key_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "not frozen"):
            validate_echo_decisions(
                [echo("3")],
                accepted={"wts_1_34:1:2:4"},
                deferred={"wts_1_34:1:2:3"},
                rejected=set(),
                resolved=set(),
            )

    def test_explicit_deferral_records_deferred(self) -> None:
        row_key = "wts_1_34:1:2:3"
        decisions = validate_echo_decisions(
            [echo("3")],
            accepted=set(),
            deferred={row_key},
            rejected=set(),
            resolved=set(),
        )
        self.assertEqual(decisions, {row_key: "deferred"})

    def test_complete_decision_mixture_succeeds(self) -> None:
        decisions = validate_echo_decisions(
            [echo("3"), echo("4"), echo("5"), echo("6")],
            accepted={"wts_1_34:1:2:3"},
            deferred={"wts_1_34:1:2:4"},
            rejected={"wts_1_34:1:2:5"},
            resolved={"wts_1_34:1:2:6"},
        )
        self.assertEqual(
            decisions,
            {
                "wts_1_34:1:2:3": "accepted",
                "wts_1_34:1:2:4": "deferred",
                "wts_1_34:1:2:5": "rejected",
                "wts_1_34:1:2:6": "resolved_elsewhere",
            },
        )

    def test_zero_echo_family_succeeds(self) -> None:
        self.assertEqual(
            validate_echo_decisions(
                [],
                accepted=set(),
                deferred=set(),
                rejected=set(),
                resolved=set(),
            ),
            {},
        )


if __name__ == "__main__":
    unittest.main()
