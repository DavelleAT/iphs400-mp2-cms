"""T15: Tables in the Editor (issue #18). The standard form's table rules
(app.markdown_form), and tables through the Editor's save path (app.editor)."""
from __future__ import annotations

import pytest

from app import editor
from app.markdown_form import to_markdown
from test_t13_editor import edited, save


def table(*rows: list[str]) -> str:
    """Editor HTML for a table: its first row the header."""
    header, *body = rows
    return ("<table><thead><tr>" + "".join(f"<th>{cell}</th>" for cell in header)
            + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
                      for row in body)
            + "</tbody></table>")


def test_a_numeric_column_is_right_aligned_and_a_text_column_left():
    html = table(["Class", "Enrolled"], ["First-year", "482"], ["Senior", "431"])
    assert to_markdown(html) == ("| Class | Enrolled |\n| :-- | --: |\n"
                                 "| First-year | 482 |\n| Senior | 431 |\n")


def alignment(*cells: str) -> str:
    """The alignment the standard form writes for a one-column table whose
    body cells are `cells`."""
    return to_markdown(table(["Value"], *([cell] for cell in cells))).split("\n")[1]


# The spec's numbers: thousands commas, a leading -, + or $, a trailing %,
# and accounting parentheses, with or without decimals.
NUMBERS = ["482", "1,234", "1,234,567", "3.2", "0.75", "-5", "-1,200.5", "$1,200",
           "-$4.50", "12%", "-0.5%", "(3.2)", "(1,000)", "($1,000)", "(12%)",
           "+3%", "+2", "+$1,200"]
# Cells that are not numbers, so their column is left-aligned.
NOT_NUMBERS = ["+-5", "-+5", "(+3)", "€5", "£1,000", "1,23", "12,3456", ",123", "3.2.1", "12 students",
               "5$", "%12", "(3.2", "3.2)", "--5", "$$5", "1e3", "Fall 2025", "n/a*"]


@pytest.mark.parametrize("number", NUMBERS)
def test_each_number_format_right_aligns_its_column(number):
    assert alignment(number, "10") == "| --: |"


@pytest.mark.parametrize("text", NOT_NUMBERS)
def test_one_cell_that_is_not_a_number_left_aligns_its_column(text):
    assert alignment("10", text, "20") == "| :-- |"


def test_blank_dash_and_na_cells_do_not_stop_a_numeric_column():
    assert alignment("482", "", "—", "n/a", "N/A", " — ", "1,200") == "| --: |"


def test_a_column_with_no_numbers_in_it_is_left_aligned():
    assert alignment("", "—", "n/a") == "| :-- |"


def test_the_header_row_never_decides_a_columns_alignment():
    assert to_markdown(table(["2024", "Enrolled"], ["First-year", "482"])).split("\n")[1] == (
        "| :-- | --: |")


def saved(html: str) -> str:
    """What the Editor's save path stores for a new item's posted `html`."""
    return editor.saved_body(editor.Posted(body="", body_html=html, body_dirty=True), None, None)


# A range copied from Excel, as it reaches the clipboard: Office markup, a
# merged header over two columns, and a merged cell down two rows.
EXCEL = """<html xmlns:o="urn:schemas-microsoft-com:office:office"
xmlns:x="urn:schemas-microsoft-com:office:excel"><head><meta name=ProgId content=Excel.Sheet>
<style>.xl65{mso-number-format:"\\#\\,\\#\\#0";text-align:right}</style></head><body>
<!--StartFragment-->
<table border=0 cellpadding=0 cellspacing=0 width=300 style='border-collapse:collapse;width:225pt'>
 <col width=100 span=3 style='width:75pt'>
 <tr height=20 style='height:15.0pt'>
  <td height=20 width=100 style='height:15.0pt;width:75pt'>Class</td>
  <td colspan=2 class=xl66 width=200 style='width:150pt'>Fall 2025</td>
 </tr>
 <tr height=20 style='height:15.0pt'>
  <td rowspan=2 height=40 style='height:30.0pt'>First-year</td>
  <td class=xl65 align=right>1,200</td>
  <td align=right>3%</td>
 </tr>
 <tr height=20 style='height:15.0pt'>
  <td class=xl65 align=right>482</td>
  <td>n/a</td>
 </tr>
 <tr height=20 style='height:15.0pt'>
  <td colspan=2 height=20 style='height:15.0pt;mso-ignore:colspan'>Senior (not surveyed)</td>
  <td align=right>—</td>
 </tr>
<!--EndFragment-->
</table></body></html>"""


