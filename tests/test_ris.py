import rispy

from conftest import FakeResponse, FakeSession, result_page
from garuda2ris import (
    Article,
    GarudaClient,
    article_to_ris,
    crawl_to_ris,
    parse_search_page,
    to_ris,
    write_ris,
)
from garuda2ris.cli import main
from garuda2ris.ris import merge_into_native, ris_author


def sample() -> Article:
    return Article(
        garuda_id="3911790",
        title="Obedience Dan Attitude of Hospital Employees on Non-Smoking Area Policy in Jombang",
        authors=["Nuswantara", "Wahyuni, Chatarina Umbul", "Daniel Christanto"],
        journal="Jurnal Kesehatan",
        volume="16",
        issue="2",
        year=2023,
        publisher="Universitas Muhammadiyah Surakarta",
        doi="10.23917/jk.v16i2.2098",
        abstract="Introduction: line one.\nMethod:   line two.",
        keywords=["non-smoking area", "obedience"],
        url="https://journals2.ums.ac.id/jk/article/view/2098/825",
        pdf_url="https://journals2.ums.ac.id/jk/article/download/2098/825",
        garuda_url="https://garuda.kemdiktisaintek.go.id/documents/detail/3911790",
    )


def test_record_layout():
    text = article_to_ris(sample())
    lines = text.split("\r\n")
    assert lines[0] == "TY  - JOUR"
    assert lines[-2] == "ER  - " and lines[-1] == ""
    assert "TI  - Obedience Dan Attitude of Hospital Employees on Non-Smoking Area Policy in Jombang" in lines
    assert [ln for ln in lines if ln.startswith("AU")] == [
        "AU  - Nuswantara", "AU  - Wahyuni, Chatarina Umbul", "AU  - Daniel Christanto"]
    for expected in (
        "PY  - 2023", "T2  - Jurnal Kesehatan", "JF  - Jurnal Kesehatan", "VL  - 16", "IS  - 2",
        "PB  - Universitas Muhammadiyah Surakarta", "DO  - 10.23917/jk.v16i2.2098",
        "AB  - Introduction: line one. Method: line two.",  # one line, whitespace collapsed
        "KW  - non-smoking area", "KW  - obedience",
        "UR  - https://journals2.ums.ac.id/jk/article/view/2098/825",
        "L1  - https://journals2.ums.ac.id/jk/article/download/2098/825",
        "L2  - https://garuda.kemdiktisaintek.go.id/documents/detail/3911790",
        "AN  - 3911790", "DB  - GARUDA",
    ):
        assert expected in lines
    # every line is a well-formed RIS tag line
    assert all(len(ln) >= 6 and ln[2:6] == "  - " for ln in lines if ln)


def test_missing_fields_are_left_out_not_blank():
    text = article_to_ris(Article("9", "Bare title", garuda_url="https://g/documents/detail/9"))
    tags = [ln[:2] for ln in text.split("\r\n") if ln]
    assert tags == ["TY", "ID", "TI", "UR", "AN", "DB", "DP", "ER"]
    assert "UR  - https://g/documents/detail/9" in text  # falls back to the Garuda page


def test_options():
    a = sample()
    assert "AU  - Christanto, Daniel" in article_to_ris(a, invert_names=True)
    assert ris_author("Nuswantara", invert=True) == "Nuswantara"  # single names stay
    assert ris_author("Wahyuni, Chatarina Umbul", invert=True) == "Wahyuni, Chatarina Umbul"
    assert "L1  - " not in article_to_ris(a, include_pdf_links=False)
    assert "\r" not in article_to_ris(a, line_ending="\n")
    conf = Article("1", "T", journal="International Interdisciplinary Conference on SDGs")
    text = article_to_ris(conf)
    assert text.startswith("TY  - CONF") and "JF  - " not in text


def test_output_is_readable_by_an_independent_ris_parser(classes_html, tmp_path):
    articles = parse_search_page(classes_html).articles
    path = write_ris(articles, tmp_path / "out.ris")
    raw = path.read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n")  # consistent CRLF
    assert not raw.startswith(b"\xef\xbb\xbf")
    with open(path, encoding="utf-8") as fh:
        entries = rispy.load(fh)
    assert len(entries) == 4
    first = entries[0]
    assert first["type_of_reference"] == "JOUR"
    assert first["authors"] == ["Adji, Iwan Setiawan", "Nabilah, Aisyah", "Alghozi, Muhammad Hilmi"]
    assert first["year"] == "2025" and first["volume"] == "16" and first["number"] == "4"
    assert first["doi"] == "10.33846/sf16430"
    assert first["secondary_title"] == "Jurnal Penelitian Kesehatan SUARA FORIKES"
    assert first["abstract"].startswith("Nasopharyngeal carcinoma")
    assert entries[2]["title"].startswith("HUBUNGAN LINGKUNGAN TERHADAP IMPLEMENTASI")


