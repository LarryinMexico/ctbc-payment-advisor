from __future__ import annotations

import unittest

from mcp_server.tools.search import search_by_channel


class SearchByChannelTests(unittest.TestCase):
    def test_named_merchant_does_not_borrow_other_merchant_microsite_offer(self):
        result = search_by_channel(
            channel="全聯",
            cards_owned=["ctbc_c_linepay", "fubon_b_lifestyle"],
            amount=2000,
            top_k=3,
        )

        linepay = next(r for r in result["results"] if r["card_id"] == "ctbc_c_linepay")
        lifestyle = next(r for r in result["results"] if r["card_id"] == "fubon_b_lifestyle")

        self.assertEqual(linepay["cashback_rate"], 0.01)
        self.assertEqual(linepay["data_source"], "api")
        self.assertNotIn("每週四", linepay.get("conditions") or "")
        self.assertEqual(lifestyle["cashback_rate"], 0.02)
        self.assertEqual(result["results"][0]["card_id"], "fubon_b_lifestyle")

    def test_named_merchant_still_uses_matching_microsite_offer(self):
        result = search_by_channel(
            channel="家樂福",
            cards_owned=["ctbc_c_linepay", "fubon_b_lifestyle"],
            amount=2000,
            top_k=3,
        )

        linepay = next(r for r in result["results"] if r["card_id"] == "ctbc_c_linepay")

        self.assertEqual(linepay["cashback_rate"], 0.05)
        self.assertEqual(linepay["data_source"], "microsite")
        self.assertIn("家樂福", linepay.get("merchant") or "")


if __name__ == "__main__":
    unittest.main()
