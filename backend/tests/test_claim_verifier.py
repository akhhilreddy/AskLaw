import unittest

from app.services.claim_verifier import (
    calculate_grounding_score,
    verify_claims,
)


class ClaimVerifierRegressionTests(unittest.TestCase):
    @staticmethod
    def _evidence(text, *, source_type="document", evidence_id="e1"):
        return {
            "evidence_id": evidence_id,
            "title": "Legal source",
            "text": text,
            "source_type": source_type,
        }

    def _support(self, claim, evidence):
        report = verify_claims(claim, evidence)
        self.assertEqual(report["summary"]["total_claims"], 1)
        return report["claims"][0]["support"]

    def test_exact_supported_claim(self):
        claim = "Article 32 provides constitutional remedies."
        evidence = [
            self._evidence("Article 32 provides constitutional remedies.")
        ]
        self.assertEqual(self._support(claim, evidence), "supported")

    def test_paraphrased_supported_claim(self):
        claim = (
            "The apex court can grant writ remedies to protect "
            "fundamental rights."
        )
        evidence = [
            self._evidence(
                "The Supreme Court may issue writs to enforce "
                "fundamental rights."
            )
        ]
        self.assertEqual(self._support(claim, evidence), "supported")

    def test_clearly_partial_claim(self):
        claim = (
            "Article 32 provides remedies and guarantees every "
            "requested form of relief."
        )
        evidence = [
            self._evidence("Article 32 provides constitutional remedies.")
        ]
        self.assertEqual(self._support(claim, evidence), "partial")

    def test_numeric_supported_claim(self):
        claim = "The Act came into force in 2012."
        evidence = [self._evidence("The Act came into force in 2012.")]
        self.assertEqual(self._support(claim, evidence), "supported")

    def test_bare_matching_numeric_value_is_supported(self):
        self.assertEqual(
            self._support("2012 is the stated year.", [self._evidence("2012 is the stated year.")]),
            "supported",
        )

    def test_numeric_contradiction_is_unsupported(self):
        claim = "The Act came into force in 2015."
        evidence = [self._evidence("The Act came into force in 2012.")]
        self.assertEqual(self._support(claim, evidence), "unsupported")

    def test_numeric_contradiction_is_not_hidden_by_weak_overlap(self):
        claim = "The Act came into force in 2015."
        evidence = [
            self._evidence(
                "The Act came into force in 2012.",
                evidence_id="contradiction",
            ),
            self._evidence(
                "The Act governs force and procedure.",
                evidence_id="weak-overlap",
            ),
        ]
        self.assertEqual(self._support(claim, evidence), "unsupported")

    def test_exact_numeric_support_can_win_across_sources(self):
        claim = "The Act came into force in 2015."
        evidence = [
            self._evidence(
                "An earlier draft proposed commencement in 2012.",
                evidence_id="draft",
            ),
            self._evidence(
                "The Act came into force in 2015.",
                evidence_id="enacted",
            ),
        ]
        self.assertEqual(self._support(claim, evidence), "supported")

    def test_article_supported(self):
        claim = "Article 32 creates the listed remedy."
        evidence = [self._evidence("Article 32 creates the listed remedy.")]
        self.assertEqual(self._support(claim, evidence), "supported")

    def test_wrong_article_is_unsupported(self):
        claim = "Article 226 creates the listed remedy."
        evidence = [self._evidence("Article 32 creates the listed remedy.")]
        self.assertEqual(self._support(claim, evidence), "unsupported")

    def test_section_supported(self):
        claim = "Section 4 requires prior notice."
        evidence = [self._evidence("Section 4 requires prior notice.")]
        self.assertEqual(self._support(claim, evidence), "supported")

    def test_wrong_section_is_unsupported(self):
        claim = "Section 5 requires prior notice."
        evidence = [self._evidence("Section 4 requires prior notice.")]
        self.assertEqual(self._support(claim, evidence), "unsupported")

    def test_mixed_supported_and_unsupported_claim_is_partial(self):
        claim = "The court may issue writs and award automatic damages."
        evidence = [self._evidence("The court may issue writs.")]
        self.assertEqual(self._support(claim, evidence), "partial")

    def test_multiple_identifiers_in_evidence_do_not_conflict(self):
        claim = "Article 226 empowers High Courts to issue writs."
        evidence = [
            self._evidence(
                "Article 32 empowers the Supreme Court to issue writs. "
                "Article 226 empowers High Courts to issue writs."
            )
        ]
        self.assertEqual(self._support(claim, evidence), "supported")

    def test_multiple_numeric_values_use_matching_proposition(self):
        claim = "The statutory penalty is 5000."
        evidence = [
            self._evidence(
                "The Act came into force in 2012. "
                "The statutory penalty is 5000."
            )
        ]
        self.assertEqual(self._support(claim, evidence), "supported")

    def test_case_number_does_not_support_factual_amount(self):
        claim = "The statutory penalty is 5000."
        evidence = [
            self._evidence("Case No. 5000 concerns the statutory penalty.")
        ]
        self.assertEqual(self._support(claim, evidence), "partial")

    def test_web_evidence_can_support_claim(self):
        claim = "Section 4 requires prior notice."
        evidence = [
            self._evidence(
                "Section 4 requires prior notice.",
                source_type="web",
            )
        ]
        self.assertEqual(self._support(claim, evidence), "supported")

    def test_document_evidence_can_support_claim(self):
        claim = "Section 4 requires prior notice."
        evidence = [
            self._evidence(
                "Section 4 requires prior notice.",
                source_type="document",
            )
        ]
        self.assertEqual(self._support(claim, evidence), "supported")

    def test_hybrid_evidence_uses_supporting_source(self):
        claim = "Article 32 provides constitutional remedies."
        evidence = [
            self._evidence(
                "Article 226 empowers High Courts to issue writs.",
                source_type="document",
                evidence_id="document-1",
            ),
            self._evidence(
                "Article 32 provides constitutional remedies.",
                source_type="web",
                evidence_id="web-1",
            ),
        ]
        self.assertEqual(self._support(claim, evidence), "supported")

    def test_truly_unsupported_claim(self):
        claim = "The source guarantees lunar mining rights."
        evidence = [self._evidence("Article 32 provides remedies.")]
        self.assertEqual(self._support(claim, evidence), "unsupported")

    def test_clause_chapter_and_part_identifiers_are_supported(self):
        claim = "Clause (2) in Chapter III of Part III protects the right."
        evidence = [
            self._evidence(
                "Clause (2) in Chapter III of Part III protects the right."
            )
        ]
        report = verify_claims(claim, evidence)
        self.assertEqual(report["claims"][0]["support"], "supported")
        self.assertEqual(report["summary"]["legal_claims"], 1)

    def test_wrong_clause_is_unsupported(self):
        claim = "Clause (3) creates the listed exception."
        evidence = [self._evidence("Clause (2) creates the listed exception.")]
        self.assertEqual(self._support(claim, evidence), "unsupported")

    def test_act_year_contradiction_is_unsupported(self):
        claim = "The Data Protection Act, 2015 requires consent."
        evidence = [
            self._evidence("The Data Protection Act, 2012 requires consent.")
        ]
        self.assertEqual(self._support(claim, evidence), "unsupported")

    def test_grounding_score_and_summary_schema_are_preserved(self):
        report = verify_claims(
            "Article 32 provides remedies. The Act commenced in 2015.",
            [
                self._evidence(
                    "Article 32 provides remedies. The Act commenced in 2012."
                )
            ],
        )
        self.assertEqual(
            set(report["summary"]),
            {
                "total_claims",
                "supported_claims",
                "partial_claims",
                "unsupported_claims",
                "legal_claims",
            },
        )
        self.assertEqual(calculate_grounding_score(report), 0.5)


if __name__ == "__main__":
    unittest.main()
