import pytest

from garuda2ris import clean_author, extract_keywords, parse_search_page, parse_source_line


def test_page_counters(classes_html, flat_html):
    page = parse_search_page(classes_html)
    assert (page.page, page.total_pages, page.total_records) == (1, 5, 47)
    # thousands separator in "Total Record : 1.047"
    page = parse_search_page(flat_html)
    assert (page.page, page.total_pages, page.total_records) == (3, 105, 1047)


def test_search_echo(classes_html, flat_html):
    page = parse_search_page(classes_html)
    assert (page.query_echo, page.field_echo) == ("Smoke-Free Area Policy", "abstract")
    # a page without the "Search ..., by ..." line simply has no echo
    page = parse_search_page(flat_html)
    assert (page.query_echo, page.field_echo) == (None, None)
    page = parse_search_page(
        '<h2>Found 0 documents</h2> Search <i>"smoke-free area" healthcare</i> <i>, by title</i>'
    )
    assert page.total_records == 0 and page.articles == []
    assert (page.query_echo, page.field_echo) == ('"smoke-free area" healthcare', "title")


def test_record_from_wrapper_layout(classes_html):
    articles = parse_search_page(classes_html).articles
    assert [a.garuda_id for a in articles] == ["5949298", "584313", "1022155", "1265595"]

    a = articles[0]
    assert a.title.startswith("Karsinoma Nasofaring dengan Manifestasi Efusi Otitis Media")
    assert a.authors == ["Adji, Iwan Setiawan", "Nabilah, Aisyah", "Alghozi, Muhammad Hilmi"]
    assert a.journal == "Jurnal Penelitian Kesehatan SUARA FORIKES"
    assert (a.volume, a.issue, a.year) == ("16", "4", 2025)
    assert a.issue_title == "Oktober-Desember 2025"
    assert a.publisher == "FORIKES"
    assert a.doi == "10.33846/sf16430"
    assert a.url == "http://forikes-ejournal.com/index.php/SF/article/view/sf16430/16430"
    assert a.pdf_url == "http://forikes-ejournal.com/index.php/SF/article/download/sf16430/16430"
    assert a.garuda_pdf_url is None
    assert a.garuda_url == "https://garuda.kemdiktisaintek.go.id/documents/detail/5949298"
    # abstract: the "Abstract" label is stripped, nothing else leaks in
    assert a.abstract.startswith("Nasopharyngeal carcinoma is a head-neck")
    assert a.abstract.endswith("emfisema paru; kejang")
    assert "Show Abstract" not in a.abstract and "Page 1 of 5" not in a.abstract


def test_garuda_pdf_link_and_missing_doi(classes_html):
    a = parse_search_page(classes_html).articles[2]
    assert a.doi is None
    assert a.garuda_pdf_url.startswith(
        "http://download.garuda.kemdiktisaintek.go.id/article.php?article=1022155"
    )
    assert " " not in a.garuda_pdf_url  # spaces in the title= part are encoded
    assert a.url == "http://e-journal.sari-mutiara.ac.id/index.php/JMKM/article/view/443"


def test_record_from_flat_layout(flat_html):
    """No classes, no wrapper per record, relative links."""
    articles = parse_search_page(flat_html).articles
    assert [a.garuda_id for a in articles] == ["2286884", "187311", "3765790", "4704220"]

    a = articles[0]
    assert a.authors == ["Rosalina, Rosalina", "Gravitiani, Evi"]
    assert a.journal == "Jurnal Ekonomi & Studi Pembangunan JESP"
    assert (a.volume, a.issue, a.year) == ("15", "2", 2014)
    assert a.publisher == "Universitas Muhammadiyah Yogyakarta"  # value on its own line
    assert a.url is None and a.pdf_url is None  # labels present but not linked
    # abstract stops at the next record
    assert a.abstract == "Placeholder abstract for test record 2286884. It stands in for the real abstract text."

    b = articles[1]
    assert b.authors == ["Listiyani, Novita", "Hasanuddin"]
    assert (b.volume, b.issue, b.year) == ("1", "2", 2014)
    assert b.title.endswith("(STUDI PADA KANTOR LINGKUNGAN HIDUP KOTA DUMAI)")
    assert b.url == "http://journal.example.org/article/view/187311"
    assert b.pdf_url == "http://journal.example.org/article/download/187311"

    last = articles[3]
    assert last.doi == "10.56338/ijhess.v7i1.6791"
    assert last.year is None and last.volume is None  # Garuda shows none; nothing invented
    assert last.abstract.endswith("stands in for the real abstract text.")  # pager not swallowed
    assert last.garuda_url == "https://garuda.kemdiktisaintek.go.id/documents/detail/4704220"


def test_base_url_is_used_for_relative_links(flat_html):
    a = parse_search_page(flat_html, base_url="https://garuda.example.id/").articles[0]
    assert a.garuda_url == "https://garuda.example.id/documents/detail/2286884"


def test_empty_result_page():
    page = parse_search_page("<html><body><h2>Found 0 documents</h2></body></html>")
    assert page.articles == [] and page.total_records == 0


