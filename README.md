# Асинхронное сжатие файлов Bzip2

Публичный репозиторий: https://github.com/mi14112007-hash/python-backend-pz2

Практическая работа №2, вариант 5. Тема курсовой работы:
«Веб-приложение с HTTP API для асинхронного сжатия файлов по алгоритму
Барроуза — Уилера (Bzip2)».

Программа сжимает файлы в формат `.bz2`. Используется стандартный модуль
Python `bz2`: он реализует Bzip2, включающий преобразование Барроуза — Уилера.
Одно преобразование BWT ещё не является полным алгоритмом сжатия Bzip2.
Архивы можно распаковать через `bz2.decompress` или утилиту `bzip2 -dc`.

## Структура проекта

| Файл | Назначение |
| --- | --- |
| `src/compress.py` | CLI: входной файл → Bzip2 в стандартный вывод |
| `src/app.py` | Восемь обработчиков Flask и проверка заголовков |
| `src/jobs.py` | Очередь, запуск CLI через subprocess, состояния задач |
| `src/memory.py` | Модель хранения в оперативной памяти, этап 2 |
| `src/database.py` | Слой SQLite с SQL-запросами, этап 3 |
| `src/schema.py` | Поля и проверка типов записей |
| `src/xmlio.py` | Чтение XML, сериализация, разбор ответов |
| `src/client.py` | Класс ApiClient с методами таблица_действие |
| `src/server.py` | Настройки и запуск сервера |
| `src/demo.py` | Пример работы со всеми маршрутами через HTTP-клиент |
| `src/examples.py` | Четыре запуска CLI с проверкой распаковки |
| `tests/test_api.py` | Независимая модель и RuleBasedStateMachine |
| `tests/test_compression.py` | Проверка CLI, фоновых задач и сохранения SQLite |

## Установка и запуск

