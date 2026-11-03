import copy
import unittest

from card_benefit.payment_card.db_pipeline.auto_approval_policy import check_auto_approval


class ApprovalPolicyTests(unittest.TestCase):
    def setUp(self):
        # normalized·check_cd·source_cnt·conflicts는 CommonBenefitRepository.attach_normalized가 원본 행에서 다시 만든 값이다.
        self.candidate = {"stg_status": "PENDING_REVIEW", "stg_kind_cd": "BENEFIT", "stg_sql_check_cd": "OK",
                          "stg_raw_item": {"certainty": "HIGH", "relations": []},
                          "check_cd": "OK", "source_cnt": 1, "conflicts": [],
                          "normalized": {"bnft_nm": "n", "relation_list": []}}
        self.evidence = [{"approval_status_cd": "PENDING", "start_pos": 1, "end_pos": 4,
                          "quote_txt": "원문 근거", "source_txt": "원문 근거"}]

    def decide(self, candidate=None, evidence=None, **kwargs):
        return check_auto_approval(candidate if candidate is not None else self.candidate,
                                   evidence if evidence is not None else self.evidence,
                                   parent_integrity_ok=kwargs.get("parent_integrity_ok", True),
                                   duplicate_free=kwargs.get("duplicate_free", True))

    def test_valid_candidate_and_idempotent_status(self):
        self.assertTrue(self.decide().eligible)
        self.candidate["stg_status"] = "AUTO_APPROVED"
        self.assertTrue(self.decide().eligible)

    def test_review_or_unsafe_sources_are_not_approved(self):
        for field, value in (("stg_sql_check_cd", "LINK_REVIEW"), ("check_cd", "LINK_REVIEW"),
                             ("stg_status", "REJECTED"), ("normalized", None), ("source_cnt", 2)):
            candidate = copy.deepcopy(self.candidate)
            candidate[field] = value
            self.assertFalse(self.decide(candidate).eligible)
        self.assertFalse(self.decide(evidence=[]).eligible)
        self.assertFalse(self.decide(evidence=[{**self.evidence[0], "source_txt": "다른 원문"}]).eligible)
        self.assertFalse(self.decide(parent_integrity_ok=False).eligible)
        self.assertFalse(self.decide(duplicate_free=False).eligible)

    def test_ambiguity_and_conflicts_are_rejected(self):
        candidate = copy.deepcopy(self.candidate)
        candidate["stg_raw_item"]["uncertainty_note"] = "불명확"
        self.assertFalse(self.decide(candidate).eligible)
        candidate = copy.deepcopy(self.candidate)
        candidate["conflicts"] = ["금액 불일치"]
        self.assertFalse(self.decide(candidate).eligible)


if __name__ == "__main__":
    unittest.main()
