# env-template-check

Check whether a local configuration has the variable names expected by a
template. Reports missing names, extra names, and duplicate assignments without
printing values. Python 3.10+, no runtime dependencies.

```sh
python -m env_template_check examples/template.txt examples/actual.txt --format json
```

Run from this checkout, or install with `python -m pip install .` to also get the
`env-template-check` command. The sample command exits **1**, reporting missing
`LOG_LEVEL` and extra `DEBUG`. All included examples are synthetic.

For your own files, provide both paths explicitly:

```sh
python -m env_template_check path/to/.env.example path/to/.env --format text
```

Exit codes: **0** means names match without duplicates; **1** means missing,
extra, or duplicate names; **2** means invalid syntax, invalid UTF-8, unreadable
input, or invalid command arguments. Default output is `text`; `json` is stable
and suitable for CI. Comparison results and file errors go to stdout. Argument
errors use argparse's stderr output. File errors identify `template` or `actual`
without printing the file path, source text, or values.

Example JSON:

```json
{
  "ok": false,
  "missing": ["LOG_LEVEL"],
  "extra": ["DEBUG"],
  "duplicates": {
    "template": {},
    "actual": {}
  }
}
```

Duplicate names appear as objects mapping a name to all its one-based line
numbers, for example `"API_URL": [2, 5]`. Names and duplicate groups are sorted.
An empty template and empty actual file conform.

## Deliberately restricted format

- UTF-8 text with LF or CRLF line endings; UTF-8 BOM is rejected.
- Blank lines and lines whose first non-space/tab character is `#` are ignored.
- Assignments contain an ASCII name (`[A-Za-z_][A-Za-z0-9_]*`), optional
  spaces/tabs, `=`, and an opaque value. Leading spaces/tabs are allowed.
- An optional `export` prefix must be followed by spaces/tabs.
- Values may be empty. Quotes, `#`, `=`, Unicode, `$NAME`, `${NAME}`, and shell
  expressions in values are treated as ordinary text. They are never evaluated.
- No interpolation, multiline value syntax, quote validation, type checking,
  or value comparison is performed. Continuation lines must independently
  satisfy the assignment grammar. This is not a general dotenv loader.

Only the two explicitly supplied files are read. The tool does not discover
configuration files, start a shell, execute values, or change `os.environ`.
It reads each file into memory; use it for ordinary configuration files.
The output reveals variable **names** and line numbers, so handle that output
according to your project's needs.

## Python API

```python
from env_template_check import compare, parse

expected = parse("APP_NAME=sample\nLOG_LEVEL=info\n")
actual = parse("APP_NAME=demo\n")
report = compare(expected, actual)
assert report.missing == ("LOG_LEVEL",)
assert not report.ok
print(report.as_dict())
```

`parse(text)` returns an immutable tuple of frozen `Assignment(name, line)`
records containing no values. Malformed lines raise `ParseError` with a `line`
attribute and a fixed message containing only its line number.
`compare(template, actual)` accepts iterables of these records and returns a
frozen `Report` with `missing`, `extra`, `template_duplicates`, and
`actual_duplicates` tuples. `report.ok` checks all four fields;
`report.as_dict()` creates a fresh JSON-ready object. These functions perform
no I/O and do not modify the environment.

Run the standard-library test suite:

```sh
python -m unittest discover -s tests -v
```

## Português

Compare os nomes de variáveis entre um modelo e sua configuração local sem
exibir os valores. Requer Python 3.10 ou superior, sem dependências de execução.

```sh
python -m env_template_check examples/template.txt examples/actual.txt --format text
```

Os exemplos são sintéticos. O comando acima retorna **1**: falta `LOG_LEVEL` e
sobra `DEBUG`. Use os caminhos dos seus próprios arquivos para conferir uma
configuração real. O programa só lê os dois arquivos informados.

Códigos de saída: **0**, nomes conformes e sem duplicação; **1**, nomes faltantes,
extras ou duplicados; **2**, erro de sintaxe, UTF-8, leitura ou argumentos.
Escolha `--format json` para automação. Duplicações incluem os números das linhas
nos dois arquivos; valores nunca aparecem no relatório.

O formato aceita comentários, linhas vazias, `NOME=valor` e o prefixo opcional
`export`. Nomes usam letras ASCII, dígitos e sublinhado, sem começar por dígito.
Valores são texto opaco: não há interpolação, execução de comandos, validação
de aspas ou valores multilinha. O programa não altera `os.environ`.

MIT License — Martin Lofrano de Oliveira.