Нужен Python 3.10 или новее. Команды выполняются из корня этого проекта.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m src.server
```

На Windows окружение активируется командой `.venv\Scripts\activate`.
Альтернативный запуск: `sh run.sh` или `run.bat`.
Сервер по умолчанию слушает `127.0.0.1:5005`, база — `data.sqlite`.

| Параметр | Значение и назначение |
| --- | --- |
| `--backend memory` | Этап 2: данные живут до завершения процесса |
| `--backend sqlite` | Этап 3: постоянное хранение; режим по умолчанию |
| `--database PATH` | Путь к базе SQLite; родительская папка должна существовать |
| `--port N` | Порт сервера; по умолчанию 5005 |
| `--fake` | Тестовый режим без subprocess и реального сжатия |

```sh
python -m src.server --backend memory --fake
python -m src.server --backend sqlite --database data.sqlite
```

В `--fake` задача завершится состоянием `done`, но `output` будет пустым:
это заглушка, а не Bzip2-архив. Демонстрацию распаковки запускают без `--fake`.

## Этап 1. Утилита командной строки

Утилита принимает путь входного файла и записывает бинарный Bzip2-поток
в stdout. Диагностика идёт в stderr. Файл читается блоками по 64 КиБ;
при ошибке чтения процесс завершается с ненулевым кодом.

```sh
python -m src.compress examples/text.txt > text.txt.bz2
bzip2 -dc text.txt.bz2
python -m src.examples
```

Четыре примера проверены запуском CLI и обратной распаковкой:

| Входной файл | До, байт | После, байт |
| --- | ---: | ---: |
| `examples/bytes.csv` | 914 | 314 |
| `examples/data.json` | 39 | 77 |
| `examples/empty.txt` | 0 | 14 |
| `examples/text.txt` | 1620 | 116 |

Небольшой или пустой файл после сжатия может стать больше из-за служебных
данных формата. `src.examples` сохраняет архивы в исключённую из Git папку
`results/` и проверяет точное совпадение распакованных байтов.

## Схема и правила данных

| Таблица | Поля |
| --- | --- |
| Person | identifier: int, time: int, locale: str, user_agent: str |
| Query | identifier: int, time: int, content: str, person: int |
| Result | identifier: int, time: int, output: str, state: str, failure: str, query: int, duration: int |

`identifier` назначает сервер, изменять его нельзя. `Query.person` ссылается
на Person, `Result.query` — на Query. При создании `time` можно опустить:
сервер подставит целое Unix-время в секундах. `duration` — длительность
вычисления в миллисекундах. При изменении нужны идентификатор и хотя бы одно
изменяемое поле. Поиск сопоставляет все переданные поля по точному равенству.
Без фильтров возвращаются все записи в пределах выбранного родителя.

`content` содержит Base64 исходного файла. `output` содержит Base64
Bzip2-архива. Это позволяет передавать произвольные байты в XML, включая
нулевые и недопустимые для XML символы. Это кодирование, не шифрование.

## Этап 2. HTTP API

Для всех запросов обязательны заголовки именно с такими значениями:

```text
Accept: text/xml
Accept-Language: ru-RU
```

Проверка идёт в этом порядке. При отсутствии или неверном значении
возвращается 406 и XML с именем первого неподходящего заголовка.
При корректных заголовках обработчики возвращают 200 и XML, в том числе
при ошибке данных: `<error><message>...</message></error>`.
Для тела XML клиент дополнительно задаёт `Content-Type: text/xml`.

| Метод | Маршрут | Параметры | Метод клиента |
| --- | --- | --- | --- |
| POST | `/api/register/person` | XML: locale, user_agent, time? | person_register |
| GET | `/api/browse/person` | Строка запроса: поля Person | person_browse |
| POST | `/api/adjust/person` | XML: identifier, изменяемые поля | person_adjust |
| POST | `/api/register/query` | XML: person, content, time? | query_register |
| GET | `/api/browse/query/:person` | Путь, строка запроса | query_browse |
| POST | `/api/adjust/query` | XML: identifier, изменяемые поля | query_adjust |
| GET | `/api/browse/result/:query` | Путь, строка запроса | result_browse |
| GET | `/api/browse/report` | Нет | report_browse |

При поиске Query и Result родитель из пути имеет приоритет над одноимённым
параметром строки запроса. Удаление записей и изменение Result через HTTP
не предусмотрены таблицей варианта, поэтому таких маршрутов нет.

### Асинхронное выполнение

Регистрация Query сохраняет запрос и Result со статусом `queued`, затем
возвращает Query. Фоновый поток меняет состояние на `running` и запускает
`src/compress.py` через `subprocess.run` с временным входным файлом.
Полученный stdout сохраняется в Result, состояние становится `done`.
При ошибке — `failed` с пояснением в `failure`.

HTTP-запрос не ждёт окончания сжатия. Результат получают повторным вызовом
`result_browse`. В очереди один исполнитель; для CLI установлен тайм-аут
30 секунд. Размер HTTP-тела ограничен 8 МиБ, включая Base64 и XML.
Изменение Query не перезапускает задачу: исполнитель получает снимок
исходного запроса. Для нового сжатия создают новую Query.

Очередь предназначена для одного процесса сервера. SQLite сохраняет записи
и результаты, но после аварийного перезапуска незавершённые задачи
автоматически не возобновляются. При штатном завершении очередь дожидается
уже поставленных задач и закрывает базу.

### Формат XML и примеры

```sh
curl -X POST http://127.0.0.1:5005/api/register/person \
  -H 'Accept: text/xml' -H 'Accept-Language: ru-RU' \
  -H 'Content-Type: text/xml' \
  -d '<person><locale>ru-RU</locale><user_agent>curl</user_agent></person>'

curl -X POST http://127.0.0.1:5005/api/register/query \
  -H 'Accept: text/xml' -H 'Accept-Language: ru-RU' \
  -H 'Content-Type: text/xml' \
  -d '<query><person>1</person><content>aGVsbG8=</content></query>'

curl http://127.0.0.1:5005/api/browse/result/1 \
  -H 'Accept: text/xml' -H 'Accept-Language: ru-RU'
