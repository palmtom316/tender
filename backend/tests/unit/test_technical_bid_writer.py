from tender_backend.services.technical_bid_writer import TechnicalBidWriter


def test_technical_self_check_flags_pricing_terms() -> None:
    result = TechnicalBidWriter()._self_check("## 响应内容\n本章不应出现投标报价。")

    assert result["has_response_section"] is True
    assert result["contains_pricing_terms"] is True
