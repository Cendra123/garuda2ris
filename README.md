# GARUDA CRAWLER (garuda2ris)

**Mengambil hasil pencarian Garuda (Garba Rujukan Digital) dan menyimpannya
sebagai berkas `.ris` untuk Zotero, Mendeley, EndNote, Rayyan, dan Covidence.**

[Garuda](https://garuda.kemdiktisaintek.go.id) adalah indeks nasional publikasi
ilmiah Indonesia. Garuda hanya menyediakan ekspor RIS satu per satu, dari
halaman detail tiap artikel, sehingga sulit dipakai sebagai sumber dalam kajian
literatur sistematis. `garuda2ris` menelusuri seluruh halaman hasil sebuah
pencarian dan menuliskannya ke satu berkas, lengkap dengan abstrak tiap entri.

- Pustaka Python sekaligus perintah terminal
- Menerima kata kunci pencarian atau URL pencarian yang disalin dari peramban
- Menulis ulang kueri yang salah dibaca oleh kotak pencarian Garuda
  (`smoke-free` justru *mengecualikan* kata "free"; tanda kutip diabaikan)
- Memeriksa setiap halaman terhadap pencarian yang diminta, sehingga halaman
  usang tidak ikut tersimpan
- Menggabungkan entri yang tercantum dua kali di Garuda dan mengambil kata
  kunci dari abstrak
- Notebook siap pakai untuk menjalankan beberapa pencarian sekaligus,
  menggabungkan hasilnya, dan mencatat log pencarian ala PRISMA:
  [`examples/garuda_multi_query.ipynb`](examples/garuda_multi_query.ipynb)

Jika Anda memakainya dalam penelitian, mohon [disitasi](#sitasi).
Jika kode tidak berjalan, silakan
[hubungi Cendra Devayana Putra](#jika-kode-tidak-berjalan).

*English version: [README.en.md](README.en.md)*

## Instalasi

```bash
pip install git+https://github.com/Cendra123/garuda2ris.git
```

atau dari salinan repositori ini:

```bash
git clone https://github.com/Cendra123/garuda2ris.git
pip install ./garuda2ris
```

Membutuhkan Python 3.9 ke atas, `requests`, dan `beautifulsoup4` (terpasang
otomatis).

## Penggunaan lewat terminal

Tuliskan kata kunci dan kolom yang ingin dicari. Contohnya, semua artikel yang
tercantum di Garuda atas nama seorang penulis:

```bash
garuda2ris "Cendra Devayana Putra" --field author -o cendra.ris
garuda2ris "Bartolomeus Priya" --field author -o bartolomeus.ris
```

Program menampilkan kemajuan halaman demi halaman, lalu menutup dengan jumlah
entri yang ditulis beserta jumlah yang dilaporkan Garuda, sehingga Anda tahu
hasilnya lengkap. (Pada 4 Oktober 2026 Garuda mencantumkan 16 entri untuk
pencarian pertama.)

Tambahkan penyaring dan perapian sesuai kebutuhan:

```bash
garuda2ris "Cendra Devayana Putra" --field author --year-from 2025 --dedupe --keywords -o cendra_2025.ris
```

Atau tempelkan URL pencarian yang sudah Anda atur di peramban:

```bash
garuda2ris "https://garuda.kemdiktisaintek.go.id/documents?q=Cendra+Devayana+Putra&select=author" -o cendra.ris
```

| Opsi | Fungsi |
| --- | --- |
| `-o FILE` | Berkas keluaran (bawaan: `garuda.ris`) |
| `-f, --field` | Kolom pencarian: `title` (bawaan), `abstract`, `author`, atau `doi` |
| `--publisher NAME` | Kotak pencarian "Publisher" di Garuda |
| `--raw-query` | Kirim kata kunci persis seperti diketik (lihat "Cara Garuda membaca kueri") |
| `--year-from / --year-to` | Hanya simpan entri dalam rentang tahun ini |
| `--drop-unknown-year` | Saat menyaring tahun, buang juga entri yang tahunnya tidak ditampilkan |
| `--dedupe` | Gabungkan entri yang tercantum dua kali (DOI sama atau judul sama) |
| `--keywords` | Salin daftar `Keywords: …` / `Kata kunci: …` di akhir abstrak ke kolom `KW` |
| `--invert-names` | Tulis `Rio Dewandika Putra` sebagai `Putra, Rio Dewandika` |
| `--native` | Pakai ekspor RIS milik Garuda untuk tiap entri (lihat di bawah) |
| `--no-pdf-links` | Jangan sertakan tautan PDF (`L1`) |
| `--max-pages N`, `--max-records N` | Berhenti lebih awal |
| `--delay SEC` | Jeda antar-permintaan (bawaan: 1.0 detik) |
| `--encoding utf-8-sig` | Tambahkan BOM, untuk EndNote lama di Windows |

## Cara Garuda membaca kueri (penting)

Diukur pada situs Garuda, Oktober 2026:

| Yang Anda ketik | Yang dilakukan Garuda |
| --- | --- |
| `kawasan tanpa rokok puskesmas` | Semua kata harus ada, urutannya bebas. Tidak ada pencarian frasa. |
| `"kawasan tanpa rokok"` | Tanda kutip tidak berpengaruh: `"rokok tanpa kawasan" puskesmas` menghasilkan 22 judul yang sama. |
| `smoke-free hospital` | Tanda hubung **mengecualikan** kata sesudahnya: yang muncul adalah entri yang memuat "smoke" dan "hospital" tetapi **tidak** memuat "free". |
| `no smoking` / `non smoking` | Kata yang sangat pendek tampaknya diabaikan: keduanya memberi hasil yang sama. |

Aturan tanda hubung diperiksa lewat jumlah hasil pada kolom abstrak:
`smoke hospital` = 242, `smoke free hospital` = 34, dan
`"smoke-free" hospital` = 208 = 242 − 34.

Karena itu kata kunci yang diberikan ke alat ini ditulis ulang lebih dahulu:
tanda hubung di antara huruf diganti spasi dan tanda kutip ganda dibuang
(`"smoke-free" hospital` dikirim sebagai `smoke free hospital`). Tanda hubung
di awal kata (`rokok -elektrik`) dibiarkan, sehingga pengecualian yang
disengaja tetap berfungsi. Gunakan `--raw-query` (`normalize=False` di Python)
untuk mengirim kata kunci apa adanya. URL yang ditempel tidak pernah ditulis
ulang; Anda hanya mendapat peringatan.

## Penggunaan di Python

```python
from garuda2ris import crawl, crawl_to_ris, write_ris

# satu panggilan
crawl_to_ris("Cendra Devayana Putra", "cendra.ris", field="author")

# atau simpan entrinya dan olah lebih lanjut
articles = crawl("Cendra Devayana Putra", field="author", remove_duplicates=True, keywords=True)
articles += crawl("Bartolomeus Priya", field="author")

for a in articles[:3]:
    print(a.year, a.journal, "-", a.title)

recent = [a for a in articles if a.year and a.year >= 2025]
write_ris(recent, "cendra_bartolomeus_2025plus.ris")

import pandas as pd                      # opsional: tabel seluruh entri
pd.DataFrame(a.to_dict() for a in articles).to_excel("publications.xlsx", index=False)
```

Tingkat yang lebih rendah:

```python
from garuda2ris import GarudaClient

client = GarudaClient(delay=2.0)
for article in client.search("Bartolomeus Priya", field="author", max_pages=3):
    print(article.title, article.authors)

page = client.fetch_page({"q": "Cendra Devayana Putra", "select": "author"}, page=2)
print(page.total_records, page.total_pages)
```

Contoh lengkap ada di [`examples/author_search.py`](examples/author_search.py).

## Isi berkas RIS

| Tag RIS | Sumber di Garuda |
| --- | --- |
| `TY` | `JOUR`; `CONF` bila nama terbitan memuat conference / proceeding / prosiding / seminar |
| `TI` | Judul |
| `AU` | Satu baris per penulis, sisa pengisian yang tidak perlu dibuang (`Minollah -` → `Minollah`) |
| `T2`, `JF` | Nama jurnal |
| `VL`, `IS`, `PY` | Diurai dari baris "Vol 16, No 4 (2025): …" |
| `PB` | Penerbit |
| `DO` | DOI |
| `AB` | Abstrak |
| `KW` | Hanya dengan `--keywords` |
| `UR` | Tautan "Original Source" (halaman Garuda bila tidak ada) |
| `L1` | Tautan "Download Original" dan "Full PDF" milik Garuda |
| `L2` | Halaman entri tersebut di Garuda |
| `AN`, `ID`, `DB` | ID entri di Garuda, nama pangkalan data |

Kolom yang tidak ditampilkan Garuda tidak diisi; tidak ada yang ditebak.
Daftar hasil Garuda tidak memuat nomor halaman, ISSN, maupun tanggal terbit.

## Cara kerja

1. Meminta `/documents?page=N&q=…&select=…` untuk N = 1, 2, … (10 entri per
   halaman).
2. Membaca "Page X of Y | Total Record : N" untuk mengetahui kapan berhenti.
   Program juga berhenti bila sebuah halaman tidak membawa entri baru.
3. Untuk tiap entri, mencari tautan judul (`/documents/detail/<id>`), tautan
   penulis (`/author/view/<id>`), tautan `doi.org`, tautan aksi yang berlabel,
   baris "Publisher :" dan baris jurnal di atasnya, serta abstrak.
4. Menulis entri sebagai RIS (UTF-8, akhir baris CRLF).

Pengurai berpegang pada pola tautan dan label tersebut, bukan pada nama kelas
CSS, sehingga perubahan tampilan situs semestinya tidak merusaknya.

### Halaman usang

Alamat `/documents` di Garuda kadang menjawab dengan halaman sisa dari
pencarian lain atau nomor halaman lain. Karena itu setiap jawaban dicocokkan
dengan baris "Search *kueri*, by *kolom*" dan baris "Page X of Y" milik Garuda
sendiri. Jawaban yang salah diambil ulang dari alamat setara
`/documents/index/<token>`, yang kemudian dipakai sampai proses selesai. Bila
masih salah, pencarian dihentikan dengan `GarudaMismatch` alih-alih menyimpan
entri milik pencarian lain.

### `--native`

Halaman detail tiap entri memiliki tombol "RIS"
(`/citation/site/RIS/<id>`). Dengan `--native`, berkas disusun dari ekspor
resmi tersebut, ditambah abstrak dan DOI dari daftar hasil bila ekspornya
tidak memuatnya. Cara ini memerlukan satu permintaan tambahan per entri, dan
entri yang ekspornya gagal diambil akan memakai data dari daftar hasil.

## Batasan dan catatan

- **Penyaring tahun diterapkan setelah pengunduhan**, memakai tahun yang
  diurai dari tiap entri. Bila ingin memakai "Filter By Year" milik Garuda,
  atur di peramban lalu tempelkan URL-nya: semua parameter URL diteruskan apa
  adanya.
- **Duplikat sering muncul.** Garuda mengindeks ulang jurnal, sehingga artikel
  yang sama bisa tercantum dengan dua ID. Gunakan `--dedupe`, atau biarkan
  pengelola referensi Anda yang menanganinya.
- **Mutu metadata mengikuti data OJS jurnalnya.** Wajar bila menemukan
  `Tukiman, MKM` (gelar di kolom nama) atau DOI yang memuat spasi.
- **Urutan nama penulis** dipertahankan seperti di Garuda. `--invert-names`
  menganggap kata terakhir sebagai nama keluarga, yang keliru untuk banyak
  nama Indonesia.
- Jaga jeda `--delay` minimal 1 detik.
- Bila Garuda berganti domain lagi, gunakan `--base-url` (atau cukup tempelkan
  URL dari domain baru).
- Di balik proxy atau CA khusus, berikan sesi Anda sendiri:
  `GarudaClient(session=my_requests_session)`.

## Jika kode tidak berjalan

Jika `garuda2ris` tidak berjalan sebagaimana mestinya, silakan hubungi
**Cendra Devayana Putra**:

- buka *issue* di <https://github.com/Cendra123/garuda2ris/issues>, atau
- hubungi lewat profil GitHub [@Cendra123](https://github.com/Cendra123).

Agar masalah cepat ditemukan, mohon sertakan:

- perintah atau kueri yang dijalankan,
- pesan galat selengkapnya,
- keluaran `garuda2ris --version` dan versi Python Anda,
- tanggal pencarian dilakukan.

Sebelum melapor, beberapa hal ini layak dicoba:

| Gejala | Yang bisa dicoba |
| --- | --- |
| `GarudaMismatch` | Garuda mengirim halaman yang salah. Tunggu beberapa menit lalu jalankan lagi. |
| Galat koneksi atau `HTTP 5xx` | Periksa apakah situs Garuda bisa dibuka di peramban; situsnya kadang tidak dapat diakses. |
| Jumlah entri lebih sedikit daripada yang dilaporkan Garuda | Jalankan ulang; bila tetap terjadi, laporkan beserta kuerinya. |
| Hasil kosong padahal di peramban ada | Garuda mungkin mengubah tampilan atau alamatnya. Laporkan agar pengurai diperbarui. |

## Pengujian

```bash
pip install pytest rispy
pytest
```

Berkas HTML di `tests/fixtures/` adalah tiruan halaman hasil Garuda yang dibuat
tangan (dua tata letak yang sengaja dibuat berbeda) dan diisi entri nyata dari
daftar hasil; berkas tersebut bukan halaman yang direkam langsung.

## Sitasi

Jika perangkat lunak ini membantu pekerjaan Anda, misalnya untuk menyusun
kumpulan artikel dalam kajian literatur, mohon disitasi:

> Putra, C. D., & Priya, B. (2026). *garuda2ris: Crawl Garuda (Garba Rujukan
> Digital) search results into RIS* (Version 0.2.0) [Computer software].
> https://github.com/Cendra123/garuda2ris

```bibtex
@software{putra_priya_garuda2ris_2026,
  author  = {Putra, Cendra Devayana and Widada, Bartolomeus Priya Perkasa Utama },
  title   = {garuda2ris: Crawl Garuda (Garba Rujukan Digital) search results into RIS},
  year    = {2026},
  version = {0.2.0},
  url     = {https://github.com/Cendra123/garuda2ris}
}
```

GitHub juga menyediakan kedua format ini lewat tombol **Cite this repository**
di bilah samping (dibaca dari [`CITATION.cff`](CITATION.cff)).

Mohon sebutkan juga Garuda sebagai sumber data pada bagian metode, beserta
tanggal tiap pencarian dijalankan.

## Penggunaan yang bertanggung jawab

Garuda adalah layanan publik yang dikelola kementerian yang membidangi
pendidikan tinggi. Jaga jeda antar-permintaan minimal satu detik, jangan
menjalankan pencarian secara paralel, dan gunakan datanya untuk penelitian
serta pengelolaan referensi.

## Lisensi

MIT. Lihat [LICENSE](LICENSE).