```

`aGVsbG8=` кодирует байты `hello`. Идентификаторы в примере рассчитаны на
пустую базу; при повторении следует подставить ID из ответа сервера.
Одиночная запись имеет корень `<person>` или `<query>`, список —
`<people>`, `<queries>`, `<results>` с элементами `<item>`. Пустой список
передаётся пустым корневым элементом. Специальные символы экранируются.

Для проверки всех восьми маршрутов через настоящий HTTP-клиент запусти
в другом терминале при работающем сервере:

```sh
python -m src.demo
```

Клиент умеет также отправить произвольный локальный файл:

```python
from src.client import ApiClient

api = ApiClient()
person = api.person_register(locale="ru-RU", user_agent="Python")
query = api.submit_file(person["identifier"], "examples/text.txt")
print(api.result_browse(query["identifier"]))
```

`submit_file` кодирует файл и вызывает `query_register`. Метод `call`
сериализует запрос; транспорт `network` выполняет его через urllib.
При HTTP-ошибке или `<error>` клиент поднимает `ValueError`.

### Отчёт по формуле (5)

Отбираются Query с `time > now - 540`. Нижняя граница не включается.
Правое соединение Person с отобранными Query сохраняет каждый такой
запрос. Затем выбираются `locale` и `content`, одинаковые пары удаляются,
как при проекции в реляционной алгебре. Порядок — locale, затем content.

## Этап 3. SQLite

`SQLiteStore` заменяет `MemoryStore` без изменения обработчиков.
Общий интерфейс: `add`, `browse`, `adjust`, `report`, `close`.
`validate` проверяет набор полей и их типы. Для SQL используются строки
запросов и связанные параметры `?`; имена полей проверяются по схеме.
Внешние ключи включены через `PRAGMA foreign_keys = ON`.

Отчёт выполняется одним SQL-запросом:

```sql
SELECT DISTINCT p.locale, q.content
FROM "query" AS q
LEFT JOIN person AS p ON p.identifier = q.person
WHERE q.time > ?
ORDER BY p.locale, q.content;
```

Это эквивалент заданного правого соединения с переставленными таблицами.
Блокировка защищает соединение от одновременных операций HTTP и фонового
исполнителя; вставки и изменения выполняются в транзакциях.

## Проверка

```sh
python -m coverage run -m pytest -q
python -m coverage report -m
python -m coverage html
python -m ruff check src tests
python -m ruff format --check src tests
```

Все тестовые случаи генерирует Hypothesis. Две `RuleBasedStateMachine`
используют один API-клиент и отдельную эталонную модель на словарях.
Проверяются создание, поиск и изменение, внешние ключи, XML, заголовки,
граница девяти минут и соответствие отчёта ожидаемым парам.
Flask test client заменяет только сетевой транспорт: маршрутизация,
заголовки, XML и обработчики выполняются реально.

Дополнительные генеративные тесты запускают настоящий subprocess,
проверяют восстановление файлов и сохранение результатов после повторного
открытия SQLite. Отдельный тест удерживает исполнитель до чтения
`running`, доказывая, что HTTP-ответ возвращается до окончания работы.

Раздельное измерение MBT для двух этапов:

```sh
python -m coverage run --data-file=.coverage-memory -m pytest -q tests/test_api.py::TestMemory
python -m coverage report --data-file=.coverage-memory -m --include='src/app.py,src/memory.py'
python -m coverage run --data-file=.coverage-sqlite -m pytest -q tests/test_api.py::TestSQLite
python -m coverage report --data-file=.coverage-sqlite -m --include='src/app.py,src/database.py'
```

Фактические результаты проверки приведены в `docs/verification.md`.
Покрытие всех обработчиков не следует путать с покрытием всех модулей:
запуск сервера и сетевой транспорт учитываются в общем отчёте отдельно.

## Источники

- Сборник практических работ №2, ИКБО-70-24, РТУ МИРЭА, 2026,
  страницы 4–5 и 20–22: требования к оформлению и вариант 5.
- https://docs.python.org/3/library/bz2.html
- https://flask.palletsprojects.com/en/stable/testing/
- https://github.com/vosilan/python-backend-pz2 — ориентир по организации
  проекта. Там вариант 19 и LZMA2; реализация этого проекта самостоятельная.
