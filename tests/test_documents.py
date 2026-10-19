from pathlib import Path

import pytest



from research_agent.documents import (
    DocumentLoadError,
    _chunk_sources,
    load_all_documents,
    load_all_documents_detailed,
    load_document,
    normalize_document_text,
    safe_document_path,
)


def _create_image_only_pdf(path: Path) -> None:
    import pymupdf

    with pymupdf.open() as source:
        page = source.new_page()
        page.insert_text((72, 72), "Visible but not searchable")
        pixmap = page.get_pixmap(alpha=False)

    with pymupdf.open() as output:
        page = output.new_page()
        page.insert_image(page.rect, pixmap=pixmap)
        output.save(path)


# T01：UTF-8 中文 TXT
def test_utf8_chinese_txt_keeps_content_and_metadata(tmp_path: Path):
    path = tmp_path / "中文资料.txt"
    path.write_text("第一行中文\n第二行内容", encoding="utf-8")

    first = load_document(path, tmp_path)
    second = load_document(path, tmp_path)

    assert len(first) == 1
    assert first[0].content == "第一行中文\n第二行内容"
    assert first[0].title == "中文资料.txt"
    assert first[0].file_path == str(path.resolve())
    assert first[0].metadata["content_kind"] == "local_document"
    assert first[0].metadata["file_name"] == "中文资料.txt"
    assert first[0].metadata["relative_path"] == "中文资料.txt"
    assert first[0].metadata["file_type"] == "txt"
    assert first[0].source_id == second[0].source_id


# T02：含 BOM 的 TXT
def test_utf8_bom_does_not_enter_content(tmp_path: Path):
    path = tmp_path / "bom.txt"
    path.write_text("中文文本", encoding="utf-8-sig")

    sources = load_document(path, tmp_path)

    assert len(sources) == 1
    assert sources[0].content == "中文文本"
    assert not sources[0].content.startswith("\ufeff")


# T03：Markdown 与 .markdown
@pytest.mark.parametrize("suffix", [".md", ".markdown"])
def test_markdown_content_enters_document_pipeline(
    tmp_path: Path,
    suffix: str,
):
    path = tmp_path / f"guide{suffix}"
    path.write_text(
        "# 使用说明\n\n"
        "- 第一项\n"
        "- 第二项\n\n"
        "```python\n"
        'print("保留代码文本")\n'
        "```\n",
        encoding="utf-8",
    )

    sources = load_document(path, tmp_path)
    content = "\n".join(source.content for source in sources)

    assert "# 使用说明" in content
    assert "- 第一项" in content
    assert 'print("保留代码文本")' in content
    assert all(source.metadata["file_type"] == "markdown" for source in sources)


def test_load_document_passes_chunk_parameters_to_text(tmp_path: Path):
    path = tmp_path / "long.txt"
    path.write_text("ABCDEFGHIJKLMNO", encoding="utf-8")

    sources = load_document(
        path,
        tmp_path,
        chunk_size=6,
        overlap=2,
    )

    assert [source.content for source in sources] == [
        "ABCDEF",
        "EFGHIJ",
        "IJKLMN",
        "MNO",
    ]


# T04：0 字节与纯空白文本
@pytest.mark.parametrize(
    "content",
    ["", "   \n\t\n   "],
    ids=["zero-bytes", "whitespace-only"],
)
def test_empty_document_has_clear_error(tmp_path: Path, content: str):
    path = tmp_path / "empty.txt"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(DocumentLoadError) as exc_info:
        load_document(path, tmp_path)

    assert exc_info.value.code == "empty_document"


# T05：非 UTF-8 字节
def test_non_utf8_document_has_encoding_error(tmp_path: Path):
    path = tmp_path / "non_utf8.txt"
    path.write_bytes(b"\xff\xfe\xfa\xfb")

    with pytest.raises(DocumentLoadError) as exc_info:
        load_document(path, tmp_path)

    assert exc_info.value.code == "encoding_error"
    assert isinstance(exc_info.value.__cause__, UnicodeDecodeError)


