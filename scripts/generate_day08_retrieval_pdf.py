"""生成固定文本 PDF 测试资料；仅重新生成时需要 reportlab。"""

from pathlib import Path


def main() -> None:
    from reportlab.pdfgen import canvas

    root = Path(__file__).resolve().parents[1]
    target = root / "data/day08/retrieval-v1/corpus/document_tracking.pdf"
    if target.exists():
        raise FileExistsError(f"固定语料已存在，请创建新数据版本再修改：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(target), pagesize=(595, 842), invariant=1)
    pdf.setTitle("Document tracking fixture")
    pdf.setAuthor("Agent Learning Lab")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(54, 780, "Document tracking notes")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(54, 745, "This fixture contains three physical PDF pages.")
    pdf.drawString(54, 723, "The second physical page is intentionally blank.")
    pdf.drawString(54, 701, "Page labels printed on a page may differ from its physical position.")
    pdf.showPage()
    pdf.showPage()  # 物理第 2 页：完全空白，不渲染页脚或页码。
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(54, 780, "Citation coordinates")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(54, 745, "Count every physical PDF page, including blank pages, when recording citations.")
    pdf.drawString(54, 723, "This text is on physical page 3, even though page 2 has no extracted text.")
    pdf.drawString(54, 701, "Do not renumber later pages after skipping a blank page during extraction.")
    pdf.save()
    print(target)


if __name__ == "__main__":
    main()
