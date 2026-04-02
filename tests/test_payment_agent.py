from __future__ import annotations

import unittest

from agent.payment_agent import PaymentAgent


class PaymentAgentFormattingTests(unittest.TestCase):
    def test_multi_channel_recommendation_is_formatted_per_channel(self):
        agent = PaymentAgent.__new__(PaymentAgent)
        payload = {
            "recommendations": [
                {
                    "query": "家樂福",
                    "best_card": {
                        "card_name": "LINE Pay信用卡",
                        "cashback_rate": 0.05,
                        "estimated_cashback": 100.0,
                        "conditions": "限以LINE Pay Visa卡支付",
                    },
                },
                {
                    "query": "星巴克",
                    "best_card": {
                        "card_name": "LINE Pay信用卡",
                        "cashback_rate": 0.05,
                        "estimated_cashback": 100.0,
                        "conditions": "限以LINE Pay Visa卡支付",
                    },
                },
            ]
        }

        reply = agent._format_recommend_payment_reply(payload)

        self.assertIsNotNone(reply)
        self.assertIn("家樂福：推薦使用 LINE Pay信用卡", reply)
        self.assertIn("星巴克：推薦使用 LINE Pay信用卡", reply)


if __name__ == "__main__":
    unittest.main()
