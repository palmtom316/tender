from __future__ import annotations

from tender_backend.services.norm_service.document_assets import PageAsset
from tender_backend.services.norm_service.outline_rebuilder import (
    collect_outline_clause_nos_from_pages,
    rebuild_outline_sections_from_pages,
)


def test_rebuild_outline_sections_from_pages_extracts_clean_normative_headings() -> None:
    pages = [
        PageAsset(
            page_number=7,
            normalized_text=(
                "目次\n"
                "4.8 本体及附件安装 ………………………………………… (46)\n"
                "4.10 热油循环 (52)"
            ),
            raw_page=None,
            source_ref="document_section:toc",
        ),
        PageAsset(
            page_number=15,
            normalized_text=(
                "4 电力变压器、油浸电抗器\n"
                "4.1 装卸、运输与就位\n"
                "4.1.1 条文正文\n"
                "1 水路运输时，应做好下列工作："
            ),
            raw_page=None,
            source_ref="document_section:p15",
        ),
        PageAsset(
            page_number=26,
            normalized_text=(
                "4.7.3 条文正文\n"
                "4.8 本体及附件安装\n"
                "4.8.1 220kV及以上变压器本体露空安装附件应符合下列规定："
            ),
            raw_page=None,
            source_ref="document_section:p26",
        ),
    ]

    sections = rebuild_outline_sections_from_pages(pages)

    assert [(section["section_code"], section["title"], section["page_start"]) for section in sections] == [
        ("4", "电力变压器、油浸电抗器", 15),
        ("4.1", "装卸、运输与就位", 15),
        ("4.8", "本体及附件安装", 26),
    ]


def test_rebuild_outline_sections_from_pages_ignores_commentary_pages_after_boundary() -> None:
    pages = [
        PageAsset(
            page_number=35,
            normalized_text=(
                "5 互感器\n"
                "5.1 一般规定\n"
                "5.1.1 条文正文"
            ),
            raw_page=None,
            source_ref="document_section:p35",
        ),
        PageAsset(
            page_number=39,
            normalized_text=(
                "本规范用词说明\n"
                "为便于在执行本规范条文时区别对待，对要求严格程度不同的用词说明如下："
            ),
            raw_page=None,
            source_ref="document_section:p39",
        ),
        PageAsset(
            page_number=47,
            normalized_text=(
                "4.2 交接与保管\n"
                "4.2.1 设备到达现场后应及时检查。"
            ),
            raw_page=None,
            source_ref="document_section:p47",
        ),
    ]

    sections = rebuild_outline_sections_from_pages(pages)

    assert [(section["section_code"], section["title"]) for section in sections] == [
        ("5", "互感器"),
        ("5.1", "一般规定"),
    ]
    assert collect_outline_clause_nos_from_pages(pages) == {"5", "5.1"}


def test_rebuild_outline_sections_from_pages_includes_appendix_headings() -> None:
    pages = [
        PageAsset(
            page_number=35,
            normalized_text=(
                "5 互感器\n"
                "5.1 一般规定\n"
                "5.1.1 条文正文"
            ),
            raw_page=None,
            source_ref="document_section:p35",
        ),
        PageAsset(
            page_number=38,
            normalized_text=(
                "附录A 新装电力变压器及油浸电抗器不需干燥的条件\n"
                "A.0.1 带油运输的变压器及电抗器应符合下列规定："
            ),
            raw_page=None,
            source_ref="document_section:p38",
        ),
        PageAsset(
            page_number=39,
            normalized_text=(
                "本规范用词说明\n"
                "为便于在执行本规范条文时区别对待，对要求严格程度不同的用词说明如下："
            ),
            raw_page=None,
            source_ref="document_section:p39",
        ),
    ]

    sections = rebuild_outline_sections_from_pages(pages)

    assert [(section["section_code"], section["title"], section["page_start"]) for section in sections] == [
        ("5", "互感器", 35),
        ("5.1", "一般规定", 35),
        ("A", "新装电力变压器及油浸电抗器不需干燥的条件", 38),
    ]
    assert collect_outline_clause_nos_from_pages(pages) == {"5", "5.1", "A"}


def test_rebuild_outline_sections_from_pages_ignores_dates_units_and_formula_like_lines() -> None:
    pages = [
        PageAsset(
            page_number=1,
            normalized_text=(
                "2010-05-31 发布\n"
                "850\\times 1168\n"
                "500\\mathrm{kV}\n"
                "1 总 则\n"
                "1.0.1 为保证施工安装质量，制定本规范。"
            ),
            raw_page=None,
            source_ref="document.raw_payload.pages[0]",
        ),
        PageAsset(
            page_number=2,
            normalized_text=(
                "4 电力变压器、油浸电抗器\n"
                "4.1 装卸、运输与就位\n"
                "20\\mathrm{km / h}\n"
                "0.03\\mathrm{MPa}"
            ),
            raw_page=None,
            source_ref="document.raw_payload.pages[1]",
        ),
    ]

    sections = rebuild_outline_sections_from_pages(pages)

    assert [(section["section_code"], section["title"]) for section in sections] == [
        ("1", "总 则"),
        ("4", "电力变压器、油浸电抗器"),
        ("4.1", "装卸、运输与就位"),
    ]


def test_rebuild_outline_sections_from_pages_ignores_numbered_list_items_between_real_headings() -> None:
    pages = [
        PageAsset(
            page_number=25,
            normalized_text=(
                "5 气体绝缘金属封闭开关设备\n"
                "5.1 一般规定\n"
                "5.1.4 GIS运到现场后的检查应符合下列规定：\n"
                "list\n"
                "6 制造厂所带支架应无变形、损伤、锈蚀和锌层脱落；\n"
                "7 出厂证件及技术资料应齐全，且应符合设备订货合同的"
            ),
            raw_page=None,
            source_ref="document_section:p25",
        ),
        PageAsset(
            page_number=26,
            normalized_text=(
                "约定。\n"
                "5.1.5 GIS运到现场后的保管应符合产品技术文件要求，且应符合下列规定：\n"
                "5.2 安装与调整\n"
                "5.2.1 GIS元件安装前及安装过程中的试验工作应满足安装需要。"
            ),
            raw_page=None,
            source_ref="document_section:p26",
        ),
        PageAsset(
            page_number=29,
            normalized_text=(
                "17 螺栓连接和紧固应对称均匀用力，其力矩值应符合产品技术文件要求。\n"
                "18 伸缩节的安装长度应符合产品技术文件要求。\n"
                "19 套管的安装、套管的导体插入深度均应符合产品技术文\n"
            ),
            raw_page=None,
            source_ref="document_section:p29",
        ),
        PageAsset(
            page_number=30,
            normalized_text=(
                "5.3 GIS中的六氟化硫断路器的安装\n"
                "5.3.1 条文正文"
            ),
            raw_page=None,
            source_ref="document_section:p30",
        ),
    ]

    sections = rebuild_outline_sections_from_pages(pages)

    assert [(section["section_code"], section["title"]) for section in sections] == [
        ("5", "气体绝缘金属封闭开关设备"),
        ("5.1", "一般规定"),
        ("5.2", "安装与调整"),
        ("5.3", "GIS中的六氟化硫断路器的安装"),
    ]