# P01：两页文本 PDF
def test_two_page_pdf_keeps_text_and_physical_pages(tmp_path: Path):
    import pymupdf

    path = tmp_path / "two_pages.pdf"
    with pymupdf.open() as document:
        page_1 = document.new_page()
        page_1.insert_text((72, 72), "FIRST_PAGE_ONLY")
        page_2 = document.new_page()
        page_2.insert_text((72, 72), "SECOND_PAGE_ONLY")
        document.save(path)

    sources = load_document(path, tmp_path)
    page_1_sources = [source for source in sources if source.page == 1]
    page_2_sources = [source for source in sources if source.page == 2]

    assert page_1_sources
    assert page_2_sources
    assert all("SECOND_PAGE_ONLY" not in source.content for source in page_1_sources)
    assert all("FIRST_PAGE_ONLY" not in source.content for source in page_2_sources)
    assert all(source.metadata["page"] == 1 for source in page_1_sources)
    assert all(source.metadata["page"] == 2 for source in page_2_sources)


def test_load_document_passes_chunk_parameters_to_pdf(tmp_path: Path):
    import pymupdf

    path = tmp_path / "chunked.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "ABCDEFGHIJKLMNO")
        document.save(path)

    sources = load_document(
        path,
        tmp_path,
        chunk_size=6,
        overlap=2,
    )

    assert [source.content for source in sources] == [
        "ABCDEF",
        "EFGHIJ",
        "IJKLMN",
        "MNO",
    ]


# P02：混合 PDF
def test_mixed_pdf_keeps_physical_page_numbers(tmp_path: Path):
    import pymupdf

    path = tmp_path / "mixed.pdf"

    with pymupdf.open() as document:
        page_1 = document.new_page()
        page_1.insert_text((72, 72), "Page one searchable text")

        document.new_page()  # 第 2 页为空白页

        page_3 = document.new_page()
        page_3.insert_text((72, 72), "Page three searchable text")

        document.save(path)

    sources = load_document(path, tmp_path)

    assert {source.page for source in sources} == {1, 3}
    assert all(source.metadata["empty_pages"] == [2] for source in sources)
    assert any("Page one" in source.content for source in sources)
    assert any("Page three" in source.content for source in sources)


# P03：图片型 PDF
def test_image_only_pdf_has_no_extractable_text(tmp_path: Path):
    import pymupdf

    path = tmp_path / "image_only.pdf"
    _create_image_only_pdf(path)

    with pymupdf.open(path) as document:
        assert document[0].get_text("text").strip() == ""

    with pytest.raises(DocumentLoadError) as exc_info:
        load_document(path, tmp_path)

    assert exc_info.value.code == "no_extractable_text"


# P04：全空白 PDF
def test_empty_pdf_has_no_extractable_text_code(tmp_path: Path):
    import pymupdf

    path = tmp_path / "empty.pdf"

    with pymupdf.open() as document:
        document.new_page()
        document.save(path)

    with pytest.raises(DocumentLoadError) as exc_info:
        load_document(path, tmp_path)

    assert exc_info.value.code == "no_extractable_text"


# P05：损坏与 0 字节 PDF
@pytest.mark.parametrize(
    "payload",
    [b"", b"%PDF-1.7\nthis is not a valid PDF"],
    ids=["zero-byte-pdf", "broken-pdf"],
)
def test_corrupted_pdf_has_parse_error_code(tmp_path: Path, payload: bytes):
    path = tmp_path / "broken.pdf"
    path.write_bytes(payload)

    with pytest.raises(DocumentLoadError) as exc_info:
        load_document(path, tmp_path)

    assert exc_info.value.code == "parse_error"
    assert exc_info.value.__cause__ is not None


# P06：需密码的 PDF
def test_password_protected_pdf_has_distinct_error(tmp_path: Path):
    import pymupdf

    path = tmp_path / "protected.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Protected content")
        document.save(
            path,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="owner-secret",
            user_pw="user-secret",
        )

    with pytest.raises(DocumentLoadError) as exc_info:
        load_document(path, tmp_path)

    assert exc_info.value.code == "password_required"

# C01：offset 精确性
def test_normalize_document_text():
    raw_text = "  第一行  \n\n  中文内容  \n   \n第三行"

    normalized = normalize_document_text(raw_text)

    assert normalized == "第一行\n中文内容\n第三行"

def test_chunk_offsets_reconstruct_content():
    raw_text = "  第一行内容  \n\n  第二行包含空格  \n第三行内容"
    normalized = normalize_document_text(raw_text)

    sources = _chunk_sources(
        raw_text,
        title="example.txt",
        file_path="example.txt",
        chunk_size=8,
        overlap=2,
    )

    assert sources

    for source in sources:
        offset = source.metadata["offset"]
        end_offset = source.metadata["end_offset"]

        assert normalized[offset:end_offset] == source.content

