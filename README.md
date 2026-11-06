# Асинхронное сжатие файлов Bzip2

Практическое задание №2, вариант 5. Тема курсовой работы:
«Веб-приложение с HTTP API для асинхронного сжатия файлов по алгоритму
Барроуза — Уилера (Bzip2)».

Репозиторий: https://github.com/mi14112007-hash/python-backend-pz2

Работа состоит из трёх этапов: CLI для сжатия файла, HTTP API на Flask
с хранением в памяти, затем постоянное хранение в SQLite через SQL-запросы.
Bzip2 реализован стандартным модулем `bz2`. Он включает преобразование
Барроуза — Уилера; само по себе преобразование BWT не является полным Bzip2.

## Структура

```text
examples/           четыре входных файла для CLI
src/compress.py     утилита Bzip2 и проверка четырёх примеров
src/app.py          восемь XML-обработчиков, очередь и запуск сервера
src/db.py           схема, MemoryStore и SQLiteStore
src/xmlio.py        сериализация и разбор XML
src/client.py       HTTP-клиент ApiClient
src/demo.py         демонстрация всех обработчиков через клиента
src/__init__.py     пакет Python
tests/test_api.py  MBT и генеративные проверки CLI и асинхронности
Makefile            установка, запуск, примеры, тесты и стиль
requirements.txt    зависимости
setup.cfg           настройки pytest и покрытия ветвей
.gitignore          исключение окружения и результатов запуска
```

## Установка и запуск

