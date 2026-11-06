# Сжатие Bzip2: этап 1

CLI читает файл и выводит Bzip2 в stdout.

```sh
python -m src.compress examples/text.txt > text.bz2
python -m src.examples
python -m pytest tests/test_cli.py
```