def test_chinese_offset_counts_characters_not_bytes():
    normalized = normalize_document_text("  甲乙  \n  中文  ")

    assert normalized == "甲乙\n中文"
    assert normalized.index("中") == 3

    # Python 字符数与 UTF-8 字节数不同
    assert len("中文") == 2
    assert len("中文".encode("utf-8")) == 6

@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [
        (0, 0),       # chunk_size 不能为 0
        (-1, 0),      # chunk_size 不能为负数
        (6, -1),      # overlap 不能为负数
        (6, 6),       # overlap 不能等于 chunk_size
        (6, 7),       # overlap 不能大于 chunk_size
        (6.5, 1),     # chunk_size 必须是整数
        (6, 1.5),     # overlap 必须是整数
        (True, 0),    # bool 不应被当作整数参数
    ],
)
def test_chunk_rejects_invalid_parameters(
    chunk_size,
    overlap,
):
    with pytest.raises(ValueError):
        _chunk_sources(
            "ABCDEFGHIJKLMNO",
            title="example.txt",
            file_path="example.txt",
            chunk_size=chunk_size,
            overlap=overlap,
        )

def test_chunking_terminates_and_preserves_overlap():
    sources = _chunk_sources(
        "ABCDEFGHIJKLMNO",
        title="example.txt",
        file_path="example.txt",
        chunk_size=6,
        overlap=2,
    )

    assert [source.content for source in sources] == [
        "ABCDEF",
        "EFGHIJ",
        "IJKLMN",
        "MNO",
    ]

    offsets = [
        source.metadata["offset"]
        for source in sources
    ]

    assert offsets == [0, 4, 8, 12]
    assert offsets == sorted(set(offsets))

def test_empty_normalized_text_creates_no_source():
    sources = _chunk_sources(
        "   \n\t\n   ",
        title="empty.txt",
        file_path="empty.txt",
        chunk_size=6,
        overlap=2,
    )

    assert sources == []

def test_every_chunk_can_be_reconstructed_from_offsets():
    text = "ABCDEFGHIJKLMNO"
    normalized = normalize_document_text(text)

    sources = _chunk_sources(
        text,
        title="example.txt",
        file_path="example.txt",
        chunk_size=6,
        overlap=2,
    )

    for source in sources:
        start = source.metadata["offset"]
        end = source.metadata["end_offset"]

        assert normalized[start:end] == source.content
        assert end > start


# C03：元数据独立
def test_chunk_metadata_is_independent():
    sources = _chunk_sources(
        "ABCDEFGHIJKLMNO",
        title="example.pdf 第 3 页",
        file_path="example.pdf",
        page=3,
        chunk_size=6,
        overlap=2,
        base_metadata={
            "content_kind": "local_document",
            "file_name": "example.pdf",
            "relative_path": "example.pdf",
            "file_type": "pdf",
            "page": 3,
            "warnings": [],
        },
    )

    assert len(sources) > 1
    assert all(source.page == 3 for source in sources)
    assert all(source.metadata["page"] == 3 for source in sources)

    sources[0].metadata["warnings"].append("测试修改")
    sources[0].metadata["custom"] = "只修改第一片"

    assert sources[1].metadata["warnings"] == []
    assert "custom" not in sources[1].metadata