Нужен Python 3.10 или новее. Все команды выполняются в корне проекта.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m src.app
```

В подготовленной папке на этом Mac окружение `.venv` уже установлено:
достаточно выполнить `source .venv/bin/activate`.
В Windows активация: `.venv\Scripts\activate`.
Альтернативные команды: `make install`, `make server`.

По умолчанию сервер слушает `127.0.0.1:5005` и хранит записи в `data.sqlite`.

| Параметр | Назначение |
| --- | --- |
| `--backend memory` | Этап 2: хранение в памяти |
| `--backend sqlite` | Этап 3: SQLite, режим по умолчанию |
| `--database PATH` | Файл SQLite, родительская папка должна существовать |
| `--port N` | Порт, по умолчанию 5005 |
| `--fake` | Выполнение задач без subprocess и сжатия |

```sh
python -m src.app --backend memory --fake
python -m src.app --backend sqlite --database data.sqlite
```

При `--fake` результат имеет состояние `done` и пустой `output`.
Для демонстрации распаковки нужен обычный режим без `--fake`.
Через Makefile параметры передаются как `make server ARGS='--backend memory'`.

## Этап 1. CLI

Утилита принимает путь входного файла и пишет бинарный архив в stdout.
Диагностика идёт в stderr; ошибка чтения даёт ненулевой код завершения.
Файл читается блоками по 64 КиБ.

```sh
python -m src.compress examples/text.txt > /tmp/text.txt.bz2
bzip2 -dc /tmp/text.txt.bz2
make examples
```

`make examples` запускает CLI на четырёх файлах, сохраняет архивы в
`results/` и проверяет точное совпадение распакованных байтов с исходными.
Без Makefile: `python -c 'from src.compress import examples; examples()'`.

| Файл | До, байт | После, байт |
| --- | ---: | ---: |
| bytes.csv | 914 | 314 |
| data.json | 39 | 77 |
| empty.txt | 0 | 14 |
| text.txt | 1620 | 116 |

Небольшие файлы могут увеличиваться из-за служебных данных формата.

## Этап 2. HTTP API

| Таблица | Поля |
| --- | --- |
| Person | identifier: int, time: int, locale: str, user_agent: str |
| Query | identifier: int, time: int, content: str, person: int |
| Result | identifier: int, time: int, output: str, state: str, failure: str, query: int, duration: int |

Сервер назначает `identifier`; изменять его нельзя. `Query.person`
ссылается на Person, `Result.query` на Query. При создании можно опустить
`time`: сервер подставит целое Unix-время в секундах. `duration` задаётся
в миллисекундах. При изменении передают identifier и изменяемые поля.
Поиск сопоставляет все переданные поля по точному равенству; пустой фильтр
возвращает все записи выбранного родителя.

`content` содержит Base64 исходных байтов, `output` — Base64 Bzip2-архива.
Это позволяет передавать произвольные файлы через XML.

Для всех запросов обязательны `Accept: text/xml` и
`Accept-Language: ru-RU`, проверяемые именно в этом порядке. Отсутствие или
неверное значение даёт HTTP 406. При корректных заголовках обработчики
возвращают HTTP 200 и XML, включая ошибки данных
`<error><message>...</message></error>`.
Для XML-тела клиент также устанавливает `Content-Type: text/xml`.

| Метод | Маршрут | Параметры | Метод клиента |
| --- | --- | --- | --- |
| POST | `/api/register/person` | XML | person_register |
| GET | `/api/browse/person` | Строка запроса | person_browse |
| POST | `/api/adjust/person` | XML | person_adjust |
| POST | `/api/register/query` | XML | query_register |
| GET | `/api/browse/query/:person` | Путь, строка запроса | query_browse |
| POST | `/api/adjust/query` | XML | query_adjust |
| GET | `/api/browse/result/:query` | Путь, строка запроса | result_browse |
| GET | `/api/browse/report` | Нет | report_browse |

Родитель из пути имеет приоритет над одноимённым фильтром.
Одиночные записи имеют корень `<person>` или `<query>`, списки —
`<people>`, `<queries>`, `<results>` и `<report>` с элементами `<item>`.
Специальные символы экранируются.

Регистрация Query сохраняет Result со статусом `queued` и возвращает
Query, не дожидаясь окончания сжатия. Один фоновый исполнитель меняет
состояние на `running`, запускает CLI через `subprocess.run`, затем
сохраняет `done` и архив или `failed` и текст ошибки в `failure`.
Клиент опрашивает `result_browse`. Тайм-аут CLI — 30 секунд,
максимальный размер HTTP-тела — 8 МиБ, включая Base64 и XML.
Изменение Query не запускает сжатие заново: задача использует снимок
запроса при регистрации. Для нового сжатия создают новую Query.
Очередь работает в одном процессе; после аварийного перезапуска
незавершённые задачи автоматически не возобновляются.

Класс `ApiClient` использует urllib. Метод `call` сериализует запрос,
методы таблица_действие соответствуют таблице маршрутов, `submit_file`
читает локальный файл и кодирует его в Base64. При HTTP-ошибке или
XML-ошибке клиент поднимает `ValueError`.

```sh
curl -X POST http://127.0.0.1:5005/api/register/person \
  -H 'Accept: text/xml' -H 'Accept-Language: ru-RU' \
  -H 'Content-Type: text/xml' \
  -d '<person><locale>ru-RU</locale><user_agent>curl</user_agent></person>'