def test_an_excel_range_is_stored_as_a_markdown_table_with_its_merges_undone():
    assert saved(EXCEL) == ("| Class | Fall 2025 |  |\n"
                            "| :-- | --: | --: |\n"
                            "| First-year | 1,200 | 3% |\n"
                            "|  | 482 | n/a |\n"
                            "| Senior (not surveyed) |  | — |\n")


# A range copied from Google Sheets: styled cells with no header markup, the
# sheet's own values in data- attributes, a line break in a cell, and a
# merged cell across the row.
SHEETS = ("""<meta charset="utf-8"><google-sheets-html-origin><style type="text/css"><!--"""
          """td {border: 1px solid #cccccc;}br {mso-data-placement:same-cell;}--></style>"""
          """<table xmlns="http://www.w3.org/1999/xhtml" cellspacing="0" cellpadding="0" """
          """dir="ltr" border="1" style="table-layout:fixed;font-size:10pt;font-family:Arial;"""
          """width:0px;border-collapse:collapse;border:none" data-sheets-root="1">"""
          """<colgroup><col width="160"/><col width="100"/><col width="100"/></colgroup><tbody>"""
          """<tr style="height:21px;">"""
          """<td style="overflow:hidden;padding:2px 3px;font-weight:bold;" """
          """data-sheets-value="{&quot;1&quot;:2,&quot;2&quot;:&quot;Survey&quot;}">Survey</td>"""
          """<td style="font-weight:bold;">Responses</td><td style="font-weight:bold;">Rate</td></tr>"""
          """<tr style="height:21px;"><td>Student experience</td>"""
          """<td style="text-align:right;" data-sheets-value="{&quot;1&quot;:3,&quot;3&quot;:1204}" """
          """data-sheets-numberformat="{&quot;1&quot;:2}">1,204</td>"""
          """<td style="text-align:right;">62%</td></tr>"""
          """<tr style="height:42px;"><td>Faculty<br>and staff</td>"""
          """<td style="text-align:right;">310</td><td style="text-align:right;">48.5%</td></tr>"""
          """<tr style="height:21px;"><td colspan="3" rowspan="1">Alumni: not run in 2025</td></tr>"""
          """</tbody></table>""")


def test_a_sheets_range_is_stored_as_a_markdown_table():
    assert saved(SHEETS) == ("| Survey | Responses | Rate |\n"
                             "| :-- | --: | --: |\n"
                             "| Student experience | 1,204 | 62% |\n"
                             "| Faculty and staff | 310 | 48.5% |\n"
                             "| Alumni: not run in 2025 |  |  |\n")


def test_bold_italic_and_links_in_a_cell_survive_and_a_pipe_is_escaped():
    html = table(["Measure", "Value"],
                 ["<strong>Retention</strong> | <em>first-year</em>", "<b>91%</b>"],
                 ['See <a href="https://example.test/cds">the CDS</a>', "n/a"])
    assert saved(html) == ("| Measure | Value |\n| :-- | --: |\n"
                           "| **Retention** \\| *first-year* | **91%** |\n"
                           "| See [the CDS](https://example.test/cds) | n/a |\n")


# A table as the standard form writes it: saving it again through the
# Editor, unchanged, gives back the same bytes.
STANDARD = ("Retention by cohort:\n\n"
            "| Cohort | Retained | Change | Note |\n"
            "| :-- | --: | --: | :-- |\n"
            "| **Fall 2024** | 1,204 | +2% | [CDS](https://example.test/cds) |\n"
            "| Fall 2023 \\| revised | (3.2) | — | *provisional* |\n"
            "|  | n/a |  |  |\n")


def test_a_stored_table_in_standard_form_survives_the_editor_unchanged():
    assert save(STANDARD, html=edited(STANDARD)) == STANDARD


def test_a_table_inside_a_cell_is_written_as_its_text():
    # A paste from a web page can nest one; a Markdown table can't.
    html = ("<table><tr><td>Class</td><td>Detail</td></tr>"
            "<tr><td>First-year</td><td><table><tr><td>x</td><td>y</td></tr>"
            "<tr><td>1</td><td>2</td></tr></table></td></tr></table>")
    assert saved(html) == ("| Class | Detail |\n| :-- | :-- |\n"
                           "| First-year | x y 1 2 |\n")


@pytest.mark.parametrize("cell", ["<b>1</b>,234", '<a href="https://example.test/n">12</a>%',
                                  "<em>$</em>1,200", "(<strong>3.2</strong>)"])
def test_a_number_with_formatting_inside_it_is_still_a_number(cell):
    assert alignment(cell, "10") == "| --: |"
