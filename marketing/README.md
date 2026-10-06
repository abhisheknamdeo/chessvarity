# Flyer

`flyer.pdf` is ready to print: one landscape A4 sheet with two identical A5 flyers side by side. Print at
**100% / actual size** (not "fit to page"), in colour, then cut along the dashed line. Every edge has a 10 mm margin,
so ordinary home and office printers can print it.

The QR code (`qr.svg`) opens https://chessvarsity.com. It was checked with a QR reader.

To change the wording, edit `FEATURES` or the text in `make_flyer.py` and run it with a Python that has Playwright
(`python marketing/make_flyer.py`). It rewrites `flyer.html`, `flyer.pdf` and a preview, `flyer.png`. You can also open
`flyer.html` in Chrome and print it (landscape, margins "None", background graphics on).