def test_single_record_does_not_swallow_page_chrome():
    html = """<html><body><div id="wrap">
      <h2>Found 1 documents</h2>
      <div><a href="/documents/detail/9">Only title</a>
        <a href="/author/view/1">Putri, Ayu</a><br>
        Jurnal Tunggal Vol 2 No 1 (2020)<br><i>Publisher :</i> UNESA
        <p>Show Abstract</p><h4>Abstract</h4><p>The only abstract on this page, long enough.</p></div>
      <div>Page 1 of 1 | Total Record : 1</div>
    </div></body></html>"""
    page = parse_search_page(html)
    assert page.total_records == 1
    (a,) = page.articles
    assert (a.title, a.journal, a.year, a.publisher) == ("Only title", "Jurnal Tunggal", 2020, "UNESA")
    assert a.abstract == "The only abstract on this page, long enough."


def test_special_characters_in_text_blocks():
    """'<', '&', entities and stray markup inside Garuda's <xmp> text blocks."""
    html = """<html><body><div>
      <div><a href="/documents/detail/1"><xmp>Effect of A & B on <i>Aedes aegypti</i></xmp></a>
        <a href="/author/view/1">Sari, Dewi</a><br>
        <xmp>Jurnal R&D Vol 2 No 1 (2021)</xmp><i>Publisher :</i> Penerbit A &amp; B
        <p>Show Abstract</p>
        <div class="abstract-article"><h4>Abstract</h4>
        <xmp class="abstract-article"><p>Risk rose when p<0.05 & n>30;
        see <b>Table 1</b>.</p></xmp></div></div>
      <div><a href="/documents/detail/2">Second</a></div>
    </div></body></html>"""
    a = parse_search_page(html).articles[0]
    assert a.title == "Effect of A & B on Aedes aegypti"
    assert a.journal == "Jurnal R&D"
    assert a.publisher == "Penerbit A & B"
    assert a.abstract == "Risk rose when p<0.05 & n>30; see Table 1 ."


@pytest.mark.parametrize(
    "line, expected",
    [
        ("Jurnal Penelitian Kesehatan SUARA FORIKES Vol 16, No 4 (2025): Oktober-Desember 2025",
         ("Jurnal Penelitian Kesehatan SUARA FORIKES", "16", "4", 2025, "Oktober-Desember 2025")),
        ("Unram Law Review Vol 1 No 2 (2017): Unram Law Review (ULREV)",
         ("Unram Law Review", "1", "2", 2017, "Unram Law Review (ULREV)")),
        ("Jurnal Kebijakan Kesehatan Indonesia Vol 1, No 2 (2012)",
         ("Jurnal Kebijakan Kesehatan Indonesia", "1", "2", 2012, None)),
        ("Jurnal Hukum Bisnis Bonum Commune Volume 4, Nomor 2 Agustus 2021",
         ("Jurnal Hukum Bisnis Bonum Commune", "4", "2", 2021, "Agustus 2021")),
        ("Jurnal Fatwa Hukum Vol. 6 No. 4 (2023): E-Jurnal Fatwa Hukum",
         ("Jurnal Fatwa Hukum", "6", "4", 2023, "E-Jurnal Fatwa Hukum")),
        ("Journal of Indonesian Health Policy and Administration Vol. 2, No. 1",
         ("Journal of Indonesian Health Policy and Administration", "2", "1", None, None)),
        ("Jurnal Komunikasi Hukum (JKH) Vol 6, No 1 (2020): Februari",
         ("Jurnal Komunikasi Hukum (JKH)", "6", "1", 2020, "Februari")),
        ("Prosiding Seminar Nasional (2019)",
         ("Prosiding Seminar Nasional", None, None, 2019, None)),
        ("International Journal of Health (IJHESS) (Special Issue) - January",
         ("International Journal of Health (IJHESS) (Special Issue) - January", None, None, None, None)),
        ("", (None, None, None, None, None)),
    ],
)
def test_parse_source_line(line, expected):
    assert parse_source_line(line) == expected


@pytest.mark.parametrize(
    "raw, cleaned",
    [
        ("Adji, Iwan Setiawan", "Adji, Iwan Setiawan"),
        ("Minollah -", "Minollah"),
        ("Florenly, Florenly -", "Florenly, Florenly"),
        ("Florenly - Florenly", "Florenly Florenly"),
        ('", Hasanuddin', "Hasanuddin"),
        ("NIM. A1011161020, SIGIT PURWADI", "SIGIT PURWADI"),
        ("R. Kintoko Rochadi", "R. Kintoko Rochadi"),
        ("  Rio   Dewandika Putra ", "Rio Dewandika Putra"),
        ("-", ""),
    ],
)
def test_clean_author(raw, cleaned):
    assert clean_author(raw) == cleaned


def test_extract_keywords():
    assert extract_keywords("Text. Keywords : Communication, Attitude, No Smoking Area") == [
        "Communication", "Attitude", "No Smoking Area"]
    bilingual = "English text.Keywords: a b; c ABSTRAK Teks Indonesia.Kata kunci: d; e."
    assert extract_keywords(bilingual) == ["a b", "c", "d", "e"]
    assert extract_keywords("No keyword list here.") == []
    assert extract_keywords(None) == []
    # the label followed by ordinary prose is not a keyword list
    assert extract_keywords("Keywords: " + "this is a very long sentence " * 20) == []
