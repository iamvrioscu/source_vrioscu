# Self-hosted fonts

The site is designed for two SIL Open Font License families, self-hosted so no
third-party font service sees visitors' IP addresses (and the CSP stays `font-src 'self'`).

| File expected here               | Family          | Source                                        |
|----------------------------------|-----------------|-----------------------------------------------|
| `Archivo-Variable.woff2`         | Archivo (wght + wdth axes) | https://github.com/Omnibus-Type/Archivo |
| `JetBrainsMono-Variable.woff2`   | JetBrains Mono  | https://github.com/JetBrains/JetBrainsMono   |

Convert the variable TTFs to WOFF2 (e.g. `pip install fonttools brotli` then
`fonttools ttLib.woff2 compress Archivo[wdth,wght].ttf`) and save with the names above.

Until the files are present the site falls back to Segoe UI on Windows and
the system UI font elsewhere. Everything remains functional.
