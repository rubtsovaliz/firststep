Нужно сделать явную и надежную нормализацию типа погодного рынка в нашем пайплайне парсинга/обработки JSON событий.

Цель:
убрать зависимость торговой логики от текста в tags / event_title / event_slug и всегда иметь нормализованные поля:

- market_type: "max_temperature" | "min_temperature" | null
- temperature_metric: "high" | "low" | null

Что нужно сделать:

1. Найди место в коде, где мы парсим/нормализуем weather market event из JSON.
2. Добавь или приведи к единому виду поля:
   - market_type
   - temperature_metric
3. Логика нормализации должна быть такой:
   - если событие про Highest temperature:
     - market_type = "max_temperature"
     - temperature_metric = "high"
   - если событие про Lowest temperature:
     - market_type = "min_temperature"
     - temperature_metric = "low"
   - если тип не удалось определить уверенно:
     - market_type = null
     - temperature_metric = null

4. Приоритет источников определения типа:
   1) уже существующее поле market_type, если оно валидное
   2) event_slug
   3) event_title
   4) tags
   5) при необходимости question / all_outcomes[*].question как fallback

5. Поддержи такие текстовые сигналы:
   - highest temperature -> max_temperature / high
   - lowest temperature -> min_temperature / low
   - highest-temperature-... -> max_temperature / high
   - lowest-temperature-... -> min_temperature / low

6. Сделай нормализацию устойчивой:
   - case-insensitive
   - trim/lowercase
   - не завязывайся на точное положение строки
   - не ломай существующие поля

7. Добавь helper-функцию, например:
   - normalizeMarketType(event) -> { market_type, temperature_metric }
или аналогичную по стилю проекта.

8. Если в JSON уже есть market_type:
   - "max_temperature" -> temperature_metric = "high"
   - "min_temperature" -> temperature_metric = "low"
   - любые другие значения не считать валидными без дополнительной проверки

9. Добавь тесты/проверки на кейсы:
   - Highest temperature in Beijing on June 5?
   - highest-temperature-in-beijing-on-june-5-2026
   - tags: ["Weather", "Highest temperature"]
   - Lowest temperature in Austin on June 5?
   - lowest-temperature-in-austin-on-june-5-2026
   - неизвестный weather event без явного указания highest/lowest

10. Обнови типы/схемы/интерфейсы, если проект на TypeScript/Pydantic/dataclass:
   - market_type: Literal["max_temperature", "min_temperature"] | None
   - temperature_metric: Literal["high", "low"] | None

11. В конце покажи:
   - какие файлы изменил
   - финальную функцию нормализации
   - пример результата нормализации на 2-3 реальных входах

Важно:
- не делай вывод типа рынка только по tags, если уже есть валидный market_type
- не хардкодь города
- не меняй остальную бизнес-логику без необходимости
- если где-то сейчас логика опирается на текст tags/event_title/event_slug, переведи ее на normalized fields