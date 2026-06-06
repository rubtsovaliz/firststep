Отвечаю по решениям для phase 2 / phase 1.5.

1) STORAGE: выбираем один файл на event/день/город, а не один файл на каждый bucket.

Причина:
- это ближе к старому рабочему паттерну из matule95;
- один weather event = один объект наблюдения;
- внутри одного файла должны лежать все outcomes/buckets этого события;
- так проще хранить forecast snapshots, market snapshots, all_outcomes и потом считать аналитику/консенсус/сдвиг top bucket во времени;
- per-bucket files слишком раздробят данные и усложнят phase 2.

Принять как основной ключ файла:
{city_slug}_{date}.json

Например:
seoul_2026-06-05.json
ankara_2026-06-04.json

Если есть риск коллизии, можно добавить fallback key:
{city_slug}_{date}_{event_id}.json
Но базовый формат хочу оставить человекочитаемым.

2) DISCOVERY: делаем оба канала.
Нужен:
- полный scan /events с pagination, active=true, closed=false;
- параллельно weather-focused shortcut через tag_slug=weather (если доступен / стабилен).

Логика:
- tag/weather канал использовать как быстрый discovery path;
- полный scan использовать как fallback и контроль полноты;
- итоговый список дедуплицировать по event id / slug / market ids.

Почему так:
- не хочу зависеть только от tag heuristics;
- но и полный scan без shortcut может быть медленнее и шумнее;
- combined mode даст более надежный discovery.

3) parse_temp_range: включить сейчас, на этапе normalizer, не откладывать.

Это нужно уже в phase 1.5, потому что:
- без этого нельзя нормально построить canonical all_outcomes;
- нельзя определить bucket ordering;
- нельзя вычислять top bucket / neighbor buckets / dead zone later;
- это фундаментальная часть нормализации weather market, а не forecast-only фича.

Требование:
- parse_temp_range должен поддерживать как минимум:
  - “X or below”
  - “X or higher”
  - “between A-B”
  - одиночный bucket типа “be 27C”
- хранить normalized range как:
  {
    "bucket_low": ...,
    "bucket_high": ...
  }

4) PROJECT LOCATION:
оставляем weather-polymarket-bot/ внутри wb/ пока что.
Не переносим в корень wb/ сейчас.

Причина:
- так безопаснее на текущем этапе;
- меньше шанс сломать соседние проекты;
- после стабилизации структуры можно будет отдельно решить, нужен ли перенос.

5) Что хочу видеть в storage schema теперь

Один файл на event должен содержать:
- event metadata
- city/date/station/unit
- discovery metadata
- normalized all_outcomes
- forecast_snapshots (append-only)
- market_snapshots (append-only)
- optional raw payload references / hashes
- status fields

Важно:
- trading fields сейчас не нужны;
- не хранить position/pnl/order execution как часть основной схемы phase 2;
- если какие-то legacy поля уже есть, вынести их в optional legacy block или убрать.

6) Что прошу изменить сейчас

Пожалуйста, обнови реализацию так, чтобы:
- storage switched to one-file-per-event/day/city;
- all outcomes одного weather event сохранялись в одном JSON;
- discovery использовал combined mode: full scan + weather tag path;
- parse_temp_range был встроен в normalizer;
- per-market bucket files не были основной моделью хранения.

7) После изменений покажи мне:

A. финальную структуру JSON одного event-файла;
B. как выглядит canonical WeatherMarket / WeatherEvent model;
C. какие поля заполняются на discovery refresh;
D. какие endpoint’ы backend уже готовы;
E. какие команды мне локально выполнить для проверки:
   - health
   - refresh discovery
   - просмотр сохраненных JSON

Пока новый большой код не наращивай сверх этого.
Сначала приведи discovery/storage к этой схеме и покажи diff по архитектуре.