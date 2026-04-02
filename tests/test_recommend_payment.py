from __future__ import annotations

import unittest

from mcp_server.tools.recommend import recommend_payment


class RecommendPaymentTests(unittest.TestCase):
    def test_named_merchants_are_preserved_in_multi_channel_recommendation(self):
        cards = [
            "ctbc_c_uniopen",
            "ctbc_c_linepay",
            "ctbc_c_fp",
            "ctbc_b_cashback_signature",
            "ctbc_b_hae",
            "fubon_b_lifestyle",
        ]

        result = recommend_payment(
            "今天要去全聯跟 momo 購物網，各花 2000 元，幫我分別推薦",
            cards,
        )

        self.assertIsNone(result["error"])
        self.assertEqual(len(result["recommendations"]), 2)

        by_query = {item["query"]: item for item in result["recommendations"]}

        self.assertIn("全聯", by_query)
        self.assertEqual(
            by_query["全聯"]["best_card"]["card_id"],
            "fubon_b_lifestyle",
        )

        self.assertIn("momo購物", by_query)
        self.assertNotEqual(
            by_query["momo購物"]["best_card"]["card_id"],
            "ctbc_c_linepay",
        )
        self.assertNotEqual(
            by_query["momo購物"]["best_card"].get("merchant"),
            "OB嚴選",
        )


if __name__ == "__main__":
    unittest.main()
