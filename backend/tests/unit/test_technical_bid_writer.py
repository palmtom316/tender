from tender_backend.services.technical_bid_writer import TechnicalBidWriter


def test_technical_self_check_flags_pricing_terms() -> None:
    result = TechnicalBidWriter()._self_check("## 响应内容\n本章不应出现投标报价。")

    assert result["has_response_section"] is True
    assert result["contains_pricing_terms"] is True


def test_technical_self_check_detects_strategy_sections_and_chart_placeholders() -> None:
    result = TechnicalBidWriter()._self_check(
        """
        ## 编制原则
        ## 质量目标响应
        ## 质量管理组织
        ## 过程质量控制措施
        ## 质量检查与闭环改进
        {{chart:quality_system}}
        """
    )

    assert result["has_strategy_sections"] is True
    assert result["strategy_section_count"] == 4
    assert result["chart_placeholder_count"] == 1