def test_bom_encoding(tmp_path):
    path = write_ris([sample()], tmp_path / "bom.ris", encoding="utf-8-sig")
    assert path.read_bytes().startswith(b"\xef\xbb\xbfTY  - JOUR")


def test_merge_into_native_adds_only_what_is_missing():
    native = "TY  - JOUR\nT1  - Native title\nAU  - Nuswantara\nUR  - http://native\nER  - \n"
    lines = merge_into_native(native, sample())
    assert lines[0] == "TY  - JOUR" and lines[-1] == "ER  - "
    assert "T1  - Native title" in lines
    assert "AB  - Introduction: line one. Method: line two." in lines
    assert "DO  - 10.23917/jk.v16i2.2098" in lines
    assert [ln for ln in lines if ln.startswith("UR")] == ["UR  - http://native"]
    assert sum(ln.startswith("ER") for ln in lines) == 1


def _site(native_ok=("1",)):
    def handler(url, params):
        if "/citation/site/RIS/" in url:
            gid = url.rsplit("/", 1)[1]
            if gid in native_ok:
                return FakeResponse(f"TY  - JOUR\nT1  - Native {gid}\nER  - \n")
            return FakeResponse(status_code=404)
        page = int(params["page"])
        return result_page({1: ["1", "2"], 2: ["3"]}[page], page, 2, 3)
    return handler


def test_crawl_to_ris_end_to_end(tmp_path):
    session = FakeSession(_site())
    client = GarudaClient(session=session, delay=0, sleep=lambda s: None)
    out = tmp_path / "result.ris"
    articles = crawl_to_ris("kawasan tanpa rokok", out, client=client, field="abstract")
    assert len(articles) == 3
    with open(out, encoding="utf-8") as fh:
        entries = rispy.load(fh)
    assert [e["title"] for e in entries] == ["Title number 1", "Title number 2", "Title number 3"]
    assert entries[0]["publisher"] == "Penerbit 1"
    assert entries[2]["urls"] == ["http://j.example/view/3"]


def test_native_mode_falls_back_per_record(tmp_path):
    session = FakeSession(_site(native_ok=("1",)))
    client = GarudaClient(session=session, delay=0, max_retries=0, sleep=lambda s: None)
    out = tmp_path / "native.ris"
    crawl_to_ris("x", out, client=client, native=True)
    with open(out, encoding="utf-8") as fh:
        entries = rispy.load(fh)
    # record 1 comes from Garuda's export (plus our abstract), 2 and 3 are built
    assert [e.get("primary_title") or e.get("title") for e in entries] == [
        "Native 1", "Title number 2", "Title number 3"]
    assert entries[0]["abstract"].startswith("Abstract text for record 1")


def test_cli(tmp_path, monkeypatch, capsys):
    session = FakeSession(_site())
    monkeypatch.setattr("garuda2ris.client.requests.Session", lambda: session)
    monkeypatch.setattr("garuda2ris.client.time.sleep", lambda s: None)
    out = tmp_path / "cli.ris"
    code = main(["kawasan tanpa rokok", "-f", "abstract", "-o", str(out), "--delay", "0", "-q"])
    assert code == 0
    assert out.read_text(encoding="utf-8").count("TY  - JOUR") == 3
    assert "wrote 3 records" in capsys.readouterr().err
    assert dict(session.calls[0][1])["select"] == "abstract"


def test_cli_failure_tells_the_user_whom_to_contact(tmp_path, monkeypatch, capsys):
    session = FakeSession(lambda url, params: FakeResponse(status_code=404))
    monkeypatch.setattr("garuda2ris.client.requests.Session", lambda: session)
    out = tmp_path / "none.ris"
    code = main(["x", "-o", str(out), "--delay", "0", "-q"])
    err = capsys.readouterr().err
    assert code == 1 and not out.exists()
    assert "HTTP 404" in err
    assert "Cendra Devayana Putra" in err and "github.com/Cendra123/garuda2ris/issues" in err