```

## Этап 3. SQLite

В `src/db.py` классы MemoryStore и SQLiteStore имеют общий интерфейс:
`add`, `browse`, `adjust`, `report`, `close`. Функция `validate` проверяет
набор полей и точные типы. SQLiteStore использует строки SQL и связанные
параметры `?`, без ORM. Внешние ключи включены через
`PRAGMA foreign_keys = ON`, изменения выполняются в транзакциях.
Блокировка защищает операции HTTP и фонового исполнителя.

Отчёт по формуле (5) возвращает уникальные пары locale/content для Query
с `time > now - 540`; точная нижняя граница исключается. Правое соединение
Person с отобранными Query записано как равносильное левое соединение:

```sql
SELECT DISTINCT p.locale, q.content
FROM "query" AS q
LEFT JOIN person AS p ON p.identifier = q.person
WHERE q.time > ?
ORDER BY p.locale, q.content;
```

## Демонстрация на защите

Открыть папку проекта в VS Code и два терминала.

Первый терминал:

```sh
source .venv/bin/activate
python -m src.app
```

Второй терминал:

```sh
source .venv/bin/activate
python -m src.demo
make examples
make test
make lint
```

Демонстрация вызывает все восемь маршрутов, создаёт Person, показывает
поиск и изменение, отправляет файл, опрашивает Result и проверяет
распаковку. Архив сохраняется в `results/demo.bz2`.
Отчёт coverage находится в `htmlcov/index.html`; его можно открыть
в браузере. Остановка сервера — Control+C в первом терминале.
Графический интерфейс не предусмотрен: демонстрируется HTTP API.

## Тестирование и результаты

Все пять тестов генерируют случаи через Hypothesis. Две
RuleBasedStateMachine вызывают API через ApiClient и сравнивают ответы
с независимой моделью на словарях. Проверяются оба хранилища, создание,
поиск, изменение, внешние ключи, XML, заголовки и граница девяти минут.
Flask test client заменяет только сетевой транспорт.
Дополнительные генеративные проверки запускают реальный CLI, проверяют
распаковку, сохранение SQLite и возврат HTTP-ответа до завершения сжатия.

```sh
python -m coverage run -m pytest -q
python -m coverage report -m
python -m coverage html
```

Раздельное измерение MBT для каждого этапа:

```sh
python -m coverage run --data-file=.coverage-memory -m pytest -q tests/test_api.py::TestMemory
python -m coverage report --data-file=.coverage-memory -m
python -m coverage run --data-file=.coverage-sqlite -m pytest -q tests/test_api.py::TestSQLite
python -m coverage report --data-file=.coverage-sqlite -m
```

Проверено 6 ноября 2026 года: Python 3.14.4, Flask 3.1.3.
После объединения модулей: `5 passed`; Ruff и форматирование прошли.

```text
Name              Stmts   Miss Branch BrPart  Cover   Missing
-------------------------------------------------------------
src/__init__.py       0      0      0      0   100%
src/app.py          133     11     14      1    92%   211-222, 226
src/client.py        49      8      6      0    85%   16-21, 90-91
src/compress.py      31     16      6      1    49%   23-29, 34-45, 49
src/db.py           101      3     28      3    95%   32, 78, 165
src/xmlio.py         38      1     22      1    97%   18
-------------------------------------------------------------
TOTAL               352     39     76      6    89%
```

В отдельных MBT-прогонах памяти и SQLite все восемь обработчиков
имеют 100% покрытия строк и ветвей. Проверены диапазоны функций
`person_register`, `person_browse`, `person_adjust`, `query_register`,
`query_browse`, `query_adjust`, `result_browse`, `report_browse`
в JSON-отчётах coverage: отсутствующих строк и ветвей в них нет.
Общее покрытие `app.py` включает также очередь и запуск сервера,
а `compress.py` — CLI и демонстрацию четырёх файлов. Поэтому процент
всего модуля отличается от покрытия HTTP-обработчиков.
CLI в дочернем процессе не добавляет покрытие к родительскому процессу.

## Источники

- Сборник задания №2, ИКБО-70-24: страницы 4–5 и 20–22, вариант 5.
- https://docs.python.org/3/library/bz2.html
- https://flask.palletsprojects.com/en/stable/testing/
- https://github.com/vosilan/python-backend-pz2 — ориентир по структуре.
  У примера вариант 19 и LZMA2; здесь вариант 5, Bzip2 и собственный код.

Текущее оформление проверено по перечню нарушений: Makefile выполняет
требование скрипта запуска; в Git нет архивов, бинарных файлов, окружения
и результатов запуска. Максимумы для Python-кода: 320 строк в файле,
33 строки в функции, 5 аргументов, 79 символов в строке. Комментариев
вне docstring и числовых констант в операндах сравнений нет.
Проверки Ruff включают PEP8, именование и сложность не выше 10.