# B01：混合目录
def test_detailed_batch_keeps_successes_and_errors(
    tmp_path: Path,
):
    import pymupdf

    # 1. 正常 TXT
    (tmp_path / "notes.txt").write_text(
        "正常文本",
        encoding="utf-8",
    )

    # 2. 正常 Markdown
    (tmp_path / "guide.md").write_text(
        "# 使用说明\n正文",
        encoding="utf-8",
    )

    # 3. 两页正常 PDF
    two_pages = tmp_path / "two_pages.pdf"
    with pymupdf.open() as document:
        page_1 = document.new_page()
        page_1.insert_text((72, 72), "Page one")

        page_2 = document.new_page()
        page_2.insert_text((72, 72), "Page two")

        document.save(two_pages)

    # 4. 混合 PDF：第 2 页无文字
    mixed = tmp_path / "mixed.pdf"
    with pymupdf.open() as document:
        page_1 = document.new_page()
        page_1.insert_text((72, 72), "Mixed page one")

        document.new_page()

        page_3 = document.new_page()
        page_3.insert_text((72, 72), "Mixed page three")

        document.save(mixed)

    # 5. 空文本
    (tmp_path / "empty.txt").write_text(
        "",
        encoding="utf-8",
    )

    # 6. 坏编码
    (tmp_path / "bad_encoding.txt").write_bytes(
        b"\xff\xfe\xfa\xfb"
    )

    # 7. 损坏 PDF
    (tmp_path / "broken.pdf").write_bytes(
        b"%PDF-1.7\ninvalid PDF"
    )

    # 8. 没有文字层的 PDF
    _create_image_only_pdf(tmp_path / "image_only.pdf")

    # 9. 不支持的类型
    (tmp_path / "ignored.bin").write_bytes(b"binary")

    result = load_all_documents_detailed(tmp_path)

    assert result.loaded_files == 4
    assert result.failed_files == 4
    assert result.skipped_files == 1

    assert result.sources
    assert {error.relative_path for error in result.errors} == {
        "empty.txt",
        "bad_encoding.txt",
        "broken.pdf",
        "image_only.pdf",
    }

    error_codes = {
        error.relative_path: error.error_code
        for error in result.errors
    }

    assert error_codes["empty.txt"] == "empty_document"
    assert error_codes["bad_encoding.txt"] == "encoding_error"
    assert error_codes["broken.pdf"] == "parse_error"
    assert (
        error_codes["image_only.pdf"]
        == "no_extractable_text"
    )

    assert any(
        warning.relative_path == "mixed.pdf"
        and warning.page == 2
        and warning.warning_code == "no_text_on_page"
        for warning in result.warnings
    )

    # mixed.pdf 的第 1、3 页仍然成功保留
    mixed_sources = [
        source
        for source in result.sources
        if source.metadata["relative_path"] == "mixed.pdf"
    ]

    assert {source.page for source in mixed_sources} == {1, 3}


def test_detailed_batch_rejects_missing_root(tmp_path: Path):
    missing = tmp_path / "misspelled-directory"

    with pytest.raises(DocumentLoadError) as exc_info:
        load_all_documents_detailed(missing)

    assert exc_info.value.code == "not_found"
    assert not missing.exists()


def test_legacy_batch_keeps_compatible_return_type(tmp_path: Path):
    root = tmp_path / "new-document-root"

    sources = load_all_documents(root)

    assert sources == []
    assert root.is_dir()


# S01：根目录边界
def test_document_inside_root_can_be_loaded(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    path = root / "notes.txt"
    path.write_text("正常文档", encoding="utf-8")

    resolved = safe_document_path(root, path)
    sources = load_document(path, root)

    assert resolved == path.resolve()
    assert sources
    assert sources[0].metadata["relative_path"] == "notes.txt"
    assert sources[0].metadata["file_type"] == "txt"


def test_parent_path_cannot_escape_root(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("外部文件", encoding="utf-8")

    with pytest.raises(DocumentLoadError) as exc_info:
        load_document(root / ".." / "outside.txt", root)

    assert exc_info.value.code == "outside_root"


def test_sibling_with_same_prefix_is_outside_root(tmp_path: Path):
    root = tmp_path / "docs"
    sibling = tmp_path / "docs-other"
    root.mkdir()
    sibling.mkdir()
    outside = sibling / "outside.txt"
    outside.write_text("外部文件", encoding="utf-8")

    with pytest.raises(DocumentLoadError) as exc_info:
        load_document(outside, root)

    assert exc_info.value.code == "outside_root"


def test_missing_path_has_distinct_error(tmp_path: Path):
    with pytest.raises(DocumentLoadError) as exc_info:
        load_document(tmp_path / "missing.txt", tmp_path)

    assert exc_info.value.code == "not_found"


def test_directory_is_not_a_file(tmp_path: Path):
    directory = tmp_path / "documents"
    directory.mkdir()

    with pytest.raises(DocumentLoadError) as exc_info:
        load_document(directory, tmp_path)

    assert exc_info.value.code == "not_a_file"


def test_unsupported_file_type(tmp_path: Path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"binary")

    with pytest.raises(DocumentLoadError) as exc_info:
        load_document(path, tmp_path)

    assert exc_info.value.code == "unsupported_type"
